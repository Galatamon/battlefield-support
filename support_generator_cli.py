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
    print(f"    Tip Diameter: {SupportConfig.SUPPORT_TIP_DIAMETER}mm")
    print(f"    Max Bridge Length: {SupportConfig.MAX_BRIDGE_LENGTH}mm")
    print(f"    Max Overhang Angle: {SupportConfig.MAX_OVERHANG_ANGLE}°")
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

    # Print configuration
    print_config_info()

    # Update config from command line
    SupportConfig.SUPPORT_TIP_DIAMETER = args.support_tip
    SupportConfig.MAX_BRIDGE_LENGTH = args.max_bridge
    SupportConfig.MIN_ISLAND_AREA = args.min_island_area
    SupportConfig.MAX_OVERHANG_ANGLE = args.overhang_angle
    AnalysisConfig.SLICE_LAYER_HEIGHT = args.layer_height

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
    if not args.no_auto_orient:
        print("\n" + "="*60)
        print("STEP 2: Auto-Orientation")
        print("="*60)

        optimizer = OrientationOptimizer(mesh)
        optimizer.apply_optimal_orientation(num_samples=args.orientation_samples)

        # Center on build plate
        loader.center_on_build_plate()

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
                max_angle=args.overhang_angle
            )
            all_support_points.extend(overhang_points)

        if not args.no_bridges:
            bridge_points = overhang_detector.detect_bridges(
                max_length=args.max_bridge
            )
            all_support_points.extend(bridge_points)

        print(overhang_detector.get_detection_summary(all_support_points))

    # Generate supports
    print("\n" + "="*60)
    print("STEP 5: Support Generation")
    print("="*60)

    generator = SupportGenerator(mesh)
    supports = generator.generate_supports(all_support_points)

    if supports is not None:
        print(generator.get_support_summary(supports))

        # Merge with model
        final_mesh = generator.merge_with_model(supports)
    else:
        print("\nNo supports needed! Model can print without supports.")
        final_mesh = mesh

    # Export
    print("\n" + "="*60)
    print("STEP 6: Export")
    print("="*60)

    try:
        final_mesh.export(output_file)
        print(f"\nSuccessfully exported to: {output_file}")

        # Print final statistics
        print("\n" + "="*60)
        print("Summary")
        print("="*60)
        print(f"Input file: {args.input}")
        print(f"Output file: {output_file}")
        print(f"Support points generated: {len(all_support_points)}")
        if supports is not None:
            print(f"Support volume: {supports.volume:.2f} mm³")
            print(f"Estimated support resin: {supports.volume / 1000:.2f} ml")
        print(f"Final model: {len(final_mesh.vertices)} vertices, {len(final_mesh.faces)} faces")
        print("\n✓ Support generation complete!")
        print("  Import the STL into your slicer and proceed with printing.")

    except Exception as e:
        print(f"\nError exporting mesh: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
