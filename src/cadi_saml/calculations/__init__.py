"""
CADI-SAML Engineering Calculations & Materials Database Package.
Provides materials lookup and mechanical engineering analytical sizing formulas.
"""

from cadi_saml.calculations.materials_db import (
    EngineeringMaterial,
    MATERIALS,
    get_material,
)
from cadi_saml.calculations.machinery_formulas import (
    calculate_shaft_diameter,
    calculate_keyway_stresses,
    calculate_bearing_l10h_life,
    calculate_bolt_preload,
    calculate_pressure_vessel_wall_thickness,
)

__all__ = [
    "EngineeringMaterial",
    "MATERIALS",
    "get_material",
    "calculate_shaft_diameter",
    "calculate_keyway_stresses",
    "calculate_bearing_l10h_life",
    "calculate_bolt_preload",
    "calculate_pressure_vessel_wall_thickness",
]
