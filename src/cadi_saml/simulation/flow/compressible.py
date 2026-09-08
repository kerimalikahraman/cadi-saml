"""
cadi_saml.simulation.flow.compressible

Compressible (high-speed) gas pipe flow — Fanno flow model.
Accounts for Mach-number-dependent friction, choking, and normal shocks.

Physics
-------
Fanno flow: adiabatic, steady, 1D, constant-area duct with wall friction.
Governing equations (ideal gas, γ = const):

  Ma²(x) varies along duct via:
    dMa²/dx = -γ·Ma²·(1 + (γ-1)/2·Ma²) / (1 - Ma²) * (4f/D)

  Property ratios relative to sonic (*) conditions:
    T/T* = (γ+1)/2 / (1 + (γ-1)/2·Ma²)
    P/P* = (1/Ma) * sqrt(T/T*)
    ρ/ρ* = 1/(Ma * sqrt(T/T*))
    P0/P0* = (1/Ma) * ((2/(γ+1)) * (1 + (γ-1)/2·Ma²))^((γ+1)/(2(γ-1)))

Reference
---------
  Anderson, J.D. (2003) Modern Compressible Flow, 3rd ed.
  Shapiro, A.H. (1953) The Dynamics and Thermodynamics of Compressible Flow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from .fluid_properties import FluidState, get_air_properties


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FannoPoint:
    """Local state at a cross-section along a Fanno-flow duct."""
    position_m: float      # Distance from inlet (m)
    mach: float            # Local Mach number
    temperature_k: float   # Static temperature (K)
    pressure_pa: float     # Static pressure (Pa)
    density_kg_m3: float   # Static density (kg/m³)
    velocity_m_s: float    # Flow velocity (m/s)
    total_pressure_pa: float   # Stagnation pressure (Pa)
    total_temperature_k: float  # Stagnation temperature (K)


@dataclass
class CompressibleFlowResult:
    """
    Full result of a Fanno (compressible adiabatic pipe) flow calculation.
    """
    # Geometry
    diameter_m: float
    length_m: float

    # Inlet / outlet Mach numbers
    mach_inlet: float
    mach_outlet: float

    # Inlet conditions
    inlet_temperature_k: float
    inlet_pressure_pa: float
    inlet_velocity_m_s: float
    mass_flow_rate_kg_s: float

    # Outlet conditions
    outlet_temperature_k: float
    outlet_pressure_pa: float
    outlet_velocity_m_s: float

    # Pressure loss
    static_pressure_drop_pa: float
    static_pressure_drop_bar: float
    total_pressure_drop_pa: float   # stagnation pressure loss (loss of work capacity)
    total_pressure_drop_bar: float

    # Flow state
    is_choked: bool          # True if outlet reached Ma = 1 (sonic throat)
    choking_length_m: Optional[float]  # Length at which flow would choke
    gamma: float             # Heat capacity ratio used

    # Fluid
    fluid: FluidState

    # Full axial profile (optional — generated if n_points > 0)
    profile: List[FannoPoint] = field(default_factory=list)

    # Warnings
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diameter_mm": round(self.diameter_m * 1e3, 2),
            "length_m": round(self.length_m, 3),
            "mach_inlet": round(self.mach_inlet, 4),
            "mach_outlet": round(self.mach_outlet, 4),
            "inlet_temperature_c": round(self.inlet_temperature_k - 273.15, 2),
            "inlet_pressure_bar": round(self.inlet_pressure_pa / 1e5, 4),
            "inlet_velocity_m_s": round(self.inlet_velocity_m_s, 2),
            "mass_flow_rate_kg_s": round(self.mass_flow_rate_kg_s, 5),
            "outlet_temperature_c": round(self.outlet_temperature_k - 273.15, 2),
            "outlet_pressure_bar": round(self.outlet_pressure_pa / 1e5, 4),
            "outlet_velocity_m_s": round(self.outlet_velocity_m_s, 2),
            "static_pressure_drop_bar": round(self.static_pressure_drop_bar, 5),
            "total_pressure_drop_bar": round(self.total_pressure_drop_bar, 5),
            "is_choked": self.is_choked,
            "choking_length_m": self.choking_length_m,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Fanno-flow analytic relations (referenced to sonic state *)
# ---------------------------------------------------------------------------

def _fanno_4fLstar_D(mach: float, gamma: float) -> float:
    """
    Compute the Fanno parameter 4f·L*/D from Ma to sonic (*) condition.
    This is the maximum duct length (in D units times 4f) before choking.

    4fL*/D = (1-Ma²)/(γ·Ma²) + (γ+1)/(2γ) · ln[(γ+1)·Ma²/(2+(γ-1)·Ma²)]
    """
    if abs(mach - 1.0) < 1e-9:
        return 0.0
    g = gamma
    ma2 = mach ** 2
    term1 = (1.0 - ma2) / (g * ma2)
    inner = (g + 1.0) * ma2 / (2.0 + (g - 1.0) * ma2)
    if inner <= 0:
        return 0.0
    term2 = ((g + 1.0) / (2.0 * g)) * math.log(inner)
    return term1 + term2


def _fanno_t_ratio(mach: float, gamma: float) -> float:
    """T/T* ratio."""
    g = gamma
    return (g + 1.0) / 2.0 / (1.0 + (g - 1.0) / 2.0 * mach ** 2)


def _fanno_p_ratio(mach: float, gamma: float) -> float:
    """P/P* ratio."""
    return (1.0 / mach) * math.sqrt(_fanno_t_ratio(mach, gamma))


def _fanno_p0_ratio(mach: float, gamma: float) -> float:
    """P0/P0* ratio (stagnation pressure)."""
    g = gamma
    base = (2.0 / (g + 1.0)) * (1.0 + (g - 1.0) / 2.0 * mach ** 2)
    exp = (g + 1.0) / (2.0 * (g - 1.0))
    return (1.0 / mach) * (base ** exp)


def _mach_from_4fL(target: float, gamma: float, subsonic: bool = True) -> float:
    """
    Numerically invert _fanno_4fLstar_D to find Ma given 4fL*/D = target.
    Uses bisection search.
    """
    if target <= 0.0:
        return 1.0

    lo, hi = (1e-4, 1.0 - 1e-6) if subsonic else (1.0 + 1e-6, 20.0)

    for _ in range(80):
        mid = (lo + hi) / 2.0
        val = _fanno_4fLstar_D(mid, gamma)
        if abs(val - target) < 1e-10:
            break
        if (val > target) == subsonic:
            hi = mid
        else:
            lo = mid

    return (lo + hi) / 2.0


def _speed_of_sound(temperature_k: float, gamma: float, r_specific: float) -> float:
    """Speed of sound: a = sqrt(γ·R·T)."""
    return math.sqrt(gamma * r_specific * max(1.0, temperature_k))


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def analyze_compressible_pipe_flow(
    inlet_pressure_bar: float,
    inlet_temperature_c: float,
    diameter_mm: float,
    length_mm: float,
    mass_flow_rate_kg_s: Optional[float] = None,
    inlet_mach: Optional[float] = None,
    fluid: Optional[FluidState] = None,
    gamma: float = 1.4,
    r_specific: float = 287.058,
    material_roughness_m: float = 4.5e-5,
    n_profile_points: int = 0,
) -> CompressibleFlowResult:
    """
    Analyze Fanno (adiabatic compressible) pipe flow.

    Provide EITHER mass_flow_rate_kg_s OR inlet_mach to specify the flow.
    If both are given, mass_flow_rate takes priority.

    Parameters
    ----------
    inlet_pressure_bar     : Inlet static pressure [bar]
    inlet_temperature_c    : Inlet static temperature [°C]
    diameter_mm            : Inner pipe diameter [mm]
    length_mm              : Pipe length [mm]
    mass_flow_rate_kg_s    : Mass flow rate [kg/s] (optional)
    inlet_mach             : Inlet Mach number (optional, alternative to mass flow)
    fluid                  : FluidState (optional — defaults to air at inlet T)
    gamma                  : Specific heat ratio γ (1.4 for air, 1.3 for CO₂)
    r_specific             : Specific gas constant [J/(kg·K)]
    material_roughness_m   : Absolute wall roughness [m]
    n_profile_points       : Number of axial profile points to compute (0 = skip)

    Returns
    -------
    CompressibleFlowResult with full inlet/outlet state and optional axial profile.
    """
    # --- Geometry ---------------------------------------------------------
    d_m = diameter_mm * 1e-3
    l_m = length_mm * 1e-3
    area_m2 = math.pi / 4.0 * d_m ** 2

    # --- Inlet thermodynamics ---------------------------------------------
    p_in_pa = inlet_pressure_bar * 1e5
    t_in_k = inlet_temperature_c + 273.15

    if fluid is None:
        fluid = get_air_properties(inlet_temperature_c, pressure_pa=p_in_pa)

    rho_in = p_in_pa / (r_specific * t_in_k)
    a_in = _speed_of_sound(t_in_k, gamma, r_specific)

    # --- Determine inlet Mach ---------------------------------------------
    warnings_list: List[str] = []

    if mass_flow_rate_kg_s is not None:
        v_in = mass_flow_rate_kg_s / (rho_in * area_m2)
        ma_in = v_in / a_in
        if ma_in >= 1.0:
            warnings_list.append(
                f"Computed inlet Ma={ma_in:.3f} ≥ 1 (supersonic/choked at inlet). "
                "Clamping to Ma=0.999."
            )
            ma_in = 0.999
    elif inlet_mach is not None:
        ma_in = float(inlet_mach)
        v_in = ma_in * a_in
        mass_flow_rate_kg_s = rho_in * v_in * area_m2
    else:
        raise ValueError("Provide either 'mass_flow_rate_kg_s' or 'inlet_mach'.")

    if ma_in <= 0.0:
        raise ValueError(f"Inlet Mach number must be positive, got {ma_in:.4f}.")

    # --- Friction factor (Colebrook-White at inlet Re) --------------------
    mu_in = fluid.dynamic_viscosity
    re_in = rho_in * v_in * d_m / mu_in if mu_in > 0 else 1e6
    rel_roughness = material_roughness_m / d_m

    # Haaland explicit approximation
    inv_sqrt_f = -1.8 * math.log10((rel_roughness / 3.7) ** 1.11 + 6.9 / max(1.0, re_in))
    f_darcy = 1.0 / max(1e-6, inv_sqrt_f ** 2)
    f_darcy = max(0.005, min(0.15, f_darcy))
    f_fanning = f_darcy / 4.0  # Fanno uses Fanning friction factor

    # --- Choking analysis -------------------------------------------------
    # 4fL*/D from inlet to sonic point
    _4fLstar_in = _fanno_4fLstar_D(ma_in, gamma)
    # 4fL/D for actual duct
    _4fL_duct = 4.0 * f_fanning * l_m / d_m

    is_choked = False
    choking_length_m: Optional[float] = None

    if _4fL_duct >= _4fLstar_in:
        # Duct is long enough to choke the flow
        is_choked = True
        # Actual choking length from inlet
        choking_length_m = _4fLstar_in * d_m / (4.0 * f_fanning) if f_fanning > 0 else None
        warnings_list.append(
            f"Flow is CHOKED: duct 4fL/D={_4fL_duct:.3f} ≥ 4fL*/D={_4fLstar_in:.3f}. "
            "Outlet conditions limited to Ma=1."
        )
        _4fLstar_out = 0.0
        ma_out = 1.0
    else:
        # Compute remaining 4fL*/D at outlet
        _4fLstar_out = _4fLstar_in - _4fL_duct
        ma_out = _mach_from_4fL(_4fLstar_out, gamma, subsonic=(ma_in < 1.0))

    # --- Sonic (*) reference state ----------------------------------------
    # We know inlet Ma and inlet static state; derive sonic reference
    p_ratio_in = _fanno_p_ratio(ma_in, gamma)
    t_ratio_in = _fanno_t_ratio(ma_in, gamma)
    p0_ratio_in = _fanno_p0_ratio(ma_in, gamma)

    p_star = p_in_pa / p_ratio_in
    t_star = t_in_k / t_ratio_in
    # Stagnation at inlet
    t0_in = t_in_k * (1.0 + (gamma - 1.0) / 2.0 * ma_in ** 2)
    p0_in = p_in_pa * (t0_in / t_in_k) ** (gamma / (gamma - 1.0))

    # --- Outlet state -----------------------------------------------------
    t_ratio_out = _fanno_t_ratio(ma_out, gamma)
    p_ratio_out = _fanno_p_ratio(ma_out, gamma)
    p0_ratio_out = _fanno_p0_ratio(ma_out, gamma)

    t_out_k = t_star * t_ratio_out
    p_out_pa = p_star * p_ratio_out
    p0_out = p_star * p0_ratio_out if p_star > 0 else 0.0

    a_out = _speed_of_sound(t_out_k, gamma, r_specific)
    v_out = ma_out * a_out

    dp_static_pa = p_in_pa - p_out_pa
    dp_total_pa = p0_in - p0_out

    # --- Axial profile ----------------------------------------------------
    profile: List[FannoPoint] = []
    if n_profile_points > 1:
        x_points = [i * l_m / (n_profile_points - 1) for i in range(n_profile_points)]
        for x in x_points:
            _4fL_x = 4.0 * f_fanning * x / d_m
            _4fLstar_x = max(0.0, _4fLstar_in - _4fL_x)
            ma_x = _mach_from_4fL(_4fLstar_x, gamma, subsonic=(ma_in < 1.0)) if _4fLstar_x > 0 else 1.0
            t_x = t_star * _fanno_t_ratio(ma_x, gamma)
            p_x = p_star * _fanno_p_ratio(ma_x, gamma)
            rho_x = p_x / (r_specific * max(1.0, t_x))
            a_x = _speed_of_sound(t_x, gamma, r_specific)
            v_x = ma_x * a_x
            t0_x = t_x * (1.0 + (gamma - 1.0) / 2.0 * ma_x ** 2)
            p0_x = p_x * (t0_x / max(1.0, t_x)) ** (gamma / (gamma - 1.0))
            profile.append(FannoPoint(
                position_m=x,
                mach=round(ma_x, 5),
                temperature_k=round(t_x, 3),
                pressure_pa=round(p_x, 2),
                density_kg_m3=round(rho_x, 4),
                velocity_m_s=round(v_x, 3),
                total_pressure_pa=round(p0_x, 2),
                total_temperature_k=round(t0_in, 3),  # adiabatic: T0 = const
            ))

    return CompressibleFlowResult(
        diameter_m=d_m,
        length_m=l_m,
        mach_inlet=round(ma_in, 5),
        mach_outlet=round(ma_out, 5),
        inlet_temperature_k=t_in_k,
        inlet_pressure_pa=p_in_pa,
        inlet_velocity_m_s=round(v_in, 3),
        mass_flow_rate_kg_s=round(mass_flow_rate_kg_s, 6),
        outlet_temperature_k=round(t_out_k, 3),
        outlet_pressure_pa=round(p_out_pa, 2),
        outlet_velocity_m_s=round(v_out, 3),
        static_pressure_drop_pa=round(dp_static_pa, 2),
        static_pressure_drop_bar=round(dp_static_pa / 1e5, 6),
        total_pressure_drop_pa=round(dp_total_pa, 2),
        total_pressure_drop_bar=round(dp_total_pa / 1e5, 6),
        is_choked=is_choked,
        choking_length_m=choking_length_m,
        gamma=gamma,
        fluid=fluid,
        profile=profile,
        warnings=warnings_list,
    )
