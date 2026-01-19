"""
Lattice tower generation
Creates triangular braced lattice towers to consolidate support roots
"""

import numpy as np
import trimesh
from config import SupportConfig
from curved_support import CurvedSupportGenerator


class LatticeTowerGenerator:
    """Generate triangular lattice towers for support consolidation"""

    def __init__(self):
        """Initialize lattice tower generator"""
        self.curved_generator = CurvedSupportGenerator()

    def cluster_support_endpoints(self, support_endpoints, spacing=None):
        """
        Cluster support endpoints into groups for lattice towers
        Subdivides large clusters to prevent mega-towers

        Args:
            support_endpoints: List of [x, y, z] points where supports reach down
            spacing: Maximum spacing for clustering (mm)

        Returns:
            List of clusters, each cluster is a list of point indices
        """
        if spacing is None:
            spacing = SupportConfig.LATTICE_SPACING

        endpoints = [np.array(p) for p in support_endpoints]
        initial_clusters = []
        unclustered = set(range(len(endpoints)))

        # Phase 1: Initial clustering based on spacing
        while unclustered:
            # Start new cluster with first unclustered point
            seed_idx = min(unclustered)
            cluster = [seed_idx]
            unclustered.remove(seed_idx)

            # Find all points within spacing of cluster
            changed = True
            while changed:
                changed = False
                to_add = []

                for idx in unclustered:
                    # Check distance to any point in cluster
                    for cluster_idx in cluster:
                        dist = np.linalg.norm(endpoints[idx][:2] - endpoints[cluster_idx][:2])
                        if dist <= spacing:
                            to_add.append(idx)
                            changed = True
                            break

                for idx in to_add:
                    cluster.append(idx)
                    unclustered.remove(idx)

            initial_clusters.append(cluster)

        # Phase 2: Subdivide oversized clusters
        final_clusters = []
        max_size = SupportConfig.LATTICE_MAX_CLUSTER_SIZE

        for cluster in initial_clusters:
            if len(cluster) <= max_size:
                final_clusters.append(cluster)
            else:
                # Subdivide large cluster using K-means-like approach
                subdivided = self._subdivide_cluster(cluster, endpoints, max_size)
                final_clusters.extend(subdivided)

        return final_clusters

    def _subdivide_cluster(self, cluster, endpoints, max_size):
        """
        Subdivide a large cluster into smaller sub-clusters

        Args:
            cluster: List of point indices
            endpoints: List of all endpoint positions
            max_size: Maximum cluster size

        Returns:
            List of sub-clusters
        """
        cluster_points = [endpoints[i] for i in cluster]

        # Determine number of sub-clusters needed
        num_subclusters = (len(cluster) + max_size - 1) // max_size

        # Use simple spatial subdivision
        # Sort by X coordinate and divide into strips
        sorted_indices = sorted(cluster, key=lambda idx: endpoints[idx][0])

        subclusters = []
        subcluster_size = len(cluster) // num_subclusters

        for i in range(num_subclusters):
            start = i * subcluster_size
            if i == num_subclusters - 1:
                # Last cluster gets remaining points
                end = len(sorted_indices)
            else:
                end = (i + 1) * subcluster_size

            subclusters.append(sorted_indices[start:end])

        return subclusters

    def create_lattice_tower(self, base_points, build_plate_z, tower_height=None):
        """
        Create a triangular lattice tower from multiple support endpoints

        Args:
            base_points: List of [x, y, z] points that need support
            build_plate_z: Z height of build plate
            tower_height: Height of lattice tower (if None, auto-calculate)

        Returns:
            tuple: (tower_mesh, attachment_points)
                tower_mesh: Trimesh of lattice structure
                attachment_points: Dict mapping base_point indices to tower attachment [x,y,z]
        """
        if len(base_points) == 0:
            return None, {}

        base_points = [np.array(p) for p in base_points]

        # Calculate tower parameters
        center = np.mean([p for p in base_points], axis=0)
        center[2] = build_plate_z  # Tower base at build plate

        if tower_height is None:
            # Tower height based on highest support point
            max_z = max(p[2] for p in base_points)
            tower_height = max_z - build_plate_z

        # For single or two points, create simple vertical supports
        if len(base_points) <= 2:
            return self._create_simple_tower(base_points, build_plate_z)

        # Create triangular lattice tower
        # Find three vertices that form largest triangle for tower base
        tower_base = self._find_tower_base_triangle(base_points, center[:2])

        # Create main vertical columns at tower vertices
        meshes = []
        attachment_points = {}

        # Main vertical columns
        main_radius = SupportConfig.LATTICE_MAIN_DIAMETER / 2
        strut_radius = SupportConfig.LATTICE_STRUT_DIAMETER / 2

        tower_top_z = build_plate_z + tower_height
        tower_vertices = []

        for vertex_xy in tower_base:
            bottom = np.array([vertex_xy[0], vertex_xy[1], build_plate_z])
            top = np.array([vertex_xy[0], vertex_xy[1], tower_top_z])
            tower_vertices.append((bottom, top))

            # Create vertical column
            column = self.curved_generator.create_straight_segment(
                bottom, top, main_radius, main_radius
            )
            if column is not None:
                meshes.append(column)

        # Horizontal bracing at multiple heights
        num_levels = max(3, int(tower_height / 10.0))
        for level in range(num_levels + 1):
            z = build_plate_z + (level / num_levels) * tower_height

            # Create horizontal triangle connecting vertices
            level_points = []
            for vertex_xy in tower_base:
                level_points.append(np.array([vertex_xy[0], vertex_xy[1], z]))

            # Connect triangle edges
            for i in range(3):
                start = level_points[i]
                end = level_points[(i + 1) % 3]

                strut = self.curved_generator.create_straight_segment(
                    start, end, strut_radius, strut_radius
                )
                if strut is not None:
                    meshes.append(strut)

        # Diagonal bracing
        brace_angle = SupportConfig.LATTICE_BRACE_ANGLE
        for level in range(num_levels):
            z_bottom = build_plate_z + (level / num_levels) * tower_height
            z_top = build_plate_z + ((level + 1) / num_levels) * tower_height

            # Diagonal braces between levels
            for i in range(3):
                # Bottom vertex to top adjacent vertex
                bottom_xy = tower_base[i]
                top_xy = tower_base[(i + 1) % 3]

                start = np.array([bottom_xy[0], bottom_xy[1], z_bottom])
                end = np.array([top_xy[0], top_xy[1], z_top])

                brace = self.curved_generator.create_straight_segment(
                    start, end, strut_radius, strut_radius
                )
                if brace is not None:
                    meshes.append(brace)

        # Attachment points for supports to connect to tower
        # Distribute base points around tower top
        tower_top_center = center.copy()
        tower_top_center[2] = tower_top_z

        for i, base_point in enumerate(base_points):
            # Find closest tower vertex
            min_dist = float('inf')
            closest_vertex = None

            for vertex_xy in tower_base:
                vertex_3d = np.array([vertex_xy[0], vertex_xy[1], tower_top_z])
                dist = np.linalg.norm(base_point[:2] - vertex_xy)
                if dist < min_dist:
                    min_dist = dist
                    closest_vertex = vertex_3d

            attachment_points[i] = closest_vertex

        # Combine all tower components
        if meshes:
            tower_mesh = trimesh.util.concatenate(meshes)
            return tower_mesh, attachment_points
        else:
            return None, {}

    def _find_tower_base_triangle(self, points, center):
        """
        Find three points that form a good triangle for tower base

        Args:
            points: List of points
            center: Center point [x, y]

        Returns:
            List of three [x, y] vertices
        """
        points_2d = [p[:2] for p in points]

        # If 3 or fewer points, use them directly
        if len(points_2d) <= 3:
            # Create equilateral triangle around center
            radius = 2.0  # 2mm radius
            vertices = []
            for i in range(3):
                angle = 2 * np.pi * i / 3
                x = center[0] + radius * np.cos(angle)
                y = center[1] + radius * np.sin(angle)
                vertices.append([x, y])
            return vertices

        # Find convex hull
        from scipy.spatial import ConvexHull

        try:
            hull = ConvexHull(points_2d)
            hull_points = [points_2d[i] for i in hull.vertices]

            if len(hull_points) >= 3:
                # Find three points with maximum spread
                max_area = 0
                best_triangle = None

                for i in range(len(hull_points)):
                    for j in range(i+1, len(hull_points)):
                        for k in range(j+1, len(hull_points)):
                            p1 = np.array(hull_points[i])
                            p2 = np.array(hull_points[j])
                            p3 = np.array(hull_points[k])

                            # Calculate triangle area
                            area = 0.5 * abs(
                                (p2[0] - p1[0]) * (p3[1] - p1[1]) -
                                (p3[0] - p1[0]) * (p2[1] - p1[1])
                            )

                            if area > max_area:
                                max_area = area
                                best_triangle = [p1.tolist(), p2.tolist(), p3.tolist()]

                if best_triangle:
                    return best_triangle

        except Exception:
            pass

        # Fallback: equilateral triangle
        radius = 3.0
        vertices = []
        for i in range(3):
            angle = 2 * np.pi * i / 3
            x = center[0] + radius * np.cos(angle)
            y = center[1] + radius * np.sin(angle)
            vertices.append([x, y])
        return vertices

    def _create_simple_tower(self, base_points, build_plate_z):
        """
        Create simple vertical supports for 1-2 points

        Args:
            base_points: List of support endpoints
            build_plate_z: Build plate Z

        Returns:
            tuple: (tower_mesh, attachment_points)
        """
        meshes = []
        attachment_points = {}
        radius = SupportConfig.LATTICE_MAIN_DIAMETER / 2

        for i, point in enumerate(base_points):
            point = np.array(point)
            bottom = point.copy()
            bottom[2] = build_plate_z

            support = self.curved_generator.create_straight_segment(
                bottom, point, radius, radius
            )

            if support is not None:
                meshes.append(support)

            # Attachment point is the top of the support
            attachment_points[i] = point.tolist()

        if meshes:
            tower_mesh = trimesh.util.concatenate(meshes)
            return tower_mesh, attachment_points
        else:
            return None, {}

    def consolidate_supports_with_towers(self, support_paths, build_plate_z):
        """
        Consolidate multiple support paths using lattice towers

        Args:
            support_paths: List of support paths (each path is list of points)
            build_plate_z: Z height of build plate

        Returns:
            tuple: (tower_meshes, modified_paths)
                tower_meshes: List of lattice tower meshes
                modified_paths: List of modified support paths that connect to towers
        """
        if not SupportConfig.LATTICE_TOWER_ENABLED:
            return [], support_paths

        # Extract endpoints (lowest points of each support)
        endpoints = []
        for path in support_paths:
            if len(path) > 0:
                # Find point with lowest Z
                lowest = min(path, key=lambda p: p[2])
                endpoints.append(lowest)

        if len(endpoints) < SupportConfig.LATTICE_MIN_CLUSTER_SIZE:
            # Not enough supports to warrant towers
            return [], support_paths

        # Cluster endpoints
        clusters = self.cluster_support_endpoints(endpoints)

        print(f"    Clustered {len(endpoints)} endpoints into {len(clusters)} clusters")
        for i, cluster in enumerate(clusters):
            if len(cluster) >= SupportConfig.LATTICE_MIN_CLUSTER_SIZE:
                print(f"    Cluster {i}: {len(cluster)} supports -> creating tower")
            else:
                print(f"    Cluster {i}: {len(cluster)} supports -> too small, using individual supports")

        tower_meshes = []
        modified_paths = []

        # Track which supports belong to which tower
        support_to_cluster = {}
        for cluster_idx, cluster in enumerate(clusters):
            for support_idx in cluster:
                support_to_cluster[support_idx] = cluster_idx

        # Create towers for each cluster
        cluster_towers = {}
        for cluster_idx, cluster in enumerate(clusters):
            if len(cluster) < SupportConfig.LATTICE_MIN_CLUSTER_SIZE:
                # Too few supports for tower
                continue

            cluster_endpoints = [endpoints[i] for i in cluster]

            tower_mesh, attachment_points = self.create_lattice_tower(
                cluster_endpoints, build_plate_z
            )

            if tower_mesh is not None:
                tower_meshes.append(tower_mesh)
                cluster_towers[cluster_idx] = attachment_points

        # Modify support paths to connect to towers
        for support_idx, path in enumerate(support_paths):
            if support_idx in support_to_cluster:
                cluster_idx = support_to_cluster[support_idx]

                if cluster_idx in cluster_towers:
                    # Get attachment point on tower
                    cluster = clusters[cluster_idx]
                    local_idx = cluster.index(support_idx)
                    attachment_point = cluster_towers[cluster_idx][local_idx]

                    # Modify path to end at attachment point instead of build plate
                    modified_path = path.copy()
                    # Replace lowest point with attachment point
                    if len(modified_path) > 0:
                        modified_path[-1] = attachment_point
                    modified_paths.append(modified_path)
                else:
                    modified_paths.append(path)
            else:
                modified_paths.append(path)

        return tower_meshes, modified_paths
