#!/usr/bin/env python3
"""
Battlefield Support Generator - CLI
Automatic support generation for resin 3D printing
"""

import argparse
import sys
import os
from pathlib import Path

from mesh_loader import MeshLoader
from orientation import OrientationOptimizer
from island_detector import IslandDetector
from overhang_detector import OverhangDetector
from support_structures import SupportGenerator
from support_optimizer import SupportOptimizer
from config import (
    PrinterConfig, ResinConfig, SupportConfig, AnalysisConfig, get_config
)


def print_banner():
    """Print application banner"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║         Battlefield Support Generator v1.0                ║
║    Automatic Support Generation for Resin 3D Printing     ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config_info():
    """Print configuration information"""
    print("Configuration:")
    print(f"  Printer: {PrinterConfig.PRINTER_NAME}")
    print(f"    Resolution: {PrinterConfig.XY_RESOLUTION}mm ({PrinterConfig.RESOLUTION_X}x{PrinterConfig.RESOLUTION_Y})")
    print(f"    Build Volume: {PrinterConfig.BUILD_VOLUME_X}x{PrinterConfig.BUILD_VOLUME_Y}x{PrinterConfig.BUILD_VOLUME_Z}mm")
    print(f"  Resin: {ResinConfig.RESIN_NAME}")
    print(f"    Tensile Strength: {ResinConfig.TENSILE_STRENGTH} MPa")
    print(f"  Support Parameters:")
    print(f"    Tip Diameter: {SupportConfig.SUPPORT_TIP_DIAMETER}mm (light: {SupportConfig.SUPPORT_TIP_DIAMETER_LIGHT}mm)")
    print(f"    Base Diameter: {SupportConfig.SUPPORT_BASE_DIAMETER}mm")
    print(f"    Support Spacing: {SupportConfig.SUPPORT_SPACING}mm")
    print(f"    Max Bridge Length: {SupportConfig.MAX_BRIDGE_LENGTH}mm")
    print(f"    Max Overhang Angle: {SupportConfig.MAX_OVERHANG_ANGLE}°")
    print(f"  Optimization:")
    print(f"    Merge Radius: {SupportConfig.MERGE_RADIUS}mm")
    print(f"    Safety Margin: {SupportConfig.SAFETY_MARGIN}x")
    print()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Generate optimized supports for resin 3D printing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s model.stl
  %(prog)s model.stl -o model_supported.stl
  %(prog)s model.stl --no-auto-orient --support-tip 0.4
  %(prog)s model.stl --max-bridge 7.0 --overhang-angle 50
        """
    )

    parser.add_argument('input', type=str,
                        help='Input STL file')

    parser.add_argument('-o', '--output', type=str,
                        help='Output STL file (default: <input>_supported.stl)')

    parser.add_argument('--layer-height', type=float,
                        default=AnalysisConfig.SLICE_LAYER_HEIGHT,
                        help=f'Layer height in mm (default: {AnalysisConfig.SLICE_LAYER_HEIGHT})')

    parser.add_argument('--support-tip', type=float,
                        default=SupportConfig.SUPPORT_TIP_DIAMETER,
                        help=f'Support tip diameter in mm (default: {SupportConfig.SUPPORT_TIP_DIAMETER})')

    parser.add_argument('--max-bridge', type=float,
                        default=SupportConfig.MAX_BRIDGE_LENGTH,
                        help=f'Maximum unsupported bridge length in mm (default: {SupportConfig.MAX_BRIDGE_LENGTH})')

    parser.add_argument('--min-island-area', type=float,
                        default=SupportConfig.MIN_ISLAND_AREA,
                        help=f'Minimum island area to support in mm² (default: {SupportConfig.MIN_ISLAND_AREA})')

    parser.add_argument('--overhang-angle', type=float,
                        default=SupportConfig.MAX_OVERHANG_ANGLE,
                        help=f'Maximum overhang angle in degrees (default: {SupportConfig.MAX_OVERHANG_ANGLE})')

    parser.add_argument('--no-auto-orient', action='store_true',
                        help='Disable auto-orientation')

    parser.add_argument('--no-islands', action='store_true',
                        help='Skip island detection')

    parser.add_argument('--no-overhangs', action='store_true',
                        help='Skip overhang detection')

    parser.add_argument('--no-bridges', action='store_true',
                        help='Skip bridge detection')

    parser.add_argument('--orientation-samples', type=int, default=20,
                        help='Number of orientations to test (default: 20)')

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')

    parser.add_argument('--show-config', action='store_true',
                        help='Show configuration and exit')

    # Optimization options
    parser.add_argument('--no-optimize', action='store_true',
                        help='Disable support point optimization')

    parser.add_argument('--miniature-mode', action='store_true',
                        help='Optimize for miniatures (aggressive detail preservation)')

    parser.add_argument('--merge-radius', type=float,
                        default=SupportConfig.MERGE_RADIUS,
                        help=f'Radius for merging nearby support points (default: {SupportConfig.MERGE_RADIUS}mm)')

    parser.add_argument('--support-spacing', type=float,
                        default=SupportConfig.SUPPORT_SPACING,
                        help=f'Distance between support points (default: {SupportConfig.SUPPORT_SPACING}mm)')

    # BattleTech-specific: front-face preservation
    parser.add_argument('--front', type=str, default='auto',
                        choices=['auto', '+X', '-X', '+Y', '-Y'],
                        help='Front-facing world axis (auto-detect by default). '
                             'Supports will avoid this side of the mech.')

    parser.add_argument('--strict-front', action='store_true',
                        help='If a front-face overhang is bridgeable, skip it entirely '
                             'instead of snapping the contact to the nearest non-front edge.')

    parser.add_argument('--micro-tip', type=float,
                        default=SupportConfig.SUPPORT_TIP_DIAMETER_MICRO,
                        help=f'Tip diameter for micro tier (thin/high-detail features). '
                             f'Default: {SupportConfig.SUPPORT_TIP_DIAMETER_MICRO}mm')

    parser.add_argument('--supports-only', action='store_true',
                        help='Emit only the supports-only STL (skip fused output).')

    parser.add_argument('--no-fused', action='store_true',
                        help='Skip the fused model+supports STL output.')

    parser.add_argument('--no-preview', action='store_true',
                        help='Skip the support contact preview PNG.')

    parser.add_argument('--preview-image', type=str, default=None,
                        help='Path for the contact preview PNG (default: <stem>_preview.png).')

    return parser.parse_args()


def main():
    """Main application entry point"""
    # Parse arguments
    args = parse_args()

    # Print banner
    print_banner()

    # Show config if requested
    if args.show_config:
        print_config_info()
        return 0

    # Validate input file
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found")
        return 1

    # Determine output filename
    if args.output:
        output_file = args.output
    else:
        input_path = Path(args.input)
        output_file = str(input_path.parent / f"{input_path.stem}_supported.stl")

    # Apply miniature mode if requested (overrides other settings)
    if args.miniature_mode:
        print("Miniature Mode: Optimizing for detail preservation")
        # Even more aggressive settings for miniatures
        SupportConfig.SUPPORT_SPACING = 5.0  # Very sparse
        SupportConfig.EDGE_SUPPORT_SPACING = 3.0
        SupportConfig.MAX_OVERHANG_ANGLE = 55.0  # Let resin self-support more
        SupportConfig.MAX_BRIDGE_LENGTH = 7.0  # Longer bridges
        SupportConfig.MIN_ISLAND_AREA = 1.0  # Skip tiny islands
        SupportConfig.MERGE_RADIUS = 2.0  # Aggressive merging
        SupportConfig.SAFETY_MARGIN = 1.0  # No safety margin
        SupportConfig.SUPPORT_TIP_DIAMETER = 0.25  # Smaller tips
        SupportConfig.SUPPORT_BASE_DIAMETER = 0.7  # Thinner supports
        print()

    # Update config from command line (only if not in miniature mode)
    if not args.miniature_mode:
        SupportConfig.SUPPORT_TIP_DIAMETER = args.support_tip
        SupportConfig.MAX_BRIDGE_LENGTH = args.max_bridge
        SupportConfig.MIN_ISLAND_AREA = args.min_island_area
        SupportConfig.MAX_OVERHANG_ANGLE = args.overhang_angle
        SupportConfig.SUPPORT_SPACING = args.support_spacing
    SupportConfig.MERGE_RADIUS = args.merge_radius
    SupportConfig.SUPPORT_TIP_DIAMETER_MICRO = args.micro_tip
    AnalysisConfig.SLICE_LAYER_HEIGHT = args.layer_height

    # Print configuration (after all settings applied)
    print_config_info()

    print("="*60)
    print("STEP 1: Loading Model")
    print("="*60)

    # Load mesh
    loader = MeshLoader()
    try:
        mesh = loader.load(args.input)
    except Exception as e:
        print(f"Error loading mesh: {e}")
        return 1

    # Print mesh info
    dims = loader.get_dimensions()
    print(f"\nModel dimensions: {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f} mm")
    print(f"Model volume: {loader.get_volume():.2f} mm³")
    print(f"Model surface area: {loader.get_surface_area():.2f} mm²")

    # Check if fits in build volume
    if (dims[0] > PrinterConfig.BUILD_VOLUME_X or
        dims[1] > PrinterConfig.BUILD_VOLUME_Y or
        dims[2] > PrinterConfig.BUILD_VOLUME_Z):
        print("\nWarning: Model may not fit in build volume!")
        print(f"Build volume: {PrinterConfig.BUILD_VOLUME_X}x{PrinterConfig.BUILD_VOLUME_Y}x{PrinterConfig.BUILD_VOLUME_Z}mm")

    # Auto-orientation
    front_axis = None
    front_axis_label = None
    if not args.no_auto_orient:
        print("\n" + "="*60)
        print("STEP 2: Auto-Orientation")
        print("="*60)

        optimizer = OrientationOptimizer(mesh, front_axis=args.front)
        optimizer.apply_optimal_orientation(num_samples=args.orientation_samples)

        # Rotate the resolved front axis into the new world frame so downstream
        # code can use it without re-running the auto-detect.
        front_axis = optimizer.front_axis.copy()
        front_axis_label = optimizer.front_axis_label

        # Center on build plate
        loader.center_on_build_plate()
    else:
        # Still resolve the front axis (no rotation applied) so support
        # placement can avoid the front face.
        from orientation import parse_front_axis
        resolved = parse_front_axis(args.front)
        if resolved is not None:
            front_axis = resolved
            front_axis_label = args.front
        else:
            # No orientation step and no override -> auto-detect on the
            # untransformed mesh.
            optimizer = OrientationOptimizer(mesh, front_axis='auto')
            front_axis = optimizer.front_axis.copy()
            front_axis_label = optimizer.front_axis_label

    # Collect support points
    all_support_points = []

    # Island detection
    if not args.no_islands:
        print("\n" + "="*60)
        print("STEP 3: Island Detection")
        print("="*60)

        detector = IslandDetector(mesh, layer_height=args.layer_height)
        islands = detector.detect_islands()
        print(detector.get_island_summary())

        # Add island support points
        if isinstance(islands, list):
            for island in islands:
                if isinstance(island, list):
                    all_support_points.extend(island)
                elif isinstance(island, dict):
                    all_support_points.append(island)

    # Overhang and bridge detection
    if not args.no_overhangs or not args.no_bridges:
        print("\n" + "="*60)
        print("STEP 4: Overhang & Bridge Detection")
        print("="*60)

        overhang_detector = OverhangDetector(mesh)

        if not args.no_overhangs:
            overhang_points = overhang_detector.detect_overhangs(
                max_angle=SupportConfig.MAX_OVERHANG_ANGLE
            )
            all_support_points.extend(overhang_points)

        if not args.no_bridges:
            bridge_points = overhang_detector.detect_bridges(
                max_length=SupportConfig.MAX_BRIDGE_LENGTH
            )
            all_support_points.extend(bridge_points)

        print(overhang_detector.get_detection_summary(all_support_points))

    # Optimize support points
    if not args.no_optimize and all_support_points:
        print("\n" + "="*60)
        print("STEP 5: Support Optimization")
        print("="*60)

        optimizer_config = {
            'merge_radius': SupportConfig.MERGE_RADIUS,
            'curvature_threshold': SupportConfig.DETAIL_CURVATURE_THRESHOLD,
            'thin_feature_threshold': SupportConfig.THIN_FEATURE_THRESHOLD,
        }
        optimizer = SupportOptimizer(mesh, config=optimizer_config)
        all_support_points = optimizer.optimize_support_points(all_support_points)

    # Generate supports
    print("\n" + "="*60)
    print("STEP 6: Support Generation")
    print("="*60)

    if front_axis is not None:
        print(f"  Front axis for placement: {front_axis_label or front_axis} "
              f"(strict={args.strict_front})")
    generator = SupportGenerator(
        mesh,
        front_axis=front_axis,
        strict_front=args.strict_front,
    )
    supports = generator.generate_supports(all_support_points)

    if supports is not None:
        print(generator.get_support_summary(supports))
    else:
        print("\nNo supports needed! Model can print without supports.")

    # Export
    print("\n" + "="*60)
    print("STEP 7: Export")
    print("="*60)

    input_path = Path(args.input)
    out_dir = Path(output_file).parent if args.output else input_path.parent
    stem = Path(output_file).stem.replace('_supported', '') if args.output else input_path.stem
    fused_path = str(out_dir / f"{stem}_supported.stl") if not args.output else output_file
    supports_only_path = str(out_dir / f"{stem}_supports_only.stl")
    meta_path = str(out_dir / f"{stem}_supports_meta.json")

    emit_fused = not args.supports_only and not args.no_fused
    emit_supports_only = supports is not None

    try:
        # Fused (model + supports) STL
        if emit_fused:
            final_mesh = generator.merge_with_model(supports) if supports is not None else mesh
            final_mesh.export(fused_path)
            print(f"\nFused STL: {fused_path}")
            final_vertex_count = len(final_mesh.vertices)
            final_face_count = len(final_mesh.faces)
        else:
            final_vertex_count = len(mesh.vertices)
            final_face_count = len(mesh.faces)

        # Supports-only STL (no model). Also emit the oriented bare model so
        # users dropping these into Chitubox/Lychee as two separate objects
        # don't have to re-orient by hand to make the supports align.
        if emit_supports_only:
            supports.export(supports_only_path)
            print(f"Supports-only STL: {supports_only_path}")
            if not emit_fused:
                oriented_path = str(out_dir / f"{stem}_oriented_model.stl")
                mesh.export(oriented_path)
                print(f"Oriented model STL: {oriented_path}")

        # Sidecar metadata JSON
        if supports is not None and generator.contact_metadata:
            import json
            meta = {
                'input': str(args.input),
                'front_axis': front_axis.tolist() if front_axis is not None else None,
                'front_axis_label': front_axis_label,
                'strict_front': bool(args.strict_front),
                'support_count': len(generator.contact_metadata),
                'support_volume_mm3': float(supports.volume),
                'contacts': generator.contact_metadata,
            }
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            print(f"Metadata: {meta_path}")

        # Preview PNG
        if supports is not None and not args.no_preview:
            preview_path = args.preview_image or str(out_dir / f"{stem}_preview.png")
            try:
                from render_preview import render_support_preview
                render_support_preview(
                    mesh,
                    generator.contact_metadata,
                    preview_path,
                    front_axis=front_axis,
                )
                print(f"Preview PNG: {preview_path}")
            except Exception as e:
                print(f"  Preview render failed: {e}")

        # Print final statistics
        print("\n" + "="*60)
        print("Summary")
        print("="*60)
        print(f"Input file: {args.input}")
        print(f"Support points generated: {len(all_support_points)}")
        if supports is not None:
            print(f"Support volume: {supports.volume:.2f} mm³")
            print(f"Estimated support resin: {supports.volume / 1000:.2f} ml")
        print(f"Final model: {final_vertex_count} vertices, {final_face_count} faces")
        print("\n✓ Support generation complete!")
        if emit_fused and emit_supports_only:
            print("  Import the fused STL for one-click printing, or the supports-only")
            print("  STL as a second object in Chitubox/Lychee for hand-editing.")
        elif emit_supports_only:
            print("  Import the supports-only STL as a second object alongside your model.")

    except Exception as e:
        print(f"\nError exporting mesh: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
