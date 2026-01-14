#!/usr/bin/env python3
"""
Verify and analyze the generated supports
"""

import trimesh
import numpy as np

def analyze_model(filepath):
    """Analyze a mesh file"""
    mesh = trimesh.load(filepath)

    print(f"\nAnalyzing: {filepath}")
    print("="*60)
    print(f"Vertices: {len(mesh.vertices)}")
    print(f"Faces: {len(mesh.faces)}")
    print(f"Volume: {mesh.volume:.2f} mm³")
    print(f"Surface Area: {mesh.area:.2f} mm²")
    print(f"Bounding Box: {mesh.bounds[1] - mesh.bounds[0]}")
    print(f"Is Watertight: {mesh.is_watertight}")

    # Z-height analysis
    z_min, z_max = mesh.bounds[0, 2], mesh.bounds[1, 2]
    print(f"Z-height: {z_min:.2f} to {z_max:.2f} mm (height: {z_max - z_min:.2f} mm)")

    return mesh

def compare_models(original_file, supported_file):
    """Compare original and supported models"""
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)

    orig = analyze_model(original_file)
    supp = analyze_model(supported_file)

    print("\n" + "="*60)
    print("SUPPORT ANALYSIS")
    print("="*60)

    # Calculate support volume
    support_volume = supp.volume - orig.volume
    print(f"\nSupport volume added: {support_volume:.2f} mm³")
    print(f"Support resin usage: {support_volume / 1000:.3f} ml")

    # Calculate percentage
    support_pct = (support_volume / orig.volume) * 100
    print(f"Support volume as % of model: {support_pct:.1f}%")

    # Verify supports touch build plate
    if supp.bounds[0, 2] < 0.01:
        print("✓ Supports reach build plate (Z=0)")
    else:
        print(f"⚠ Warning: Model starts at Z={supp.bounds[0, 2]:.2f}mm, may not adhere!")

    # Check if model grew in XY (should be minimal)
    orig_xy = (orig.bounds[1, 0] - orig.bounds[0, 0]) * (orig.bounds[1, 1] - orig.bounds[0, 1])
    supp_xy = (supp.bounds[1, 0] - supp.bounds[0, 0]) * (supp.bounds[1, 1] - supp.bounds[0, 1])
    xy_growth = ((supp_xy - orig_xy) / orig_xy) * 100
    print(f"XY footprint growth: {xy_growth:.1f}%")

    if xy_growth < 20:
        print("✓ Minimal XY footprint growth (supports are compact)")
    else:
        print(f"⚠ Warning: Large XY footprint growth, supports may extend far")

    # Geometry increase
    face_growth = ((len(supp.faces) - len(orig.faces)) / len(orig.faces)) * 100
    print(f"\nGeometry complexity increase: {face_growth:.0f}%")
    print(f"  Original: {len(orig.faces)} faces")
    print(f"  With supports: {len(supp.faces)} faces")
    print(f"  Added: {len(supp.faces) - len(orig.faces)} faces")

if __name__ == '__main__':
    compare_models(
        'test_models/test_mech.stl',
        'test_models/test_mech_supported.stl'
    )
