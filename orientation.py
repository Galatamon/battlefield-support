"""
Auto-orientation algorithm to optimize model placement for printing.

For BattleTech minis we replace random rotations with a small set of canonical
mech poses (upright with tilt-back variants, plus prone for aerospace) and add
a heavy penalty against any orientation that points the model's "front" face
toward the build plate.
"""

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from mesh_loader import MeshAnalyzer
from config import SupportConfig, PrinterConfig


AXIS_VECTORS = {
    '+X': np.array([1.0, 0.0, 0.0]),
    '-X': np.array([-1.0, 0.0, 0.0]),
    '+Y': np.array([0.0, 1.0, 0.0]),
    '-Y': np.array([0.0, -1.0, 0.0]),
}


def parse_front_axis(value):
    """Convert a string like '+Y' into a unit vector. Returns None for 'auto'."""
    if value is None or value == 'auto':
        return None
    if isinstance(value, np.ndarray):
        return value / np.linalg.norm(value)
    if value not in AXIS_VECTORS:
        raise ValueError(f"Invalid front axis '{value}'. Expected one of "
                         f"{list(AXIS_VECTORS.keys())} or 'auto'.")
    return AXIS_VECTORS[value].copy()


class OrientationOptimizer:
    """Optimize model orientation for minimal scarring and best print quality."""

    def __init__(self, mesh, config=None, front_axis='auto'):
        self.mesh = mesh
        self.config = config or {}
        self.analyzer = MeshAnalyzer(mesh)

        # Front axis is the world vector the mech's visible front points along
        # BEFORE any orientation transform. May be auto-detected lazily.
        if isinstance(front_axis, str):
            self.front_axis = parse_front_axis(front_axis)
            self.front_axis_source = 'override' if self.front_axis is not None else 'auto'
        else:
            self.front_axis = front_axis
            self.front_axis_source = 'override'

        if self.front_axis is None:
            self.front_axis, self.front_axis_label = self._auto_detect_front()
            self.front_axis_source = 'auto'
        else:
            # Find which canonical label matches this vector (if any).
            self.front_axis_label = None
            for label, vec in AXIS_VECTORS.items():
                if np.allclose(self.front_axis, vec):
                    self.front_axis_label = label
                    break

    def _auto_detect_front(self):
        """
        Guess which world-axis is the mech's "front" by looking at the mid-Z
        band of the mesh: bin the area of each near-horizontal face into the
        four cardinal directions (+X, -X, +Y, -Y) by its dominant horizontal
        normal component. The bin with the most area wins.

        Returns:
            (unit_vector, label_str)
        """
        bounds = self.mesh.bounds
        z_lo = bounds[0, 2] + 0.3 * (bounds[1, 2] - bounds[0, 2])
        z_hi = bounds[0, 2] + 0.7 * (bounds[1, 2] - bounds[0, 2])

        centers = self.mesh.triangles_center
        normals = self.mesh.face_normals
        areas = self.mesh.area_faces

        mid_band = (centers[:, 2] >= z_lo) & (centers[:, 2] <= z_hi)
        # Faces whose normals are within 60deg of horizontal (|n_z| < sin(30deg) = 0.5)
        near_horizontal = np.abs(normals[:, 2]) < 0.5
        candidate = mid_band & near_horizontal

        bins = {label: 0.0 for label in AXIS_VECTORS}
        if not np.any(candidate):
            print("  Front auto-detect: no usable mid-band faces; defaulting to +Y")
            return AXIS_VECTORS['+Y'].copy(), '+Y'

        for label, axis_vec in AXIS_VECTORS.items():
            # Project each candidate normal onto this axis; only count the
            # component aligned with the axis (clipped to non-negative).
            alignment = normals[candidate] @ axis_vec
            mask = alignment > 0.5  # at least 60deg-aligned
            bins[label] += float(np.sum(areas[candidate][mask] * alignment[mask]))

        ranked = sorted(bins.items(), key=lambda kv: kv[1], reverse=True)
        top_label, top_score = ranked[0]
        second_label, second_score = ranked[1]

        if top_score <= 0:
            print("  Front auto-detect: no clear winner; defaulting to +Y")
            return AXIS_VECTORS['+Y'].copy(), '+Y'

        if second_score > 0 and (top_score - second_score) / top_score < 0.1:
            print(f"  Front auto-detect: ambiguous (top {top_label}={top_score:.1f} "
                  f"vs {second_label}={second_score:.1f}). Defaulting to {top_label}; "
                  f"pass --front to override.")
        else:
            print(f"  Front auto-detected: {top_label} (score {top_score:.1f}, "
                  f"runner-up {second_label}={second_score:.1f})")

        return AXIS_VECTORS[top_label].copy(), top_label

    def optimize(self, num_samples=None):
        """
        Pick the best of a small set of canonical mech poses.

        Args:
            num_samples: ignored; kept for backward compatibility with the CLI.

        Returns:
            4x4 transformation matrix
        """
        print("Optimizing model orientation (canonical mech poses)...")
        print(f"  Front axis ({self.front_axis_source}): {self.front_axis_label or self.front_axis}")

        poses = list(self._generate_mech_poses())
        if not poses:
            return np.eye(4)

        best_score = float('inf')
        best_transform = np.eye(4)
        best_name = ''

        for name, rotation_matrix in poses:
            transform = np.eye(4)
            transform[:3, :3] = rotation_matrix
            test_mesh = self.mesh.copy()
            test_mesh.apply_transform(transform)

            score = self._score_orientation(test_mesh, rotation_matrix)
            print(f"  {name:<24} score = {score:.2f}")

            if score < best_score:
                best_score = score
                best_transform = transform
                best_name = name

        print(f"  Best orientation: {best_name} (score {best_score:.2f})")
        return best_transform

    def _generate_mech_poses(self):
        """
        Yield (name, 3x3 rotation matrix) pairs for physically sensible mech
        poses. Tilt-back rotates the model around the axis perpendicular to
        both world-Z and the front-axis, tipping the front upward by `angle`.

        We do NOT include random rotations: a mech should never end up on its
        side or upside down just because the scorer found a local minimum.
        """
        # Tilt axis: rotate around the world-horizontal axis that is
        # perpendicular to the front-axis (so front rotates around it).
        tilt_axis = np.cross(self.front_axis, np.array([0.0, 0.0, 1.0]))
        if np.linalg.norm(tilt_axis) < 1e-6:
            # front_axis is vertical (degenerate); fall back to X
            tilt_axis = np.array([1.0, 0.0, 0.0])
        tilt_axis = tilt_axis / np.linalg.norm(tilt_axis)

        # Upright variants: tilt the front upward by [-30, -15, 0, +15, +30] degrees.
        # Positive tilt = front rotates up (good — front-face points up-away from plate).
        # Negative tilt = front rotates down (allowed but penalized later).
        for angle_deg in (0, 15, 30, -15, -30):
            R = Rotation.from_rotvec(tilt_axis * np.radians(angle_deg)).as_matrix()
            yield (f"upright tilt {angle_deg:+d}°", R)

        # Prone poses for aerospace / artillery: lay the mech on its back or
        # belly. Back-down rotates 90° such that what was the original +Z
        # becomes either +front or -front.
        R_back = Rotation.from_rotvec(tilt_axis * np.radians(90)).as_matrix()
        yield ("prone on back", R_back)
        R_belly = Rotation.from_rotvec(tilt_axis * np.radians(-90)).as_matrix()
        yield ("prone on belly", R_belly)

    def _score_orientation(self, mesh, rotation_matrix):
        """
        Score an orientation (lower is better). Combines:
          1. Overhang area penalty
          2. Bottom-contact reward
          3. Z-height stability
          4. Build-volume fit (hard penalty)
          5. Front-face scar penalty (BattleTech-specific)
        """
        score = 0.0
        analyzer = MeshAnalyzer(mesh)

        # 1. Overhang penalty
        overhang_faces = analyzer.get_overhang_faces(
            max_angle=SupportConfig.MAX_OVERHANG_ANGLE
        )
        overhang_area = float(np.sum(mesh.area_faces[overhang_faces])) if len(overhang_faces) else 0.0
        score += overhang_area * 10.0

        # 2. Bottom contact reward
        bottom_faces = analyzer.get_bottom_faces()
        if len(bottom_faces) > 0:
            bottom_normals = mesh.face_normals[bottom_faces]
            facing_up = bottom_normals[:, 2] > 0.9
            bottom_up_area = float(np.sum(mesh.area_faces[bottom_faces[facing_up]]))
            score -= bottom_up_area * 5.0

        # 3. Z-height stability
        bounds = mesh.bounds
        z_height = bounds[1, 2] - bounds[0, 2]
        xy_footprint = (bounds[1, 0] - bounds[0, 0]) * (bounds[1, 1] - bounds[0, 1])
        footprint_diag = np.sqrt(xy_footprint) if xy_footprint > 0 else 0.0
        if z_height < footprint_diag / 4:
            score += (footprint_diag / 4 - z_height) * 20.0

        # 4. Build-volume fit
        x_size = bounds[1, 0] - bounds[0, 0]
        y_size = bounds[1, 1] - bounds[0, 1]
        if (x_size > PrinterConfig.BUILD_VOLUME_X or
            y_size > PrinterConfig.BUILD_VOLUME_Y or
            z_height > PrinterConfig.BUILD_VOLUME_Z):
            score += 100000.0

        # 5. Front-face scar penalty: the original front_axis is rotated by R.
        # If the rotated front points DOWN (toward build plate), the front face
        # would either touch the plate or get covered in supports. Either way,
        # huge scarring on the visible side.
        front_world = rotation_matrix @ self.front_axis
        if front_world[2] < 0:
            # front points down — bad
            penalty = SupportConfig.FRONT_FACE_SCAR_PENALTY * (-front_world[2])
            # Scale by mesh size so it's comparable to overhang area terms
            score += penalty * mesh.area * 0.05
        elif front_world[2] > 0.9:
            # front points straight up — also bad (the table-facing side is now hidden
            # under the model and the BACK is exposed)
            score += SupportConfig.FRONT_FACE_SCAR_PENALTY * 0.4 * front_world[2] * mesh.area * 0.05

        return score

    def apply_optimal_orientation(self, num_samples=None):
        """Find and apply the optimal canonical pose to the mesh."""
        transform = self.optimize(num_samples)
        self.mesh.apply_transform(transform)
        return transform
