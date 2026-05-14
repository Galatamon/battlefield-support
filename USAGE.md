# Usage Guide

## Quick Start

The simplest way to use the tool:

```bash
python support_generator_cli.py your_model.stl
```

This will:
1. Load your STL file
2. Auto-detect the mech's "front" face (the side that must stay scar-free)
3. Auto-orient it for optimal printing (canonical mech poses only)
4. Detect islands, overhangs, and bridges
5. Generate minimal support structures, avoiding the front face
6. Output:
   - `your_model_supported.stl` — fused (model + supports) for one-click printing
   - `your_model_supports_only.stl` — supports as a separate object for hand-editing in Chitubox/Lychee
   - `your_model_supports_meta.json` — per-contact metadata (tier, face class, tip radius)
   - `your_model_preview.png` — visual preview showing where supports land (green=front, yellow=side, blue=back)

## BattleTech-specific Flags

```bash
# Tell the tool which direction the mech's visible front points.
# Default is "auto" — uses a heuristic on the mid-Z face areas. Pass the
# explicit axis when auto-detect is ambiguous (warning printed when this happens).
# NOTE: argparse needs the "=" form for negative axes: --front=-Y
python support_generator_cli.py model.stl --front +Y
python support_generator_cli.py model.stl --front=-Y

# Strict-front: skip front-face overhangs that the resin can self-bridge
# (span < 3mm by default) instead of snapping them off to the nearest
# non-front edge. Use this when ANY support scar on the front is unacceptable.
python support_generator_cli.py model.stl --front +Y --strict-front

# Override the micro-tier tip diameter (default 0.15mm). Used for sub-0.5mm
# features (antennae, weapon-barrel tips). Smaller = harder to clean off,
# but leaves no visible scar.
python support_generator_cli.py model.stl --micro-tip 0.12

# Only emit the supports-only STL (skip the fused output). Useful when you
# want to hand-edit supports in Chitubox/Lychee before slicing. The tool will
# also emit `<stem>_oriented_model.stl` so you can drop both into the slicer
# with correct alignment.
python support_generator_cli.py model.stl --supports-only

# Skip the preview PNG (faster on large models)
python support_generator_cli.py model.stl --no-preview
```

## Basic Usage

### Specify Output File

```bash
python support_generator.py input.stl -o output_with_supports.stl
```

### Disable Auto-Orientation

If you want to keep your model's current orientation:

```bash
python support_generator.py model.stl --no-auto-orient
```

## Advanced Options

### Adjust Support Parameters

```bash
# Smaller support tips for finer details (default: 0.3mm)
python support_generator.py model.stl --support-tip 0.2

# Allow longer bridges (default: 5.0mm)
python support_generator.py model.stl --max-bridge 7.0

# More aggressive overhang detection (default: 45°)
python support_generator.py model.stl --overhang-angle 40
```

### Layer Height

Adjust slicing layer height for analysis:

```bash
python support_generator.py model.stl --layer-height 0.05
```

### Selective Detection

Disable specific detection types:

```bash
# Skip island detection (use when model has no overhangs)
python support_generator.py model.stl --no-islands

# Skip overhang detection
python support_generator.py model.stl --no-overhangs

# Skip bridge detection
python support_generator.py model.stl --no-bridges
```

### Orientation Testing

Test more orientations for better results (default: 20):

```bash
python support_generator.py model.stl --orientation-samples 50
```

More samples = better orientation but slower processing.

## Configuration

View current configuration:

```bash
python support_generator.py --show-config
```

## Examples for Battletech Miniatures

### Standard Battletech Mech

```bash
python support_generator.py atlas_mech.stl \
    --support-tip 0.25 \
    --overhang-angle 45 \
    --max-bridge 5.0
```

This uses very small support tips to minimize scarring on visible surfaces.

### Vehicle with Large Flat Surfaces

```bash
python support_generator.py vehicle.stl \
    --max-bridge 7.0 \
    --support-tip 0.3
```

Vehicles can often handle longer bridges due to larger flat surfaces.

### Complex Model with Fine Details

```bash
python support_generator.py detailed_mech.stl \
    --support-tip 0.2 \
    --min-island-area 0.3 \
    --overhang-angle 40
```

More aggressive support detection to ensure all small details print correctly.

### Pre-Oriented Model

If you've already oriented your model in your slicer:

```bash
python support_generator.py model.stl \
    --no-auto-orient \
    -o model_supports_only.stl
```

## Workflow Integration

### Typical Workflow

1. **Design/Download** your Battletech miniature STL
2. **Generate Supports**:
   ```bash
   python support_generator.py my_mech.stl
   ```
3. **Import to Slicer**: Open `my_mech_supported.stl` in your slicer (Chitubox, Lychee, etc.)
4. **Fine-tune**: Adjust exposure settings for your resin
5. **Slice & Print**

### Iterative Testing

Test with minimal supports first:

```bash
# Conservative approach - fewer supports
python support_generator.py model.stl \
    --max-bridge 7.0 \
    --overhang-angle 50 \
    --min-island-area 1.0
```

If print fails, increase support density:

```bash
# Aggressive approach - more supports
python support_generator.py model.stl \
    --max-bridge 4.0 \
    --overhang-angle 40 \
    --min-island-area 0.3
```

## Understanding Output

The tool will display:

- **Model Info**: Dimensions, volume, surface area
- **Orientation Score**: Lower is better
- **Island Count**: Disconnected regions found
- **Support Points**: Number of support structures
- **Support Volume**: Amount of resin used for supports
- **Final Statistics**: Total vertices and faces

Example output:
```
Model dimensions: 45.23 x 38.56 x 67.89 mm
Support points generated: 47
Support volume: 234.56 mm³
Estimated support resin: 0.23 ml
```

## Troubleshooting

### "Mesh is not watertight"

The tool will attempt automatic repair. If it fails:
1. Repair mesh in Meshmixer or Netfabb
2. Re-export as binary STL
3. Try again

### Too Many Supports

Reduce support density:
```bash
python support_generator.py model.stl \
    --max-bridge 7.0 \
    --overhang-angle 50 \
    --min-island-area 1.0
```

### Not Enough Supports / Print Fails

Increase support density:
```bash
python support_generator.py model.stl \
    --max-bridge 3.0 \
    --overhang-angle 35 \
    --support-tip 0.35
```

### Model Too Large

If model doesn't fit in build volume, the tool will warn you. Scale down in your 3D software before adding supports.

### Slow Processing

Large models with many faces take longer. Speed up by:
- Using fewer orientation samples: `--orientation-samples 10`
- Increasing layer height: `--layer-height 0.1`
- Disabling unneeded detection: `--no-bridges`

## Tips for Best Results

1. **Clean Models**: Ensure STL is manifold and error-free
2. **Appropriate Scale**: Most mechs print well at 6mm (1/285) to 8mm (1/200) scale
3. **Test Supports**: Print a test piece with your settings before committing to a full batch
4. **Post-Processing**: Remove supports carefully with flush cutters
5. **Resin Temperature**: Warm resin (25-30°C) flows better and reduces support failures
6. **Layer Exposure**: Tune your bottom layers and normal exposure for your specific resin

## Support Settings by Model Type

### Infantry (6mm scale)
```bash
--support-tip 0.2 --overhang-angle 45 --max-bridge 3.0
```

### Light/Medium Mechs (6-8mm)
```bash
--support-tip 0.25 --overhang-angle 45 --max-bridge 5.0
```

### Heavy/Assault Mechs (8mm+)
```bash
--support-tip 0.3 --overhang-angle 45 --max-bridge 6.0
```

### Vehicles
```bash
--support-tip 0.3 --overhang-angle 50 --max-bridge 7.0
```

### Aerospace Fighters
```bash
--support-tip 0.25 --overhang-angle 40 --max-bridge 4.0
```
(Aerospace typically needs more supports due to wings and tail fins)
