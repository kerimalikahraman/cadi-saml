"""
Comprehensive Engineering Materials Database for CADI-SAML.
Includes structural steels, stainless, alloys, aluminum, brass, and engineering polymers.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class EngineeringMaterial:
    name: str
    category: str
    yield_strength_mpa: float  # Re / Rp0.2
    tensile_strength_mpa: float  # Rm
    elastic_modulus_gpa: float  # E
    poisson_ratio: float  # nu
    density_kg_m3: float  # rho
    shear_modulus_gpa: float  # G
    fatigue_limit_mpa: float  # sigma_D
    thermal_expansion_coeff: float  # 1e-6 / K

    @property
    def youngs_modulus_mpa(self) -> float:
        return self.elastic_modulus_gpa * 1000.0

    @property
    def youngs_modulus_gpa(self) -> float:
        return self.elastic_modulus_gpa

    @property
    def poissons_ratio(self) -> float:
        return self.poisson_ratio

    @property
    def shear_modulus_mpa(self) -> float:
        return self.shear_modulus_gpa * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "yield_strength_mpa": self.yield_strength_mpa,
            "tensile_strength_mpa": self.tensile_strength_mpa,
            "elastic_modulus_gpa": self.elastic_modulus_gpa,
            "poisson_ratio": self.poisson_ratio,
            "density_kg_m3": self.density_kg_m3,
            "shear_modulus_gpa": self.shear_modulus_gpa,
            "fatigue_limit_mpa": self.fatigue_limit_mpa,
            "thermal_expansion_coeff": self.thermal_expansion_coeff,
        }


MATERIALS: Dict[str, EngineeringMaterial] = {
    # Structural Steels
    "S235JR": EngineeringMaterial("S235JR", "Structural Steel", 235.0, 360.0, 210.0, 0.30, 7850.0, 81.0, 160.0, 12.0),
    "S355J2": EngineeringMaterial("S355J2", "Structural Steel", 355.0, 510.0, 210.0, 0.30, 7850.0, 81.0, 240.0, 12.0),
    "C45": EngineeringMaterial("C45", "Carbon Steel", 370.0, 650.0, 210.0, 0.30, 7850.0, 81.0, 290.0, 11.5),

    # Alloy & Shaft Steels
    "42CrMo4": EngineeringMaterial("42CrMo4", "Alloy Steel", 750.0, 1000.0, 210.0, 0.30, 7850.0, 81.0, 450.0, 11.2),
    "16MnCr5": EngineeringMaterial("16MnCr5", "Case Hardening Steel", 600.0, 900.0, 210.0, 0.30, 7850.0, 81.0, 400.0, 11.5),

    # Stainless Steels
    "AISI_304": EngineeringMaterial("AISI_304", "Austenitic Stainless", 230.0, 540.0, 193.0, 0.29, 7930.0, 75.0, 240.0, 17.2),
    "AISI_316L": EngineeringMaterial("AISI_316L", "Austenitic Stainless", 240.0, 580.0, 193.0, 0.29, 8000.0, 75.0, 260.0, 16.5),

    # Aluminum Alloys
    "AL_6061_T6": EngineeringMaterial("AL_6061_T6", "Aluminum Alloy", 276.0, 310.0, 68.9, 0.33, 2700.0, 26.0, 96.0, 23.6),
    "AL_7075_T6": EngineeringMaterial("AL_7075_T6", "Aerospace Aluminum", 503.0, 572.0, 71.7, 0.33, 2810.0, 26.9, 159.0, 23.4),

    # Copper Alloys
    "CuZn39Pb3": EngineeringMaterial("CuZn39Pb3", "Machining Brass", 250.0, 440.0, 102.0, 0.34, 8470.0, 37.0, 180.0, 19.8),

    # Engineering Polymers
    "POM_C": EngineeringMaterial("POM_C", "Polyacetal", 65.0, 70.0, 2.8, 0.35, 1410.0, 1.0, 35.0, 110.0),
    "PA66_GF30": EngineeringMaterial("PA66_GF30", "Glass Filled Nylon", 110.0, 175.0, 8.5, 0.35, 1360.0, 3.1, 75.0, 30.0),
}

_ALIASES: Dict[str, str] = {
    "steel": "S235JR",
    "structural_steel": "S235JR",
    "aluminum": "AL_6061_T6",
    "alu": "AL_6061_T6",
    "6061": "AL_6061_T6",
    "7075": "AL_7075_T6",
    "stainless": "AISI_304",
    "stainless304": "AISI_304",
    "inox": "AISI_304",
    "c45": "C45",
    "c45e": "C45",
    "42crmo4": "42CrMo4",
}


def get_material(name_or_key: str) -> EngineeringMaterial:
    key = name_or_key.strip().replace(" ", "_").replace("-", "_")
    for k, v in MATERIALS.items():
        if k.lower() == key.lower() or v.name.lower() == name_or_key.lower():
            return v
    if key.lower() in _ALIASES:
        return MATERIALS[_ALIASES[key.lower()]]
    raise ValueError(f"Unknown material '{name_or_key}'. Available: {list(MATERIALS.keys())}")
