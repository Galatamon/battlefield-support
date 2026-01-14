"""
Island detection through layer-by-layer slicing
Islands are regions that appear in a layer without connection to previous layers
"""

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.ops import unary_union
import trimesh
from config import AnalysisConfig, SupportConfig


class IslandDetector:
    """Detect islands in a mesh through layer-by-layer analysis"""

    def __init__(self, mesh, layer_height=None):
        self.mesh = mesh
        self.layer_height = layer_height or AnalysisConfig.SLICE_LAYER_HEIGHT
        self.layers = []
        self.islands = []

    def detect_islands(self):
        """
        Detect all islands in the mesh

        Returns:
            List of island support points (x, y, z, area)
        """
        print("Detecting islands through layer slicing...")

        # Get mesh bounds
        min_z = self.mesh.bounds[0, 2]
        max_z = self.mesh.bounds[1, 2]

        # Generate slice heights
        num_layers = int(np.ceil((max_z - min_z) / self.layer_height))
        slice_heights = np.linspace(min_z + self.layer_height, max_z, num_layers)

        print(f"  Slicing {num_layers} layers at {self.layer_height}mm height...")

        # Slice the mesh
        self.layers = []
        prev_polygons = []

        islands_found = []

        for i, z in enumerate(slice_heights):
            # Slice mesh at this height
            slice_2d = self.mesh.section(plane_origin=[0, 0, z],
                                          plane_normal=[0, 0, 1])

            if slice_2d is None:
                # No geometry at this layer
                current_polygons = []
            else:
                # Convert to 2D polygons
                current_polygons = self._extract_polygons(slice_2d)

            # Detect islands by comparing with previous layer
            if i > 0 and current_polygons:
                layer_islands = self._find_layer_islands(
                    current_polygons, prev_polygons, z
                )
                islands_found.extend(layer_islands)

            self.layers.append({
                'z': z,
                'polygons': current_polygons,
                'islands': len(islands_found) if i > 0 else 0
            })

            prev_polygons = current_polygons

            if (i + 1) % 50 == 0:
                print(f"    Processed {i+1}/{num_layers} layers, found {len(islands_found)} islands so far...")

        self.islands = islands_found
        print(f"  Found {len(self.islands)} total islands requiring support")

        return self.islands

    def _extract_polygons(self, slice_2d):
        """
        Extract 2D polygons from a mesh slice

        Args:
            slice_2d: 2D slice from trimesh

        Returns:
            List of Shapely polygons
        """
        polygons = []

        try:
            # Get the 2D path
            if hasattr(slice_2d, 'polygons_full'):
                # Multiple polygons
                for polygon_data in slice_2d.polygons_full:
                    shell = polygon_data.exterior.coords
                    holes = [interior.coords for interior in polygon_data.interiors]
                    poly = Polygon(shell, holes)

                    if poly.is_valid and poly.area >= SupportConfig.MIN_ISLAND_AREA:
                        polygons.append(poly)

            elif hasattr(slice_2d, 'vertices'):
                # Single path - try to create polygons from the vertices
                vertices_2d = slice_2d.vertices[:, :2]  # XY coordinates

                if len(vertices_2d) >= 3:
                    try:
                        poly = Polygon(vertices_2d)
                        if poly.is_valid and poly.area >= SupportConfig.MIN_ISLAND_AREA:
                            polygons.append(poly)
                    except:
                        pass

        except Exception as e:
            # Failed to extract polygons - skip this slice
            pass

        return polygons

    def _find_layer_islands(self, current_polygons, prev_polygons, z_height):
        """
        Find islands in current layer by checking connectivity to previous layer

        An island is a polygon that doesn't overlap with any polygon from the previous layer

        Args:
            current_polygons: List of Shapely polygons in current layer
            prev_polygons: List of Shapely polygons in previous layer
            z_height: Z height of current layer

        Returns:
            List of island support points
        """
        islands = []

        if not prev_polygons:
            # If no previous layer, all polygons are islands
            # (except the first layer which sits on build plate)
            if z_height > self.mesh.bounds[0, 2] + self.layer_height * 2:
                for poly in current_polygons:
                    island_info = self._create_island_support(poly, z_height)
                    if island_info:
                        islands.append(island_info)
            return islands

        # Create union of all previous polygons for faster checking
        try:
            prev_union = unary_union(prev_polygons)
        except:
            # If union fails, check against each polygon individually
            prev_union = None

        for poly in current_polygons:
            # Check if this polygon overlaps with previous layer
            is_island = False

            if prev_union is not None:
                # Use union for efficient checking
                # Allow small tolerance for connection
                buffered_prev = prev_union.buffer(AnalysisConfig.ISLAND_CONNECTION_TOLERANCE)
                if not poly.intersects(buffered_prev):
                    is_island = True
            else:
                # Check against each previous polygon
                connected = False
                for prev_poly in prev_polygons:
                    buffered_prev = prev_poly.buffer(AnalysisConfig.ISLAND_CONNECTION_TOLERANCE)
                    if poly.intersects(buffered_prev):
                        connected = True
                        break
                if not connected:
                    is_island = True

            if is_island:
                island_info = self._create_island_support(poly, z_height)
                if island_info:
                    islands.append(island_info)

        return islands

    def _create_island_support(self, polygon, z_height):
        """
        Create support point information for an island

        Args:
            polygon: Shapely polygon representing the island
            z_height: Z height of the island

        Returns:
            Dictionary with support point information
        """
        # Calculate area
        area = polygon.area

        # Skip if area is too small
        if area < SupportConfig.MIN_ISLAND_AREA:
            return None

        # Calculate centroid for support placement
        centroid = polygon.centroid

        # Calculate number of supports needed based on area
        # One support per SUPPORT_SPACING^2 area
        support_area_coverage = SupportConfig.SUPPORT_SPACING ** 2
        num_supports = max(1, int(np.ceil(area / support_area_coverage)))

        # For small islands, just use centroid
        if num_supports == 1:
            return {
                'x': centroid.x,
                'y': centroid.y,
                'z': z_height,
                'area': area,
                'type': 'island',
                'polygon': polygon
            }

        # For larger islands, distribute supports
        # Sample points within the polygon
        supports = []
        minx, miny, maxx, maxy = polygon.bounds

        # Grid-based sampling within bounds
        grid_size = int(np.ceil(np.sqrt(num_supports)))
        x_samples = np.linspace(minx, maxx, grid_size + 2)[1:-1]
        y_samples = np.linspace(miny, maxy, grid_size + 2)[1:-1]

        for x in x_samples:
            for y in y_samples:
                point = Point(x, y)
                if polygon.contains(point):
                    supports.append({
                        'x': x,
                        'y': y,
                        'z': z_height,
                        'area': area / num_supports,
                        'type': 'island',
                        'polygon': polygon
                    })

                if len(supports) >= num_supports:
                    break
            if len(supports) >= num_supports:
                break

        # If we didn't get enough points, add centroid
        if not supports:
            supports.append({
                'x': centroid.x,
                'y': centroid.y,
                'z': z_height,
                'area': area,
                'type': 'island',
                'polygon': polygon
            })

        return supports if len(supports) > 1 else supports[0]

    def get_island_summary(self):
        """Get summary statistics about detected islands"""
        if not self.islands:
            return "No islands detected"

        total = len(self.islands)
        total_area = sum(island['area'] for island in self.islands)
        z_range = (
            min(island['z'] for island in self.islands),
            max(island['z'] for island in self.islands)
        )

        return f"""Island Detection Summary:
  Total islands: {total}
  Total area requiring support: {total_area:.2f} mm²
  Z-range: {z_range[0]:.2f} - {z_range[1]:.2f} mm
  Average island area: {total_area/total:.2f} mm²"""
