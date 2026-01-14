"""
Auto-orientation algorithm to optimize model placement for printing
"""

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from mesh_loader import MeshAnalyzer
from config import SupportConfig, PrinterConfig


class OrientationOptimizer:
    """Optimize model orientation for minimal support and best print quality"""

    def __init__(self, mesh, config=None):
        self.mesh = mesh
        self.config = config or {}
        self.analyzer = MeshAnalyzer(mesh)

    def optimize(self, num_samples=20):
        """
        Find optimal orientation for the model

        Args:
            num_samples: Number of orientations to test

        Returns:
            Transformation matrix for optimal orientation
        """
        print("Optimizing model orientation...")

        best_score = float('inf')
        best_transform = np.eye(4)

        # Generate candidate orientations
        orientations = self._generate_orientations(num_samples)

        for i, rotation_matrix in enumerate(orientations):
            # Create transformation matrix
            transform = np.eye(4)
            transform[:3, :3] = rotation_matrix

            # Apply transformation to a copy of the mesh
            test_mesh = self.mesh.copy()
            test_mesh.apply_transform(transform)

            # Score this orientation
            score = self._score_orientation(test_mesh)

            print(f"  Orientation {i+1}/{num_samples}: score = {score:.2f}")

            if score < best_score:
                best_score = score
                best_transform = transform

        print(f"  Best orientation found with score: {best_score:.2f}")

        return best_transform

    def _generate_orientations(self, num_samples):
        """
        Generate candidate orientations to test

        Args:
            num_samples: Number of orientations to generate

        Returns:
            List of rotation matrices
        """
        orientations = []

        # Always include identity (original orientation)
        orientations.append(np.eye(3))

        # Try aligning each principal axis with Z
        # This gives us orientations with major flat faces down
        for i in range(3):
            for sign in [1, -1]:
                axis = np.zeros(3)
                axis[i] = sign
                # Create rotation that aligns this axis with Z
                rot = self._rotation_to_align(axis, np.array([0, 0, 1]))
                orientations.append(rot)

        # Add some random rotations for exploration
        num_random = max(0, num_samples - len(orientations))
        for _ in range(num_random):
            # Random rotation
            angles = np.random.uniform(-np.pi, np.pi, 3)
            rot = Rotation.from_euler('xyz', angles).as_matrix()
            orientations.append(rot)

        return orientations[:num_samples]

    def _rotation_to_align(self, v1, v2):
        """
        Create rotation matrix that aligns vector v1 with v2

        Args:
            v1: Source vector
            v2: Target vector

        Returns:
            3x3 rotation matrix
        """
        v1 = v1 / np.linalg.norm(v1)
        v2 = v2 / np.linalg.norm(v2)

        # Find rotation axis
        axis = np.cross(v1, v2)
        axis_length = np.linalg.norm(axis)

        # Handle parallel/antiparallel case
        if axis_length < 1e-6:
            if np.dot(v1, v2) > 0:
                return np.eye(3)  # Already aligned
            else:
                # Find perpendicular axis
                if abs(v1[0]) < abs(v1[1]):
                    perp = np.array([1, 0, 0])
                else:
                    perp = np.array([0, 1, 0])
                axis = np.cross(v1, perp)
                axis = axis / np.linalg.norm(axis)
                angle = np.pi
        else:
            axis = axis / axis_length
            angle = np.arcsin(axis_length)

        # Create rotation matrix using Rodriguez formula
        return Rotation.from_rotvec(axis * angle).as_matrix()

    def _score_orientation(self, mesh):
        """
        Score an orientation (lower is better)

        Scoring criteria:
        1. Minimize overhang area
        2. Maximize bottom contact area
        3. Penalize small Z-height (unstable)
        4. Reward flat bottom surface

        Args:
            mesh: Mesh in test orientation

        Returns:
            Score (lower is better)
        """
        score = 0.0
        analyzer = MeshAnalyzer(mesh)

        # 1. Overhang penalty - count faces that need support
        overhang_faces = analyzer.get_overhang_faces(
            max_angle=SupportConfig.MAX_OVERHANG_ANGLE
        )
        overhang_count = len(overhang_faces)

        # Calculate overhang area
        if overhang_count > 0:
            overhang_area = np.sum(mesh.area_faces[overhang_faces])
        else:
            overhang_area = 0.0

        # Weight overhang heavily
        score += overhang_area * 10.0

        # 2. Bottom contact area - reward large flat bottom
        bottom_faces = analyzer.get_bottom_faces()
        if len(bottom_faces) > 0:
            # Get normals of bottom faces
            bottom_normals = mesh.face_normals[bottom_faces]
            # Check how many are facing up (good for adhesion)
            facing_up = bottom_normals[:, 2] > 0.9  # Nearly vertical
            bottom_up_area = np.sum(mesh.area_faces[bottom_faces[facing_up]])

            # Reward flat bottom (negative score)
            score -= bottom_up_area * 5.0

        # 3. Z-height stability - penalize very short prints
        bounds = mesh.bounds
        z_height = bounds[1, 2] - bounds[0, 2]
        xy_footprint = (bounds[1, 0] - bounds[0, 0]) * (bounds[1, 1] - bounds[0, 1])

        # Penalize if height is less than 1/4 of footprint diagonal
        footprint_diag = np.sqrt(xy_footprint)
        if z_height < footprint_diag / 4:
            score += (footprint_diag / 4 - z_height) * 20.0

        # 4. Check if fits in build volume
        x_size = bounds[1, 0] - bounds[0, 0]
        y_size = bounds[1, 1] - bounds[0, 1]

        if (x_size > PrinterConfig.BUILD_VOLUME_X or
            y_size > PrinterConfig.BUILD_VOLUME_Y or
            z_height > PrinterConfig.BUILD_VOLUME_Z):
            # Massive penalty for not fitting
            score += 100000.0

        # 5. Penalize sharp corners at bottom (prefer smooth contact)
        if len(bottom_faces) > 0:
            bottom_vertices_idx = np.unique(mesh.faces[bottom_faces].flatten())
            bottom_vertices = mesh.vertices[bottom_vertices_idx]
            # Calculate variance in Z (flat bottom has low variance)
            z_variance = np.var(bottom_vertices[:, 2])
            score += z_variance * 100.0

        return score

    def apply_optimal_orientation(self, num_samples=20):
        """
        Find and apply optimal orientation to the mesh

        Args:
            num_samples: Number of orientations to test

        Returns:
            The transformation matrix applied
        """
        transform = self.optimize(num_samples)
        self.mesh.apply_transform(transform)
        return transform
