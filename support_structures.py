"""
Support structure generation
Creates 3D geometry for support pillars
"""

import numpy as np
import trimesh
from config import SupportConfig


class SupportGenerator:
    """Generate 3D support structures"""

    def __init__(self, mesh, config=None):
        self.mesh = mesh
        self.config = config or {}
        self.support_meshes = []

    def generate_supports(self, support_points):
        """
        Generate 3D support structures for all support points

        Args:
            support_points: List of support point dictionaries

        Returns:
            Trimesh object containing all supports
        """
        print(f"\nGenerating {len(support_points)} support structures...")

        if not support_points:
            print("  No supports needed")
            return None

        # Get build plate level (minimum Z)
        build_plate_z = self.mesh.bounds[0, 2]

        # Generate support for each point
        supports = []

        for i, point in enumerate(support_points):
            support_mesh = self._create_support(
                point['x'],
                point['y'],
                point['z'],
                build_plate_z,
                point.get('type', 'unknown')
            )

            if support_mesh is not None:
                supports.append(support_mesh)

            if (i + 1) % 100 == 0:
                print(f"  Generated {i+1}/{len(support_points)} supports...")

        if not supports:
            print("  Warning: No valid supports could be generated")
            return None

        # Combine all supports into one mesh
        print("  Combining support structures...")
        combined_supports = trimesh.util.concatenate(supports)

        print(f"  Generated {len(supports)} support structures")
        print(f"  Total support volume: {combined_supports.volume:.2f} mm³")

        self.support_meshes = supports
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
            z_base: Base Z height
            height: Support height
            tip_radius: Radius at tip (top)
            base_radius: Radius at base (bottom)

        Returns:
            Trimesh object
        """
        # Create cone
        # Trimesh creates cone with point at origin, opening upward
        # We need to flip and position it

        segments = 16  # Number of sides

        # Create cone with tip at top, base at bottom
        cone = trimesh.creation.cone(
            radius=base_radius,
            height=height,
            sections=segments
        )

        # The cone is created with tip at (0,0,0) pointing up
        # We need tip at top, base at bottom
        # First flip it
        flip_transform = trimesh.transformations.rotation_matrix(
            np.pi, [1, 0, 0]
        )
        cone.apply_transform(flip_transform)

        # Now scale the tip to be smaller
        # We need a non-uniform scaling along the height
        # Create a custom cone by modifying vertices
        vertices = cone.vertices.copy()

        # Find top and bottom vertices
        z_vals = vertices[:, 2]
        z_min, z_max = z_vals.min(), z_vals.max()

        # Scale radially based on Z position
        for i, vertex in enumerate(vertices):
            z_pos = vertex[2]
            # Interpolate radius from tip to base
            t = (z_pos - z_min) / (z_max - z_min)  # 0 at bottom, 1 at top
            target_radius = base_radius + t * (tip_radius - base_radius)

            # Current radius
            current_radius = np.sqrt(vertex[0]**2 + vertex[1]**2)

            if current_radius > 0.001:
                scale = target_radius / current_radius
                vertices[i, 0] *= scale
                vertices[i, 1] *= scale

        cone.vertices = vertices

        # Position the support
        # Move so tip is at (x, y, z_base + height)
        translation = [x, y, z_base + height - z_max]
        cone.apply_translation(translation)

        return cone

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
  Estimated resin usage: {supports.volume / 1000:.2f} ml"""
