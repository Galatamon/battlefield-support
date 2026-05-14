#!/usr/bin/env python3
"""
Create a HARD test mech model with features that exercise BattleTech-specific
support logic that the easier `create_test_mech.py` doesn't:

  - Sub-0.5mm antennae cylinders (force the 'micro' tier)
  - Recessed cockpit on the front (should be self-bridged, not supported, in
    --strict-front mode)
  - Forward-cantilevered gun barrels (front-cone overhangs that MUST be
    supported from the underside / rear, never on the front)
  - Asymmetric front/back so auto-detect should pick the right axis

Front of mech is +Y by construction.
"""

import numpy as np
import trimesh


def create_hard_mech():
    parts = []

    # Torso: 12mm wide x 10mm deep x 14mm tall, with a flat front face at +Y.
    torso = trimesh.creation.box(extents=[12.0, 10.0, 14.0])
    torso.apply_translation([0.0, 0.0, 14.0])

    # Recessed cockpit: subtract a small sphere from the front face. The sphere
    # is partly inside the torso so the "cockpit" is a concave dome on +Y.
    cockpit = trimesh.creation.icosphere(radius=2.0, subdivisions=3)
    cockpit.apply_translation([0.0, 5.0, 16.0])  # +Y face center
    try:
        torso = torso.difference(cockpit)
    except Exception:
        # If boolean fails (no engine), keep the plain torso.
        pass
    parts.append(torso)

    # Legs (asymmetric: left taller than right by 1mm, to make pose unique)
    leg_l = trimesh.creation.cylinder(radius=2.0, height=7.0, sections=20)
    leg_l.apply_translation([-3.5, 0.0, 3.5])
    parts.append(leg_l)

    leg_r = trimesh.creation.cylinder(radius=2.0, height=8.0, sections=20)
    leg_r.apply_translation([3.5, 0.0, 4.0])
    parts.append(leg_r)

    # Shoulders
    for sx in (-7.0, 7.0):
        shoulder = trimesh.creation.icosphere(radius=2.2, subdivisions=3)
        shoulder.apply_translation([sx, 0.0, 16.0])
        parts.append(shoulder)

    # Forward-cantilevered gun barrels (the classic front-face support problem).
    # Each is a 1mm-radius cylinder, 12mm long, pointing forward (+Y).
    for bx in (-7.0, 7.0):
        barrel = trimesh.creation.cylinder(radius=1.0, height=12.0, sections=16)
        # Cylinder default axis is +Z, rotate to +Y
        barrel.apply_transform(trimesh.transformations.rotation_matrix(
            -np.pi / 2, [1.0, 0.0, 0.0]
        ))
        barrel.apply_translation([bx, 6.0, 15.0])  # protrudes forward from shoulder
        parts.append(barrel)

    # Head + cockpit canopy
    head = trimesh.creation.box(extents=[4.0, 4.0, 3.5])
    head.apply_translation([0.0, 0.0, 22.5])
    parts.append(head)

    # ULTRA-FINE antennae: 0.3mm-radius cylinders (sub-mm diameter) on the head.
    # Vertical ones are self-supporting at this scale; the horizontal whisker
    # cantilevered off the side has a tiny-area overhang that MUST get the
    # 'micro' tier so the support tip doesn't snap it off during cleanup.
    for ax in (-1.2, 0.0, 1.2):
        antenna = trimesh.creation.cylinder(radius=0.15, height=5.0, sections=8)
        antenna.apply_translation([ax, 0.0, 26.5])
        parts.append(antenna)

    # Tiny horizontal whisker on the right side of the head (radius 0.2mm,
    # length 4mm). Its underside is a sub-1mm² horizontal overhang.
    whisker = trimesh.creation.cylinder(radius=0.2, height=4.0, sections=8)
    whisker.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [0.0, 1.0, 0.0]
    ))
    whisker.apply_translation([4.0, 0.0, 23.0])  # protrudes +X from head
    parts.append(whisker)

    # Backpack / jump jets: clearly on the BACK (-Y side)
    backpack = trimesh.creation.box(extents=[10.0, 3.0, 7.0])
    backpack.apply_translation([0.0, -6.5, 14.0])
    parts.append(backpack)

    combined = trimesh.util.concatenate(parts)
    # Drop to z=0
    combined.apply_translation([0.0, 0.0, -combined.bounds[0, 2]])
    return combined


if __name__ == '__main__':
    print("Creating HARD test mech (BattleTech corner cases)...")
    mech = create_hard_mech()

    output_file = "test_models/test_mech_hard.stl"
    mech.export(output_file)

    print(f"Hard test mech: {output_file}")
    print(f"  Vertices: {len(mech.vertices)}")
    print(f"  Faces: {len(mech.faces)}")
    print(f"  Dimensions: {mech.bounds[1] - mech.bounds[0]}")
    print(f"  Volume: {mech.volume:.2f} mm³")
    print("  Front: +Y (forward-cantilevered gun barrels point +Y)")
