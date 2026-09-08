"""
cadi_saml.simulation.thermal.thermal_stress

Thermal expansion and thermal stress analysis.
Computes stresses arising from constrained thermal expansion,
temperature gradients through pipe walls, and bi-material interfaces.

Physics
-------
1. Free thermal strain:  ε_th = α · ΔT
2. Constrained stress:   σ_th = -E · α · ΔT   (fully constrained)
3. Pipe radial gradient: σ_r, σ_θ, σ_z via Lamé equations with T(r)
4. Thermal expansion of pipe:  ΔL = α · L · ΔT,  ΔD = α · D · ΔT

Reference
---------
  Timoshenko, S. & Goodier, J.N. (1970). Theory of Elasticity. McGraw-Hill.
  ASME B31.3 Process Piping — thermal expansion load calculations.
  Boley, B.A. & Weiner, J.H. (1985). Theory of Thermal Stresses. Dover.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Thermal expansion coefficients [1/°C] for common materials
# ---------------------------------------------------------------------------

THERMAL_EXPANSION_COEFFICIENTS: Dict[str, float] = {
    # Steels
    "carbon_steel": 11.7e-6,
    "stainless_316l": 16.0e-6,
    "stainless_304": 17.2e-6,
    "alloy_steel_4140": 12.3e-6,
    # Non-ferrous metals
    "aluminum_6061": 23.6e-6,
    "aluminum_7075": 23.4e-6,
    "copper": 17.0e-6,
    "brass": 19.2e-6,
    "bronze": 18.0e-6,
    # Titanium
    "ti_6al_4v": 8.6e-6,
    "titanium_cp": 8.4e-6,
    # Superalloys
    "inconel_718": 13.0e-6,
    "inconel_625": 12.8e-6,
    "hastelloy_c276": 11.2e-6,
    # Polymers
    "ptfe": 112.0e-6,
    "nylon_pa12": 100.0e-6,
    "peek": 47.0e-6,
    # Composites
    "cfrp_axial": 0.5e-6,     # Along fiber direction
    "cfrp_transverse": 30.0e-6,  # Across fiber direction
    # Ceramics / Glass
    "borosilicate_glass": 3.3e-6,
    "alumina": 7.2e-6,
    "silicon_carbide": 4.0e-6,
}

# Elastic moduli [GPa]
ELASTIC_MODULI_GPA: Dict[str, float] = {
    "carbon_steel": 200.0,
    "stainless_316l": 193.0,
    "stainless_304": 193.0,
    "alloy_steel_4140": 205.0,
    "aluminum_6061": 69.0,
    "aluminum_7075": 71.7,
    "copper": 110.0,
    "brass": 97.0,
    "ti_6al_4v": 113.8,
    "titanium_cp": 102.0,
    "inconel_718": 200.0,
    "inconel_625": 207.0,
    "hastelloy_c276": 205.0,
    "nylon_pa12": 1.75,
    "peek": 3.6,
    "cfrp_axial": 135.0,
    "cfrp_transverse": 10.0,
}

# Poisson's ratios
POISSON_RATIOS: Dict[str, float] = {
    "carbon_steel": 0.29,
    "stainless_316l": 0.30,
    "stainless_304": 0.30,
    "alloy_steel_4140": 0.29,
    "aluminum_6061": 0.33,
    "aluminum_7075": 0.33,
    "copper": 0.34,
    "brass": 0.34,
    "ti_6al_4v": 0.34,
    "titanium_cp": 0.34,
    "inconel_718": 0.29,
    "nylon_pa12": 0.39,
    "peek": 0.40,
    "cfrp_axial": 0.28,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ThermalStressResult:
    """
    Thermal stress analysis result.
    All stresses in MPa.
    """
    material: str
    alpha_1_k: float          # CTE [1/K]
    elastic_modulus_gpa: float

    # Temperature input
    t_reference_c: float      # Stress-free (assembly/installation) temperature
    t_operating_c: float      # Operating temperature
    delta_t_k: float          # ΔT = T_op - T_ref

    # Free thermal strain
    thermal_strain: float     # ε_th = α · ΔT [dimensionless]
    thermal_expansion_mm_per_m: float  # mm/m of free expansion

    # Fully-constrained stress
    sigma_constrained_mpa: float   # σ = -E·α·ΔT (compressive if heating)
    sigma_von_mises_mpa: float     # Von Mises for biaxial constraint

    # Safety assessment
    yield_strength_mpa: Optional[float]
    safety_factor: Optional[float]
    status: str   # 'SAFE', 'WARNING', 'FAIL'
    notes: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material": self.material,
            "alpha_1_k": self.alpha_1_k,
            "delta_t_k": self.delta_t_k,
            "thermal_strain": round(self.thermal_strain, 8),
            "thermal_expansion_mm_per_m": round(self.thermal_expansion_mm_per_m, 4),
            "sigma_constrained_mpa": round(self.sigma_constrained_mpa, 3),
            "sigma_von_mises_mpa": round(self.sigma_von_mises_mpa, 3),
            "yield_strength_mpa": self.yield_strength_mpa,
            "safety_factor": round(self.safety_factor, 3) if self.safety_factor else None,
            "status": self.status,
            "notes": self.notes,
            "warnings": self.warnings,
        }


@dataclass
class PipeThermalExpansionResult:
    """Thermal expansion result for a pipe or rod segment."""
    material: str
    length_original_mm: float
    diameter_original_mm: float
    wall_thickness_mm: Optional[float]

    delta_length_mm: float       # ΔL = α · L · ΔT
    delta_diameter_mm: float     # ΔD = α · D · ΔT
    delta_wall_mm: Optional[float]  # Δt = α · t · ΔT

    length_final_mm: float
    diameter_final_mm: float

    axial_force_n: Optional[float] = None  # If end-constrained
    axial_stress_mpa: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material": self.material,
            "delta_length_mm": round(self.delta_length_mm, 4),
            "delta_diameter_mm": round(self.delta_diameter_mm, 5),
            "length_final_mm": round(self.length_final_mm, 3),
            "diameter_final_mm": round(self.diameter_final_mm, 4),
            "axial_force_n": round(self.axial_force_n, 2) if self.axial_force_n else None,
            "axial_stress_mpa": round(self.axial_stress_mpa, 3) if self.axial_stress_mpa else None,
        }


# ---------------------------------------------------------------------------
# Yield strength defaults [MPa] at room temperature
# ---------------------------------------------------------------------------

_YIELD_STRENGTHS_MPA: Dict[str, float] = {
    "carbon_steel": 250.0,
    "stainless_316l": 170.0,
    "stainless_304": 205.0,
    "alloy_steel_4140": 655.0,
    "aluminum_6061": 276.0,
    "aluminum_7075": 503.0,
    "copper": 70.0,
    "brass": 125.0,
    "ti_6al_4v": 880.0,
    "titanium_cp": 370.0,
    "inconel_718": 1035.0,
    "inconel_625": 490.0,
    "nylon_pa12": 48.0,
    "peek": 100.0,
    "cfrp_axial": 1500.0,
}


# ---------------------------------------------------------------------------
# Main functions
# ---------------------------------------------------------------------------

def analyze_thermal_stress(
    material: str,
    t_reference_c: float,
    t_operating_c: float,
    constraint_type: str = "full",
    yield_strength_mpa: Optional[float] = None,
    alpha_override: Optional[float] = None,
    elastic_modulus_override_gpa: Optional[float] = None,
    poisson_override: Optional[float] = None,
) -> ThermalStressResult:
    """
    Compute thermal stress for a constrained structural element.

    Parameters
    ----------
    material           : Material identifier (see THERMAL_EXPANSION_COEFFICIENTS)
    t_reference_c      : Stress-free temperature (assembly/welding temp) [°C]
    t_operating_c      : Service temperature [°C]
    constraint_type    : 'full' (fully constrained, 1D) or 'biaxial' (plate)
    yield_strength_mpa : Override yield strength [MPa] (optional)
    alpha_override     : Override CTE [1/°C] (optional)
    elastic_modulus_override_gpa : Override E [GPa] (optional)
    poisson_override   : Override Poisson's ratio (optional — for biaxial)

    Returns
    -------
    ThermalStressResult with constrained thermal stress and safety assessment.
    """
    mat = material.lower().strip()
    warnings_list: List[str] = []

    # --- Material properties -------------------------------------------
    alpha = alpha_override or THERMAL_EXPANSION_COEFFICIENTS.get(mat)
    if alpha is None:
        alpha = 12.0e-6  # default generic metal
        warnings_list.append(
            f"Material '{material}' not in database — using α=12×10⁻⁶ /°C (generic steel). "
            f"Available: {', '.join(list(THERMAL_EXPANSION_COEFFICIENTS.keys())[:10])}..."
        )

    E_gpa = elastic_modulus_override_gpa or ELASTIC_MODULI_GPA.get(mat, 200.0)
    E_pa = E_gpa * 1e9

    nu = poisson_override or POISSON_RATIOS.get(mat, 0.30)
    Sy = yield_strength_mpa or _YIELD_STRENGTHS_MPA.get(mat)

    # --- Temperature change --------------------------------------------
    delta_t = t_operating_c - t_reference_c
    eps_th = alpha * delta_t

    # --- Constrained thermal stress ------------------------------------
    if constraint_type == "biaxial":
        # Biaxial constraint (plate): σ = -E·α·ΔT / (1 - ν)
        sigma_constr = -E_pa * eps_th / (1.0 - nu) / 1e6  # MPa
        # Von Mises for equal biaxial: σ_VM = |σ| (same in both directions)
        sigma_vm = abs(sigma_constr)
    else:
        # Uniaxial full constraint: σ = -E·α·ΔT
        sigma_constr = -E_pa * eps_th / 1e6  # MPa
        sigma_vm = abs(sigma_constr)

    # --- Thermal expansion (free) per meter length ----------------------
    exp_mm_per_m = alpha * abs(delta_t) * 1000.0

    # --- Safety assessment ----------------------------------------------
    sf = None
    if Sy is not None:
        sf = Sy / max(1e-6, sigma_vm)

    if sigma_vm < 0.01:
        status = "SAFE"
    elif Sy is None:
        status = "UNKNOWN"
        warnings_list.append("Yield strength not available — cannot assess safety.")
    elif sf and sf >= 1.5:
        status = "SAFE"
    elif sf and sf >= 1.0:
        status = "WARNING"
        warnings_list.append(
            f"Safety factor {sf:.2f} < 1.5 — thermal stress is significant. "
            "Consider expansion joints or stress-relieving."
        )
    else:
        status = "FAIL"
        warnings_list.append(
            f"Thermal stress ({sigma_vm:.1f} MPa) EXCEEDS yield strength ({Sy:.1f} MPa). "
            "Plastic deformation expected — redesign required."
        )

    if abs(delta_t) > 200:
        warnings_list.append(
            f"Large ΔT = {delta_t:.0f}°C — material property temperature dependence may be significant."
        )

    notes = (
        f"ΔT = {delta_t:+.1f}°C → free thermal strain = {eps_th*100:.4f}%. "
        + (f"SF = {sf:.2f}" if sf else "")
    )

    return ThermalStressResult(
        material=material,
        alpha_1_k=alpha,
        elastic_modulus_gpa=E_gpa,
        t_reference_c=t_reference_c,
        t_operating_c=t_operating_c,
        delta_t_k=delta_t,
        thermal_strain=eps_th,
        thermal_expansion_mm_per_m=round(exp_mm_per_m, 5),
        sigma_constrained_mpa=round(sigma_constr, 4),
        sigma_von_mises_mpa=round(sigma_vm, 4),
        yield_strength_mpa=Sy,
        safety_factor=round(sf, 3) if sf else None,
        status=status,
        notes=notes,
        warnings=warnings_list,
    )


def analyze_pipe_thermal_expansion(
    material: str,
    length_mm: float,
    outer_diameter_mm: float,
    wall_thickness_mm: Optional[float] = None,
    t_installation_c: float = 20.0,
    t_operating_c: float = 100.0,
    end_condition: str = "free",
    elastic_modulus_override_gpa: Optional[float] = None,
    alpha_override: Optional[float] = None,
) -> PipeThermalExpansionResult:
    """
    Compute dimensional changes and constrained forces for a pipe under
    thermal loading.

    Parameters
    ----------
    material           : Material identifier
    length_mm          : Original pipe length [mm]
    outer_diameter_mm  : Outer diameter [mm]
    wall_thickness_mm  : Wall thickness [mm] (optional)
    t_installation_c   : Installation (stress-free) temperature [°C]
    t_operating_c      : Operating temperature [°C]
    end_condition      : 'free' or 'fixed' (both ends anchored)
    elastic_modulus_override_gpa : Override E [GPa] (optional)
    alpha_override     : Override CTE [1/°C] (optional)

    Returns
    -------
    PipeThermalExpansionResult with dimensional change and optional reaction forces.
    """
    mat = material.lower().strip()
    alpha = alpha_override or THERMAL_EXPANSION_COEFFICIENTS.get(mat, 12.0e-6)
    E_gpa = elastic_modulus_override_gpa or ELASTIC_MODULI_GPA.get(mat, 200.0)

    delta_t = t_operating_c - t_installation_c
    eps_th = alpha * delta_t

    delta_l = length_mm * eps_th
    delta_d = outer_diameter_mm * eps_th
    delta_t_wall = wall_thickness_mm * eps_th if wall_thickness_mm else None

    l_final = length_mm + delta_l
    d_final = outer_diameter_mm + delta_d

    # Constrained case: axial force = E·A·α·ΔT
    axial_force = None
    axial_stress = None

    if end_condition == "fixed" and wall_thickness_mm:
        # Cross-sectional area of pipe wall
        r_o = outer_diameter_mm / 2.0
        r_i = r_o - wall_thickness_mm
        a_mm2 = math.pi * (r_o ** 2 - r_i ** 2)
        a_m2 = a_mm2 * 1e-6
        E_pa = E_gpa * 1e9
        axial_force = E_pa * a_m2 * alpha * abs(delta_t)  # N (magnitude)
        if delta_t > 0:
            axial_force = -axial_force  # Compressive (want to expand but constrained)
        axial_stress = axial_force / max(1e-10, a_m2) / 1e6  # MPa

    return PipeThermalExpansionResult(
        material=material,
        length_original_mm=length_mm,
        diameter_original_mm=outer_diameter_mm,
        wall_thickness_mm=wall_thickness_mm,
        delta_length_mm=round(delta_l, 4),
        delta_diameter_mm=round(delta_d, 5),
        delta_wall_mm=round(delta_t_wall, 6) if delta_t_wall else None,
        length_final_mm=round(l_final, 3),
        diameter_final_mm=round(d_final, 4),
        axial_force_n=round(axial_force, 2) if axial_force else None,
        axial_stress_mpa=round(axial_stress, 4) if axial_stress else None,
    )
