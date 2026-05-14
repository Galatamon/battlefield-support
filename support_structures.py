"""
Support structure generation
Creates 3D geometry for support pillars with collision avoidance and lattice towers
"""

import numpy as np
import trimesh
from collections import deque
from config import SupportConfig
from collision_detector import CollisionDetector
from path_router import PathRouter
from curved_support import CurvedSupportGenerator
from lattice_tower import LatticeTowerGenerator
from support_optimizer import get_support_tip_diameter, get_support_base_diameter


class SupportGenerator:
    """Generate 3D support structures with collision avoidance"""

    def __init__(self, mesh, config=None, front_axis=None, strict_front=False):
        self.mesh = mesh
        self.config = config or {}
        self.support_meshes = []

        # BattleTech: front-axis is a unit vector in world coords. Support
        # contacts whose face normal points within FRONT_FACE_CONE_DEG of this
        # vector are "front" and must be snapped or skipped.
        self.front_axis = (np.array(front_axis, dtype=float)
                           if front_axis is not None else None)
        self.strict_front = bool(strict_front)
        self.contact_metadata = []

        # Initialize new components
        print("  Initializing collision detection...")
        self.collision_detector = CollisionDetector(mesh)

        # Get build plate Z
        self.build_plate_z = mesh.bounds[0, 2]

        print("  Initializing path router...")
        self.path_router = PathRouter(self.collision_detector, self.build_plate_z)

        print("  Initializing curved support generator...")
        self.curved_generator = CurvedSupportGenerator()

        print("  Initializing lattice tower generator...")
        self.lattice_generator = LatticeTowerGenerator()

    def _classify_point_relative_to_front(self, point):
        """
        Classify a support contact relative to the front axis.

        Returns:
            'front' if the contact face normal is within FRONT_FACE_CONE_DEG of +front_axis,
            'back'  if within FRONT_FACE_CONE_DEG of -front_axis,
            'side'  otherwise.
        """
        if self.front_axis is None or 'face_normal' not in point:
            return 'side'

        normal = np.asarray(point['face_normal'], dtype=float)
        n = np.linalg.norm(normal)
        if n < 1e-9:
            return 'side'
        normal = normal / n

        cos_threshold = np.cos(np.radians(SupportConfig.FRONT_FACE_CONE_DEG))
        front_dot = float(np.dot(normal, self.front_axis))
        if front_dot >= cos_threshold:
            return 'front'
        if front_dot <= -cos_threshold:
            return 'back'
        return 'side'

    def _snap_off_front_face(self, point):
        """
        Walk the face-adjacency graph (BFS up to depth 3) from the point's
        face looking for a face whose normal is NOT in the front cone. If
        found, move the contact to that face's center, nudged slightly along
        its inward normal so the support tip embeds slightly into the
        non-front surface (and the contact ends up under an edge, not on the
        visible front).

        Returns the (possibly mutated) point and a bool indicating success.
        """
        if self.front_axis is None or 'face_index' not in point:
            return point, False

        start_idx = int(point['face_index'])
        cos_threshold = np.cos(np.radians(SupportConfig.FRONT_FACE_CONE_DEG))

        # Build face adjacency (cached on the mesh)
        adjacency = self.mesh.face_adjacency  # (M, 2) pairs of face indices
        adj_map = {}
        for a, b in adjacency:
            adj_map.setdefault(int(a), []).append(int(b))
            adj_map.setdefault(int(b), []).append(int(a))

        visited = {start_idx}
        queue = deque([(start_idx, 0)])
        max_depth = 3
        best_face = None

        while queue:
            face_idx, depth = queue.popleft()
            if depth > max_depth:
                continue
            normal = self.mesh.face_normals[face_idx]
            if depth > 0 and float(np.dot(normal, self.front_axis)) < cos_threshold:
                best_face = face_idx
                break
            for neighbor in adj_map.get(face_idx, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        if best_face is None:
            return point, False

        # Move the contact to the centroid of the chosen face, nudged inward
        # by a tiny amount along that face's normal (so the support tip
        # actually touches geometry, not floats next to it).
        new_center = self.mesh.triangles_center[best_face]
        new_normal = self.mesh.face_normals[best_face]
        nudge = 0.05  # mm
        new_pos = new_center - new_normal * nudge

        point['x'] = float(new_pos[0])
        point['y'] = float(new_pos[1])
        point['z'] = float(new_pos[2])
        point['face_index'] = int(best_face)
        point['face_normal'] = new_normal.tolist()
        point['snapped_from_front'] = True
        return point, True

    def _apply_front_face_policy(self, support_points):
        """
        Classify each point and either snap it off the front face or (if
        strict_front and the resin can self-bridge the gap) drop it. Returns
        the filtered, possibly-mutated list.
        """
        if self.front_axis is None:
            for p in support_points:
                p['face_class'] = 'side'
            return support_points

        kept = []
        front_in = 0
        snapped = 0
        skipped = 0
        unsnap_able = 0

        for p in support_points:
            cls = self._classify_point_relative_to_front(p)
            if cls == 'front':
                front_in += 1
                if self.strict_front:
                    # Strict policy: skip if the unsupported span is short
                    # enough that ABS-like resin can self-bridge.
                    bridge = p.get('bridge_length', 0.0) or 0.0
                    if bridge and bridge < SupportConfig.MAX_FRONT_SELF_BRIDGE_MM:
                        skipped += 1
                        continue
                p, ok = self._snap_off_front_face(p)
                if ok:
                    snapped += 1
                    p['face_class'] = self._classify_point_relative_to_front(p)
                else:
                    unsnap_able += 1
                    # Last resort: keep the point but flag it so the preview
                    # paints it red as a known scar.
                    p['face_class'] = 'front'
            else:
                p['face_class'] = cls
            kept.append(p)

        print(f"  Front-face policy: {front_in} on front cone "
              f"({snapped} snapped, {skipped} skipped, {unsnap_able} kept as scar)")
        return kept

    def generate_supports(self, support_points):
        """
        Generate 3D support structures for all support points with collision avoidance

        Args:
            support_points: List of support point dictionaries

        Returns:
            Trimesh object containing all supports
        """
        print(f"\nGenerating {len(support_points)} support structures...")

        if not support_points:
            print("  No supports needed")
            return None

        # Phase 0: Front-face policy (BattleTech) — classify + snap/skip
        support_points = self._apply_front_face_policy(support_points)

        # Phase 1: Route support paths with collision avoidance
        print("  Phase 1: Routing support paths with collision avoidance...")
        support_paths = []
        support_tiers = []  # Track tier for each path
        per_path_meta = []  # Parallel metadata list for contact_metadata

        for i, point in enumerate(support_points):
            start_point = [point['x'], point['y'], point['z']]

            # Check minimum height
            height = point['z'] - self.build_plate_z
            if height < SupportConfig.MIN_SUPPORT_HEIGHT:
                continue

            # Get tier-specific tip diameter
            tier = point.get('tier', 'medium')
            tip_radius = get_support_tip_diameter(tier) / 2

            # Route path from contact point to build plate
            path = self.path_router.route_support_path(
                start_point,
                target_z=None,  # Will go to build plate
                radius=tip_radius,
                max_iterations=300
            )

            if path is not None:
                # Smooth path to remove unnecessary waypoints
                path = self.path_router.smooth_path(path, tip_radius)
                support_paths.append(path)
                support_tiers.append(tier)
                per_path_meta.append({
                    'xyz': [float(point['x']), float(point['y']), float(point['z'])],
                    'tier': tier,
                    'tip_radius': float(tip_radius),
                    'face_class': point.get('face_class', 'side'),
                    'type': point.get('type', ''),
                })

            if (i + 1) % 50 == 0:
                print(f"    Routed {i+1}/{len(support_points)} paths...")

        print(f"  Routed {len(support_paths)} support paths")

        if not support_paths:
            print("  Warning: No valid support paths could be generated")
            return None

        # Phase 2: Create lattice towers to consolidate support roots
        print("  Phase 2: Creating lattice towers...")
        tower_meshes, modified_paths = self.lattice_generator.consolidate_supports_with_towers(
            support_paths, self.build_plate_z
        )

        if tower_meshes:
            print(f"  Created {len(tower_meshes)} lattice towers")
        else:
            print("  No lattice towers needed (using individual supports)")
            modified_paths = support_paths

        # Phase 3: Generate support geometry following routed paths
        print("  Phase 3: Generating support geometry...")
        supports = []

        # consolidate_supports_with_towers preserves index order, so tier
        # alignment with paths is intact unless the routing dropped a support.
        if len(support_tiers) != len(modified_paths):
            support_tiers = ['medium'] * len(modified_paths)

        for i, path in enumerate(modified_paths):
            if len(path) < 2:
                continue

            tier = support_tiers[i] if i < len(support_tiers) else 'medium'
            tip_radius = get_support_tip_diameter(tier) / 2
            base_radius = get_support_base_diameter(tier) / 2

            support_mesh = self.curved_generator.create_curved_support(
                path, tip_radius, base_radius
            )

            if support_mesh is not None:
                supports.append(support_mesh)

            if (i + 1) % 100 == 0:
                print(f"    Generated {i+1}/{len(modified_paths)} support geometries...")

        print(f"  Generated {len(supports)} support structures")

        # Combine supports and towers
        all_meshes = supports + tower_meshes

        if not all_meshes:
            print("  Warning: No valid supports could be generated")
            return None

        # Stash contact metadata for the preview renderer + sidecar JSON.
        self.contact_metadata = per_path_meta

        # Combine all supports into one mesh
        print("  Combining support structures...")
        combined_supports = trimesh.util.concatenate(all_meshes)

        print(f"  Total support volume: {combined_supports.volume:.2f} mm³")
        print(f"  Total support surface area: {combined_supports.area:.2f} mm²")

        self.support_meshes = all_meshes
        self._last_supports = combined_supports
        return combined_supports

    def _create_support(self, x, y, z_top, z_bottom, support_type):
        """
        Create a single support pillar

        Args:
            x, y: XY position of support
            z_top: Top of support (contact point with model)
            z_bottom: Bottom of support (build plate)
            support_type: Type of support ('island', 'overhang', 'bridge')

        Returns:
            Trimesh object for the support
        """
        # Calculate support height
        height = z_top - z_bottom

        # Skip if too short
        if height < SupportConfig.MIN_SUPPORT_HEIGHT:
            return None

        # Support parameters
        tip_radius = SupportConfig.SUPPORT_TIP_DIAMETER / 2
        base_radius = SupportConfig.SUPPORT_BASE_DIAMETER / 2
        taper_angle = np.radians(SupportConfig.SUPPORT_TAPER_ANGLE)

        # For very tall supports, use tree-like branching
        if height > 20.0:
            return self._create_tree_support(x, y, z_top, z_bottom)

        # Create a cone-shaped support
        # Start with tip at model, expand to base on build plate
        support = self._create_cone_support(
            x, y, z_bottom, height, tip_radius, base_radius
        )

        return support

    def _create_cone_support(self, x, y, z_base, height, tip_radius, base_radius):
        """
        Create a simple cone support

        Args:
            x, y: Center position
            z_base: Base Z height (build plate)
            height: Support height
            tip_radius: Radius at tip (top, contacts model)
            base_radius: Radius at base (bottom, on build plate)

        Returns:
            Trimesh object
        """
        segments = 16  # Number of sides

        # Create a cylinder and taper it to create proper cone
        # Start with cylinder at base_radius (largest radius)
        cylinder = trimesh.creation.cylinder(
            radius=base_radius,
            height=height,
            sections=segments
        )

        # Cylinder is created centered at origin with height along Z
        # Modify vertices to create taper from base to tip
        vertices = cylinder.vertices.copy()
        z_vals = vertices[:, 2]
        z_min, z_max = z_vals.min(), z_vals.max()

        # Scale radially based on Z position
        # Bottom (z_min) should be base_radius (large)
        # Top (z_max) should be tip_radius (small)
        for i, vertex in enumerate(vertices):
            z_pos = vertex[2]
            # Interpolate: t=0 at bottom, t=1 at top
            t = (z_pos - z_min) / (z_max - z_min) if z_max > z_min else 0

            # Interpolate radius from base (large) to tip (small)
            target_radius = base_radius * (1 - t) + tip_radius * t

            # Current radius
            current_radius = np.sqrt(vertex[0]**2 + vertex[1]**2)

            if current_radius > 0.001:
                scale = target_radius / current_radius
                vertices[i, 0] *= scale
                vertices[i, 1] *= scale

        cylinder.vertices = vertices

        # Position the support
        # Bottom should be at z_base, top at z_base + height
        # Cylinder is centered at 0, so shift it up
        translation = [x, y, z_base + height/2]
        cylinder.apply_translation(translation)

        return cylinder

    def _create_tree_support(self, x, y, z_top, z_bottom):
        """
        Create a tree-like support for tall structures

        Args:
            x, y: Top position
            z_top: Top Z
            z_bottom: Bottom Z

        Returns:
            Trimesh object
        """
        # For tall supports, create branches
        # Main trunk in center, tip reaches model

        height = z_top - z_bottom

        # Create main trunk
        trunk_radius = SupportConfig.SUPPORT_BASE_DIAMETER / 2
        tip_radius = SupportConfig.SUPPORT_TIP_DIAMETER / 2

        # Split into segments for better stability
        num_segments = max(2, int(height / 10))
        segment_height = height / num_segments

        segments = []

        for i in range(num_segments):
            z_start = z_bottom + i * segment_height
            z_end = z_start + segment_height

            # Interpolate radius
            t_start = i / num_segments
            t_end = (i + 1) / num_segments

            r_start = trunk_radius + t_start * (tip_radius - trunk_radius)
            r_end = trunk_radius + t_end * (tip_radius - trunk_radius)

            # Create segment
            segment = self._create_cylinder(
                x, y, z_start, segment_height, r_start, r_end
            )
            segments.append(segment)

        # Combine segments
        if segments:
            return trimesh.util.concatenate(segments)
        else:
            return None

    def _create_cylinder(self, x, y, z_base, height, radius_bottom, radius_top):
        """Create a cylinder/cone segment"""
        segments = 12

        # Create cone
        cone = trimesh.creation.cone(
            radius=radius_bottom,
            height=height,
            sections=segments
        )

        # Modify top radius
        vertices = cone.vertices.copy()
        z_vals = vertices[:, 2]
        z_min, z_max = z_vals.min(), z_vals.max()

        for i, vertex in enumerate(vertices):
            z_pos = vertex[2]
            t = (z_pos - z_min) / (z_max - z_min) if z_max > z_min else 0
            target_radius = radius_bottom + t * (radius_top - radius_bottom)

            current_radius = np.sqrt(vertex[0]**2 + vertex[1]**2)
            if current_radius > 0.001:
                scale = target_radius / current_radius
                vertices[i, 0] *= scale
                vertices[i, 1] *= scale

        cone.vertices = vertices

        # Position
        cone.apply_translation([x, y, z_base])

        return cone

    def merge_with_model(self, supports):
        """
        Merge support structures with the original model

        Args:
            supports: Trimesh object containing supports

        Returns:
            Combined mesh
        """
        if supports is None:
            return self.mesh

        print("\nMerging supports with model...")

        # Combine meshes
        combined = trimesh.util.concatenate([self.mesh, supports])

        print(f"  Combined mesh: {len(combined.vertices)} vertices, {len(combined.faces)} faces")

        return combined

    def get_support_summary(self, supports):
        """Get summary of generated supports"""
        if supports is None:
            return "No supports generated"

        return f"""Support Generation Summary:
  Number of support structures: {len(self.support_meshes)}
  Total support volume: {supports.volume:.2f} mm³
  Support surface area: {supports.area:.2f} mm²
  Estimated resin usage: {supports.volume / 1000:.2f} ml

  Features:
  - Collision detection: {"Enabled" if SupportConfig.COLLISION_CHECK_ENABLED else "Disabled"}
  - Lateral routing: {"Enabled" if SupportConfig.LATERAL_ROUTING_ENABLED else "Disabled"}
  - Lattice towers: {"Enabled" if SupportConfig.LATTICE_TOWER_ENABLED else "Disabled"}
  - Max support diameter: {SupportConfig.SUPPORT_MAX_DIAMETER} mm"""
