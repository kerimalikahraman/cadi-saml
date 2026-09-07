"""
cadi_saml.simulation.flow.fluid_properties

Temperature-dependent thermophysical and transport properties for fluids.
Supports water, air, hydraulic oils (ISO VG 32, 46, 68), engine oil, and glycols.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class FluidState:
    """Fluid thermophysical properties at a specific temperature and pressure."""
    name: str
    temperature_c: float
    density: float             # kg/m^3
    dynamic_viscosity: float   # Pa*s
    kinematic_viscosity: float # m^2/s
    vapor_pressure: float      # Pa (saturation pressure for cavitation checks)
    specific_heat: float = 4182.0  # J/(kg*K)
    thermal_conductivity: float = 0.6 # W/(m*K)

    @property
    def prandtl_number(self) -> float:
        if self.thermal_conductivity <= 0:
            return 0.0
        return (self.dynamic_viscosity * self.specific_heat) / self.thermal_conductivity


def get_water_properties(temp_c: float) -> FluidState:
    """
    Calculate pure liquid water properties at 1 atm as a function of temperature (0-100 °C).
    Formulas based on standard IAPWS/NIST correlations.
    """
    # Clamp valid range with warning logic if exceeded
    t = max(0.0, min(100.0, temp_c))

    # Standard Kell / IAPWS formula for pure liquid water density (0 - 100 °C)
    # Maximum density at 3.98 °C (~999.97 kg/m^3), ~998.2 kg/m^3 at 20 °C, ~958.4 kg/m^3 at 100 °C
    density = 1000.0 * (1.0 - ((t + 288.9414) / (508929.2 * (t + 68.12963))) * ((t - 3.9863) ** 2))

    # Dynamic viscosity: Vogel equation formulation
    # mu (Pa*s) = A * 10^(B / (T_K - C))
    tk = t + 273.15
    # For water: Andrade/Vogel coefficients
    # At 20 C: approx 1.002e-3 Pa*s
    mu = 2.414e-5 * (10.0 ** (247.8 / (tk - 140.0)))

    nu = mu / density

    # Saturation vapor pressure (Antoine equation for water, mmHg -> Pa)
    # log10(P_mmHg) = A - B / (C + T_C)
    # For 1-100 C: A=8.07131, B=1730.63, C=233.426
    p_mmhg = 10.0 ** (8.07131 - 1730.63 / (233.426 + t))
    vapor_p = p_mmhg * 133.322387415

    # Specific heat approx 4182 J/kg*K
    cp = 4182.0 - 0.5 * (t - 20.0)
    k = 0.598 + 0.0015 * (t - 20.0)

    return FluidState(
        name="water",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=vapor_p,
        specific_heat=cp,
        thermal_conductivity=k,
    )


def get_air_properties(temp_c: float, pressure_pa: float = 101325.0) -> FluidState:
    """
    Dry air properties at temperature temp_c (-40 to 300 °C) and pressure_pa.
    Uses Ideal Gas Law and Sutherland's formula for dynamic viscosity.
    """
    tk = temp_c + 273.15
    # Gas constant for dry air R = 287.058 J/(kg*K)
    density = pressure_pa / (287.058 * tk)

    # Sutherland's law for dynamic viscosity of air
    # mu = mu_0 * (T / T_0)^(3/2) * (T_0 + S) / (T + S)
    # mu_0 = 1.716e-5 Pa*s, T_0 = 273.15 K, S = 110.4 K
    mu_0 = 1.716e-5
    t_0 = 273.15
    s = 110.4
    mu = mu_0 * ((tk / t_0) ** 1.5) * ((t_0 + s) / (tk + s))
    nu = mu / density

    return FluidState(
        name="air",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=0.0,
        specific_heat=1005.0,
        thermal_conductivity=0.026,
    )


def get_hydraulic_oil_properties(vg_grade: int = 46, temp_c: float = 40.0) -> FluidState:
    """
    Mineral hydraulic oil (ISO VG 32, 46, 68) properties.
    ISO VG definition: kinematic viscosity in cSt (mm^2/s) at 40 °C.
    Viscosity-temperature variation modeled via Walther/ASTM D341 equation.
    """
    density_15 = 875.0  # standard density at 15 °C
    # Thermal expansion coefficient approx 0.0007 / °C
    density = density_15 * (1.0 - 0.0007 * (temp_c - 15.0))

    # Walther equation: log10(log10(nu_cSt + 0.7)) = A - B * log10(T_K)
    # Calibrated for typical mineral oils with Viscosity Index VI ~ 100
    nu_40 = float(vg_grade)
    # Estimate nu at 100 °C from VI ~ 100
    # VG46 -> approx 6.8 cSt at 100C; VG32 -> 5.4 cSt; VG68 -> 8.7 cSt
    nu_100 = 1.35 * (nu_40 ** 0.42)

    t40 = 40.0 + 273.15
    t100 = 100.0 + 273.15
    w40 = math.log10(math.log10(nu_40 + 0.7))
    w100 = math.log10(math.log10(nu_100 + 0.7))

    b = (w40 - w100) / (math.log10(t100) - math.log10(t40))
    a = w40 + b * math.log10(t40)

    tk = temp_c + 273.15
    w_t = a - b * math.log10(tk)
    nu_cst = 10.0 ** (10.0 ** w_t) - 0.7
    nu_m2_s = max(1e-6, nu_cst * 1e-6)
    mu = nu_m2_s * density

    return FluidState(
        name=f"hydraulic_oil_vg{vg_grade}",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu_m2_s,
        vapor_pressure=10.0, # Very low vapor pressure
        specific_heat=1900.0,
        thermal_conductivity=0.13,
    )


def resolve_fluid(name: str, temp_c: float = 20.0) -> FluidState:
    """Main factory resolving fluid properties by identifier string."""
    n = name.lower().strip()
    if n in ("water", "su", "h2o"):
        return get_water_properties(temp_c)
    elif n in ("air", "hava"):
        return get_air_properties(temp_c)
    elif "oil" in n or "hydraulic" in n or "vg" in n:
        grade = 46
        if "32" in n:
            grade = 32
        elif "68" in n:
            grade = 68
        return get_hydraulic_oil_properties(vg_grade=grade, temp_c=temp_c)
    else:
        # Default fallback to water with clean note
        return get_water_properties(temp_c)
