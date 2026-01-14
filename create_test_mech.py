#!/usr/bin/env python3
"""
Create a test model that simulates a Battletech mech
with typical challenging features for support generation
"""

import numpy as np
import trimesh

# Create a simplified mech-like model with:
# - Body (torso)
# - Legs (stable base)
# - Arms (overhangs)
# - Weapons (bridges/islands)
# - Head (small overhang on top)

def create_test_mech():
    """Create a test mech model with support challenges"""

    meshes = []

    # Torso - main body (slightly angled trapezoid)
    torso = trimesh.creation.box(extents=[8, 6, 10])
    torso.apply_translation([0, 0, 12])
    meshes.append(torso)

    # Legs - two cylinders for stability
    leg_left = trimesh.creation.cylinder(radius=2, height=10, sections=16)
    leg_left.apply_translation([-3, 0, 5])
    meshes.append(leg_left)

    leg_right = trimesh.creation.cylinder(radius=2, height=10, sections=16)
    leg_right.apply_translation([3, 0, 5])
    meshes.append(leg_right)

    # Arms - extended horizontally (will need supports)
    # Left arm
    arm_left = trimesh.creation.cylinder(radius=1.5, height=8, sections=12)
    # Rotate to horizontal
    arm_left.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi/2, [0, 1, 0]
    ))
    arm_left.apply_translation([-8, 0, 12])
    meshes.append(arm_left)

    # Right arm
    arm_right = trimesh.creation.cylinder(radius=1.5, height=8, sections=12)
    arm_right.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi/2, [0, 1, 0]
    ))
    arm_right.apply_translation([8, 0, 12])
    meshes.append(arm_right)

    # Shoulder joints
    shoulder_left = trimesh.creation.icosphere(radius=2, subdivisions=2)
    shoulder_left.apply_translation([-5, 0, 12])
    meshes.append(shoulder_left)

    shoulder_right = trimesh.creation.icosphere(radius=2, subdivisions=2)
    shoulder_right.apply_translation([5, 0, 12])
    meshes.append(shoulder_right)

    # Weapons on arms (small cylinders - potential bridges)
    weapon_left = trimesh.creation.cylinder(radius=0.5, height=6, sections=8)
    weapon_left.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi/2, [0, 1, 0]
    ))
    weapon_left.apply_translation([-12, 2, 12])
    meshes.append(weapon_left)

    weapon_right = trimesh.creation.cylinder(radius=0.5, height=6, sections=8)
    weapon_right.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi/2, [0, 1, 0]
    ))
    weapon_right.apply_translation([12, -2, 12])
    meshes.append(weapon_right)

    # Head - small box on top (overhang)
    head = trimesh.creation.box(extents=[4, 4, 3])
    head.apply_translation([0, 0, 18.5])
    meshes.append(head)

    # Cockpit canopy (angled face)
    canopy = trimesh.creation.box(extents=[3, 3, 2])
    canopy.apply_translation([0, 2, 18])
    meshes.append(canopy)

    # Antenna (thin cylinder - island risk)
    antenna = trimesh.creation.cylinder(radius=0.3, height=4, sections=8)
    antenna.apply_translation([0, 0, 22])
    meshes.append(antenna)

    # Create backpack/jump jets (overhang on back)
    backpack = trimesh.creation.box(extents=[6, 2, 6])
    backpack.apply_translation([0, -4, 14])
    meshes.append(backpack)

    # Combine all meshes
    combined = trimesh.util.concatenate(meshes)

    # Move so bottom is at Z=0
    bounds = combined.bounds
    combined.apply_translation([0, 0, -bounds[0, 2]])

    return combined

if __name__ == '__main__':
    print("Creating test mech model...")
    mech = create_test_mech()

    output_file = "test_models/test_mech.stl"
    mech.export(output_file)

    print(f"Test mech created: {output_file}")
    print(f"  Vertices: {len(mech.vertices)}")
    print(f"  Faces: {len(mech.faces)}")
    print(f"  Dimensions: {mech.bounds[1] - mech.bounds[0]}")
    print(f"  Volume: {mech.volume:.2f} mm³")
