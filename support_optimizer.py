"""
Support optimization for detail preservation
Implements point consolidation, detail zone detection, and tiered support sizing
"""

import numpy as np
from scipy.spatial import KDTree
from collections import defaultdict
from config import SupportConfig


class SupportOptimizer:
    """Optimize support point placement for detail preservation"""

    def __init__(self, mesh, config=None):
        self.mesh = mesh
        self.config = config or {}

        # Detail detection parameters
        self.curvature_threshold = self.config.get('curvature_threshold', 0.5)
        self.thin_feature_threshold = self.config.get('thin_feature_threshold', 2.0)  # mm

        # Consolidation parameters
        self.merge_radius = self.config.get('merge_radius', 1.5)  # mm - merge points closer than this

        # Analyze mesh for detail zones
        self._analyze_mesh_details()

    def _analyze_mesh_details(self):
        """Analyze mesh to identify high-detail areas using curvature"""
        print("  Analyzing mesh for detail zones...")

        # Create spatial index for fast queries (needed by other methods)
        self.vertex_tree = KDTree(self.mesh.vertices)

        # Calculate vertex curvature using discrete mean curvature
        self.vertex_curvature = self._calculate_vertex_curvature()

        # Identify thin features using local thickness estimation
        self.thin_features = self._detect_thin_features()

        # Calculate per-face detail scores
        self.face_detail_scores = self._calculate_face_detail_scores()

        high_detail_faces = np.sum(self.face_detail_scores > 0.5)
        print(f"    Found {high_detail_faces} high-detail faces ({100*high_detail_faces/len(self.mesh.faces):.1f}%)")

    def _calculate_vertex_curvature(self):
        """Calculate mean curvature at each vertex using angle deficit method"""
        num_vertices = len(self.mesh.vertices)
        curvature = np.zeros(num_vertices)

        # Get vertex neighbors through face adjacency
        vertex_faces = defaultdict(list)
        for i, face in enumerate(self.mesh.faces):
            for v in face:
                vertex_faces[v].append(i)

        for v_idx in range(num_vertices):
            adjacent_faces = vertex_faces[v_idx]
            if len(adjacent_faces) < 3:
                continue

            # Calculate angle sum around vertex
            angle_sum = 0.0
            for face_idx in adjacent_faces:
                face = self.mesh.faces[face_idx]
                # Find position of this vertex in face
                v_pos = np.where(face == v_idx)[0][0]

                # Get the three vertices
                v0 = self.mesh.vertices[face[v_pos]]
                v1 = self.mesh.vertices[face[(v_pos + 1) % 3]]
                v2 = self.mesh.vertices[face[(v_pos + 2) % 3]]

                # Calculate angle at this vertex
                vec1 = v1 - v0
                vec2 = v2 - v0

                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)

                if norm1 > 1e-10 and norm2 > 1e-10:
                    cos_angle = np.clip(np.dot(vec1, vec2) / (norm1 * norm2), -1, 1)
                    angle_sum += np.arccos(cos_angle)

            # Gaussian curvature approximation: angle deficit
            angle_deficit = 2 * np.pi - angle_sum

            # Normalize by approximate area (sum of adjacent face areas / 3)
            area = sum(self.mesh.area_faces[f] for f in adjacent_faces) / 3
            if area > 1e-10:
                curvature[v_idx] = abs(angle_deficit) / area

        # Normalize curvature to 0-1 range
        if curvature.max() > 0:
            curvature = curvature / curvature.max()

        return curvature

    def _detect_thin_features(self):
        """Detect thin features using local geometry analysis"""
        thin_vertices = np.zeros(len(self.mesh.vertices), dtype=bool)

        # Use a simpler approach based on local vertex neighborhood
        # Thin features have vertices very close to other vertices on the "opposite" side
        try:
            # Try ray-based detection if rtree is available
            sample_size = min(500, len(self.mesh.vertices))
            sample_indices = np.random.choice(len(self.mesh.vertices), sample_size, replace=False)

            for v_idx in sample_indices:
                vertex = self.mesh.vertices[v_idx]

                # Get vertex normal (average of adjacent face normals)
                adjacent_faces = np.where(np.any(self.mesh.faces == v_idx, axis=1))[0]
                if len(adjacent_faces) == 0:
                    continue

                normal = np.mean(self.mesh.face_normals[adjacent_faces], axis=0)
                norm_length = np.linalg.norm(normal)
                if norm_length < 1e-10:
                    continue
                normal = normal / norm_length

                # Cast ray in both directions to estimate thickness
                ray_origin = vertex + normal * 0.01  # Offset slightly

                # Check distance to nearest surface in opposite direction
                locations, index_ray, index_tri = self.mesh.ray.intersects_location(
                    ray_origins=[ray_origin],
                    ray_directions=[-normal]
                )

                if len(locations) > 0:
                    # Find closest intersection
                    distances = np.linalg.norm(locations - vertex, axis=1)
                    min_dist = np.min(distances)

                    if min_dist < self.thin_feature_threshold:
                        thin_vertices[v_idx] = True

        except (ImportError, ModuleNotFoundError):
            # Fallback: use vertex proximity analysis
            # Find vertices that have nearby vertices on "opposite" sides
            print("    Using fallback thin feature detection (rtree not available)")

            # Use the existing vertex tree for simple proximity check
            for v_idx in range(min(500, len(self.mesh.vertices))):
                # Find nearby vertices
                nearby = self.vertex_tree.query_ball_point(
                    self.mesh.vertices[v_idx],
                    self.thin_feature_threshold
                )

                # If there are many nearby vertices that aren't directly connected,
                # this might be a thin feature
                if len(nearby) > 5:
                    # Get connected vertices through edges
                    adjacent_faces = np.where(np.any(self.mesh.faces == v_idx, axis=1))[0]
                    connected = set()
                    for f in adjacent_faces:
                        connected.update(self.mesh.faces[f])

                    # Count non-connected nearby vertices
                    non_connected = [n for n in nearby if n not in connected]
                    if len(non_connected) > 3:
                        thin_vertices[v_idx] = True

        except Exception as e:
            # If all else fails, return empty array (no thin feature detection)
            print(f"    Thin feature detection failed: {e}")

        return thin_vertices

    def _calculate_face_detail_scores(self):
        """Calculate detail score (0-1) for each face"""
        scores = np.zeros(len(self.mesh.faces))

        for i, face in enumerate(self.mesh.faces):
            # Average curvature of face vertices
            avg_curvature = np.mean(self.vertex_curvature[face])

            # Check if any vertex is thin
            has_thin_feature = np.any(self.thin_features[face])

            # Combine into detail score
            # High curvature or thin features = high detail
            score = avg_curvature * 0.7
            if has_thin_feature:
                score += 0.3

            scores[i] = min(1.0, score)

        return scores

    def get_detail_score_at_point(self, point):
        """Get the detail score for a 3D point"""
        # Find nearest vertex
        dist, idx = self.vertex_tree.query(point)

        # Find faces containing this vertex
        adjacent_faces = np.where(np.any(self.mesh.faces == idx, axis=1))[0]

        if len(adjacent_faces) == 0:
            return 0.0

        # Return maximum detail score of adjacent faces
        return np.max(self.face_detail_scores[adjacent_faces])

    def consolidate_support_points(self, support_points):
        """
        Merge nearby support points to reduce density

        Args:
            support_points: List of support point dictionaries

        Returns:
            Consolidated list of support points
        """
        if not support_points or len(support_points) < 2:
            return support_points

        print(f"  Consolidating {len(support_points)} support points...")

        # Extract coordinates
        coords = np.array([[p['x'], p['y'], p['z']] for p in support_points])

        # Build KD-tree for spatial queries
        tree = KDTree(coords)

        # Track which points have been merged
        merged = np.zeros(len(support_points), dtype=bool)
        consolidated = []

        for i, point in enumerate(support_points):
            if merged[i]:
                continue

            # Find all points within merge radius
            coord = [point['x'], point['y'], point['z']]
            neighbors = tree.query_ball_point(coord, self.merge_radius)

            # Filter to unmerged neighbors
            unmerged_neighbors = [n for n in neighbors if not merged[n]]

            if len(unmerged_neighbors) <= 1:
                # No merging needed
                consolidated.append(point)
                merged[i] = True
            else:
                # Merge these points
                merged_point = self._merge_points([support_points[n] for n in unmerged_neighbors])
                consolidated.append(merged_point)

                # Mark all as merged
                for n in unmerged_neighbors:
                    merged[n] = True

        print(f"    Reduced to {len(consolidated)} support points ({100*len(consolidated)/len(support_points):.1f}%)")
        return consolidated

    def _merge_points(self, points):
        """Merge multiple support points into one"""
        # Calculate weighted centroid (weight by area if available)
        total_weight = 0
        weighted_x, weighted_y, weighted_z = 0, 0, 0

        for p in points:
            weight = p.get('area', 1.0) or 1.0
            weighted_x += p['x'] * weight
            weighted_y += p['y'] * weight
            weighted_z += p['z'] * weight
            total_weight += weight

        merged = {
            'x': weighted_x / total_weight,
            'y': weighted_y / total_weight,
            'z': weighted_z / total_weight,
            'area': sum(p.get('area', 0) for p in points),
            'type': points[0].get('type', 'merged'),
            'merged_count': len(points)
        }

        # Preserve angle if available (use minimum - most critical)
        angles = [p.get('angle') for p in points if p.get('angle') is not None]
        if angles:
            merged['angle'] = min(angles)

        return merged

    def classify_support_tier(self, support_point):
        """
        Classify a support point into light/medium/heavy tier

        Args:
            support_point: Support point dictionary

        Returns:
            'light', 'medium', or 'heavy'
        """
        coord = [support_point['x'], support_point['y'], support_point['z']]
        detail_score = self.get_detail_score_at_point(coord)

        # Get point properties
        area = support_point.get('area', 0)
        angle = support_point.get('angle', 45)  # degrees from horizontal
        point_type = support_point.get('type', '')
        height = support_point['z'] - self.mesh.bounds[0, 2]

        # Decision logic for tier assignment
        # Light: High detail areas, small features, near-vertical surfaces
        # Medium: Standard overhangs, moderate areas
        # Heavy: Large horizontal surfaces, structural areas, islands at low height

        # High detail areas always get light supports
        if detail_score > 0.6:
            return 'light'

        # Near-vertical surfaces (>60 degrees from horizontal) get light supports
        if angle > 60:
            return 'light'

        # Very small areas get light supports
        if area < 2.0:  # mm²
            return 'light'

        # Islands close to build plate need heavy supports
        if point_type == 'island' and height < 5.0:
            return 'heavy'

        # Large horizontal areas need heavy supports
        if angle < 20 and area > 10.0:
            return 'heavy'

        # Bridge supports are structural
        if point_type == 'bridge':
            return 'medium'

        # Default to medium
        return 'medium'

    def assign_support_tiers(self, support_points):
        """
        Assign tier (light/medium/heavy) to each support point

        Args:
            support_points: List of support point dictionaries

        Returns:
            Support points with 'tier' field added
        """
        print("  Assigning support tiers...")

        tier_counts = {'light': 0, 'medium': 0, 'heavy': 0}

        for point in support_points:
            tier = self.classify_support_tier(point)
            point['tier'] = tier
            tier_counts[tier] += 1

        print(f"    Light: {tier_counts['light']}, Medium: {tier_counts['medium']}, Heavy: {tier_counts['heavy']}")
        return support_points

    def adaptive_spacing_filter(self, support_points):
        """
        Apply adaptive spacing based on local density needs

        Reduces support density in areas that don't need it
        """
        if not support_points:
            return support_points

        print("  Applying adaptive spacing filter...")

        # Group points by approximate Z height (layer grouping)
        layer_height = 1.0  # mm grouping
        layers = defaultdict(list)

        for point in support_points:
            layer_idx = int(point['z'] / layer_height)
            layers[layer_idx].append(point)

        filtered_points = []

        for layer_idx, layer_points in layers.items():
            if len(layer_points) <= 1:
                filtered_points.extend(layer_points)
                continue

            # Calculate adaptive spacing for this layer
            coords = np.array([[p['x'], p['y']] for p in layer_points])
            tree = KDTree(coords)

            kept = np.ones(len(layer_points), dtype=bool)

            for i, point in enumerate(layer_points):
                if not kept[i]:
                    continue

                tier = point.get('tier', 'medium')
                detail_score = self.get_detail_score_at_point([point['x'], point['y'], point['z']])

                # Calculate adaptive spacing based on tier and detail
                if tier == 'light' or detail_score > 0.5:
                    # High detail areas - keep supports closer together
                    min_spacing = SupportConfig.EDGE_SUPPORT_SPACING * 0.8
                elif tier == 'heavy':
                    # Structural areas - can space further apart
                    min_spacing = SupportConfig.SUPPORT_SPACING * 1.5
                else:
                    # Medium - use standard spacing
                    min_spacing = SupportConfig.SUPPORT_SPACING

                # Find neighbors within min_spacing
                coord = [point['x'], point['y']]
                neighbors = tree.query_ball_point(coord, min_spacing)

                # Remove redundant neighbors (keep current point, remove others)
                for n in neighbors:
                    if n != i and kept[n]:
                        # Keep the one with higher priority (lower tier or more critical)
                        other_tier = layer_points[n].get('tier', 'medium')
                        tier_priority = {'heavy': 0, 'medium': 1, 'light': 2}

                        if tier_priority.get(other_tier, 1) > tier_priority.get(tier, 1):
                            kept[n] = False

            filtered_points.extend([p for p, k in zip(layer_points, kept) if k])

        print(f"    Filtered to {len(filtered_points)} support points ({100*len(filtered_points)/len(support_points):.1f}%)")
        return filtered_points

    def optimize_support_points(self, support_points):
        """
        Full optimization pipeline for support points

        Args:
            support_points: List of support point dictionaries

        Returns:
            Optimized list of support points
        """
        if not support_points:
            return support_points

        original_count = len(support_points)
        print(f"\nOptimizing {original_count} support points for detail preservation...")

        # Step 1: Consolidate nearby points
        points = self.consolidate_support_points(support_points)

        # Step 2: Assign support tiers
        points = self.assign_support_tiers(points)

        # Step 3: Apply adaptive spacing
        points = self.adaptive_spacing_filter(points)

        final_count = len(points)
        reduction = 100 * (1 - final_count / original_count)
        print(f"  Optimization complete: {original_count} -> {final_count} points ({reduction:.1f}% reduction)")

        return points


def get_support_tip_diameter(tier):
    """
    Get support tip diameter based on tier

    Args:
        tier: 'light', 'medium', or 'heavy'

    Returns:
        Tip diameter in mm
    """
    diameters = {
        'light': 0.2,   # Very small contact for delicate details
        'medium': 0.3,  # Standard contact
        'heavy': 0.4    # Larger contact for structural support
    }
    return diameters.get(tier, 0.3)


def get_support_base_diameter(tier):
    """
    Get support base diameter based on tier

    Args:
        tier: 'light', 'medium', or 'heavy'

    Returns:
        Base diameter in mm
    """
    diameters = {
        'light': 0.6,   # Thinner support
        'medium': 0.8,  # Standard
        'heavy': 1.0    # Thicker for stability
    }
    return diameters.get(tier, 0.8)
