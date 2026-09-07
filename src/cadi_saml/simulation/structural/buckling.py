"""
cadi_saml.simulation.structural.buckling

Column stability and compressive buckling analysis using Euler and Johnson-Euler methods.
Evaluates critical buckling load, slenderness ratio, and safety factors for structural columns and struts.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from ...analysis.materials import Material, get_material


# Column effective length factors K for standard end boundary conditions:
# - pinned_pinned: K = 1.0 (both ends free to rotate)
# - fixed_free:    K = 2.0 (cantilever / flagpole)
# - fixed_pinned:  K = 0.7 (one end clamped, one pinned)
# - fixed_fixed:   K = 0.5 (both ends clamped rigidly)
END_CONDITION_K_FACTORS: Dict[str, float] = {
    "pinned_pinned": 1.0,
    "fixed_free": 2.0,
    "fixed_pinned": 0.7,
    "fixed_fixed": 0.5,
}


@dataclass
class BucklingResult:
    column_name: str
    length_mm: float
    effective_length_mm: float
    cross_section_area_mm2: float
    min_moment_of_inertia_mm4: float
    radius_of_gyration_mm: float
    slenderness_ratio: float
    critical_slenderness: float
    buckling_regime: str  # "EULER_ELASTIC" or "JOHNSON_INELASTIC"
    critical_load_n: float
    critical_stress_mpa: float
    applied_load_n: Optional[float] = None
    safety_factor: Optional[float] = None
    is_safe: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "length_mm": self.length_mm,
            "effective_length_mm": self.effective_length_mm,
            "slenderness_ratio": round(self.slenderness_ratio, 2),
            "critical_slenderness": round(self.critical_slenderness, 2),
            "buckling_regime": self.buckling_regime,
            "critical_load_n": round(self.critical_load_n, 1),
            "critical_load_kn": round(self.critical_load_n / 1e3, 2),
            "critical_stress_mpa": round(self.critical_stress_mpa, 2),
            "applied_load_n": self.applied_load_n,
            "safety_factor": round(self.safety_factor, 2) if self.safety_factor is not None else None,
            "is_safe": self.is_safe,
            "notes": self.notes,
        }


def analyze_column_buckling(
    column_name: str,
    length_mm: float,
    cross_section_type: str,  # "solid_round", "hollow_round", "solid_square", "hollow_square"
    dimensions: Dict[str, float],
    material: Union[str, Material] = "S235JR",
    end_condition: str = "pinned_pinned",
    applied_compressive_load_n: Optional[float] = None,
    required_safety_factor: float = 2.0,
) -> BucklingResult:
    """
    Calculate critical compressive buckling load using Euler/Johnson formulation.

    Parameters:
    -----------
    length_mm: Total unsupported length of column in mm.
    cross_section_type: "solid_round" (diameter), "hollow_round" (outer_dia, wall_thickness),
                        "solid_square" (width), "hollow_square" (width, wall_thickness)
    dimensions: Geometry measurements in mm.
    end_condition: 'pinned_pinned', 'fixed_free', 'fixed_pinned', 'fixed_fixed'
    applied_compressive_load_n: Compressive axial force in Newtons.
    required_safety_factor: Minimum target safety margin (default 2.0).
    """
    mat = get_material(material) if isinstance(material, str) else material
    e_mpa = mat.youngs_modulus_mpa
    sy_mpa = mat.yield_strength_mpa

    # 1. Compute Area (A) and Minimum Moment of Inertia (I_min)
    cs = cross_section_type.lower().strip()
    if cs == "solid_round":
        d = float(dimensions.get("diameter", dimensions.get("dia", 20.0)))
        area = (math.pi / 4.0) * (d ** 2)
        i_min = (math.pi / 64.0) * (d ** 4)
    elif cs in ("hollow_round", "pipe", "tube"):
        od = float(dimensions.get("outer_dia", dimensions.get("outer_diameter", 30.0)))
        wt = float(dimensions.get("wall_thickness", 2.0))
        id_d = max(0.1, od - 2.0 * wt)
        area = (math.pi / 4.0) * (od ** 2 - id_d ** 2)
        i_min = (math.pi / 64.0) * (od ** 4 - id_d ** 4)
    elif cs == "solid_square":
        w = float(dimensions.get("width", 25.0))
        h = float(dimensions.get("height", w))
        area = w * h
        i_min = (min(w, h) ** 3 * max(w, h)) / 12.0
    elif cs in ("hollow_square", "box_profile"):
        w = float(dimensions.get("width", 40.0))
        h = float(dimensions.get("height", w))
        t = float(dimensions.get("wall_thickness", 2.0))
        area = (w * h) - ((w - 2.0 * t) * (h - 2.0 * t))
        i_min = ((w * h**3) - ((w - 2*t) * (h - 2*t)**3)) / 12.0
    else:
        raise ValueError(f"Unknown cross section type: '{cross_section_type}'")

    # 2. Radius of gyration r = sqrt(I / A)
    r_gyr = math.sqrt(i_min / area) if area > 0 else 0.0

    # 3. Effective length Le = K * L
    k_factor = END_CONDITION_K_FACTORS.get(end_condition.lower().strip(), 1.0)
    l_eff = k_factor * length_mm

    # 4. Slenderness ratio lambda = Le / r
    slenderness = l_eff / r_gyr if r_gyr > 0 else 1e9

    # 5. Critical transition slenderness lambda_c = sqrt(2 * pi^2 * E / Sy)
    lambda_c = math.sqrt((2.0 * (math.pi ** 2) * e_mpa) / sy_mpa)

    # 6. Critical buckling load:
    # If lambda >= lambda_c: Euler Elastic Buckling
    # If lambda < lambda_c:  Johnson Inelastic Parabolic Transition
    if slenderness >= lambda_c:
        regime = "EULER_ELASTIC"
        # P_cr = pi^2 * E * I / Le^2
        p_cr = ((math.pi ** 2) * e_mpa * i_min) / (l_eff ** 2)
        sigma_cr = p_cr / area
    else:
        regime = "JOHNSON_INELASTIC"
        # P_cr = A * Sy * (1 - (Sy * lambda^2) / (4 * pi^2 * E))
        bracket = 1.0 - (sy_mpa * (slenderness ** 2)) / (4.0 * (math.pi ** 2) * e_mpa)
        p_cr = area * sy_mpa * max(0.0, bracket)
        sigma_cr = p_cr / area

    # 7. Safety evaluation
    sf = None
    is_safe = True
    notes = []
    if applied_compressive_load_n is not None and applied_compressive_load_n > 0:
        sf = p_cr / applied_compressive_load_n
        if sf < required_safety_factor:
            is_safe = False
            notes.append(
                f"BUCKLING RISK: Factor of Safety ({sf:.2f}) is below required ({required_safety_factor:.2f}). "
                f"Critical load: {p_cr/1e3:.2f} kN, Applied: {applied_compressive_load_n/1e3:.2f} kN."
            )
        else:
            notes.append(f"Safe from buckling with safety factor {sf:.2f} >= {required_safety_factor:.2f}.")

    return BucklingResult(
        column_name=column_name,
        length_mm=length_mm,
        effective_length_mm=l_eff,
        cross_section_area_mm2=area,
        min_moment_of_inertia_mm4=i_min,
        radius_of_gyration_mm=r_gyr,
        slenderness_ratio=slenderness,
        critical_slenderness=lambda_c,
        buckling_regime=regime,
        critical_load_n=p_cr,
        critical_stress_mpa=sigma_cr,
        applied_load_n=applied_compressive_load_n,
        safety_factor=sf,
        is_safe=is_safe,
        notes=" ".join(notes),
    )
