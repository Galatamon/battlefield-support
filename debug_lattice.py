#!/usr/bin/env python3
"""
Debug script to check lattice tower clustering
"""

import trimesh
import numpy as np
from support_structures import SupportGenerator
from overhang_detector import OverhangDetector
from island_detector import IslandDetector
from config import SupportConfig

# Load test mech
mesh = trimesh.load('test_models/test_mech.stl')

# Get support points
island_detector = IslandDetector(mesh)
islands = island_detector.detect_islands()

overhang_detector = OverhangDetector(mesh)
overhangs = overhang_detector.detect_overhangs()
bridges = overhang_detector.detect_bridges()

support_points = islands + overhangs + bridges

print(f"Total support points: {len(support_points)}")
print(f"Model bounds: {mesh.bounds}")
print(f"Model size: {mesh.bounds[1] - mesh.bounds[0]}")

# Generate supports
generator = SupportGenerator(mesh)

# Route paths
build_plate_z = mesh.bounds[0, 2]
support_paths = []

print("\nRouting a sample of paths...")
for i, point in enumerate(support_points[:50]):  # Just first 50 for testing
    start_point = [point['x'], point['y'], point['z']]
    height = point['z'] - build_plate_z

    if height < SupportConfig.MIN_SUPPORT_HEIGHT:
        continue

    tip_radius = SupportConfig.SUPPORT_TIP_DIAMETER / 2
    path = generator.path_router.route_support_path(
        start_point,
        target_z=None,
        radius=tip_radius,
        max_iterations=300
    )

    if path is not None:
        support_paths.append(path)

print(f"Routed {len(support_paths)} paths")

# Extract endpoints
endpoints = []
for path in support_paths:
    if len(path) > 0:
        lowest = min(path, key=lambda p: p[2])
        endpoints.append(lowest)

print(f"\nEndpoints extracted: {len(endpoints)}")

# Check endpoint distribution
if endpoints:
    endpoints_array = np.array(endpoints)
    print(f"Endpoint XY range: X=[{endpoints_array[:,0].min():.1f}, {endpoints_array[:,0].max():.1f}], "
          f"Y=[{endpoints_array[:,1].min():.1f}, {endpoints_array[:,1].max():.1f}]")
    print(f"Endpoint Z range: [{endpoints_array[:,2].min():.1f}, {endpoints_array[:,2].max():.1f}]")

# Test clustering
from lattice_tower import LatticeTowerGenerator

lattice_gen = LatticeTowerGenerator()

print(f"\nClustering with spacing={SupportConfig.LATTICE_SPACING}mm...")
clusters = lattice_gen.cluster_support_endpoints(endpoints, SupportConfig.LATTICE_SPACING)

print(f"Found {len(clusters)} clusters:")
for i, cluster in enumerate(clusters):
    print(f"  Cluster {i}: {len(cluster)} supports")
    if len(cluster) >= 3:
        print(f"    -> Will create lattice tower")
    else:
        print(f"    -> Too small for tower (need 3+)")

# Calculate distances between endpoints
print("\nAnalyzing endpoint spacing...")
if len(endpoints) > 1:
    distances = []
    for i in range(len(endpoints)):
        for j in range(i+1, len(endpoints)):
            dist_2d = np.linalg.norm(np.array(endpoints[i][:2]) - np.array(endpoints[j][:2]))
            distances.append(dist_2d)

    distances = np.array(distances)
    print(f"  Min distance: {distances.min():.2f}mm")
    print(f"  Max distance: {distances.max():.2f}mm")
    print(f"  Mean distance: {distances.mean():.2f}mm")
    print(f"  Median distance: {np.median(distances):.2f}mm")

    # Suggest better spacing
    suggested_spacing = np.percentile(distances, 75)
    print(f"\nSuggested LATTICE_SPACING: {suggested_spacing:.1f}mm (75th percentile)")
