#!/usr/bin/env python3
"""
Render visual preview of STL models
"""

import trimesh
import numpy as np
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
from matplotlib import patches
import os


FACE_CLASS_COLOR = {
    'front': '#2ecc71',   # green = visible front (we want zero of these)
    'side':  '#f1c40f',   # yellow = acceptable
    'back':  '#3498db',   # blue = back / underside
    'unknown': '#7f8c8d',
}

def render_stl_views(filepath, output_image):
    """Render front, side, and top views of an STL"""
    mesh = trimesh.load(filepath)

    # Create figure with subplots
    fig = plt.figure(figsize=(15, 5))

    # Front view (XZ plane)
    ax1 = fig.add_subplot(131, projection='3d')
    ax1.set_title('Front View (XZ)', fontsize=12, fontweight='bold')

    # Side view (YZ plane)
    ax2 = fig.add_subplot(132, projection='3d')
    ax2.set_title('Side View (YZ)', fontsize=12, fontweight='bold')

    # Perspective view
    ax3 = fig.add_subplot(133, projection='3d')
    ax3.set_title('Perspective View', fontsize=12, fontweight='bold')

    # Plot mesh on each subplot
    for ax in [ax1, ax2, ax3]:
        ax.plot_trisurf(
            mesh.vertices[:, 0],
            mesh.vertices[:, 1],
            mesh.vertices[:, 2],
            triangles=mesh.faces,
            cmap='viridis',
            alpha=0.8,
            edgecolor='none',
            linewidth=0
        )

        # Set equal aspect ratio
        max_range = np.array([
            mesh.vertices[:, 0].max() - mesh.vertices[:, 0].min(),
            mesh.vertices[:, 1].max() - mesh.vertices[:, 1].min(),
            mesh.vertices[:, 2].max() - mesh.vertices[:, 2].min()
        ]).max() / 2.0

        mid_x = (mesh.vertices[:, 0].max() + mesh.vertices[:, 0].min()) * 0.5
        mid_y = (mesh.vertices[:, 1].max() + mesh.vertices[:, 1].min()) * 0.5
        mid_z = (mesh.vertices[:, 2].max() + mesh.vertices[:, 2].min()) * 0.5

        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(mid_z - max_range, mid_z + max_range)

        ax.set_xlabel('X (mm)', fontsize=9)
        ax.set_ylabel('Y (mm)', fontsize=9)
        ax.set_zlabel('Z (mm)', fontsize=9)

        # Grid
        ax.grid(True, alpha=0.3)

    # Set viewing angles
    ax1.view_init(elev=0, azim=0)  # Front
    ax2.view_init(elev=0, azim=90)  # Side
    ax3.view_init(elev=20, azim=45)  # Perspective

    plt.tight_layout()
    plt.savefig(output_image, dpi=150, bbox_inches='tight')
    print(f"Saved render: {output_image}")
    plt.close()

def render_comparison(original_file, supported_file, output_image):
    """Render side-by-side comparison"""
    orig = trimesh.load(original_file)
    supp = trimesh.load(supported_file)

    fig = plt.figure(figsize=(16, 8))

    # Original model - front view
    ax1 = fig.add_subplot(231, projection='3d')
    ax1.set_title('Original - Front', fontsize=11, fontweight='bold')

    # Original model - side view
    ax2 = fig.add_subplot(232, projection='3d')
    ax2.set_title('Original - Side', fontsize=11, fontweight='bold')

    # Original model - perspective
    ax3 = fig.add_subplot(233, projection='3d')
    ax3.set_title('Original - Perspective', fontsize=11, fontweight='bold')

    # Supported model - front view
    ax4 = fig.add_subplot(234, projection='3d')
    ax4.set_title('With Supports - Front', fontsize=11, fontweight='bold', color='green')

    # Supported model - side view
    ax5 = fig.add_subplot(235, projection='3d')
    ax5.set_title('With Supports - Side', fontsize=11, fontweight='bold', color='green')

    # Supported model - perspective
    ax6 = fig.add_subplot(236, projection='3d')
    ax6.set_title('With Supports - Perspective', fontsize=11, fontweight='bold', color='green')

    # Plot original
    for ax in [ax1, ax2, ax3]:
        ax.plot_trisurf(
            orig.vertices[:, 0],
            orig.vertices[:, 1],
            orig.vertices[:, 2],
            triangles=orig.faces,
            cmap='coolwarm',
            alpha=0.9,
            edgecolor='none'
        )

        # Build plate indicator
        x_min, x_max = orig.vertices[:, 0].min(), orig.vertices[:, 0].max()
        y_min, y_max = orig.vertices[:, 1].min(), orig.vertices[:, 1].max()
        xx, yy = np.meshgrid([x_min, x_max], [y_min, y_max])
        zz = np.zeros_like(xx)
        ax.plot_surface(xx, yy, zz, alpha=0.2, color='gray')

        setup_axis(ax, orig)

    # Plot supported
    for ax in [ax4, ax5, ax6]:
        ax.plot_trisurf(
            supp.vertices[:, 0],
            supp.vertices[:, 1],
            supp.vertices[:, 2],
            triangles=supp.faces,
            cmap='summer',
            alpha=0.9,
            edgecolor='none'
        )

        # Build plate
        x_min, x_max = supp.vertices[:, 0].min(), supp.vertices[:, 0].max()
        y_min, y_max = supp.vertices[:, 1].min(), supp.vertices[:, 1].max()
        xx, yy = np.meshgrid([x_min, x_max], [y_min, y_max])
        zz = np.zeros_like(xx)
        ax.plot_surface(xx, yy, zz, alpha=0.2, color='gray')

        setup_axis(ax, supp)

    # Set viewing angles
    ax1.view_init(elev=0, azim=0)
    ax2.view_init(elev=0, azim=90)
    ax3.view_init(elev=20, azim=45)

    ax4.view_init(elev=0, azim=0)
    ax5.view_init(elev=0, azim=90)
    ax6.view_init(elev=20, azim=45)

    plt.tight_layout()
    plt.savefig(output_image, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved comparison: {output_image}")
    plt.close()

def setup_axis(ax, mesh):
    """Setup axis for consistent view"""
    max_range = np.array([
        mesh.vertices[:, 0].max() - mesh.vertices[:, 0].min(),
        mesh.vertices[:, 1].max() - mesh.vertices[:, 1].min(),
        mesh.vertices[:, 2].max() - mesh.vertices[:, 2].min()
    ]).max() / 2.0

    mid_x = (mesh.vertices[:, 0].max() + mesh.vertices[:, 0].min()) * 0.5
    mid_y = (mesh.vertices[:, 1].max() + mesh.vertices[:, 1].min()) * 0.5
    mid_z = (mesh.vertices[:, 2].max() + mesh.vertices[:, 2].min()) * 0.5

    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(0, mid_z + max_range)  # Always show from build plate up

    ax.set_xlabel('X', fontsize=8)
    ax.set_ylabel('Y', fontsize=8)
    ax.set_zlabel('Z', fontsize=8)
    ax.grid(True, alpha=0.3)

    # Smaller tick labels
    ax.tick_params(labelsize=7)

def _view_for_front(front_axis):
    """
    Compute matplotlib (elev, azim) so the front of the mech faces the camera.

    Matplotlib's 3D azim=0 looks along +X (toward origin), elev=0 is horizontal.
    We want the camera to be on the +front_axis side looking toward origin.
    """
    if front_axis is None:
        return (15, -60)
    fx, fy = float(front_axis[0]), float(front_axis[1])
    # azim such that view direction (toward origin) is roughly opposite to front
    azim = np.degrees(np.arctan2(fy, fx)) - 90.0
    return (0, azim)


def render_support_preview(model_mesh, contact_metadata, output_image, front_axis=None):
    """
    Render a 3-panel preview of the model with support contact points colored by
    face_class (green=front=visible, yellow=side, blue=back).

    Args:
        model_mesh: trimesh.Trimesh of the ORIGINAL model (already oriented).
        contact_metadata: list of dicts with 'xyz', 'tier', 'tip_radius', 'face_class'.
        output_image: output PNG path.
        front_axis: numpy array; used to pick the "front view" camera angle.
    """
    fig = plt.figure(figsize=(15, 5))
    fig.suptitle('Support contact preview — green=FRONT (avoid), yellow=side, blue=back',
                 fontsize=11, fontweight='bold')

    ax_front = fig.add_subplot(131, projection='3d')
    ax_side = fig.add_subplot(132, projection='3d')
    ax_iso = fig.add_subplot(133, projection='3d')

    ax_front.set_title('Front view (visible side)', fontsize=10)
    ax_side.set_title('Side view', fontsize=10)
    ax_iso.set_title('Iso view', fontsize=10)

    front_elev, front_azim = _view_for_front(front_axis)
    side_elev, side_azim = (front_elev, front_azim + 90)

    for ax in (ax_front, ax_side, ax_iso):
        ax.plot_trisurf(
            model_mesh.vertices[:, 0],
            model_mesh.vertices[:, 1],
            model_mesh.vertices[:, 2],
            triangles=model_mesh.faces,
            color='lightgrey',
            alpha=0.45,
            edgecolor='none',
            linewidth=0,
        )

    # Scatter the support contacts. Use a scatter (sized by tip diameter) — it's
    # legible, fast, and doesn't choke on dense contacts.
    if contact_metadata:
        xs = [c['xyz'][0] for c in contact_metadata]
        ys = [c['xyz'][1] for c in contact_metadata]
        zs = [c['xyz'][2] for c in contact_metadata]
        colors = [FACE_CLASS_COLOR.get(c.get('face_class', 'unknown'),
                                       FACE_CLASS_COLOR['unknown'])
                  for c in contact_metadata]
        # tip diameter mm -> visual point size; clamp so micro tips are still visible
        sizes = [max(15, 200 * c.get('tip_radius', 0.15)) for c in contact_metadata]

        for ax in (ax_front, ax_side, ax_iso):
            ax.scatter(xs, ys, zs, c=colors, s=sizes,
                       edgecolor='black', linewidth=0.4, depthshade=False)

    ax_front.view_init(elev=front_elev, azim=front_azim)
    ax_side.view_init(elev=side_elev, azim=side_azim)
    ax_iso.view_init(elev=25, azim=front_azim + 45)

    for ax in (ax_front, ax_side, ax_iso):
        setup_axis(ax, model_mesh)

    # Build the legend on the iso axis
    legend_handles = [
        plt.Line2D([0], [0], marker='o', linestyle='', color=FACE_CLASS_COLOR['front'],
                   label='front (scar — avoid)'),
        plt.Line2D([0], [0], marker='o', linestyle='', color=FACE_CLASS_COLOR['side'],
                   label='side'),
        plt.Line2D([0], [0], marker='o', linestyle='', color=FACE_CLASS_COLOR['back'],
                   label='back'),
    ]
    ax_iso.legend(handles=legend_handles, loc='upper right', fontsize=7)

    plt.tight_layout()
    plt.savefig(output_image, dpi=130, bbox_inches='tight', facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    print("Rendering STL previews...")

    # Render comparison
    render_comparison(
        'test_models/test_mech.stl',
        'test_models/test_mech_supported.stl',
        'test_models/comparison.png'
    )

    print("\nDone! Check test_models/comparison.png")
