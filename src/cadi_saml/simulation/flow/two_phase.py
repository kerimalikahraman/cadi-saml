"""
cadi_saml.simulation.flow.two_phase

Two-phase (gas-liquid) pipe flow analysis using the Lockhart-Martinelli
separated-flow model and flow regime classification.

Physics
-------
For a gas-liquid mixture flowing in a pipe, the total pressure drop has
three components:
  ΔP_total = ΔP_friction + ΔP_gravity + ΔP_acceleration

This module implements the Lockhart-Martinelli (1949) correlation for
frictional pressure gradient, extended by Chisholm (1967) for turbulent-
turbulent (tt) and turbulent-laminar (tv) flow combinations.

Flow Regime Map
---------------
Baker (1954) flow regime map is used to classify the regime:
  BUBBLE, SLUG, PLUG, STRATIFIED, WAVY, ANNULAR, MIST

Reference
---------
  Lockhart, R.W. & Martinelli, R.C. (1949). Chem. Eng. Prog. 45(1), 39-48.
  Chisholm, D. (1967). Int. J. Heat Mass Transfer 10, 1767-1778.
  Baker, O. (1954). Oil Gas J. 53, 185-190.
  Thome, J.R. (2010). Engineering Data Book III, Wolverine Tube Inc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from .fluid_properties import FluidState, get_water_properties, get_air_properties


# ---------------------------------------------------------------------------
# Flow Regime Constants
# ---------------------------------------------------------------------------

# Lockhart-Martinelli C constants for two-phase multiplier φ²
# Based on liquid/gas flow regime combination:
_LM_C_COEFFICIENTS: Dict[str, float] = {
    "tt": 20.0,  # Both turbulent (Re_L > 2000, Re_G > 2000) — most common
    "tv": 12.0,  # Liquid turbulent, gas viscous (laminar)
    "vt": 10.0,  # Liquid viscous (laminar), gas turbulent
    "vv": 5.0,   # Both laminar
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TwoPhaseFlowResult:
    """
    Complete two-phase flow analysis result.
    All pressures in Pa unless noted.
    """
    # Input echo
    diameter_m: float
    length_m: float
    quality_x: float          # Thermodynamic quality (0=liquid, 1=dry vapour)
    mass_flux_kg_m2_s: float  # G = ṁ/A [kg/(m²·s)]

    # Single-phase reference results
    dp_liquid_only_pa: float  # Pressure drop if entire flow were liquid
    dp_gas_only_pa: float     # Pressure drop if entire flow were gas

    # Two-phase multipliers
    martinelli_parameter_x: float   # Xtt = sqrt(dp_L / dp_G)
    phi_liquid_sq: float            # φ²_L — two-phase multiplier for liquid
    phi_gas_sq: float               # φ²_G — two-phase multiplier for gas

    # Pressure drops
    dp_friction_pa: float      # Frictional pressure drop (dominant term)
    dp_gravity_pa: float       # Gravitational/hydrostatic pressure drop
    dp_acceleration_pa: float  # Acceleration pressure drop (phase change)
    dp_total_pa: float
    dp_total_bar: float

    # Phase flow parameters
    reynolds_liquid: float
    reynolds_gas: float
    void_fraction: float       # α = volume fraction occupied by gas
    flow_regime: str           # 'BUBBLE', 'SLUG', 'ANNULAR', 'MIST', etc.
    lm_regime: str             # 'tt', 'tv', 'vt', 'vv' (turbulent/viscous)

    # Fluids
    liquid_fluid: FluidState
    gas_fluid: FluidState

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diameter_mm": round(self.diameter_m * 1e3, 2),
            "length_m": round(self.length_m, 3),
            "quality_x": self.quality_x,
            "mass_flux_kg_m2_s": round(self.mass_flux_kg_m2_s, 2),
            "martinelli_parameter": round(self.martinelli_parameter_x, 4),
            "phi_liquid_squared": round(self.phi_liquid_sq, 3),
            "void_fraction": round(self.void_fraction, 4),
            "flow_regime": self.flow_regime,
            "dp_friction_bar": round(self.dp_friction_pa / 1e5, 5),
            "dp_gravity_bar": round(self.dp_gravity_pa / 1e5, 5),
            "dp_acceleration_bar": round(self.dp_acceleration_pa / 1e5, 5),
            "dp_total_bar": round(self.dp_total_bar, 5),
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Helper: single-phase friction factor (Haaland explicit)
# ---------------------------------------------------------------------------

def _friction_factor(reynolds: float, relative_roughness: float) -> float:
    """Darcy friction factor via Haaland (1983) explicit approximation."""
    if reynolds <= 0.0:
        return 0.0
    if reynolds < 2300.0:
        return 64.0 / reynolds
    inv_sqrt_f = -1.8 * math.log10(
        (relative_roughness / 3.7) ** 1.11 + 6.9 / reynolds
    )
    f = 1.0 / max(1e-8, inv_sqrt_f ** 2)
    return max(0.005, min(0.15, f))


def _single_phase_dp(
    mass_flux: float,
    diameter_m: float,
    length_m: float,
    density: float,
    dynamic_viscosity: float,
    roughness_m: float = 4.5e-5,
) -> tuple[float, float]:
    """
    Returns (pressure_drop_Pa, Reynolds_number) for single-phase flow.
    Uses Darcy-Weisbach: ΔP = f·(L/D)·(G²/(2ρ))
    """
    if density <= 0 or diameter_m <= 0 or mass_flux <= 0:
        return 0.0, 0.0
    vel = mass_flux / density
    re = mass_flux * diameter_m / max(1e-10, dynamic_viscosity)
    f = _friction_factor(re, roughness_m / diameter_m)
    dp = f * (length_m / diameter_m) * (mass_flux ** 2) / (2.0 * density)
    return dp, re


# ---------------------------------------------------------------------------
# Void fraction (Lockhart-Martinelli simple correlation)
# ---------------------------------------------------------------------------

def _void_fraction_lm(quality_x: float, liq: FluidState, gas: FluidState) -> float:
    """
    Void fraction α from Lockhart-Martinelli slip ratio.
    Simplified Zivi (1964) slip ratio: S = (ρ_L/ρ_G)^(1/3)
    α = 1 / (1 + S·(1-x)/x · ρ_G/ρ_L)
    """
    if quality_x <= 0.0:
        return 0.0
    if quality_x >= 1.0:
        return 1.0
    rho_ratio = liq.density / max(1e-3, gas.density)
    slip = rho_ratio ** (1.0 / 3.0)
    alpha = 1.0 / (1.0 + slip * (1.0 - quality_x) / quality_x * (1.0 / rho_ratio))
    return max(0.0, min(1.0, alpha))


# ---------------------------------------------------------------------------
# Flow regime classification (simplified Baker map)
# ---------------------------------------------------------------------------

def _classify_regime(
    quality_x: float,
    mass_flux: float,
    liq: FluidState,
    gas: FluidState,
    void_fraction: float,
) -> str:
    """
    Classify two-phase flow regime using simplified Baker (1954) criteria.
    """
    rho_L = liq.density
    rho_G = gas.density

    # Superficial velocities
    j_L = mass_flux * (1.0 - quality_x) / max(1e-3, rho_L)
    j_G = mass_flux * quality_x / max(1e-6, rho_G)

    if j_G <= 0.01 and j_L > 0.1:
        return "BUBBLE"
    elif j_G <= 0.1 and j_L > 0.05:
        return "SLUG"
    elif j_G <= 1.0 and j_L > 0.01:
        return "PLUG"
    elif j_G > 3.0 and void_fraction > 0.8:
        return "ANNULAR"
    elif j_G > 15.0 and void_fraction > 0.95:
        return "MIST"
    elif j_L < 0.01 and j_G < 3.0:
        return "STRATIFIED"
    elif j_L < 0.05 and j_G < 6.0:
        return "WAVY"
    else:
        return "INTERMITTENT"


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def analyze_two_phase_flow(
    diameter_mm: float,
    length_mm: float,
    mass_flow_rate_kg_s: float,
    quality_x: float,
    liquid_fluid: Optional[FluidState] = None,
    gas_fluid: Optional[FluidState] = None,
    fluid_name: str = "water",
    temperature_c: float = 100.0,
    inclination_deg: float = 0.0,
    material_roughness_m: float = 4.5e-5,
) -> TwoPhaseFlowResult:
    """
    Analyze two-phase gas-liquid pipe flow using Lockhart-Martinelli model.

    Parameters
    ----------
    diameter_mm       : Inner pipe diameter [mm]
    length_mm         : Pipe length [mm]
    mass_flow_rate_kg_s : Total mass flow rate [kg/s]
    quality_x         : Thermodynamic quality x (0=saturated liquid, 1=dry vapour)
    liquid_fluid      : Liquid phase FluidState (optional — auto from fluid_name)
    gas_fluid         : Gas phase FluidState (optional — auto from fluid_name)
    fluid_name        : Used to auto-create phases if not provided ('water', 'r134a')
    temperature_c     : Bulk temperature for auto-created phases [°C]
    inclination_deg   : Pipe inclination angle from horizontal (+ve = uphill) [°]
    material_roughness_m : Absolute wall roughness [m]

    Returns
    -------
    TwoPhaseFlowResult with pressure drop breakdown and flow regime.
    """
    # --- Resolve fluids ---------------------------------------------------
    if liquid_fluid is None:
        liquid_fluid = get_water_properties(temperature_c)
    if gas_fluid is None:
        # Steam / gas phase: use air as approximation if water not specified
        gas_fluid = get_air_properties(temperature_c)

    quality_x = max(0.0, min(1.0, quality_x))

    d_m = diameter_mm * 1e-3
    l_m = length_mm * 1e-3
    area_m2 = math.pi / 4.0 * d_m ** 2
    G = mass_flow_rate_kg_s / max(1e-12, area_m2)  # mass flux kg/(m²·s)

    warnings_list: List[str] = []

    if quality_x == 0.0:
        warnings_list.append("quality_x=0: Single-phase liquid flow. Use analyze_pipe_flow() instead.")
    if quality_x == 1.0:
        warnings_list.append("quality_x=1: Single-phase gas flow.")

    # --- Single-phase reference pressure drops ----------------------------
    # Liquid-only: entire flow is liquid
    G_L = G * (1.0 - quality_x)  # liquid mass flux
    G_G = G * quality_x           # gas mass flux

    dp_L_only, re_L = _single_phase_dp(
        G_L, d_m, l_m,
        liquid_fluid.density, liquid_fluid.dynamic_viscosity, material_roughness_m,
    )
    dp_G_only, re_G = _single_phase_dp(
        G_G, d_m, l_m,
        gas_fluid.density, gas_fluid.dynamic_viscosity, material_roughness_m,
    )

    # --- Lockhart-Martinelli parameter Xtt --------------------------------
    # X² = (dP/dz)_L / (dP/dz)_G
    if dp_G_only > 1e-10:
        xtt = math.sqrt(dp_L_only / dp_G_only)
    elif quality_x < 1e-3:
        xtt = 1e6  # pure liquid limit
    else:
        xtt = 0.0  # pure gas limit

    # --- Flow regime (tt/tv/vt/vv) ----------------------------------------
    lm_liq = "t" if re_L >= 2300 else "v"
    lm_gas = "t" if re_G >= 2300 else "v"
    lm_regime = lm_liq + lm_gas
    C = _LM_C_COEFFICIENTS.get(lm_regime, 20.0)

    # --- Chisholm two-phase multipliers -----------------------------------
    # φ²_L = 1 + C/X + 1/X²
    # φ²_G = 1 + C·X + X²
    if xtt > 1e-8:
        phi_L_sq = 1.0 + C / xtt + 1.0 / (xtt ** 2)
        phi_G_sq = 1.0 + C * xtt + xtt ** 2
    else:
        phi_L_sq = 1.0
        phi_G_sq = 1.0 + C * xtt + xtt ** 2

    # --- Two-phase frictional pressure drop (use liquid-phase reference) --
    dp_friction = phi_L_sq * dp_L_only

    # --- Void fraction & flow regime --------------------------------------
    alpha = _void_fraction_lm(quality_x, liquid_fluid, gas_fluid)
    flow_regime = _classify_regime(quality_x, G, liquid_fluid, gas_fluid, alpha)

    # --- Gravitational pressure drop --------------------------------------
    theta = math.radians(inclination_deg)
    rho_mix = liquid_fluid.density * (1.0 - alpha) + gas_fluid.density * alpha
    dp_gravity = rho_mix * 9.80665 * l_m * math.sin(theta)

    # --- Acceleration pressure drop (from phase change / density change) --
    # Simplified: ΔP_acc = G² · d/dz[(x²/α·ρ_G) + ((1-x)²/(1-α)·ρ_L)] · L
    # Here simplified as zero for constant quality / adiabatic flow
    dp_acceleration = 0.0

    dp_total = dp_friction + dp_gravity + dp_acceleration

    if dp_total < 0:
        warnings_list.append(
            f"Total pressure drop is negative ({dp_total:.1f} Pa) — "
            "downhill flow with gravity-driven pressure recovery."
        )

    return TwoPhaseFlowResult(
        diameter_m=d_m,
        length_m=l_m,
        quality_x=quality_x,
        mass_flux_kg_m2_s=round(G, 3),
        dp_liquid_only_pa=round(dp_L_only, 2),
        dp_gas_only_pa=round(dp_G_only, 2),
        martinelli_parameter_x=round(xtt, 4),
        phi_liquid_sq=round(phi_L_sq, 4),
        phi_gas_sq=round(phi_G_sq, 4),
        dp_friction_pa=round(dp_friction, 2),
        dp_gravity_pa=round(dp_gravity, 2),
        dp_acceleration_pa=round(dp_acceleration, 2),
        dp_total_pa=round(dp_total, 2),
        dp_total_bar=round(dp_total / 1e5, 6),
        reynolds_liquid=round(re_L, 1),
        reynolds_gas=round(re_G, 1),
        void_fraction=round(alpha, 4),
        flow_regime=flow_regime,
        lm_regime=lm_regime,
        liquid_fluid=liquid_fluid,
        gas_fluid=gas_fluid,
        warnings=warnings_list,
    )
