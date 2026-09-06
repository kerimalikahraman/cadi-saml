"""
cadi_saml.standards.catalogs
============================
Centralized, authoritative engineering standards catalog for CADI-SAML.
Single source of truth for standard mechanical dimensions:
- DIN 1025-1: Hot-rolled I-beams (IPE 80 - IPE 600)
- ISO 7005-1 / DIN 2501: Circular mounting flanges (PN10, PN16, PN25)
- DIN 6885-1: Parallel drive keyways (Form A)
- DIN 471: External circlip / retaining ring grooves
- ISO 4200 / EN 10220: Seamless and welded steel tubes & pipes
- ISO 965-1: Metric screw thread profiles (M3 - M36)
- DIN 115 / DIN 116: Rigid flange shaft couplings
- DIN 6935: Cold bending sheet metal allowances and neutral axis K-factors

All generator scripts, macros, and contract provenance validators reference this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


CATALOG_VERSION = "2026.1"


# -----------------------------------------------------------------------------
# 1. DIN 1025-1: Hot-rolled I-beams (IPE series)
# Dimensions in mm:
# h: height, b: flange width, tw: web thickness, tf: flange thickness, r: root radius
# -----------------------------------------------------------------------------
DIN_1025_1_IPE: Dict[str, Dict[str, float]] = {
    "IPE 80": {"height": 80.0, "flange_width": 46.0, "web_thickness": 3.8, "flange_thickness": 5.2, "root_radius": 5.0},
    "IPE 100": {"height": 100.0, "flange_width": 55.0, "web_thickness": 4.1, "flange_thickness": 5.7, "root_radius": 7.0},
    "IPE 120": {"height": 120.0, "flange_width": 64.0, "web_thickness": 4.4, "flange_thickness": 6.3, "root_radius": 7.0},
    "IPE 140": {"height": 140.0, "flange_width": 73.0, "web_thickness": 4.7, "flange_thickness": 6.9, "root_radius": 7.0},
    "IPE 160": {"height": 160.0, "flange_width": 82.0, "web_thickness": 5.0, "flange_thickness": 7.4, "root_radius": 9.0},
    "IPE 180": {"height": 180.0, "flange_width": 91.0, "web_thickness": 5.3, "flange_thickness": 8.0, "root_radius": 9.0},
    "IPE 200": {"height": 200.0, "flange_width": 100.0, "web_thickness": 5.6, "flange_thickness": 8.5, "root_radius": 12.0},
    "IPE 220": {"height": 220.0, "flange_width": 110.0, "web_thickness": 5.9, "flange_thickness": 9.2, "root_radius": 12.0},
    "IPE 240": {"height": 240.0, "flange_width": 120.0, "web_thickness": 6.2, "flange_thickness": 9.8, "root_radius": 15.0},
    "IPE 270": {"height": 270.0, "flange_width": 135.0, "web_thickness": 6.6, "flange_thickness": 10.2, "root_radius": 15.0},
    "IPE 300": {"height": 300.0, "flange_width": 150.0, "web_thickness": 7.1, "flange_thickness": 10.7, "root_radius": 15.0},
    "IPE 330": {"height": 330.0, "flange_width": 160.0, "web_thickness": 7.5, "flange_thickness": 11.5, "root_radius": 18.0},
    "IPE 360": {"height": 360.0, "flange_width": 170.0, "web_thickness": 8.0, "flange_thickness": 12.7, "root_radius": 18.0},
    "IPE 400": {"height": 400.0, "flange_width": 180.0, "web_thickness": 8.6, "flange_thickness": 13.5, "root_radius": 21.0},
}


# -----------------------------------------------------------------------------
# 2. ISO 7005-1 / DIN 2501: Circular Mounting Flanges
# Dimensions in mm:
# outer_diameter, thickness, inner_bore, bolt_pcd, bolt_count, bolt_diameter
# -----------------------------------------------------------------------------
ISO_7005_1_FLANGES: Dict[str, Dict[str, float]] = {
    "ISO 7005-1 PN10 DN20": {"outer_diameter": 100.0, "thickness": 10.0, "inner_bore": 25.0, "bolt_pcd": 70.0, "bolt_count": 4, "bolt_diameter": 9.0},
    "ISO 7005-1 PN16 DN25": {"outer_diameter": 120.0, "thickness": 12.0, "inner_bore": 30.0, "bolt_pcd": 80.0, "bolt_count": 4, "bolt_diameter": 9.0},
    "ISO 7005-1 PN16 DN32": {"outer_diameter": 140.0, "thickness": 15.0, "inner_bore": 40.0, "bolt_pcd": 100.0, "bolt_count": 6, "bolt_diameter": 11.0},
    "DIN 2501 PN16 DN40": {"outer_diameter": 160.0, "thickness": 16.0, "inner_bore": 50.0, "bolt_pcd": 120.0, "bolt_count": 6, "bolt_diameter": 14.0},
    "DIN 2501 PN16 DN50": {"outer_diameter": 180.0, "thickness": 18.0, "inner_bore": 60.0, "bolt_pcd": 135.0, "bolt_count": 8, "bolt_diameter": 14.0},
    "ISO 7005-1 PN25 DN65": {"outer_diameter": 200.0, "thickness": 20.0, "inner_bore": 70.0, "bolt_pcd": 150.0, "bolt_count": 8, "bolt_diameter": 18.0},
    "ISO 7005-1 PN25 DN80": {"outer_diameter": 215.0, "thickness": 22.0, "inner_bore": 85.0, "bolt_pcd": 160.0, "bolt_count": 8, "bolt_diameter": 18.0},
    "ISO 7005-1 PN25 DN100": {"outer_diameter": 235.0, "thickness": 24.0, "inner_bore": 105.0, "bolt_pcd": 190.0, "bolt_count": 8, "bolt_diameter": 22.0},
}


# -----------------------------------------------------------------------------
# 3. DIN 6885-1: Parallel Drive Keyways (Form A)
# Shaft diameter ranges mapped to standard keyway width, depth (shaft t1), depth (hub t2)
# -----------------------------------------------------------------------------
DIN_6885_1_KEYWAYS: Dict[str, Dict[str, float]] = {
    "d8_10": {"shaft_d_min": 8.0, "shaft_d_max": 10.0, "key_width": 3.0, "key_depth": 1.8, "key_height": 3.0, "shaft_depth": 1.8, "hub_depth": 1.4},
    "d10_12": {"shaft_d_min": 10.0, "shaft_d_max": 12.0, "key_width": 4.0, "key_depth": 2.5, "key_height": 4.0, "shaft_depth": 2.5, "hub_depth": 1.8},
    "d12_17": {"shaft_d_min": 12.0, "shaft_d_max": 17.0, "key_width": 5.0, "key_depth": 3.0, "key_height": 5.0, "shaft_depth": 3.0, "hub_depth": 2.3},
    "d17_22": {"shaft_d_min": 17.0, "shaft_d_max": 22.0, "key_width": 6.0, "key_depth": 3.5, "key_height": 6.0, "shaft_depth": 3.5, "hub_depth": 2.8},
    "d22_30": {"shaft_d_min": 22.0, "shaft_d_max": 30.0, "key_width": 8.0, "key_depth": 4.0, "key_height": 7.0, "shaft_depth": 4.0, "hub_depth": 3.3},
    "d30_38": {"shaft_d_min": 30.0, "shaft_d_max": 38.0, "key_width": 10.0, "key_depth": 5.0, "key_height": 8.0, "shaft_depth": 5.0, "hub_depth": 3.3},
    "d38_44": {"shaft_d_min": 38.0, "shaft_d_max": 44.0, "key_width": 12.0, "key_depth": 5.0, "key_height": 8.0, "shaft_depth": 5.0, "hub_depth": 3.3},
    "d44_50": {"shaft_d_min": 44.0, "shaft_d_max": 50.0, "key_width": 14.0, "key_depth": 5.5, "key_height": 9.0, "shaft_depth": 5.5, "hub_depth": 3.8},
    "d50_58": {"shaft_d_min": 50.0, "shaft_d_max": 58.0, "key_width": 16.0, "key_depth": 6.0, "key_height": 10.0, "shaft_depth": 6.0, "hub_depth": 4.3},
    "d58_65": {"shaft_d_min": 58.0, "shaft_d_max": 65.0, "key_width": 18.0, "key_depth": 7.0, "key_height": 11.0, "shaft_depth": 7.0, "hub_depth": 4.4},
    "d65_75": {"shaft_d_min": 65.0, "shaft_d_max": 75.0, "key_width": 20.0, "key_depth": 7.5, "key_height": 12.0, "shaft_depth": 7.5, "hub_depth": 4.9},
}


# -----------------------------------------------------------------------------
# 3b. DIN 471: External Circlip / Retaining Ring Grooves
# -----------------------------------------------------------------------------
DIN_471_CIRCLIPS: Dict[str, Dict[str, float]] = {
    "d10": {"shaft_diameter": 10.0, "groove_width": 1.10, "groove_depth": 0.40, "ring_thickness": 1.0},
    "d15": {"shaft_diameter": 15.0, "groove_width": 1.10, "groove_depth": 0.50, "ring_thickness": 1.0},
    "d20": {"shaft_diameter": 20.0, "groove_width": 1.30, "groove_depth": 0.60, "ring_thickness": 1.2},
    "d25": {"shaft_diameter": 25.0, "groove_width": 1.30, "groove_depth": 0.65, "ring_thickness": 1.2},
    "d30": {"shaft_diameter": 30.0, "groove_width": 1.60, "groove_depth": 0.80, "ring_thickness": 1.5},
    "d40": {"shaft_diameter": 40.0, "groove_width": 1.85, "groove_depth": 1.00, "ring_thickness": 1.75},
    "d50": {"shaft_diameter": 50.0, "groove_width": 2.15, "groove_depth": 1.20, "ring_thickness": 2.0},
    "d65": {"shaft_diameter": 65.0, "groove_width": 2.65, "groove_depth": 1.50, "ring_thickness": 2.5},
    "d80": {"shaft_diameter": 80.0, "groove_width": 3.15, "groove_depth": 1.75, "ring_thickness": 3.0},
    "d100": {"shaft_diameter": 100.0, "groove_width": 3.15, "groove_depth": 2.00, "ring_thickness": 3.0},
}


# -----------------------------------------------------------------------------
# 4. ISO 4200 / EN 10220: Seamless and Welded Steel Tubes & Pipes
# Dimensions in mm:
# outer_diameter, wall_thickness, min_bend_radius
# -----------------------------------------------------------------------------
ISO_4200_PIPING: Dict[str, Dict[str, float]] = {
    "DN10": {"outer_diameter": 17.2, "outer_dia": 17.2, "wall_thickness": 1.8, "bend_radius": 30.0},
    "DN15": {"outer_diameter": 21.3, "outer_dia": 21.3, "wall_thickness": 2.0, "bend_radius": 35.0},
    "DN20": {"outer_diameter": 26.9, "outer_dia": 26.9, "wall_thickness": 2.3, "bend_radius": 40.0},
    "DN25": {"outer_diameter": 33.7, "outer_dia": 33.7, "wall_thickness": 2.6, "bend_radius": 50.0},
    "DN32": {"outer_diameter": 42.4, "outer_dia": 42.4, "wall_thickness": 2.6, "bend_radius": 65.0},
    "DN40": {"outer_diameter": 48.3, "outer_dia": 48.3, "wall_thickness": 2.9, "bend_radius": 75.0},
    "DN50": {"outer_diameter": 60.3, "outer_dia": 60.3, "wall_thickness": 2.9, "bend_radius": 90.0},
    "DN65": {"outer_diameter": 76.1, "outer_dia": 76.1, "wall_thickness": 2.9, "bend_radius": 115.0},
    "DN80": {"outer_diameter": 88.9, "outer_dia": 88.9, "wall_thickness": 3.2, "bend_radius": 135.0},
    "DN100": {"outer_diameter": 114.3, "outer_dia": 114.3, "wall_thickness": 3.6, "bend_radius": 170.0},
    # Metric hydraulic line series (OD based)
    "HYDRO_18": {"outer_diameter": 18.0, "outer_dia": 18.0, "wall_thickness": 1.5, "bend_radius": 30.0},
    "HYDRO_20": {"outer_diameter": 20.0, "outer_dia": 20.0, "wall_thickness": 2.0, "bend_radius": 35.0},
    "HYDRO_25": {"outer_diameter": 25.0, "outer_dia": 25.0, "wall_thickness": 2.5, "bend_radius": 40.0},
    "HYDRO_28": {"outer_diameter": 28.0, "outer_dia": 28.0, "wall_thickness": 2.5, "bend_radius": 45.0},
    "HYDRO_32": {"outer_diameter": 32.0, "outer_dia": 32.0, "wall_thickness": 3.0, "bend_radius": 50.0},
    "HYDRO_38": {"outer_diameter": 38.0, "outer_dia": 38.0, "wall_thickness": 3.5, "bend_radius": 60.0},
}


# -----------------------------------------------------------------------------
# 5. ISO 965-1: Metric Screw Thread Profiles
# nominal diameter d, standard coarse pitch p, tap drill diameter, clearance hole
# -----------------------------------------------------------------------------
ISO_965_1_THREADS: Dict[str, Dict[str, float]] = {
    "M3": {"nominal_dia": 3.0, "pitch": 0.5, "tap_drill": 2.5, "clearance_hole": 3.4, "clearance_fine": 3.2, "clearance_medium": 3.4},
    "M4": {"nominal_dia": 4.0, "pitch": 0.7, "tap_drill": 3.3, "clearance_hole": 4.5, "clearance_fine": 4.3, "clearance_medium": 4.5},
    "M5": {"nominal_dia": 5.0, "pitch": 0.8, "tap_drill": 4.2, "clearance_hole": 5.5, "clearance_fine": 5.3, "clearance_medium": 5.5},
    "M6": {"nominal_dia": 6.0, "pitch": 1.0, "tap_drill": 5.0, "clearance_hole": 6.6, "clearance_fine": 6.4, "clearance_medium": 6.6},
    "M8": {"nominal_dia": 8.0, "pitch": 1.25, "tap_drill": 6.8, "clearance_hole": 9.0, "clearance_fine": 8.4, "clearance_medium": 9.0},
    "M10": {"nominal_dia": 10.0, "pitch": 1.5, "tap_drill": 8.5, "clearance_hole": 11.0, "clearance_fine": 10.5, "clearance_medium": 11.0},
    "M12": {"nominal_dia": 12.0, "pitch": 1.75, "tap_drill": 10.2, "clearance_hole": 13.5, "clearance_fine": 13.0, "clearance_medium": 13.5},
    "M14": {"nominal_dia": 14.0, "pitch": 2.0, "tap_drill": 12.0, "clearance_hole": 15.5, "clearance_fine": 15.0, "clearance_medium": 15.5},
    "M16": {"nominal_dia": 16.0, "pitch": 2.0, "tap_drill": 14.0, "clearance_hole": 17.5, "clearance_fine": 17.0, "clearance_medium": 17.5},
    "M20": {"nominal_dia": 20.0, "pitch": 2.5, "tap_drill": 17.5, "clearance_hole": 22.0, "clearance_fine": 21.0, "clearance_medium": 22.0},
    "M24": {"nominal_dia": 24.0, "pitch": 3.0, "tap_drill": 21.0, "clearance_hole": 26.0, "clearance_fine": 25.0, "clearance_medium": 26.0},
}


# -----------------------------------------------------------------------------
# 6. DIN 115: Rigid Flange Shaft Couplings
# Dimensions in mm:
# shaft_diameter, outer_diameter, length, bolt_count, bolt_diameter, bolt_pcd, flange_thickness
# -----------------------------------------------------------------------------
DIN_115_COUPLINGS: Dict[str, Dict[str, float]] = {
    "DIN 115 d20": {"shaft_diameter": 20.0, "outer_diameter": 80.0, "length": 50.0, "total_length": 50.0, "bolt_count": 4, "bolt_diameter": 8.0, "bolt_dia": 8.0, "bolt_pcd": 60.0, "flange_thickness": 10.0},
    "DIN 115 d22": {"shaft_diameter": 22.0, "outer_diameter": 85.0, "length": 55.0, "total_length": 55.0, "bolt_count": 4, "bolt_diameter": 8.0, "bolt_dia": 8.0, "bolt_pcd": 64.0, "flange_thickness": 11.0},
    "DIN 115 d25": {"shaft_diameter": 25.0, "outer_diameter": 90.0, "length": 60.0, "total_length": 60.0, "bolt_count": 4, "bolt_diameter": 10.0, "bolt_dia": 10.0, "bolt_pcd": 67.5, "flange_thickness": 12.0},
    "DIN 115 d30": {"shaft_diameter": 30.0, "outer_diameter": 110.0, "length": 75.0, "total_length": 75.0, "bolt_count": 4, "bolt_diameter": 12.0, "bolt_dia": 12.0, "bolt_pcd": 82.5, "flange_thickness": 14.0},
    "DIN 115 d35": {"shaft_diameter": 35.0, "outer_diameter": 125.0, "length": 85.0, "total_length": 85.0, "bolt_count": 6, "bolt_diameter": 12.0, "bolt_dia": 12.0, "bolt_pcd": 95.0, "flange_thickness": 16.0},
    "DIN 115 d40": {"shaft_diameter": 40.0, "outer_diameter": 140.0, "length": 100.0, "total_length": 100.0, "bolt_count": 6, "bolt_diameter": 14.0, "bolt_dia": 14.0, "bolt_pcd": 105.0, "flange_thickness": 18.0},
}


# -----------------------------------------------------------------------------
# 7. DIN 6935: Sheet Metal Bending Parameters
# thickness -> default inner bend radius, neutral line K-factor
# -----------------------------------------------------------------------------
DIN_6935_SHEET_METAL: Dict[str, Dict[str, float]] = {
    "t1.0": {"thickness": 1.0, "inner_radius": 1.5, "k_factor": 0.45},
    "t1.5": {"thickness": 1.5, "inner_radius": 2.5, "k_factor": 0.45},
    "t1.8": {"thickness": 1.8, "inner_radius": 3.0, "k_factor": 0.45},
    "t2.0": {"thickness": 2.0, "inner_radius": 3.0, "k_factor": 0.45},
    "t2.5": {"thickness": 2.5, "inner_radius": 4.0, "k_factor": 0.45},
    "t3.0": {"thickness": 3.0, "inner_radius": 5.0, "k_factor": 0.45},
    "t4.0": {"thickness": 4.0, "inner_radius": 6.0, "k_factor": 0.45},
}


# Master catalog registry
CATALOG_REGISTRY: Dict[str, Dict[str, Dict[str, float]]] = {
    "DIN_1025_1_IPE": DIN_1025_1_IPE,
    "ISO_7005_1_FLANGES": ISO_7005_1_FLANGES,
    "DIN_6885_1_KEYWAYS": DIN_6885_1_KEYWAYS,
    "DIN_471_CIRCLIPS": DIN_471_CIRCLIPS,
    "ISO_4200_PIPING": ISO_4200_PIPING,
    "ISO_965_1_THREADS": ISO_965_1_THREADS,
    "DIN_115_COUPLINGS": DIN_115_COUPLINGS,
    "DIN_6935_SHEET_METAL": DIN_6935_SHEET_METAL,
}


# Metadata and Schema per catalog family
CATALOG_METADATA: Dict[str, Dict[str, Any]] = {
    "DIN_1025_1_IPE": {
        "standard_name": "DIN 1025-1",
        "description": "Hot-rolled I-beams (IPE series)",
        "catalog_version": CATALOG_VERSION,
        "units": {"height": "mm", "flange_width": "mm", "web_thickness": "mm", "flange_thickness": "mm", "root_radius": "mm"},
        "valid_parameters": ["height", "flange_width", "web_thickness", "flange_thickness", "root_radius"],
        "source_ref_prefix": "DIN 1025-1",
    },
    "ISO_7005_1_FLANGES": {
        "standard_name": "ISO 7005-1 / DIN 2501",
        "description": "Circular mounting flanges (PN10, PN16, PN25)",
        "catalog_version": CATALOG_VERSION,
        "units": {"outer_diameter": "mm", "thickness": "mm", "inner_bore": "mm", "bolt_pcd": "mm", "bolt_count": "int", "bolt_diameter": "mm"},
        "valid_parameters": ["outer_diameter", "thickness", "inner_bore", "bolt_pcd", "bolt_count", "bolt_diameter"],
        "source_ref_prefix": "ISO 7005-1",
    },
    "DIN_6885_1_KEYWAYS": {
        "standard_name": "DIN 6885-1",
        "description": "Parallel drive keyways (Form A)",
        "catalog_version": CATALOG_VERSION,
        "units": {"shaft_d_min": "mm", "shaft_d_max": "mm", "key_width": "mm", "key_depth": "mm", "key_height": "mm", "shaft_depth": "mm", "hub_depth": "mm"},
        "valid_parameters": ["key_width", "key_depth", "key_height", "shaft_depth", "hub_depth"],
        "source_ref_prefix": "DIN 6885-1",
    },
    "DIN_471_CIRCLIPS": {
        "standard_name": "DIN 471",
        "description": "External circlip / retaining ring grooves",
        "catalog_version": CATALOG_VERSION,
        "units": {"shaft_diameter": "mm", "groove_width": "mm", "groove_depth": "mm", "ring_thickness": "mm"},
        "valid_parameters": ["groove_width", "groove_depth", "ring_thickness"],
        "source_ref_prefix": "DIN 471",
    },
    "ISO_4200_PIPING": {
        "standard_name": "ISO 4200 / EN 10220",
        "description": "Seamless and welded steel tubes & pipes",
        "catalog_version": CATALOG_VERSION,
        "units": {"outer_diameter": "mm", "wall_thickness": "mm", "bend_radius": "mm"},
        "valid_parameters": ["outer_diameter", "outer_dia", "wall_thickness", "bend_radius"],
        "source_ref_prefix": "ISO 4200",
    },
    "ISO_965_1_THREADS": {
        "standard_name": "ISO 965-1",
        "description": "Metric screw thread profiles",
        "catalog_version": CATALOG_VERSION,
        "units": {"nominal_dia": "mm", "pitch": "mm", "tap_drill": "mm", "clearance_hole": "mm"},
        "valid_parameters": ["nominal_dia", "pitch", "tap_drill", "clearance_hole"],
        "source_ref_prefix": "ISO 965-1",
    },
    "DIN_115_COUPLINGS": {
        "standard_name": "DIN 115",
        "description": "Rigid flange shaft couplings",
        "catalog_version": CATALOG_VERSION,
        "units": {"shaft_diameter": "mm", "outer_diameter": "mm", "length": "mm", "bolt_count": "int", "bolt_diameter": "mm", "bolt_pcd": "mm", "flange_thickness": "mm"},
        "valid_parameters": ["shaft_diameter", "outer_diameter", "length", "bolt_count", "bolt_diameter", "bolt_pcd", "flange_thickness"],
        "source_ref_prefix": "DIN 115",
    },
    "DIN_6935_SHEET_METAL": {
        "standard_name": "DIN 6935",
        "description": "Cold bending sheet metal allowances and neutral axis K-factors",
        "catalog_version": CATALOG_VERSION,
        "units": {"thickness": "mm", "inner_radius": "mm", "k_factor": "ratio"},
        "valid_parameters": ["thickness", "inner_radius", "k_factor"],
        "source_ref_prefix": "DIN 6935",
    },
}


def lookup_catalog(standard_name: str, designation: str) -> Optional[Dict[str, float]]:
    """
    Look up standard entry in the registered engineering catalogs.
    """
    cat = CATALOG_REGISTRY.get(standard_name)
    if not cat:
        # Try normalized lookup (remove hyphens, spaces, convert to lower)
        norm_std = standard_name.lower().replace("-", "").replace("_", "").replace(" ", "").replace(".", "")
        for k, v in CATALOG_REGISTRY.items():
            k_norm = k.lower().replace("-", "").replace("_", "").replace(" ", "").replace(".", "")
            if norm_std in k_norm or k_norm in norm_std:
                cat = v
                break
    if not cat:
        return None
    
    res = cat.get(designation)
    if res:
        return res
    # Try normalized lookup
    clean_des = designation.strip().upper()
    for k, v in cat.items():
        if k.strip().upper() == clean_des or clean_des in k.strip().upper():
            return v
    return None


def get_catalog_metadata(standard_name: str) -> Optional[Dict[str, Any]]:
    """Returns official metadata for a standard family."""
    for k, meta in CATALOG_METADATA.items():
        if k.lower() == standard_name.lower() or meta["standard_name"].lower() == standard_name.lower():
            return meta
    norm = standard_name.lower().replace("-", "").replace("_", "").replace(" ", "")
    for k, meta in CATALOG_METADATA.items():
        k_norm = k.lower().replace("-", "").replace("_", "").replace(" ", "")
        if norm in k_norm or k_norm in norm:
            return meta
    return None


def validate_catalog_parameter(
    standard_name: str,
    designation: str,
    parameter: str,
    value: float,
    tolerance: float = 0.05,
) -> bool:
    """Validate that a parameter strictly matches the catalog value."""
    entry = lookup_catalog(standard_name, designation)
    if not entry:
        return False
    expected = entry.get(parameter)
    if expected is None:
        return False
    return abs(float(value) - float(expected)) <= tolerance


def lookup_din_6885(shaft_dia: float) -> Tuple[float, float, float, float]:
    """Returns (b, h, t1, t2) for a given shaft diameter in DIN 6885-1 Form A."""
    from ..core.exceptions import CADISpecificationError
    sd = float(shaft_dia)
    if sd < 6.0:
        raise CADISpecificationError(
            f"DIN 6885 parallel keyways are defined for shafts >= 6mm. Received diameter: {sd}mm.",
            parameter="shaft_diameter",
            suggested_fix="For shafts under 6mm, use set screws, D-cut shafts, or pins instead of parallel keyways.",
        )
    for des, spec in DIN_6885_1_KEYWAYS.items():
        if spec["shaft_d_min"] <= sd <= spec["shaft_d_max"] + 1e-6:
            return spec["key_width"], spec["key_height"], spec["shaft_depth"], spec["hub_depth"]
    if sd > 75.0:
        return 22.0, 14.0, 9.0, 5.4
    raise CADISpecificationError(
        f"Shaft diameter {sd}mm not found in DIN 6885-1 tables.",
        parameter="shaft_diameter",
    )


def lookup_din_471(shaft_dia: float) -> Tuple[float, float, float]:
    """Returns (groove_width_m, groove_depth_t, ring_thickness_s) in DIN 471."""
    # Find closest entry <= shaft_dia
    matching = None
    for des, spec in sorted(DIN_471_CIRCLIPS.items(), key=lambda x: x[1]["shaft_diameter"]):
        if shaft_dia <= spec["shaft_diameter"] + 1e-6:
            matching = spec
            break
    if matching is None:
        matching = list(DIN_471_CIRCLIPS.values())[-1]
    return matching["groove_width"], matching["groove_depth"], matching["ring_thickness"]


def find_standard_by_source_ref(source_ref: str) -> Optional[Dict[str, float]]:
    """
    Resolve a free-form source reference string like 'DIN 1025-1 IPE 80' to catalog values.
    """
    norm = source_ref.strip()

    # 1. Exact or substring match across all catalogs (longest designation first)
    for cat_name, cat in CATALOG_REGISTRY.items():
        for des, data in sorted(cat.items(), key=lambda x: len(x[0]), reverse=True):
            if des in norm or norm in des:
                return data

    # 2. Specific family heuristics with exact size matching
    if "1025" in norm or "IPE" in norm:
        for des, data in sorted(DIN_1025_1_IPE.items(), key=lambda x: len(x[0]), reverse=True):
            if des in norm:
                return data
    if "7005" in norm or "2501" in norm or "PN" in norm or "DN" in norm:
        for des, data in sorted(ISO_7005_1_FLANGES.items(), key=lambda x: len(x[0]), reverse=True):
            parts = des.split()
            dn_part = [p for p in parts if p.startswith("DN")]
            if dn_part and dn_part[0] in norm:
                return data
            if des in norm:
                return data
    if "6885" in norm:
        for des, data in DIN_6885_1_KEYWAYS.items():
            if des in norm:
                return data
    if "471" in norm:
        for des, data in DIN_471_CIRCLIPS.items():
            if des in norm:
                return data
    if "4200" in norm or "HYDRO" in norm:
        for des, data in sorted(ISO_4200_PIPING.items(), key=lambda x: len(x[0]), reverse=True):
            if des in norm:
                return data
    if "965" in norm or norm.startswith("M"):
        for des, data in sorted(ISO_965_1_THREADS.items(), key=lambda x: len(x[0]), reverse=True):
            if des in norm:
                return data
    if "115" in norm:
        for des, data in sorted(DIN_115_COUPLINGS.items(), key=lambda x: len(x[0]), reverse=True):
            if des in norm or f"d{int(data['shaft_diameter'])}" in norm:
                return data
    if "6935" in norm:
        for des, data in DIN_6935_SHEET_METAL.items():
            if des in norm:
                return data
    return None
