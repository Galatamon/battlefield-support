"""
Curved support generation
Creates 3D geometry for curved/bent support structures that follow paths
"""

import numpy as np
import trimesh
from config import SupportConfig


class CurvedSupportGenerator:
    """Generate curved support structures along paths"""

    def __init__(self):
        """Initialize curved support generator"""
        self.segments_per_mm = 2  # Resolution of curve
        self.radial_segments = 12  # Number of sides in cylinder

    def create_curved_support(self, path, tip_radius, base_radius=None):
        """
        Create a curved support following a path

        Args:
            path: List of [x, y, z] waypoints
            tip_radius: Radius at tip (top, contacts model)
            base_radius: Radius at base (bottom, on build plate). If None, uses tip_radius

        Returns:
            Trimesh object of curved support
        """
        if len(path) < 2:
            return None

        if base_radius is None:
            base_radius = tip_radius

        # Ensure path is numpy array
        path = [np.array(p, dtype=float) for p in path]

        # Interpolate path for smooth curve
        interpolated_path = self._interpolate_path(path)

        if len(interpolated_path) < 2:
            return None

        # Calculate radius at each point (taper from tip to base)
        total_length = self._path_length(interpolated_path)
        radii = []
        current_length = 0.0

        for i in range(len(interpolated_path)):
            if i > 0:
                segment_length = np.linalg.norm(
                    interpolated_path[i] - interpolated_path[i-1]
                )
                current_length += segment_length

            # Interpolate radius based on distance along path
            t = current_length / total_length if total_length > 0 else 0
            radius = tip_radius + t * (base_radius - tip_radius)
            radii.append(radius)

        # Create mesh by sweeping circle along path
        mesh = self._sweep_circle_along_path(interpolated_path, radii)

        return mesh

    def _interpolate_path(self, path):
        """
        Interpolate path with more points for smooth curves

        Args:
            path: List of waypoints

        Returns:
            List of interpolated points
        """
        if len(path) < 2:
            return path

        interpolated = [path[0]]

        for i in range(len(path) - 1):
            start = path[i]
            end = path[i + 1]
            segment_length = np.linalg.norm(end - start)

            # Number of interpolation points
            num_points = max(2, int(segment_length * self.segments_per_mm))

            for j in range(1, num_points + 1):
                t = j / num_points
                point = start + t * (end - start)
                interpolated.append(point)

        return interpolated

    def _path_length(self, path):
        """Calculate total path length"""
        length = 0.0
        for i in range(len(path) - 1):
            length += np.linalg.norm(path[i+1] - path[i])
        return length

    def _sweep_circle_along_path(self, path, radii):
        """
        Create mesh by sweeping circle along path with varying radius

        Args:
            path: List of [x, y, z] points along centerline
            radii: List of radii at each point

        Returns:
            Trimesh object
        """
        if len(path) < 2 or len(radii) != len(path):
            return None

        vertices = []
        faces = []

        # For each point along path, create a circle perpendicular to path direction
        for i, (center, radius) in enumerate(zip(path, radii)):
            # Calculate local coordinate system
            if i == 0:
                # First point: use direction to next point
                direction = path[i+1] - path[i]
            elif i == len(path) - 1:
                # Last point: use direction from previous point
                direction = path[i] - path[i-1]
            else:
                # Middle points: average of directions
                dir1 = path[i] - path[i-1]
                dir2 = path[i+1] - path[i]
                direction = dir1 + dir2

            direction = direction / (np.linalg.norm(direction) + 1e-6)

            # Create perpendicular vectors for circle plane
            # Find a vector perpendicular to direction
            if abs(direction[2]) < 0.9:
                up = np.array([0, 0, 1])
            else:
                up = np.array([1, 0, 0])

            right = np.cross(direction, up)
            right = right / (np.linalg.norm(right) + 1e-6)

            up = np.cross(right, direction)
            up = up / (np.linalg.norm(up) + 1e-6)

            # Create circle vertices
            circle_vertices = []
            for j in range(self.radial_segments):
                angle = 2 * np.pi * j / self.radial_segments
                offset = radius * (np.cos(angle) * right + np.sin(angle) * up)
                vertex = center + offset
                circle_vertices.append(vertex)

            # Add vertices to list
            vertex_start_idx = len(vertices)
            vertices.extend(circle_vertices)

            # Create faces connecting to previous circle
            if i > 0:
                prev_start = vertex_start_idx - self.radial_segments
                curr_start = vertex_start_idx

                for j in range(self.radial_segments):
                    next_j = (j + 1) % self.radial_segments

                    # Two triangles per quad
                    # Triangle 1
                    faces.append([
                        prev_start + j,
                        curr_start + j,
                        prev_start + next_j
                    ])

                    # Triangle 2
                    faces.append([
                        curr_start + j,
                        curr_start + next_j,
                        prev_start + next_j
                    ])

        # Add caps at both ends
        if len(vertices) >= self.radial_segments * 2:
            # Bottom cap
            bottom_center_idx = len(vertices)
            vertices.append(path[0])

            for j in range(self.radial_segments):
                next_j = (j + 1) % self.radial_segments
                faces.append([bottom_center_idx, next_j, j])

            # Top cap
            top_center_idx = len(vertices)
            vertices.append(path[-1])

            top_start = len(vertices) - self.radial_segments - 2

            for j in range(self.radial_segments):
                next_j = (j + 1) % self.radial_segments
                faces.append([
                    top_center_idx,
                    top_start + j,
                    top_start + next_j
                ])

        # Create mesh
        if len(vertices) < 3 or len(faces) < 1:
            return None

        vertices = np.array(vertices)
        faces = np.array(faces)

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Fix normals
        mesh.fix_normals()

        return mesh

    def create_straight_segment(self, start, end, radius_start, radius_end):
        """
        Create a simple straight tapered segment

        Args:
            start: Start point [x, y, z]
            end: End point [x, y, z]
            radius_start: Radius at start
            radius_end: Radius at end

        Returns:
            Trimesh object
        """
        start = np.array(start)
        end = np.array(end)

        # Simple path with just two points
        path = [start, end]
        radii = [radius_start, radius_end]

        return self._sweep_circle_along_path(path, radii)

    def create_branching_support(self, trunk_path, branch_points, tip_radius, base_radius):
        """
        Create a support with multiple branches from a main trunk

        Args:
            trunk_path: Main trunk path (to build plate)
            branch_points: List of (branch_start, branch_end) tuples
            tip_radius: Radius at branch tips
            base_radius: Radius at trunk base

        Returns:
            Trimesh object combining trunk and branches
        """
        meshes = []

        # Create main trunk
        trunk_mesh = self.create_curved_support(trunk_path, tip_radius, base_radius)
        if trunk_mesh is not None:
            meshes.append(trunk_mesh)

        # Create branches
        for branch_start, branch_end in branch_points:
            branch_path = [branch_start, branch_end]
            branch_mesh = self.create_curved_support(branch_path, tip_radius, tip_radius)
            if branch_mesh is not None:
                meshes.append(branch_mesh)

        # Combine all meshes
        if len(meshes) > 0:
            return trimesh.util.concatenate(meshes)
        else:
            return None
