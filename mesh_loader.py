"""
Mesh loading and analysis utilities
"""

import numpy as np
import trimesh
from config import AnalysisConfig


class MeshLoader:
    """Load and prepare STL meshes for analysis"""

    def __init__(self, config=None):
        self.config = config or {}
        self.mesh = None
        self.original_mesh = None

    def load(self, filepath):
        """Load an STL file and prepare it for analysis"""
        print(f"Loading mesh from {filepath}...")

        # Load the mesh
        self.mesh = trimesh.load(filepath, force='mesh')
        self.original_mesh = self.mesh.copy()

        # Basic validation
        if not isinstance(self.mesh, trimesh.Trimesh):
            raise ValueError("File does not contain a valid mesh")

        print(f"  Loaded mesh: {len(self.mesh.vertices)} vertices, {len(self.mesh.faces)} faces")

        # Repair mesh if configured
        if AnalysisConfig.MESH_REPAIR:
            self._repair_mesh()

        return self.mesh

    def _repair_mesh(self):
        """Attempt to repair common mesh issues"""
        print("  Checking mesh integrity...")

        # Check if mesh is watertight
        if not self.mesh.is_watertight:
            print("    Warning: Mesh is not watertight, attempting repair...")
            trimesh.repair.fix_normals(self.mesh)
            trimesh.repair.fix_inversion(self.mesh)

            # Fill holes if any
            if not self.mesh.is_watertight:
                self.mesh.fill_holes()

            if self.mesh.is_watertight:
                print("    Mesh repaired successfully")
            else:
                print("    Warning: Could not fully repair mesh, results may be suboptimal")

        # Remove degenerate faces
        self.mesh.remove_degenerate_faces()

        # Merge close vertices
        self.mesh.merge_vertices()

        # Ensure correct winding
        self.mesh.fix_normals()

        print(f"    Final mesh: {len(self.mesh.vertices)} vertices, {len(self.mesh.faces)} faces")

    def get_bounds(self):
        """Get mesh bounding box"""
        return self.mesh.bounds

    def get_dimensions(self):
        """Get mesh dimensions (x, y, z)"""
        bounds = self.mesh.bounds
        return bounds[1] - bounds[0]

    def get_volume(self):
        """Get mesh volume in mm³"""
        return self.mesh.volume

    def get_surface_area(self):
        """Get mesh surface area in mm²"""
        return self.mesh.area

    def center_on_build_plate(self):
        """Center the mesh on the XY plane at Z=0"""
        # Move to origin
        self.mesh.apply_translation(-self.mesh.centroid)

        # Place bottom on Z=0
        min_z = self.mesh.bounds[0, 2]
        self.mesh.apply_translation([0, 0, -min_z])

        print(f"  Centered mesh at origin, bottom at Z=0")

    def transform(self, matrix):
        """Apply transformation matrix to mesh"""
        self.mesh.apply_transform(matrix)

    def export(self, filepath):
        """Export mesh to STL file"""
        self.mesh.export(filepath)
        print(f"Exported mesh to {filepath}")


class MeshAnalyzer:
    """Analyze mesh geometry for support generation"""

    def __init__(self, mesh):
        self.mesh = mesh

    def get_overhang_faces(self, max_angle=45.0):
        """
        Find faces that exceed the maximum overhang angle

        Args:
            max_angle: Maximum angle from vertical (degrees)

        Returns:
            Array of face indices that need support
        """
        # Get face normals
        normals = self.mesh.face_normals

        # Calculate angle from vertical (Z-axis)
        # Vertical up is [0, 0, 1]
        # Angle from vertical is arccos(dot(normal, [0,0,1]))
        vertical = np.array([0, 0, 1])
        dot_products = np.dot(normals, vertical)

        # Clip to valid range for arccos
        dot_products = np.clip(dot_products, -1.0, 1.0)

        # Calculate angles in degrees
        angles = np.degrees(np.arccos(dot_products))

        # Find overhanging faces (angle > max_angle from vertical)
        # Faces pointing down (angle > 90) definitely need support
        # Faces with angle > max_angle also need support
        overhang_faces = angles > max_angle

        # Only consider downward-facing components
        # (normals with negative Z component)
        downward_faces = normals[:, 2] < 0

        return np.where(overhang_faces & downward_faces)[0]

    def get_face_centers(self, face_indices=None):
        """Get centers of specified faces (or all faces)"""
        if face_indices is None:
            face_indices = np.arange(len(self.mesh.faces))

        vertices = self.mesh.vertices
        faces = self.mesh.faces[face_indices]

        # Calculate center of each face
        centers = np.mean(vertices[faces], axis=1)

        return centers

    def get_bottom_faces(self, z_threshold=None):
        """
        Get faces on or near the bottom of the mesh

        Args:
            z_threshold: Z height threshold (default: 10% of model height)

        Returns:
            Array of face indices on the bottom
        """
        if z_threshold is None:
            height = self.mesh.bounds[1, 2] - self.mesh.bounds[0, 2]
            z_threshold = self.mesh.bounds[0, 2] + height * 0.1

        face_centers = self.get_face_centers()
        bottom_faces = face_centers[:, 2] <= z_threshold

        return np.where(bottom_faces)[0]

    def sample_points_on_surface(self, count=1000):
        """
        Sample random points on the mesh surface

        Args:
            count: Number of points to sample

        Returns:
            Array of 3D points on the surface
        """
        points, face_indices = trimesh.sample.sample_surface(self.mesh, count)
        return points

    def raycast_down(self, points):
        """
        Raycast downward from points to find intersections with mesh

        Args:
            points: Array of 3D points to cast from

        Returns:
            Array of Z-distances to first hit (or None if no hit)
        """
        # Cast rays downward (-Z direction)
        ray_directions = np.tile([0, 0, -1], (len(points), 1))

        # Perform raycasting
        locations, index_ray, index_tri = self.mesh.ray.intersects_location(
            ray_origins=points,
            ray_directions=ray_directions
        )

        # Calculate distances
        distances = np.full(len(points), None)
        for i, ray_idx in enumerate(index_ray):
            if distances[ray_idx] is None:
                distances[ray_idx] = points[ray_idx, 2] - locations[i, 2]

        return distances
