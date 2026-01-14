# Battlefield Support Generator

Automatic support generator for resin 3D printing Battletech miniatures and other detailed models.

## Overview

This tool automatically generates optimized support structures for resin printing, designed to:
- Minimize supports on visible/detailed areas
- Ensure successful prints by detecting islands and unsupported bridges
- Auto-orient models for optimal printing
- Use minimal contact points to preserve fine details

## Printer Configuration

Default configuration is optimized for:
- **Printer**: Anycubic Photon Mono 4
  - Resolution: 10K (9024x5120px)
  - XY Resolution: 17µm × 17µm
  - Build Volume: 153.4 × 87 × 165 mm

- **Resin**: Elegoo ABS-Like V3+
  - Tensile Strength: ~50 MPa
  - Curing: 405nm UV
  - Heat Deflection: High
  - Low viscosity for better layer adhesion

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python support_generator.py input.stl -o output.stl
```

### Options

- `-o, --output`: Output STL file with supports (default: input_supported.stl)
- `--layer-height`: Layer height in mm (default: 0.05)
- `--support-tip`: Support tip diameter in mm (default: 0.3)
- `--max-bridge`: Maximum unsupported bridge length in mm (default: 5.0)
- `--min-island-area`: Minimum island area to support in mm² (default: 0.5)
- `--overhang-angle`: Maximum overhang angle before support needed (default: 45)
- `--auto-orient`: Auto-orient model for optimal printing (default: True)
- `--config`: Custom configuration file

## How It Works

1. **Auto-Orientation**: Rotates model to minimize overhangs and place supports on less visible bottom surfaces
2. **Layer Slicing**: Simulates layer-by-layer printing to detect islands
3. **Island Detection**: Identifies disconnected regions that need support pillars
4. **Bridge Analysis**: Detects spans exceeding resin tensile strength limits
5. **Support Generation**: Creates minimal tree-like supports with small contact points
6. **STL Export**: Merges model and supports into a single STL file

## Technical Details

### Support Calculations

Based on Elegoo ABS-Like V3+ resin properties:
- **Tensile Strength**: ~50 MPa
- **Maximum Bridge Length**: 5mm (conservative for partially cured resin)
- **Minimum Support Tip**: 0.3mm (balance between adhesion and minimal scarring)
- **Overhang Threshold**: 45° (steeper angles need support)

### Island Detection

Islands are detected by:
1. Slicing model at each layer height
2. Identifying polygon regions
3. Detecting regions not connected to the build plate or previous layers
4. Calculating center of mass for support placement

### Support Structure

Supports use a cone shape:
- **Tip diameter**: 0.3mm (configurable)
- **Base diameter**: 1.5-2.0mm
- **Angle**: 5-10° taper for stability
- **Density**: Adaptive based on model weight and surface area

## Sources

Technical specifications researched from:
- [Anycubic Photon Mono 4 Specifications](https://store.anycubic.com/products/photon-mono-4)
- [Elegoo ABS-Like Resin V3.0](https://us.elegoo.com/products/elegoo-abs-like-resin-v-3-0)
- [ABS-Like Resin Technical Data](https://pmc.ncbi.nlm.nih.gov/articles/PMC10647641/)
- [SainSmart ABS-Like Technical Specs](https://www.sainsmart.com/products/sainsmart-abs-like-405nm-uv-curing-rapid-resin-low-odor-500g)

## License

See LICENSE file for details.
