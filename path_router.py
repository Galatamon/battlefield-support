"""
Path routing for support structures
Routes supports around model obstacles using RRT-based pathfinding
"""

import numpy as np
from config import SupportConfig
import heapq


class PathRouter:
    """Route support paths around model obstacles"""

    def __init__(self, collision_detector, build_plate_z):
        """
        Initialize path router

        Args:
            collision_detector: CollisionDetector instance
            build_plate_z: Z-height of build plate
        """
        self.collision_detector = collision_detector
        self.build_plate_z = build_plate_z
        self.step_size = SupportConfig.ROUTING_STEP_SIZE

    def route_support_path(self, start_point, target_z=None, radius=0.5, max_iterations=500):
        """
        Route a support path from start point to build plate or target Z

        Uses RRT (Rapidly-exploring Random Tree) with bias toward goal

        Args:
            start_point: Starting point [x, y, z] (contact with model)
            target_z: Target Z height (default: build plate)
            radius: Support radius for collision checking
            max_iterations: Maximum pathfinding iterations

        Returns:
            list: Path as list of [x, y, z] points, or None if no path found
        """
        if not SupportConfig.LATERAL_ROUTING_ENABLED:
            # Simple straight-down path if routing disabled
            return self._straight_path(start_point, target_z)

        start_point = np.array(start_point, dtype=float)
        if target_z is None:
            target_z = self.build_plate_z

        # If start point is already at or below target, return simple path
        if start_point[2] <= target_z:
            return [start_point.tolist()]

        # Initialize RRT tree
        tree = RRTTree(start_point)

        # Goal region: any point at target_z
        goal_reached = False
        best_node = None

        for iteration in range(max_iterations):
            # Sample random point with bias toward goal
            if np.random.random() < 0.3:  # 30% bias toward goal
                # Sample point directly below current position
                sample = start_point.copy()
                sample[2] = np.random.uniform(target_z, start_point[2])
            else:
                # Random sample in reachable space
                sample = self._sample_random_point(start_point, target_z)

            # Find nearest node in tree
            nearest_node = tree.nearest(sample)

            # Steer toward sample
            new_point = self._steer(nearest_node.point, sample, self.step_size)

            # Check constraints: max angle and collision
            if not self._check_routing_constraints(nearest_node.point, new_point, radius):
                continue

            # Add to tree
            new_node = tree.add_node(new_point, nearest_node)

            # Check if we reached target Z
            if new_point[2] <= target_z + self.step_size:
                # Reached goal region
                goal_reached = True
                best_node = new_node
                break

            # Track best node (closest to target Z)
            if best_node is None or new_point[2] < best_node.point[2]:
                best_node = new_node

        # Extract path
        if goal_reached:
            path = tree.extract_path(best_node)
            # Ensure final point is exactly at target Z
            final_point = path[-1].copy()
            final_point[2] = target_z
            path.append(final_point)
            return path
        elif best_node is not None:
            # Partial path - extend straight down from best node
            path = tree.extract_path(best_node)
            final_point = path[-1].copy()
            final_point[2] = target_z
            path.append(final_point)
            return path
        else:
            # Fallback to straight path
            print(f"    Warning: Could not find routed path, using straight fallback")
            return self._straight_path(start_point, target_z)

    def _straight_path(self, start_point, target_z=None):
        """Create a simple straight-down path"""
        start_point = np.array(start_point)
        if target_z is None:
            target_z = self.build_plate_z

        end_point = start_point.copy()
        end_point[2] = target_z

        return [start_point.tolist(), end_point.tolist()]

    def _sample_random_point(self, start_point, target_z):
        """Sample a random point in the reachable space"""
        # Sample within a cone below the start point
        z_height = start_point[2] - target_z
        max_lateral = z_height * np.tan(np.radians(SupportConfig.MAX_ROUTING_ANGLE))

        # Random point within cylinder
        angle = np.random.uniform(0, 2*np.pi)
        radius = np.random.uniform(0, max_lateral)
        z = np.random.uniform(target_z, start_point[2])

        x = start_point[0] + radius * np.cos(angle)
        y = start_point[1] + radius * np.sin(angle)

        return np.array([x, y, z])

    def _steer(self, from_point, to_point, max_distance):
        """Steer from one point toward another with max distance"""
        from_point = np.array(from_point)
        to_point = np.array(to_point)

        direction = to_point - from_point
        distance = np.linalg.norm(direction)

        if distance <= max_distance:
            return to_point

        # Limit to max_distance
        direction = direction / distance
        return from_point + direction * max_distance

    def _check_routing_constraints(self, from_point, to_point, radius):
        """
        Check if a routing segment satisfies all constraints

        Args:
            from_point: Start point
            to_point: End point
            radius: Support radius

        Returns:
            bool: True if segment is valid
        """
        from_point = np.array(from_point)
        to_point = np.array(to_point)

        # Check 1: Must be generally downward
        if to_point[2] > from_point[2]:
            return False

        # Check 2: Angle constraint
        direction = to_point - from_point
        distance = np.linalg.norm(direction)

        if distance < 0.001:
            return False

        # Calculate angle from vertical
        vertical = np.array([0, 0, -1])
        angle = np.degrees(np.arccos(np.clip(np.dot(direction / distance, vertical), -1, 1)))

        if angle > SupportConfig.MAX_ROUTING_ANGLE:
            return False

        # Check 3: Collision with model
        if self.collision_detector.check_cylinder_collision(from_point, to_point, radius):
            return False

        return True

    def smooth_path(self, path, radius, iterations=3):
        """
        Smooth a path by removing unnecessary waypoints

        Args:
            path: List of [x, y, z] points
            radius: Support radius
            iterations: Number of smoothing iterations

        Returns:
            list: Smoothed path
        """
        if len(path) <= 2:
            return path

        smoothed = path.copy()

        for _ in range(iterations):
            i = 0
            while i < len(smoothed) - 2:
                # Try to connect point i directly to point i+2
                if not self.collision_detector.check_cylinder_collision(
                    smoothed[i], smoothed[i+2], radius
                ):
                    # Can skip point i+1
                    smoothed.pop(i+1)
                else:
                    i += 1

        return smoothed

    def calculate_path_cost(self, path):
        """
        Calculate the cost of a path (length + bending penalty)

        Args:
            path: List of [x, y, z] points

        Returns:
            float: Path cost
        """
        if len(path) < 2:
            return 0.0

        total_cost = 0.0
        prev_direction = None

        for i in range(len(path) - 1):
            segment = np.array(path[i+1]) - np.array(path[i])
            length = np.linalg.norm(segment)
            total_cost += length

            # Add penalty for direction changes
            if prev_direction is not None:
                direction = segment / (length + 1e-6)
                angle = np.degrees(np.arccos(np.clip(np.dot(direction, prev_direction), -1, 1)))
                total_cost += angle * 0.1  # Penalty for bending

            prev_direction = segment / (length + 1e-6)

        return total_cost


class RRTTree:
    """Simple RRT tree structure for pathfinding"""

    def __init__(self, root_point):
        """Initialize tree with root node"""
        self.root = RRTNode(root_point)
        self.nodes = [self.root]

    def add_node(self, point, parent):
        """Add a new node to the tree"""
        node = RRTNode(point, parent)
        self.nodes.append(node)
        return node

    def nearest(self, point):
        """Find nearest node to a point"""
        point = np.array(point)
        min_dist = float('inf')
        nearest_node = None

        for node in self.nodes:
            dist = np.linalg.norm(node.point - point)
            if dist < min_dist:
                min_dist = dist
                nearest_node = node

        return nearest_node

    def extract_path(self, node):
        """Extract path from root to node"""
        path = []
        current = node

        while current is not None:
            path.append(current.point.tolist())
            current = current.parent

        path.reverse()
        return path


class RRTNode:
    """Node in RRT tree"""

    def __init__(self, point, parent=None):
        """Initialize node"""
        self.point = np.array(point, dtype=float)
        self.parent = parent
