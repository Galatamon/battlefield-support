#!/usr/bin/env python3
"""
Verify and analyze the generated supports.

Usage:
    python verify_supports.py                              # legacy compare on test_mech
    python verify_supports.py SUPPORTS.stl [META.json]     # analyze a supports-only STL
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import trimesh

from config import PrinterConfig


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

    support_volume = supp.volume - orig.volume
    print(f"\nSupport volume added: {support_volume:.2f} mm³")
    print(f"Support resin usage: {support_volume / 1000:.3f} ml")

    support_pct = (support_volume / orig.volume) * 100
    print(f"Support volume as % of model: {support_pct:.1f}%")

    if supp.bounds[0, 2] < 0.01:
        print("✓ Supports reach build plate (Z=0)")
    else:
        print(f"⚠ Warning: Model starts at Z={supp.bounds[0, 2]:.2f}mm, may not adhere!")

    orig_xy = (orig.bounds[1, 0] - orig.bounds[0, 0]) * (orig.bounds[1, 1] - orig.bounds[0, 1])
    supp_xy = (supp.bounds[1, 0] - supp.bounds[0, 0]) * (supp.bounds[1, 1] - supp.bounds[0, 1])
    xy_growth = ((supp_xy - orig_xy) / orig_xy) * 100
    print(f"XY footprint growth: {xy_growth:.1f}%")

    if xy_growth < 20:
        print("✓ Minimal XY footprint growth (supports are compact)")
    else:
        print(f"⚠ Warning: Large XY footprint growth, supports may extend far")

    face_growth = ((len(supp.faces) - len(orig.faces)) / len(orig.faces)) * 100
    print(f"\nGeometry complexity increase: {face_growth:.0f}%")
    print(f"  Original: {len(orig.faces)} faces")
    print(f"  With supports: {len(supp.faces)} faces")
    print(f"  Added: {len(supp.faces) - len(orig.faces)} faces")


def analyze_supports_only(supports_path, meta_path=None):
    """
    Analyze a supports-only STL plus its sidecar metadata JSON.

    Reports:
      * Tip-diameter histogram (per tier)
      * face_class distribution and explicit count of front-cone contacts
      * Build-volume sanity (does the supports mesh fit?)
    """
    print(f"\nAnalyzing supports: {supports_path}")
    print("="*60)
    mesh = trimesh.load(supports_path)
    print(f"Vertices: {len(mesh.vertices)}")
    print(f"Faces: {len(mesh.faces)}")
    print(f"Volume: {mesh.volume:.2f} mm³")
    print(f"Surface Area: {mesh.area:.2f} mm²")
    bounds = mesh.bounds
    dims = bounds[1] - bounds[0]
    print(f"Bounding box: {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f} mm")

    # Build-volume sanity
    fits = (dims[0] <= PrinterConfig.BUILD_VOLUME_X and
            dims[1] <= PrinterConfig.BUILD_VOLUME_Y and
            dims[2] <= PrinterConfig.BUILD_VOLUME_Z)
    bv = f"{PrinterConfig.BUILD_VOLUME_X}x{PrinterConfig.BUILD_VOLUME_Y}x{PrinterConfig.BUILD_VOLUME_Z}"
    print(f"Build volume ({bv}mm): {'✓ fits' if fits else '⚠ DOES NOT FIT'}")

    # Z floor
    if bounds[0, 2] < 0.05:
        print("✓ Supports reach build plate (Z≈0)")
    else:
        print(f"⚠ Supports start at Z={bounds[0,2]:.2f}mm — won't adhere")

    if meta_path is None:
        # Guess sidecar filename
        guess = Path(supports_path).with_name(
            Path(supports_path).stem.replace('_supports_only', '_supports_meta') + '.json'
        )
        if guess.exists():
            meta_path = str(guess)

    if meta_path and Path(meta_path).exists():
        with open(meta_path) as f:
            meta = json.load(f)

        print(f"\nSidecar metadata: {meta_path}")
        print(f"  Front axis: {meta.get('front_axis_label')} "
              f"({'strict' if meta.get('strict_front') else 'snap'} policy)")
        contacts = meta.get('contacts', [])
        print(f"  Support contacts: {len(contacts)}")

        # Tip-diameter histogram (per tier)
        tier_counter = Counter(c['tier'] for c in contacts)
        print("\nTier distribution:")
        for tier in ('micro', 'light', 'medium', 'heavy'):
            n = tier_counter.get(tier, 0)
            print(f"  {tier:<6}: {n}")

        # Numerical tip-diameter histogram (in case of CLI overrides)
        tip_diams = [c['tip_radius'] * 2 for c in contacts]
        if tip_diams:
            buckets = [0.15, 0.2, 0.3, 0.4]
            tol = 0.02
            bucket_counts = Counter()
            for d in tip_diams:
                closest = min(buckets, key=lambda b: abs(b - d))
                if abs(closest - d) < tol:
                    bucket_counts[closest] += 1
                else:
                    bucket_counts['other'] += 1
            print("\nTip diameter histogram:")
            for b in buckets:
                print(f"  {b}mm: {bucket_counts.get(b, 0)}")
            if bucket_counts.get('other', 0):
                print(f"  other: {bucket_counts['other']}")

        # face_class distribution
        face_counter = Counter(c.get('face_class', 'unknown') for c in contacts)
        print("\nFace-class distribution:")
        for cls in ('front', 'side', 'back', 'unknown'):
            n = face_counter.get(cls, 0)
            print(f"  {cls:<5}: {n}")

        front_count = face_counter.get('front', 0)
        if front_count == 0:
            print("✓ Zero contacts on front-face cone")
        else:
            print(f"⚠ {front_count} contacts still on front-face cone "
                  f"(either un-snappable or strict-mode kept-as-scar)")
    else:
        print("\n  (No sidecar metadata found — pass it as the second argument "
              "or generate one via support_generator_cli.py)")


if __name__ == '__main__':
    if len(sys.argv) >= 2:
        # New mode: analyze a supports-only STL
        supports_path = sys.argv[1]
        meta_path = sys.argv[2] if len(sys.argv) >= 3 else None
        analyze_supports_only(supports_path, meta_path)
    else:
        # Legacy mode: compare test mech
        compare_models(
            'test_models/test_mech.stl',
            'test_models/test_mech_supported.stl'
        )
