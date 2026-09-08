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
    _cycles_str = "∞ (infinite life)" if cycles == float("inf") else f"~{int(min(cycles, 1e15)):,}"
    notes = (
        f"Infinite life achieved (SF={sf_goodman:.2f} >= {required_safety_factor:.2f})."
        if is_inf and status == "PASS"
        else f"Finite life estimated at {_cycles_str} cycles (Goodman SF={sf_goodman:.2f})."
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


# ---------------------------------------------------------------------------
# Palmgren-Miner Cumulative Damage Rule
# ---------------------------------------------------------------------------

@dataclass
class MinerLoadBlock:
    """A single constant-amplitude block in a variable-amplitude loading history."""
    sigma_max_mpa: float
    sigma_min_mpa: float
    n_applied_cycles: float   # Number of cycles applied at this amplitude


@dataclass
class MinerResult:
    """
    Palmgren-Miner cumulative damage result for variable-amplitude loading.
    """
    part_name: str
    material: Any  # Material type
    total_damage_D: float    # D = Σ(n_i / N_i). Failure at D ≥ 1.0
    status: str              # 'SAFE' (D < 0.8), 'WARNING' (0.8 ≤ D < 1.0), 'FAIL' (D ≥ 1.0)
    block_results: List[Dict[str, Any]]  # Per-block detail
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "total_damage_D": round(self.total_damage_D, 6),
            "status": self.status,
            "blocks": self.block_results,
            "notes": self.notes,
        }


def analyze_miner_cumulative_damage(
    part_name: str,
    material: Any,
    load_blocks: List[MinerLoadBlock],
    marin: Optional[MarinFactors] = None,
    required_safety_factor: float = 1.3,
) -> MinerResult:
    """
    Palmgren-Miner (1945) linear cumulative damage rule for variable-amplitude loading.

    For each load block i:
      N_i = estimated cycles to failure at that amplitude (from S-N curve)
      D_i = n_i / N_i  (partial damage fraction)
    Total damage: D = Σ D_i  →  Failure predicted when D ≥ 1.0

    Parameters
    ----------
    part_name    : Part identifier string
    material     : Material object with Sut (tensile strength) and Sy (yield strength)
    load_blocks  : List of MinerLoadBlock objects (amplitude + applied cycles)
    marin        : Marin endurance modifiers (optional, uses defaults if None)
    required_safety_factor : Minimum D-based safety factor target (default 1.3)

    Returns
    -------
    MinerResult with total damage accumulation and per-block breakdown.
    """
    from typing import List as _List

    _marin = marin or MarinFactors()
    block_results: _List[Dict[str, Any]] = []
    D_total = 0.0

    for i, blk in enumerate(load_blocks):
        # Run single-amplitude fatigue to get N_i
        blk_result = analyze_fatigue_life(
            part_name=f"{part_name}_block{i}",
            material=material,
            sigma_max_mpa=blk.sigma_max_mpa,
            sigma_min_mpa=blk.sigma_min_mpa,
            required_safety_factor=required_safety_factor,
        )

        N_i = blk_result.estimated_cycles_to_failure
        n_i = blk.n_applied_cycles

        if blk_result.is_infinite_life:
            D_i = 0.0  # No damage for stresses below endurance limit
        else:
            D_i = n_i / max(1.0, N_i)

        D_total += D_i
        block_results.append({
            "block_index": i,
            "sigma_max_mpa": blk.sigma_max_mpa,
            "sigma_min_mpa": blk.sigma_min_mpa,
            "n_applied": blk.n_applied_cycles,
            "n_to_failure": round(N_i, 0),
            "is_infinite_life": blk_result.is_infinite_life,
            "damage_fraction": round(D_i, 6),
            "cumulative_D": round(D_total, 6),
        })

    if D_total < 0.8:
        status = "SAFE"
    elif D_total < 1.0:
        status = "WARNING"
    else:
        status = "FAIL"

    notes = (
        f"Total Miner damage D = {D_total:.4f} "
        f"over {len(load_blocks)} load blocks. "
        + ("FAILURE predicted — D ≥ 1.0." if D_total >= 1.0 else f"Remaining life fraction = {max(0, 1.0 - D_total):.1%}.")
    )

    return MinerResult(
        part_name=part_name,
        material=material,
        total_damage_D=round(D_total, 6),
        status=status,
        block_results=block_results,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Multiaxial Fatigue — Von Mises equivalent stress approach
# ---------------------------------------------------------------------------

@dataclass
class MultiaxialFatigueResult:
    """
    Multiaxial fatigue result using Von Mises equivalent stress.
    """
    part_name: str
    sigma_xx_max_mpa: float
    sigma_yy_max_mpa: float
    tau_xy_max_mpa: float
    sigma_von_mises_alternating_mpa: float  # σ_a,VM
    sigma_von_mises_mean_mpa: float         # σ_m,VM
    endurance_limit_corrected_mpa: float
    goodman_safety_factor: float
    status: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "sigma_von_mises_alternating_mpa": round(self.sigma_von_mises_alternating_mpa, 3),
            "sigma_von_mises_mean_mpa": round(self.sigma_von_mises_mean_mpa, 3),
            "endurance_limit_corrected_mpa": round(self.endurance_limit_corrected_mpa, 3),
            "goodman_safety_factor": round(self.goodman_safety_factor, 3),
            "status": self.status,
            "notes": self.notes,
        }


def analyze_multiaxial_fatigue(
    part_name: str,
    material: Any,
    sigma_xx_max_mpa: float,
    sigma_xx_min_mpa: float,
    sigma_yy_max_mpa: float = 0.0,
    sigma_yy_min_mpa: float = 0.0,
    tau_xy_max_mpa: float = 0.0,
    tau_xy_min_mpa: float = 0.0,
    marin: Optional[MarinFactors] = None,
    required_safety_factor: float = 1.5,
) -> MultiaxialFatigueResult:
    """
    Multiaxial fatigue analysis using Von Mises equivalent stress method.

    This is the simplified Von Mises approach (Sines' method variant):
      σ_a,VM = sqrt(σ_a,xx² - σ_a,xx·σ_a,yy + σ_a,yy² + 3·τ_a,xy²)
      σ_m,VM = sqrt(σ_m,xx² - σ_m,xx·σ_m,yy + σ_m,yy² + 3·τ_m,xy²)

    Then apply Goodman criterion with VM stresses:
      σ_a,VM / Se + σ_m,VM / Sut = 1/SF

    Valid for: proportional loading (principal stress directions fixed).
    For non-proportional loading, critical-plane methods (Brown-Miller,
    Fatemi-Socie) should be used instead.

    Parameters
    ----------
    part_name           : Part identifier
    material            : Material with Sut, Sy attributes
    sigma_xx_max_mpa    : Maximum normal stress in x-direction [MPa]
    sigma_xx_min_mpa    : Minimum normal stress in x-direction [MPa]
    sigma_yy_max_mpa    : Maximum normal stress in y-direction [MPa]
    sigma_yy_min_mpa    : Minimum normal stress in y-direction [MPa]
    tau_xy_max_mpa      : Maximum shear stress [MPa]
    tau_xy_min_mpa      : Minimum shear stress [MPa]
    marin               : Marin modification factors (optional)
    required_safety_factor : Minimum acceptable Goodman safety factor

    Returns
    -------
    MultiaxialFatigueResult with VM equivalent stresses and Goodman assessment.
    """
    # Alternating and mean components
    def _alt_mean(sig_max: float, sig_min: float):
        return (sig_max - sig_min) / 2.0, (sig_max + sig_min) / 2.0

    a_xx, m_xx = _alt_mean(sigma_xx_max_mpa, sigma_xx_min_mpa)
    a_yy, m_yy = _alt_mean(sigma_yy_max_mpa, sigma_yy_min_mpa)
    a_xy, m_xy = _alt_mean(tau_xy_max_mpa, tau_xy_min_mpa)

    # Von Mises equivalent alternating and mean stresses
    # σ_VM = sqrt(σ_xx² - σ_xx·σ_yy + σ_yy² + 3·τ_xy²)
    def _von_mises(sx: float, sy: float, txy: float) -> float:
        val = sx**2 - sx * sy + sy**2 + 3.0 * txy**2
        return math.sqrt(max(0.0, val))

    sigma_a_vm = _von_mises(a_xx, a_yy, a_xy)
    sigma_m_vm = _von_mises(m_xx, m_yy, m_xy)

    # Endurance limit from uniaxial fatigue
    _marin = marin or MarinFactors()
    Sut = material.tensile_strength_mpa
    Sy = material.yield_strength_mpa

    se_prime = 0.504 * Sut if Sut <= 1400.0 else 700.0
    se = se_prime * _marin.combined_factor

    # Goodman criterion
    if Sut > 0 and se > 0:
        goodman_lhs = sigma_a_vm / se + sigma_m_vm / Sut
        sf_goodman = 1.0 / max(1e-9, goodman_lhs) if goodman_lhs > 0 else float("inf")
    else:
        sf_goodman = 0.0

    status = "PASS" if sf_goodman >= required_safety_factor else "FAIL"

    notes = (
        f"VM alternating: {sigma_a_vm:.2f} MPa, VM mean: {sigma_m_vm:.2f} MPa. "
        f"Se = {se:.1f} MPa, Sut = {Sut:.1f} MPa. "
        f"Goodman SF = {sf_goodman:.2f}."
    )

    return MultiaxialFatigueResult(
        part_name=part_name,
        sigma_xx_max_mpa=sigma_xx_max_mpa,
        sigma_yy_max_mpa=sigma_yy_max_mpa,
        tau_xy_max_mpa=tau_xy_max_mpa,
        sigma_von_mises_alternating_mpa=round(sigma_a_vm, 4),
        sigma_von_mises_mean_mpa=round(sigma_m_vm, 4),
        endurance_limit_corrected_mpa=round(se, 3),
        goodman_safety_factor=round(sf_goodman, 3),
        status=status,
        notes=notes,
    )
