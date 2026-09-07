"""
cadi_saml.simulation.structural.fatigue

High-cycle fatigue analysis, Marin endurance limit modifications,
Goodman/Soderberg/Gerber safety factors, and S-N Basquin fatigue life prediction.
Reference: Shigley's Mechanical Engineering Design, Dowling Mechanical Behavior of Materials.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union
from ...analysis.materials import Material, get_material


# Reliability factor ke mapping (from standard normal distribution)
RELIABILITY_FACTORS: Dict[float, float] = {
    0.50: 1.000,
    0.90: 0.897,
    0.95: 0.868,
    0.99: 0.814,
    0.999: 0.753,
    0.9999: 0.702,
}


@dataclass
class MarinFactors:
    ka_surface: float = 1.0       # Surface condition factor
    kb_size: float = 1.0          # Size effect factor
    kc_loading: float = 1.0       # Load type factor (1.0 bending, 0.85 axial, 0.59 torsion)
    kd_temperature: float = 1.0   # Temperature factor
    ke_reliability: float = 0.868 # Reliability factor (default 95% = 0.868)

    @property
    def combined_factor(self) -> float:
        return self.ka_surface * self.kb_size * self.kc_loading * self.kd_temperature * self.ke_reliability


@dataclass
class FatigueResult:
    part_name: str
    sigma_max_mpa: float
    sigma_min_mpa: float
    sigma_alternating_mpa: float
    sigma_mean_mpa: float
    endurance_limit_uncorrected_mpa: float
    endurance_limit_corrected_mpa: float
    marin_factors: MarinFactors
    goodman_safety_factor: float
    soderberg_safety_factor: float
    gerber_safety_factor: float
    estimated_cycles_to_failure: float
    is_infinite_life: bool
    status: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "sigma_max_mpa": round(self.sigma_max_mpa, 2),
            "sigma_min_mpa": round(self.sigma_min_mpa, 2),
            "sigma_alternating_mpa": round(self.sigma_alternating_mpa, 2),
            "sigma_mean_mpa": round(self.sigma_mean_mpa, 2),
            "endurance_limit_mpa": round(self.endurance_limit_corrected_mpa, 2),
            "goodman_safety_factor": round(self.goodman_safety_factor, 2),
            "soderberg_safety_factor": round(self.soderberg_safety_factor, 2),
            "gerber_safety_factor": round(self.gerber_safety_factor, 2),
            "estimated_cycles_to_failure": (
                "Infinite (>10^6)" if self.is_infinite_life else int(self.estimated_cycles_to_failure)
            ),
            "is_infinite_life": self.is_infinite_life,
            "status": self.status,
            "notes": self.notes,
        }


def calc_marin_surface_factor(surface_finish: str, sut_mpa: float) -> float:
    """
    Marin surface condition factor ka = a * (Sut)^b.
    surface_finish: 'ground', 'machined', 'cold_drawn', 'hot_rolled', 'as_forged'
    """
    finish = surface_finish.lower().strip()
    if finish in ("ground", "taslanmis", "polished"):
        a, b = 1.58, -0.085
    elif finish in ("machined", "islenmis", "cold_drawn"):
        a, b = 4.51, -0.265
    elif finish in ("hot_rolled", "sicak_hadde"):
        a, b = 57.7, -0.718
    elif finish in ("as_forged", "dovme"):
        a, b = 272.0, -0.995
    else:
        a, b = 4.51, -0.265  # default to machined

    ka = a * (sut_mpa ** b)
    return max(0.2, min(1.0, ka))


def calc_marin_size_factor(equivalent_diameter_mm: float) -> float:
    """
    Marin size factor kb for bending and torsion:
      kb = 1.24 * d^(-0.107) for 2.79 <= d <= 51 mm
      kb = 1.51 * d^(-0.157) for 51 < d <= 254 mm
    """
    d = max(2.79, equivalent_diameter_mm)
    if d <= 51.0:
        return 1.24 * (d ** -0.107)
    elif d <= 254.0:
        return 1.51 * (d ** -0.157)
    return 0.60


def analyze_fatigue_life(
    part_name: str,
    sigma_max_mpa: float,
    sigma_min_mpa: float,
    material: Union[str, Material] = "S235JR",
    surface_finish: str = "machined",
    part_diameter_mm: float = 25.0,
    loading_type: str = "bending",  # "bending", "axial", "torsion"
    operating_temp_c: float = 20.0,
    reliability: float = 0.95,
    required_safety_factor: float = 1.5,
) -> FatigueResult:
    """
    Perform complete S-N fatigue evaluation using Goodman, Soderberg, and Gerber diagrams.
    """
    mat = get_material(material) if isinstance(material, str) else material
    sy_mpa = float(getattr(mat, "yield_strength_mpa", 235.0))
    sut_mpa = float(getattr(mat, "tensile_strength_mpa", getattr(mat, "ultimate_strength_mpa", 360.0)))

    # 1. Alternating and mean stress
    sigma_a = abs(sigma_max_mpa - sigma_min_mpa) / 2.0
    sigma_m = (sigma_max_mpa + sigma_min_mpa) / 2.0

    # 2. Uncorrected endurance limit S_e' (approx 0.5 * Sut for steels <= 1400 MPa)
    se_prime = min(700.0, 0.5 * sut_mpa)

    # 3. Calculate Marin modification factors
    ka = calc_marin_surface_factor(surface_finish, sut_mpa)
    kb = calc_marin_size_factor(part_diameter_mm)
    
    lt = loading_type.lower().strip()
    if lt == "axial":
        kc = 0.85
    elif lt == "torsion":
        kc = 0.59
    else:
        kc = 1.0  # bending

    # Temperature factor kd
    if operating_temp_c <= 100.0:
        kd = 1.0
    elif operating_temp_c <= 300.0:
        kd = 0.95
    else:
        kd = 0.85

    # Reliability factor ke
    ke = RELIABILITY_FACTORS.get(reliability, 0.868)

    marin = MarinFactors(ka_surface=ka, kb_size=kb, kc_loading=kc, kd_temperature=kd, ke_reliability=ke)
    se = marin.combined_factor * se_prime

    # 4. Goodman criteria: (sigma_a / Se) + (sigma_m / Sut) = 1 / SF_Goodman
    # If sigma_m <= 0 (purely compressive mean stress), mean stress has minimal detrimental effect
    if sigma_m > 0:
        denom_goodman = (sigma_a / se) + (sigma_m / sut_mpa)
        denom_soderberg = (sigma_a / se) + (sigma_m / sy_mpa)
        # Gerber: (sigma_a / Se) + (sigma_m / Sut)^2 = 1 / SF_Gerber
        denom_gerber = (sigma_a / se) + ((sigma_m / sut_mpa) ** 2)
    else:
        denom_goodman = (sigma_a / se)
        denom_soderberg = (sigma_a / se)
        denom_gerber = (sigma_a / se)

    sf_goodman = 1.0 / denom_goodman if denom_goodman > 0 else 999.0
    sf_soderberg = 1.0 / denom_soderberg if denom_soderberg > 0 else 999.0
    sf_gerber = 1.0 / denom_gerber if denom_gerber > 0 else 999.0

    # 5. S-N Basquin Life Prediction (Finite vs Infinite Life)
    # Fully reversed equivalent stress: sigma_rev = sigma_a / (1 - (sigma_m / Sut))
    if sigma_m < sut_mpa:
        sigma_rev = sigma_a / (1.0 - max(0.0, sigma_m / sut_mpa))
    else:
        sigma_rev = sigma_a + sigma_m

    # High cycle threshold (10^6 cycles at Se, 10^3 cycles at 0.9 * Sut)
    is_inf = sigma_rev <= se
    if is_inf:
        cycles = float("inf")
    else:
        # S-N line: S_f = a * N^b
        # log10(a) = log10((0.9*Sut)^2 / Se)
        # b = -1/3 * log10( (0.9*Sut) / Se )
        f_point = 0.9 * sut_mpa
        if f_point > se:
            b_slope = -1.0 / 3.0 * math.log10(f_point / se)
            a_const = (f_point ** 2) / se
            # N = (sigma_rev / a)^(1 / b)
            if sigma_rev < f_point:
                cycles = (sigma_rev / a_const) ** (1.0 / b_slope)
            else:
                cycles = 1000.0 * ((f_point / max(1.0, sigma_rev)) ** 3)
            cycles = max(100.0, min(1e6, cycles))
        else:
            cycles = 1000.0

    status = "PASS" if sf_goodman >= required_safety_factor else "FAIL"
    notes = (
        f"Infinite life achieved (SF={sf_goodman:.2f} >= {required_safety_factor:.2f})."
        if is_inf and status == "PASS"
        else f"Finite life estimated at ~{int(cycles):,} cycles (Goodman SF={sf_goodman:.2f})."
    )

    return FatigueResult(
        part_name=part_name,
        sigma_max_mpa=sigma_max_mpa,
        sigma_min_mpa=sigma_min_mpa,
        sigma_alternating_mpa=sigma_a,
        sigma_mean_mpa=sigma_m,
        endurance_limit_uncorrected_mpa=se_prime,
        endurance_limit_corrected_mpa=se,
        marin_factors=marin,
        goodman_safety_factor=sf_goodman,
        soderberg_safety_factor=sf_soderberg,
        gerber_safety_factor=sf_gerber,
        estimated_cycles_to_failure=cycles,
        is_infinite_life=is_inf,
        status=status,
        notes=notes,
    )
