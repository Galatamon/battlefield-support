"""
Support structure generation
Creates 3D geometry for support pillars with collision avoidance and lattice towers
"""

import numpy as np
import trimesh
from config import SupportConfig
from collision_detector import CollisionDetector
from path_router import PathRouter
from curved_support import CurvedSupportGenerator
from lattice_tower import LatticeTowerGenerator


class SupportGenerator:
    """Generate 3D support structures with collision avoidance"""

    def __init__(self, mesh, config=None):
        self.mesh = mesh
        self.config = config or {}
        self.support_meshes = []

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

        # Phase 1: Route support paths with collision avoidance
        print("  Phase 1: Routing support paths with collision avoidance...")
        support_paths = []

        for i, point in enumerate(support_points):
            start_point = [point['x'], point['y'], point['z']]

            # Check minimum height
            height = point['z'] - self.build_plate_z
            if height < SupportConfig.MIN_SUPPORT_HEIGHT:
                continue

            # Route path from contact point to build plate
            tip_radius = SupportConfig.SUPPORT_TIP_DIAMETER / 2
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

        tip_radius = SupportConfig.SUPPORT_TIP_DIAMETER / 2
        base_radius = SupportConfig.SUPPORT_BASE_DIAMETER / 2

        for i, path in enumerate(modified_paths):
            if len(path) < 2:
                continue

            # Create curved support following path
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

        # Combine all supports into one mesh
        print("  Combining support structures...")
        combined_supports = trimesh.util.concatenate(all_meshes)

        print(f"  Total support volume: {combined_supports.volume:.2f} mm³")
        print(f"  Total support surface area: {combined_supports.area:.2f} mm²")

        self.support_meshes = all_meshes
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
