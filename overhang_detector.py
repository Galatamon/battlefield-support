"""
Overhang and bridge detection for support generation
"""

import numpy as np
from mesh_loader import MeshAnalyzer
from config import SupportConfig, AnalysisConfig


class OverhangDetector:
    """Detect overhangs and bridges that need support"""

    def __init__(self, mesh):
        self.mesh = mesh
        self.analyzer = MeshAnalyzer(mesh)

    def detect_overhangs(self, max_angle=None):
        """
        Detect overhang areas that need support

        Args:
            max_angle: Maximum overhang angle in degrees (default from config)

        Returns:
            List of support points for overhangs
        """
        if max_angle is None:
            max_angle = SupportConfig.MAX_OVERHANG_ANGLE

        print(f"Detecting overhangs (max angle: {max_angle}°)...")

        # Get faces that exceed overhang angle
        overhang_faces = self.analyzer.get_overhang_faces(max_angle)

        if len(overhang_faces) == 0:
            print("  No overhangs detected")
            return []

        print(f"  Found {len(overhang_faces)} overhanging faces")

        # Calculate support points for these faces
        support_points = []

        # Get centers of overhang faces
        face_centers = self.analyzer.get_face_centers(overhang_faces)
        face_areas = self.mesh.area_faces[overhang_faces]

        # Filter by minimum area
        significant_faces = face_areas >= AnalysisConfig.OVERHANG_MIN_AREA

        for idx, (center, area) in enumerate(zip(face_centers[significant_faces],
                                                   face_areas[significant_faces])):
            # Calculate number of supports needed based on area
            # and face angle
            face_normal = self.mesh.face_normals[overhang_faces[idx]]

            # More supports for more horizontal faces
            angle_from_horizontal = np.degrees(
                np.arccos(abs(face_normal[2]))
            )

            # Calculate support density based on angle
            # Near-horizontal surfaces need more support, but not excessively
            if angle_from_horizontal < 20:
                # Very horizontal - needs good support but scale with area
                base_spacing = SupportConfig.EDGE_SUPPORT_SPACING
            elif angle_from_horizontal < 40:
                # Moderately horizontal - standard spacing
                base_spacing = SupportConfig.SUPPORT_SPACING
            else:
                # More vertical - can use sparser spacing
                base_spacing = SupportConfig.SUPPORT_SPACING * 1.5

            # Adaptive spacing: larger areas get proportionally sparser supports
            # This prevents "mat of supports" on large flat areas
            # The relationship is: effective_spacing = base_spacing * (1 + log10(area/10))
            # So a 10mm² area uses base_spacing, 100mm² uses 2x spacing, etc.
            if area > 10.0:
                area_factor = 1.0 + 0.3 * np.log10(area / 10.0)
                spacing = base_spacing * min(area_factor, 2.5)  # Cap at 2.5x
            else:
                spacing = base_spacing

            # Number of supports for this face - with reasonable cap
            num_supports = max(1, int(np.ceil(area / (spacing ** 2))))
            # Cap maximum supports per face to prevent over-support
            num_supports = min(num_supports, 8)

            if num_supports == 1:
                # Single support at center
                support_points.append({
                    'x': center[0],
                    'y': center[1],
                    'z': center[2],
                    'area': area,
                    'type': 'overhang',
                    'angle': angle_from_horizontal
                })
            else:
                # Multiple supports - sample on the face
                # Get vertices of this face
                face_idx = overhang_faces[idx]
                vertices = self.mesh.vertices[self.mesh.faces[face_idx]]

                # Create grid of points on the triangular face
                supports = self._sample_points_on_triangle(
                    vertices, num_supports
                )

                for point in supports:
                    support_points.append({
                        'x': point[0],
                        'y': point[1],
                        'z': point[2],
                        'area': area / num_supports,
                        'type': 'overhang',
                        'angle': angle_from_horizontal
                    })

        print(f"  Generated {len(support_points)} overhang support points")
        return support_points

    def detect_bridges(self, max_length=None):
        """
        Detect bridges (horizontal spans) that exceed safe length

        Args:
            max_length: Maximum bridge length in mm (default from config)

        Returns:
            List of support points for bridges
        """
        if max_length is None:
            max_length = SupportConfig.MAX_BRIDGE_LENGTH

        print(f"Detecting bridges (max length: {max_length}mm)...")

        support_points = []

        # Find near-horizontal faces
        normals = self.mesh.face_normals
        z_component = abs(normals[:, 2])

        # Horizontal faces have Z component close to 0
        horizontal_threshold = 0.3  # cos(72°) - fairly horizontal
        horizontal_faces = z_component < horizontal_threshold

        # Only consider downward-facing or side faces
        downward_faces = normals[:, 2] < 0.1
        candidate_faces = horizontal_faces & downward_faces

        if not np.any(candidate_faces):
            print("  No bridge candidates detected")
            return []

        candidate_indices = np.where(candidate_faces)[0]
        print(f"  Checking {len(candidate_indices)} potential bridge faces...")

        # Check each face for bridge length
        for face_idx in candidate_indices:
            # Get vertices of this face
            vertices = self.mesh.vertices[self.mesh.faces[face_idx]]

            # Calculate edge lengths
            edge_lengths = [
                np.linalg.norm(vertices[1] - vertices[0]),
                np.linalg.norm(vertices[2] - vertices[1]),
                np.linalg.norm(vertices[0] - vertices[2])
            ]

            max_edge = max(edge_lengths)

            # If any edge exceeds max bridge length, need support
            if max_edge > max_length:
                # Find the long edge
                long_edge_idx = edge_lengths.index(max_edge)

                if long_edge_idx == 0:
                    v1, v2 = vertices[0], vertices[1]
                elif long_edge_idx == 1:
                    v1, v2 = vertices[1], vertices[2]
                else:
                    v1, v2 = vertices[2], vertices[0]

                # Add supports along the bridge
                num_supports = int(np.ceil(max_edge / max_length)) + 1

                for i in range(1, num_supports):
                    t = i / num_supports
                    point = v1 + t * (v2 - v1)

                    support_points.append({
                        'x': point[0],
                        'y': point[1],
                        'z': point[2],
                        'area': 0.0,  # Bridge support
                        'type': 'bridge',
                        'length': max_edge
                    })

        print(f"  Generated {len(support_points)} bridge support points")
        return support_points

    def _sample_points_on_triangle(self, vertices, num_points):
        """
        Sample random points on a triangle

        Args:
            vertices: 3x3 array of triangle vertices
            num_points: Number of points to sample

        Returns:
            Array of sampled points
        """
        points = []

        for _ in range(num_points):
            # Random barycentric coordinates
            r1, r2 = np.random.random(2)

            # Ensure uniform distribution
            if r1 + r2 > 1:
                r1 = 1 - r1
                r2 = 1 - r2

            r3 = 1 - r1 - r2

            # Calculate point
            point = r1 * vertices[0] + r2 * vertices[1] + r3 * vertices[2]
            points.append(point)

        return np.array(points)

    def get_all_support_points(self):
        """
        Detect all types of support needs and return combined list

        Returns:
            List of all support points needed
        """
        print("\nAnalyzing model for support requirements...")

        # Detect overhangs
        overhang_points = self.detect_overhangs()

        # Detect bridges
        bridge_points = self.detect_bridges()

        # Combine all support points
        all_points = overhang_points + bridge_points

        print(f"\nTotal support points from overhang/bridge analysis: {len(all_points)}")

        return all_points

    def get_detection_summary(self, support_points):
        """Get summary of detected support needs"""
        if not support_points:
            return "No overhangs or bridges requiring support"

        overhang_count = sum(1 for p in support_points if p['type'] == 'overhang')
        bridge_count = sum(1 for p in support_points if p['type'] == 'bridge')

        total_area = sum(p['area'] for p in support_points if 'area' in p)

        return f"""Overhang/Bridge Detection Summary:
  Overhang support points: {overhang_count}
  Bridge support points: {bridge_count}
  Total support points: {len(support_points)}
  Total area: {total_area:.2f} mm²"""
