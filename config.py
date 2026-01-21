"""
Configuration for the Battlefield Support Generator
Default values optimized for Anycubic Photon Mono 4 with Elegoo ABS-Like V3+ resin
"""

class PrinterConfig:
    """Printer-specific configuration"""

    # Anycubic Photon Mono 4 specifications
    PRINTER_NAME = "Anycubic Photon Mono 4"

    # Resolution
    RESOLUTION_X = 9024  # pixels
    RESOLUTION_Y = 5120  # pixels
    XY_RESOLUTION = 0.017  # mm (17 microns)

    # Build volume (mm)
    BUILD_VOLUME_X = 153.4
    BUILD_VOLUME_Y = 87.0
    BUILD_VOLUME_Z = 165.0

    # Layer settings
    DEFAULT_LAYER_HEIGHT = 0.05  # mm (50 microns)
    MIN_LAYER_HEIGHT = 0.01
    MAX_LAYER_HEIGHT = 0.1


class ResinConfig:
    """Resin-specific configuration"""

    # Elegoo ABS-Like V3+ properties
    RESIN_NAME = "Elegoo ABS-Like V3+"

    # Mechanical properties
    TENSILE_STRENGTH = 50.0  # MPa (conservative middle value)
    ELONGATION_AT_BREAK = 10.0  # % (typical for ABS-like)
    FLEXURAL_STRENGTH = 70.0  # MPa

    # Curing properties
    UV_WAVELENGTH = 405  # nm

    # Print strength factors (partially cured resin is weaker)
    PARTIAL_CURE_STRENGTH_FACTOR = 0.3  # 30% of full strength during printing


class SupportConfig:
    """Support generation configuration"""

    # Support geometry - tiered system for detail preservation
    # Light supports: for fine details, high-curvature areas
    SUPPORT_TIP_DIAMETER_LIGHT = 0.2  # mm - minimal contact for delicate details
    SUPPORT_BASE_DIAMETER_LIGHT = 0.6  # mm - thinner support body

    # Medium supports: standard overhangs
    SUPPORT_TIP_DIAMETER_MEDIUM = 0.3  # mm - standard contact point
    SUPPORT_BASE_DIAMETER_MEDIUM = 0.8  # mm - standard support body

    # Heavy supports: structural, large horizontal areas, low islands
    SUPPORT_TIP_DIAMETER_HEAVY = 0.4  # mm - larger contact for stability
    SUPPORT_BASE_DIAMETER_HEAVY = 1.0  # mm - thicker support body

    # Default (for backwards compatibility)
    SUPPORT_TIP_DIAMETER = 0.3  # mm - minimal contact point
    SUPPORT_BASE_DIAMETER = 0.8  # mm - reduced from 1.0mm for less scarring
    SUPPORT_MAX_DIAMETER = 1.0  # mm - absolute maximum for any support element
    SUPPORT_TAPER_ANGLE = 7.0  # degrees

    # Lattice tower configuration
    LATTICE_TOWER_ENABLED = True  # Use lattice towers to consolidate support roots
    LATTICE_STRUT_DIAMETER = 0.6  # mm - reduced from 0.8mm
    LATTICE_MAIN_DIAMETER = 0.8  # mm - reduced from 1.0mm
    LATTICE_SPACING = 10.0  # mm - increased from 8mm for fewer towers
    LATTICE_MAX_CLUSTER_SIZE = 25  # reduced from 30 for smaller towers
    LATTICE_MIN_CLUSTER_SIZE = 6  # increased from 5 to reduce small towers
    LATTICE_BRACE_ANGLE = 60.0  # degrees - angle of diagonal braces

    # Collision avoidance and routing
    COLLISION_CHECK_ENABLED = True  # Check for collisions with model
    COLLISION_RESOLUTION = 0.5  # mm - resolution for collision checking
    ROUTING_STEP_SIZE = 0.5  # mm - step size for pathfinding
    MAX_ROUTING_ANGLE = 30.0  # degrees - maximum bend angle per segment
    LATERAL_ROUTING_ENABLED = True  # Allow supports to route laterally

    # Detection thresholds - optimized for modern resins
    MAX_BRIDGE_LENGTH = 6.0  # mm - increased from 5mm (ABS-like resins handle this)
    MAX_OVERHANG_ANGLE = 50.0  # degrees from vertical - increased from 45 (resin self-supports better)
    MIN_ISLAND_AREA = 0.8  # mm² - increased from 0.5 (tiny islands often print fine)

    # Support density - optimized for miniatures
    SUPPORT_SPACING = 4.0  # mm - increased from 3mm for less density
    EDGE_SUPPORT_SPACING = 2.5  # mm - increased from 2mm

    # Safety margins
    SAFETY_MARGIN = 1.0  # reduced from 1.2 - modern resins don't need 20% extra
    MIN_SUPPORT_HEIGHT = 1.0  # mm - minimum support height

    # Auto-orientation preferences
    PREFER_FLAT_BASE = True  # prefer orientation with large flat bottom
    MINIMIZE_SUPPORT_AREA = True  # minimize total support contact area
    PREFER_HIDDEN_SUPPORTS = True  # prefer supports on less visible surfaces

    # Optimization settings
    OPTIMIZATION_ENABLED = True  # Enable support point optimization
    MERGE_RADIUS = 1.5  # mm - merge support points closer than this
    DETAIL_CURVATURE_THRESHOLD = 0.5  # Curvature threshold for detail detection
    THIN_FEATURE_THRESHOLD = 2.0  # mm - thickness below this is considered "thin"


class AnalysisConfig:
    """Analysis and detection configuration"""

    # Slicing
    SLICE_LAYER_HEIGHT = 0.05  # mm

    # Island detection
    MIN_ISLAND_PERIMETER = 1.0  # mm
    ISLAND_CONNECTION_TOLERANCE = 0.2  # mm - how close to be "connected"

    # Overhang detection
    OVERHANG_SAMPLE_DISTANCE = 0.5  # mm - sampling resolution
    OVERHANG_MIN_AREA = 1.0  # mm² - minimum overhang area to support

    # Bridge detection
    BRIDGE_SAMPLE_POINTS = 20  # number of points to sample along potential bridges
    BRIDGE_MIN_LENGTH = 1.0  # mm - minimum bridge length to consider

    # Mesh analysis
    MESH_REPAIR = True  # attempt to repair non-manifold meshes
    MERGE_TOLERANCE = 0.001  # mm - tolerance for merging nearby vertices


def get_config():
    """Get default configuration as dictionary"""
    return {
        'printer': {
            'name': PrinterConfig.PRINTER_NAME,
            'resolution': {
                'x': PrinterConfig.RESOLUTION_X,
                'y': PrinterConfig.RESOLUTION_Y,
                'xy': PrinterConfig.XY_RESOLUTION
            },
            'build_volume': {
                'x': PrinterConfig.BUILD_VOLUME_X,
                'y': PrinterConfig.BUILD_VOLUME_Y,
                'z': PrinterConfig.BUILD_VOLUME_Z
            },
            'layer_height': PrinterConfig.DEFAULT_LAYER_HEIGHT
        },
        'resin': {
            'name': ResinConfig.RESIN_NAME,
            'tensile_strength': ResinConfig.TENSILE_STRENGTH,
            'partial_cure_factor': ResinConfig.PARTIAL_CURE_STRENGTH_FACTOR
        },
        'supports': {
            'tip_diameter': SupportConfig.SUPPORT_TIP_DIAMETER,
            'base_diameter': SupportConfig.SUPPORT_BASE_DIAMETER,
            'taper_angle': SupportConfig.SUPPORT_TAPER_ANGLE,
            'max_bridge': SupportConfig.MAX_BRIDGE_LENGTH,
            'max_overhang_angle': SupportConfig.MAX_OVERHANG_ANGLE,
            'min_island_area': SupportConfig.MIN_ISLAND_AREA,
            'spacing': SupportConfig.SUPPORT_SPACING,
            'edge_spacing': SupportConfig.EDGE_SUPPORT_SPACING
        },
        'analysis': {
            'layer_height': AnalysisConfig.SLICE_LAYER_HEIGHT,
            'mesh_repair': AnalysisConfig.MESH_REPAIR
        }
    }
