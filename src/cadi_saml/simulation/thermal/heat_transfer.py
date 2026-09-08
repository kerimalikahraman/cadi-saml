"""
cadi_saml.simulation.thermal.heat_transfer

Forced convection heat transfer correlations for internal pipe flow.
Computes Nusselt number, convective heat transfer coefficient h,
and total heat flux for pipe wall boundary conditions.

Correlations implemented
------------------------
1. Dittus-Boelter (1930): Turbulent pipe flow, 0.7 ≤ Pr ≤ 160, Re > 10,000
     Nu = 0.023 · Re^0.8 · Pr^n   (n=0.4 heating, n=0.3 cooling)

2. Gnielinski (1976): Extended range, 0.5 ≤ Pr ≤ 2000, 3000 ≤ Re ≤ 5×10⁶
     Nu = (f/8)(Re - 1000)·Pr / [1 + 12.7·sqrt(f/8)·(Pr^(2/3) - 1)]
     More accurate near transition and for moderate Prandtl numbers.

3. Sieder-Tate (1936): Laminar with viscosity correction (Re < 2300)
     Nu = 1.86 · (Re·Pr·D/L)^(1/3) · (μ_bulk/μ_wall)^0.14

4. Log-Mean Temperature Difference (LMTD) for shell-and-tube HX.

Reference
---------
  Incropera, F.P. & DeWitt, D.P. (2011). Fundamentals of Heat and Mass Transfer, 7th ed.
  Gnielinski, V. (1976). Int. Chem. Eng. 16(2), 359-368.
  Dittus, F.W. & Boelter, L.M.K. (1930). Univ. California Pub. Eng. 2, 443.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from ..flow.fluid_properties import FluidState, get_water_properties
from ..flow.pipe_flow import solve_friction_factor_colebrook


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConvectionResult:
    """
    Convective heat transfer result for a pipe section.
    """
    # Geometry
    diameter_m: float
    length_m: float

    # Flow regime
    reynolds: float
    prandtl: float
    flow_regime: str   # 'LAMINAR', 'TRANSITIONAL', 'TURBULENT'

    # Heat transfer
    nusselt: float
    h_convection_w_m2_k: float      # Convective HTC [W/(m²·K)]
    heat_flux_w_m2: Optional[float]  # Q/A if wall temperature specified [W/m²]
    total_heat_transfer_w: Optional[float]  # Q_total for the pipe [W]

    # Temperature change (if heat flux or wall T provided)
    delta_t_fluid_k: Optional[float] = None  # Temperature rise of fluid [K]
    outlet_temperature_c: Optional[float] = None

    # Thermal resistance
    thermal_resistance_k_w: Optional[float] = None  # R = 1/(h·A_s) [K/W]

    # Correlation used
    correlation: str = "gnielinski"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diameter_mm": round(self.diameter_m * 1e3, 2),
            "length_m": round(self.length_m, 3),
            "reynolds": round(self.reynolds, 0),
            "prandtl": round(self.prandtl, 3),
            "flow_regime": self.flow_regime,
            "nusselt": round(self.nusselt, 3),
            "h_convection_w_m2_k": round(self.h_convection_w_m2_k, 2),
            "heat_flux_w_m2": round(self.heat_flux_w_m2, 2) if self.heat_flux_w_m2 else None,
            "total_heat_transfer_w": round(self.total_heat_transfer_w, 2) if self.total_heat_transfer_w else None,
            "delta_t_fluid_k": round(self.delta_t_fluid_k, 4) if self.delta_t_fluid_k else None,
            "outlet_temperature_c": round(self.outlet_temperature_c, 3) if self.outlet_temperature_c else None,
            "thermal_resistance_k_w": round(self.thermal_resistance_k_w, 5) if self.thermal_resistance_k_w else None,
            "correlation": self.correlation,
            "warnings": self.warnings,
        }


@dataclass
class HeatExchangerResult:
    """Log-Mean Temperature Difference (LMTD) heat exchanger analysis."""
    # Config
    hx_type: str     # 'parallel_flow', 'counter_flow', 'cross_flow'
    u_overall_w_m2_k: float    # Overall HTC [W/(m²·K)]
    area_m2: float             # Heat transfer surface area [m²]

    # Temperatures
    t_hot_in_c: float
    t_hot_out_c: float
    t_cold_in_c: float
    t_cold_out_c: float

    # Results
    lmtd_k: float
    q_transferred_w: float
    effectiveness: float
    ntu: float   # Number of Transfer Units = UA/C_min

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hx_type": self.hx_type,
            "lmtd_k": round(self.lmtd_k, 3),
            "q_transferred_kw": round(self.q_transferred_w / 1e3, 3),
            "effectiveness": round(self.effectiveness, 4),
            "ntu": round(self.ntu, 4),
            "t_hot_out_c": round(self.t_hot_out_c, 2),
            "t_cold_out_c": round(self.t_cold_out_c, 2),
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Nusselt correlations
# ---------------------------------------------------------------------------

def calc_nusselt_dittus_boelter(
    reynolds: float,
    prandtl: float,
    heating: bool = True,
) -> float:
    """
    Dittus-Boelter correlation for turbulent pipe flow.
    Valid: Re > 10,000; 0.7 ≤ Pr ≤ 160; L/D > 10.

    Nu = 0.023 · Re^0.8 · Pr^n
    n = 0.4 (fluid is being heated), n = 0.3 (fluid is being cooled)
    """
    n = 0.4 if heating else 0.3
    return 0.023 * (reynolds ** 0.8) * (prandtl ** n)


def calc_nusselt_gnielinski(
    reynolds: float,
    prandtl: float,
    friction_factor: Optional[float] = None,
    relative_roughness: float = 4.5e-5 / 0.05,  # typical default
) -> float:
    """
    Gnielinski (1976) correlation — more accurate than Dittus-Boelter.
    Valid: 3000 ≤ Re ≤ 5×10⁶; 0.5 ≤ Pr ≤ 2000.

    Nu = (f/8)(Re - 1000)·Pr / [1 + 12.7·sqrt(f/8)·(Pr^(2/3) - 1)]
    """
    if friction_factor is None:
        friction_factor = solve_friction_factor_colebrook(reynolds, relative_roughness)

    f8 = friction_factor / 8.0
    num = f8 * (reynolds - 1000.0) * prandtl
    denom = 1.0 + 12.7 * math.sqrt(f8) * (prandtl ** (2.0 / 3.0) - 1.0)
    if abs(denom) < 1e-10:
        return calc_nusselt_dittus_boelter(reynolds, prandtl)
    return max(3.66, num / denom)


def calc_nusselt_sieder_tate(
    reynolds: float,
    prandtl: float,
    diameter_m: float,
    length_m: float,
    viscosity_ratio: float = 1.0,   # μ_bulk / μ_wall
) -> float:
    """
    Sieder-Tate (1936) for laminar flow with viscosity correction.
    Valid: Re < 2300; L/D > 10.

    Nu = 1.86 · (Re·Pr·D/L)^(1/3) · (μ/μ_w)^0.14
    """
    ld = length_m / max(1e-9, diameter_m)
    gz = reynolds * prandtl / max(1e-9, ld)  # Graetz number / D
    nu = 1.86 * (gz ** (1.0 / 3.0)) * (viscosity_ratio ** 0.14)
    return max(3.66, nu)  # Minimum fully-developed laminar Nu = 3.66 (const flux)


# ---------------------------------------------------------------------------
# Main heat transfer analysis
# ---------------------------------------------------------------------------

def analyze_pipe_heat_transfer(
    pipe_diameter_mm: float,
    pipe_length_mm: float,
    flow_rate_l_s: float,
    fluid: Optional[FluidState] = None,
    fluid_name: str = "water",
    fluid_temperature_c: float = 20.0,
    wall_temperature_c: Optional[float] = None,
    heat_flux_w_m2: Optional[float] = None,
    material_roughness_m: float = 4.5e-5,
    correlation: str = "gnielinski",
) -> ConvectionResult:
    """
    Compute convective heat transfer coefficient and total heat transfer
    for a circular pipe under forced convection.

    Provide either wall_temperature_c OR heat_flux_w_m2 to compute the
    heat transfer rate. If neither is given, only Nu and h are returned.

    Parameters
    ----------
    pipe_diameter_mm    : Inner pipe diameter [mm]
    pipe_length_mm      : Pipe length [mm]
    flow_rate_l_s       : Volumetric flow rate [L/s]
    fluid               : FluidState (optional — auto from fluid_name)
    fluid_name          : Fluid identifier string (if fluid not provided)
    fluid_temperature_c : Bulk fluid temperature [°C]
    wall_temperature_c  : Wall (surface) temperature [°C] (optional)
    heat_flux_w_m2      : Uniform wall heat flux [W/m²] (optional)
    material_roughness_m: Pipe wall roughness [m]
    correlation         : 'gnielinski' (default) | 'dittus_boelter' | 'sieder_tate'

    Returns
    -------
    ConvectionResult with Nu, h, and heat transfer summary.
    """
    if fluid is None:
        from ..flow.fluid_properties import resolve_fluid
        fluid = resolve_fluid(fluid_name, fluid_temperature_c)

    d_m = pipe_diameter_mm * 1e-3
    l_m = pipe_length_mm * 1e-3
    area_m2 = math.pi / 4.0 * d_m ** 2
    surface_area_m2 = math.pi * d_m * l_m  # lateral surface

    q_m3_s = flow_rate_l_s * 1e-3
    v = q_m3_s / max(1e-12, area_m2)

    re = fluid.density * v * d_m / max(1e-10, fluid.dynamic_viscosity)
    pr = fluid.prandtl_number
    rel_r = material_roughness_m / max(1e-10, d_m)

    warnings_list: List[str] = []

    # --- Flow regime ---------------------------------------------------
    if re < 2300:
        regime = "LAMINAR"
    elif re <= 4000:
        regime = "TRANSITIONAL"
        warnings_list.append(
            f"Flow is in transitional regime (Re={re:.0f}). "
            "Heat transfer correlation accuracy reduced."
        )
    else:
        regime = "TURBULENT"

    # --- Nusselt number -----------------------------------------------
    f = solve_friction_factor_colebrook(re, rel_r)
    corr_used = correlation.lower()

    if re < 2300:
        # Laminar regime — use Sieder-Tate regardless of selection
        nu = calc_nusselt_sieder_tate(re, pr, d_m, l_m)
        corr_used = "sieder_tate"
        if pr < 0.5:
            warnings_list.append(f"Pr={pr:.3f} < 0.5: Sieder-Tate accuracy reduced (liquid metals).")
    elif corr_used == "dittus_boelter":
        heating = True
        if wall_temperature_c is not None:
            heating = wall_temperature_c > fluid_temperature_c
        nu = calc_nusselt_dittus_boelter(re, pr, heating=heating)
        if re < 10000:
            warnings_list.append(
                f"Dittus-Boelter valid for Re > 10,000 (Re={re:.0f}). Use Gnielinski for better accuracy."
            )
    else:  # gnielinski (default)
        nu = calc_nusselt_gnielinski(re, pr, friction_factor=f, relative_roughness=rel_r)
        corr_used = "gnielinski"

    # --- Convective HTC -----------------------------------------------
    # h = Nu · k / D
    h = nu * fluid.thermal_conductivity / max(1e-10, d_m)  # W/(m²·K)

    # --- Heat transfer rate -------------------------------------------
    q_flux = None
    q_total = None
    delta_t = None
    t_out = None
    R_th = None

    if wall_temperature_c is not None:
        delta_t_wf = wall_temperature_c - fluid_temperature_c  # ΔT wall-fluid
        q_flux = h * delta_t_wf  # W/m²
        q_total = q_flux * surface_area_m2  # W
    elif heat_flux_w_m2 is not None:
        q_flux = heat_flux_w_m2
        q_total = q_flux * surface_area_m2

    if q_total is not None and q_m3_s > 0:
        # Fluid temperature rise: Q = ṁ·Cp·ΔT → ΔT = Q/(ṁ·Cp)
        m_dot = fluid.density * q_m3_s
        delta_t = q_total / max(1e-10, m_dot * fluid.specific_heat)
        t_out = fluid_temperature_c + delta_t

    if surface_area_m2 > 0:
        R_th = 1.0 / max(1e-10, h * surface_area_m2)

    if pr > 500:
        warnings_list.append(f"Pr={pr:.1f} > 500 (very viscous fluid). Gnielinski accuracy may be reduced.")

    return ConvectionResult(
        diameter_m=d_m,
        length_m=l_m,
        reynolds=round(re, 1),
        prandtl=round(pr, 4),
        flow_regime=regime,
        nusselt=round(nu, 3),
        h_convection_w_m2_k=round(h, 3),
        heat_flux_w_m2=round(q_flux, 3) if q_flux else None,
        total_heat_transfer_w=round(q_total, 3) if q_total else None,
        delta_t_fluid_k=round(delta_t, 5) if delta_t else None,
        outlet_temperature_c=round(t_out, 4) if t_out else None,
        thermal_resistance_k_w=round(R_th, 6) if R_th else None,
        correlation=corr_used,
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# LMTD Heat Exchanger
# ---------------------------------------------------------------------------

def analyze_heat_exchanger_lmtd(
    u_overall_w_m2_k: float,
    area_m2: float,
    t_hot_in_c: float,
    t_cold_in_c: float,
    mass_flow_hot_kg_s: float,
    mass_flow_cold_kg_s: float,
    fluid_hot: Optional[FluidState] = None,
    fluid_cold: Optional[FluidState] = None,
    cp_hot_j_kg_k: float = 4182.0,
    cp_cold_j_kg_k: float = 4182.0,
    hx_type: str = "counter_flow",
    f_correction: float = 1.0,
) -> HeatExchangerResult:
    """
    Log-Mean Temperature Difference (LMTD) method for shell-and-tube
    or plate heat exchangers.

    The ε-NTU method is used to find outlet temperatures iteratively when
    they are not known (standard NTU-effectiveness approach).

    Parameters
    ----------
    u_overall_w_m2_k   : Overall heat transfer coefficient [W/(m²·K)]
    area_m2            : Total heat transfer area [m²]
    t_hot_in_c         : Hot fluid inlet temperature [°C]
    t_cold_in_c        : Cold fluid inlet temperature [°C]
    mass_flow_hot_kg_s : Hot fluid mass flow rate [kg/s]
    mass_flow_cold_kg_s: Cold fluid mass flow rate [kg/s]
    fluid_hot          : Hot FluidState (optional, uses cp_hot if None)
    fluid_cold         : Cold FluidState (optional, uses cp_cold if None)
    cp_hot_j_kg_k      : Hot fluid specific heat [J/(kg·K)]
    cp_cold_j_kg_k     : Cold fluid specific heat [J/(kg·K)]
    hx_type            : 'counter_flow', 'parallel_flow', 'cross_flow_unmixed'
    f_correction       : LMTD correction factor F (1.0 for counter/parallel)
    """
    warnings_list: List[str] = []

    cp_h = fluid_hot.specific_heat if fluid_hot else cp_hot_j_kg_k
    cp_c = fluid_cold.specific_heat if fluid_cold else cp_cold_j_kg_k

    C_hot = mass_flow_hot_kg_s * cp_h   # Heat capacity rate [W/K]
    C_cold = mass_flow_cold_kg_s * cp_c

    C_min = min(C_hot, C_cold)
    C_max = max(C_hot, C_cold)
    C_r = C_min / max(1e-10, C_max)   # Capacity ratio

    UA = u_overall_w_m2_k * area_m2
    NTU = UA / max(1e-10, C_min)

    # ε-NTU effectiveness
    if abs(C_r - 1.0) < 1e-6:
        if hx_type == "parallel_flow":
            epsilon = (1.0 - math.exp(-2.0 * NTU)) / 2.0
        else:  # counter_flow
            epsilon = NTU / (NTU + 1.0)
    else:
        if hx_type == "parallel_flow":
            epsilon = (1.0 - math.exp(-NTU * (1.0 + C_r))) / (1.0 + C_r)
        elif hx_type == "cross_flow_unmixed":
            epsilon = 1.0 - math.exp((1.0 / C_r) * NTU ** 0.22 * (math.exp(-C_r * NTU ** 0.78) - 1.0))
        else:  # counter_flow (default)
            exp_val = math.exp(-NTU * (1.0 - C_r))
            epsilon = (1.0 - exp_val) / (1.0 - C_r * exp_val)

    epsilon = min(1.0, max(0.0, epsilon))
    Q_max = C_min * (t_hot_in_c - t_cold_in_c)
    Q = epsilon * Q_max

    t_hot_out = t_hot_in_c - Q / max(1e-10, C_hot)
    t_cold_out = t_cold_in_c + Q / max(1e-10, C_cold)

    # LMTD
    if hx_type == "parallel_flow":
        dt1 = t_hot_in_c - t_cold_in_c
        dt2 = t_hot_out - t_cold_out
    else:  # counter_flow
        dt1 = t_hot_in_c - t_cold_out
        dt2 = t_hot_out - t_cold_in_c

    if abs(dt1 - dt2) < 1e-6:
        lmtd = dt1
    elif dt1 > 0 and dt2 > 0:
        lmtd = (dt1 - dt2) / math.log(dt1 / max(1e-10, dt2))
    else:
        lmtd = (dt1 + dt2) / 2.0
        warnings_list.append("Temperature cross detected — check fluid assignment.")

    if t_hot_out < t_cold_out and hx_type != "counter_flow":
        warnings_list.append(
            f"Outlet temperature cross: T_hot_out ({t_hot_out:.1f}°C) < T_cold_out ({t_cold_out:.1f}°C). "
            "Consider counter-flow configuration."
        )

    return HeatExchangerResult(
        hx_type=hx_type,
        u_overall_w_m2_k=u_overall_w_m2_k,
        area_m2=area_m2,
        t_hot_in_c=t_hot_in_c,
        t_hot_out_c=round(t_hot_out, 3),
        t_cold_in_c=t_cold_in_c,
        t_cold_out_c=round(t_cold_out, 3),
        lmtd_k=round(lmtd, 4),
        q_transferred_w=round(Q, 2),
        effectiveness=round(epsilon, 4),
        ntu=round(NTU, 4),
        warnings=warnings_list,
    )
