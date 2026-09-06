"""
cadi_saml.analysis.materials
============================
Engineering materials database for structural mechanics and FEA simulation.
Units:
- Young's Modulus (E): MPa (N/mm^2)
- Poisson's Ratio (nu): dimensionless
- Yield Strength (Sy): MPa (N/mm^2)
- Ultimate Tensile Strength (Sut): MPa (N/mm^2)
- Density (rho): kg/m^3
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Material:
    """Isotropic linear elastic material specification."""
    name: str
    category: str
    youngs_modulus_mpa: float      # E in MPa (N/mm^2)
    poissons_ratio: float          # nu
    yield_strength_mpa: float      # Sy in MPa
    tensile_strength_mpa: float    # Sut in MPa
    density_kg_m3: float           # Density in kg/m^3
    description: str = ""

    @property
    def shear_modulus_mpa(self) -> float:
        """Shear Modulus G = E / (2 * (1 + nu))."""
        return self.youngs_modulus_mpa / (2.0 * (1.0 + self.poissons_ratio))


# Comprehensive mechanical engineering materials database
MATERIALS_DB: Dict[str, Material] = {
    # Structural Steels
    "S235JR": Material(
        name="S235JR",
        category="Structural Steel",
        youngs_modulus_mpa=210000.0,
        poissons_ratio=0.30,
        yield_strength_mpa=235.0,
        tensile_strength_mpa=360.0,
        density_kg_m3=7850.0,
        description="Standard European structural mild steel (EN 10025-2).",
    ),
    "S355J2": Material(
        name="S355J2",
        category="Structural Steel",
        youngs_modulus_mpa=210000.0,
        poissons_ratio=0.30,
        yield_strength_mpa=355.0,
        tensile_strength_mpa=510.0,
        density_kg_m3=7850.0,
        description="High-strength structural steel for chassis and heavy frames.",
    ),
    # Medium Carbon & Alloy Steels
    "C45E": Material(
        name="C45E",
        category="Engineering Steel",
        youngs_modulus_mpa=210000.0,
        poissons_ratio=0.30,
        yield_strength_mpa=340.0,
        tensile_strength_mpa=600.0,
        density_kg_m3=7850.0,
        description="Medium carbon unalloyed machinery steel (1.0503).",
    ),
    "42CrMo4": Material(
        name="42CrMo4",
        category="Alloy Steel",
        youngs_modulus_mpa=210000.0,
        poissons_ratio=0.28,
        yield_strength_mpa=650.0,
        tensile_strength_mpa=900.0,
        density_kg_m3=7850.0,
        description="High-toughness quenched & tempered chrome-moly steel (AISI 4140).",
    ),
    "100Cr6": Material(
        name="100Cr6",
        category="Bearing Steel",
        youngs_modulus_mpa=210000.0,
        poissons_ratio=0.30,
        yield_strength_mpa=1700.0,
        tensile_strength_mpa=2000.0,
        density_kg_m3=7830.0,
        description="High-hardness chromium ball and roller bearing steel (AISI 52100).",
    ),
    # Stainless Steels
    "Stainless304": Material(
        name="Stainless304",
        category="Stainless Steel",
        youngs_modulus_mpa=193000.0,
        poissons_ratio=0.29,
        yield_strength_mpa=215.0,
        tensile_strength_mpa=505.0,
        density_kg_m3=8000.0,
        description="Austenitic stainless steel (1.4301, AISI 304).",
    ),
    "Stainless316L": Material(
        name="Stainless316L",
        category="Stainless Steel",
        youngs_modulus_mpa=193000.0,
        poissons_ratio=0.30,
        yield_strength_mpa=220.0,
        tensile_strength_mpa=520.0,
        density_kg_m3=8000.0,
        description="Marine and chemical grade corrosion-resistant stainless steel.",
    ),
    # Aluminum Alloys
    "Alu6061-T6": Material(
        name="Alu6061-T6",
        category="Aluminum Alloy",
        youngs_modulus_mpa=68900.0,
        poissons_ratio=0.33,
        yield_strength_mpa=276.0,
        tensile_strength_mpa=310.0,
        density_kg_m3=2700.0,
        description="Precipitation-hardened aircraft/general structural aluminum.",
    ),
    "Alu7075-T6": Material(
        name="Alu7075-T6",
        category="Aluminum Alloy",
        youngs_modulus_mpa=71700.0,
        poissons_ratio=0.33,
        yield_strength_mpa=503.0,
        tensile_strength_mpa=572.0,
        density_kg_m3=2810.0,
        description="Ultra-high-strength aerospace zinc-aluminum alloy.",
    ),
    # Titanium
    "Ti6Al4V": Material(
        name="Ti6Al4V",
        category="Titanium Alloy",
        youngs_modulus_mpa=113800.0,
        poissons_ratio=0.34,
        yield_strength_mpa=880.0,
        tensile_strength_mpa=950.0,
        density_kg_m3=4430.0,
        description="Grade 5 titanium alloy for high strength-to-weight applications.",
    ),
    # Polymers
    "Delrin_POM": Material(
        name="Delrin_POM",
        category="Engineering Plastic",
        youngs_modulus_mpa=3100.0,
        poissons_ratio=0.35,
        yield_strength_mpa=65.0,
        tensile_strength_mpa=70.0,
        density_kg_m3=1420.0,
        description="Polyoxymethylene (POM-H) high-stiffness low-friction engineering plastic.",
    ),
}

# Aliases for common user designations
_ALIASES: Dict[str, str] = {
    "steel": "S235JR",
    "structural_steel": "S235JR",
    "aluminum": "Alu6061-T6",
    "alu": "Alu6061-T6",
    "6061": "Alu6061-T6",
    "7075": "Alu7075-T6",
    "titanium": "Ti6Al4V",
    "ti": "Ti6Al4V",
    "stainless": "Stainless304",
    "inox": "Stainless304",
    "c45": "C45E",
    "4140": "42CrMo4",
}


def get_material(name_or_code: str) -> Material:
    """Retrieve material specification by name, code, or common alias."""
    key = name_or_code.strip()
    if key in MATERIALS_DB:
        return MATERIALS_DB[key]

    lower_key = key.lower()
    if lower_key in _ALIASES:
        return MATERIALS_DB[_ALIASES[lower_key]]

    # Case-insensitive match
    for db_key, mat in MATERIALS_DB.items():
        if db_key.lower() == lower_key:
            return mat

    raise ValueError(f"Unknown material {name_or_code!r}. Available: {sorted(MATERIALS_DB)}")
