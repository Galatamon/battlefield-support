#!/usr/bin/env python3
"""
Test and verify support cone geometry
"""

import numpy as np
import trimesh

# Recreate a single support to verify geometry
def create_test_support():
    """Create a single support cone and verify its geometry"""

    # Parameters
    tip_radius = 0.15  # 0.3mm / 2
    base_radius = 0.9  # 1.8mm / 2
    height = 10.0  # 10mm tall support

    print("Creating test support:")
    print(f"  Tip radius (top/model): {tip_radius}mm")
    print(f"  Base radius (bottom/build plate): {base_radius}mm")
    print(f"  Height: {height}mm")

    # Create cylinder and taper it to create proper cone
    cylinder = trimesh.creation.cylinder(
        radius=base_radius,
        height=height,
        sections=16
    )

    print(f"\nAfter creation (cylinder):")
    print(f"  Z range: {cylinder.vertices[:, 2].min():.3f} to {cylinder.vertices[:, 2].max():.3f}")

    # Modify vertices to taper from base to tip
    vertices = cylinder.vertices.copy()
    z_vals = vertices[:, 2]
    z_min, z_max = z_vals.min(), z_vals.max()

    print(f"\nBefore tapering:")
    print(f"  z_min: {z_min:.3f}, z_max: {z_max:.3f}")

    for i, vertex in enumerate(vertices):
        z_pos = vertex[2]
        # t=0 at bottom, t=1 at top
        t = (z_pos - z_min) / (z_max - z_min) if z_max > z_min else 0

        # Interpolate from base (large) to tip (small)
        target_radius = base_radius * (1 - t) + tip_radius * t

        current_radius = np.sqrt(vertex[0]**2 + vertex[1]**2)
        if current_radius > 0.001:
            scale = target_radius / current_radius
            vertices[i, 0] *= scale
            vertices[i, 1] *= scale

    cylinder.vertices = vertices

    # Check radii at top and bottom
    bottom_verts = vertices[np.abs(vertices[:, 2] - z_min) < 0.01]
    top_verts = vertices[np.abs(vertices[:, 2] - z_max) < 0.01]

    bottom_radii = np.sqrt(bottom_verts[:, 0]**2 + bottom_verts[:, 1]**2)
    top_radii = np.sqrt(top_verts[:, 0]**2 + top_verts[:, 1]**2)

    print(f"\nAfter tapering:")
    print(f"  Bottom (z={z_min:.3f}): radius = {bottom_radii.mean():.3f}mm (should be {base_radius}mm)")
    print(f"  Top (z={z_max:.3f}): radius = {top_radii.mean():.3f}mm (should be {tip_radius}mm)")

    # Translate to final position (build plate at 0, model at 10)
    z_base = 0.0
    translation = [0, 0, z_base + height/2]
    cylinder.apply_translation(translation)
    cone = cylinder

    print(f"\nAfter positioning:")
    print(f"  Z range: {cone.vertices[:, 2].min():.3f} to {cone.vertices[:, 2].max():.3f}")

    # Final check
    final_bottom = cone.vertices[cone.vertices[:, 2] < 0.1]
    final_top = cone.vertices[cone.vertices[:, 2] > height - 0.1]

    final_bottom_radii = np.sqrt(final_bottom[:, 0]**2 + final_bottom[:, 1]**2)
    final_top_radii = np.sqrt(final_top[:, 0]**2 + final_top[:, 1]**2)

    print(f"\nFinal verification:")
    print(f"  At build plate (z≈0): radius = {final_bottom_radii.mean():.3f}mm")
    print(f"  At model (z≈{height}): radius = {final_top_radii.mean():.3f}mm")

    if final_bottom_radii.mean() > final_top_radii.mean():
        print("\n✓ CORRECT: Large base at build plate, small tip at model")
    else:
        print("\n✗ ERROR: Inverted cone - small base at build plate, large tip at model!")

    return cone

if __name__ == '__main__':
    cone = create_test_support()
    cone.export('test_models/single_support.stl')
    print("\nSaved to test_models/single_support.stl")
