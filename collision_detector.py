"""
Collision detection for support routing
Detects collisions between support paths and the model mesh
"""

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from config import SupportConfig


class CollisionDetector:
    """Detect collisions between support paths and model geometry"""

    def __init__(self, mesh, resolution=None):
        """
        Initialize collision detector

        Args:
            mesh: Trimesh object of the model
            resolution: Resolution for collision checking (mm)
        """
        self.mesh = mesh
        self.resolution = resolution or SupportConfig.COLLISION_RESOLUTION

        # Build spatial index for fast collision queries
        self._build_spatial_index()

    def _build_spatial_index(self):
        """Build KD-tree for fast spatial queries"""
        # Sample points on mesh surface for collision detection
        # Use face centers and vertices
        self.collision_points = []

        # Add all vertices
        self.collision_points.extend(self.mesh.vertices)

        # Add face centers for better coverage
        face_centers = self.mesh.triangles_center
        self.collision_points.extend(face_centers)

        # Convert to numpy array
        self.collision_points = np.array(self.collision_points)

        # Build KD-tree for fast nearest neighbor queries
        self.kdtree = cKDTree(self.collision_points)

        print(f"  Built collision detection index with {len(self.collision_points)} points")

    def check_cylinder_collision(self, start, end, radius):
        """
        Check if a cylindrical support segment collides with the model

        Args:
            start: Start point [x, y, z]
            end: End point [x, y, z]
            radius: Cylinder radius

        Returns:
            bool: True if collision detected
        """
        if not SupportConfig.COLLISION_CHECK_ENABLED:
            return False

        start = np.array(start)
        end = np.array(end)

        # Sample points along the cylinder axis
        direction = end - start
        length = np.linalg.norm(direction)

        if length < 0.001:
            return False

        direction = direction / length

        # Number of samples based on resolution
        num_samples = max(3, int(length / self.resolution))

        for i in range(num_samples):
            t = i / (num_samples - 1)
            point = start + t * direction * length

            # Check if any collision points are within the cylinder radius
            # Add small margin for safety
            collision_radius = radius + self.resolution

            distances, indices = self.kdtree.query(point, k=10)

            for dist in distances:
                if dist < collision_radius:
                    return True

        return False

    def check_path_collision(self, path, radius):
        """
        Check if a path (series of points) collides with the model

        Args:
            path: List of [x, y, z] points
            radius: Path radius

        Returns:
            bool: True if collision detected
        """
        if not SupportConfig.COLLISION_CHECK_ENABLED:
            return False

        if len(path) < 2:
            return False

        # Check each segment
        for i in range(len(path) - 1):
            if self.check_cylinder_collision(path[i], path[i+1], radius):
                return True

        return False

    def get_closest_distance_to_model(self, point):
        """
        Get the closest distance from a point to the model surface

        Args:
            point: [x, y, z] position

        Returns:
            float: Distance to nearest model surface
        """
        point = np.array(point)
        distance, _ = self.kdtree.query(point)
        return distance

    def is_point_inside_model(self, point):
        """
        Check if a point is inside the model volume
        Uses ray casting method

        Args:
            point: [x, y, z] position

        Returns:
            bool: True if point is inside model
        """
        point = np.array(point)

        # Cast a ray in positive Z direction
        ray_origin = point.copy()
        ray_direction = np.array([0, 0, 1])

        # Count intersections
        locations, index_ray, index_tri = self.mesh.ray.intersects_location(
            ray_origins=[ray_origin],
            ray_directions=[ray_direction]
        )

        # Odd number of intersections = inside
        return len(locations) % 2 == 1

    def find_clear_direction(self, point, preferred_direction, radius, search_angles=12):
        """
        Find a clear direction from a point that avoids collisions

        Args:
            point: Starting point [x, y, z]
            preferred_direction: Preferred direction vector
            radius: Support radius
            search_angles: Number of angles to search around preferred direction

        Returns:
            numpy.array: Clear direction vector, or None if no clear path
        """
        point = np.array(point)
        preferred_direction = np.array(preferred_direction)
        preferred_direction = preferred_direction / np.linalg.norm(preferred_direction)

        # Try preferred direction first
        test_point = point + preferred_direction * (self.resolution * 2)
        if not self.check_cylinder_collision(point, test_point, radius):
            return preferred_direction

        # Create a set of test directions around the preferred direction
        # Use spherical coordinates to sample directions
        for angle in np.linspace(0, 2*np.pi, search_angles, endpoint=False):
            # Rotate around Z axis
            cos_a = np.cos(angle)
            sin_a = np.sin(angle)

            # Create rotation matrix around Z axis
            rotation = np.array([
                [cos_a, -sin_a, 0],
                [sin_a, cos_a, 0],
                [0, 0, 1]
            ])

            # Rotate preferred direction
            test_direction = rotation @ preferred_direction
            test_point = point + test_direction * (self.resolution * 2)

            if not self.check_cylinder_collision(point, test_point, radius):
                return test_direction

        # No clear direction found
        return None

    def raycast_to_buildplate(self, start_point, direction=None):
        """
        Raycast from a point toward the build plate

        Args:
            start_point: Starting point [x, y, z]
            direction: Direction vector (default: downward)

        Returns:
            tuple: (hit_point, hit_distance) or (None, None) if no hit
        """
        start_point = np.array(start_point)

        if direction is None:
            direction = np.array([0, 0, -1])  # Downward
        else:
            direction = np.array(direction)
            direction = direction / np.linalg.norm(direction)

        # Cast ray
        locations, index_ray, index_tri = self.mesh.ray.intersects_location(
            ray_origins=[start_point],
            ray_directions=[direction]
        )

        if len(locations) == 0:
            return None, None

        # Find closest intersection
        distances = np.linalg.norm(locations - start_point, axis=1)
        closest_idx = np.argmin(distances)

        return locations[closest_idx], distances[closest_idx]
