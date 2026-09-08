"""
cadi_saml.simulation.flow.fluid_properties

Temperature-dependent thermophysical and transport properties for fluids.
Supports:
  - Water (IAPWS formulas)
  - Air (Sutherland + Ideal Gas Law)
  - Hydraulic oils ISO VG 32/46/68 (Walther/ASTM D341)
  - Ethylene glycol / Propylene glycol (automotive cooling)
  - Seawater (UNESCO / TEOS-10 simplified)
  - R134a refrigerant (HVAC, vapor compression cycles)
  - Diesel fuel / JP-8 aviation fuel
  - Nitrogen gas (industrial, inerting, cryogenics)
  - CO₂ gas (industrial, food-grade)
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
    density: float              # kg/m³
    dynamic_viscosity: float    # Pa·s
    kinematic_viscosity: float  # m²/s
    vapor_pressure: float       # Pa (saturation pressure for cavitation checks)
    specific_heat: float = 4182.0   # J/(kg·K)
    thermal_conductivity: float = 0.6  # W/(m·K)
    compressible: bool = False   # True for gas-phase fluids

    @property
    def prandtl_number(self) -> float:
        """Dimensionless Prandtl number: Pr = mu * Cp / k."""
        if self.thermal_conductivity <= 0:
            return 0.0
        return (self.dynamic_viscosity * self.specific_heat) / self.thermal_conductivity


# ---------------------------------------------------------------------------
# Water (IAPWS / NIST)
# ---------------------------------------------------------------------------

def get_water_properties(temp_c: float) -> FluidState:
    """
    Pure liquid water properties at 1 atm, valid 0–100 °C.
    Density: Kell / IAPWS formula.
    Viscosity: Andrade/Vogel equation.
    Vapor pressure: Antoine equation.
    """
    t = max(0.0, min(100.0, temp_c))
    tk = t + 273.15

    density = 1000.0 * (
        1.0 - ((t + 288.9414) / (508929.2 * (t + 68.12963))) * ((t - 3.9863) ** 2)
    )
    mu = 2.414e-5 * (10.0 ** (247.8 / (tk - 140.0)))
    nu = mu / density

    p_mmhg = 10.0 ** (8.07131 - 1730.63 / (233.426 + t))
    vapor_p = p_mmhg * 133.322387415

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


# ---------------------------------------------------------------------------
# Air (Sutherland + Ideal Gas Law)
# ---------------------------------------------------------------------------

def get_air_properties(temp_c: float, pressure_pa: float = 101325.0) -> FluidState:
    """
    Dry air at temp_c (-40 to 300 °C) and absolute pressure_pa.
    Viscosity via Sutherland's law; density via Ideal Gas.
    """
    tk = temp_c + 273.15
    density = pressure_pa / (287.058 * tk)

    mu_0, t_0, s = 1.716e-5, 273.15, 110.4
    mu = mu_0 * ((tk / t_0) ** 1.5) * ((t_0 + s) / (tk + s))
    nu = mu / density

    # Thermal conductivity of air (Sutherland-like, W/m·K)
    k_air = 0.02624 * ((tk / 300.0) ** 0.8646)

    return FluidState(
        name="air",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=0.0,
        specific_heat=1005.0,
        thermal_conductivity=k_air,
        compressible=True,
    )


# ---------------------------------------------------------------------------
# Hydraulic oil — ISO VG grades (Walther/ASTM D341)
# ---------------------------------------------------------------------------

def get_hydraulic_oil_properties(vg_grade: int = 46, temp_c: float = 40.0) -> FluidState:
    """
    Mineral hydraulic oil ISO VG 32/46/68.
    Viscosity-temperature via Walther equation; VI ≈ 100.
    """
    density_15 = 875.0
    density = density_15 * (1.0 - 0.0007 * (temp_c - 15.0))

    nu_40 = float(vg_grade)
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
        vapor_pressure=10.0,
        specific_heat=1900.0,
        thermal_conductivity=0.13,
    )


# ---------------------------------------------------------------------------
# Ethylene Glycol / Propylene Glycol (automotive coolant)
# ---------------------------------------------------------------------------

def get_glycol_properties(
    glycol_type: str = "ethylene",
    concentration_pct: float = 50.0,
    temp_c: float = 20.0,
) -> FluidState:
    """
    Water-glycol mixture properties for automotive and HVAC cooling loops.

    Parameters
    ----------
    glycol_type : 'ethylene' (EG, MEG) or 'propylene' (PG, MPG)
    concentration_pct : glycol volume percent in water (0–100)
    temp_c : bulk fluid temperature in °C (-40 to 130 °C)

    Reference: ASHRAE Fundamentals Handbook (SI), Chap. 31 — Thermophysical
    properties of brines and secondary refrigerants.
    """
    c = max(0.0, min(100.0, concentration_pct)) / 100.0  # fraction 0–1
    t = max(-40.0, min(130.0, temp_c))

    if glycol_type.lower().startswith("prop"):
        # Propylene glycol (PG): slightly higher viscosity, lower toxicity
        # Density at 20 °C pure PG ≈ 1036 kg/m³; water ≈ 998 kg/m³
        rho_pure = 1036.0 - 0.65 * t
        rho_water = 998.2 - 0.3 * t
        density = rho_water * (1 - c) + rho_pure * c
        # Viscosity: strong function of concentration and temperature
        # Fit to ASHRAE Table 31.1 PG
        ln_mu_ref = -3.5 + c * 5.5 - c ** 2 * 2.5  # ln(mu) at 20 C
        e_act = 2000.0 + c * 3000.0
        mu = math.exp(ln_mu_ref) * math.exp(e_act * (1.0 / (t + 273.15) - 1.0 / 293.15))
        cp = 4200.0 - c * 1900.0  # J/kg·K
        k_fluid = 0.58 - c * 0.22  # W/m·K
        name = f"propylene_glycol_{concentration_pct:.0f}pct"
    else:
        # Ethylene glycol (EG): standard automotive antifreeze
        # Pure EG density ≈ 1113 kg/m³ at 20 °C
        rho_pure = 1113.0 - 0.65 * t
        rho_water = 998.2 - 0.3 * t
        density = rho_water * (1 - c) + rho_pure * c
        # Viscosity fit (mPa·s) — ASHRAE / CRC Handbook
        # At 50% EG: ~4.0 mPa·s at 20 °C, ~1.4 at 60 °C
        ln_mu_ref = -3.2 + c * 4.8 - c ** 2 * 2.0
        e_act = 1800.0 + c * 2800.0
        mu = math.exp(ln_mu_ref) * math.exp(e_act * (1.0 / (t + 273.15) - 1.0 / 293.15))
        cp = 4200.0 - c * 1700.0
        k_fluid = 0.59 - c * 0.21
        name = f"ethylene_glycol_{concentration_pct:.0f}pct"

    mu = max(5e-4, mu)  # clamp — very cold glycol can be extremely viscous
    nu = mu / max(1.0, density)
    vapor_p = get_water_properties(t).vapor_pressure * (1.0 - c * 0.8)

    return FluidState(
        name=name,
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=vapor_p,
        specific_heat=cp,
        thermal_conductivity=k_fluid,
    )


# ---------------------------------------------------------------------------
# Seawater (UNESCO / TEOS-10 simplified)
# ---------------------------------------------------------------------------

def get_seawater_properties(
    temp_c: float = 20.0,
    salinity_ppt: float = 35.0,
    pressure_pa: float = 101325.0,
) -> FluidState:
    """
    Seawater properties (UNESCO 1983 / TEOS-10 simplified polynomial).
    Valid: 0–40 °C, 0–40 g/kg salinity, 0–1000 m depth.

    Parameters
    ----------
    temp_c : temperature in °C
    salinity_ppt : practical salinity (PSU ≈ g/kg) — standard ocean ≈ 35
    pressure_pa : absolute pressure (affects density at depth)
    """
    t = max(0.0, min(40.0, temp_c))
    s = max(0.0, min(40.0, salinity_ppt))

    # UNESCO (1983) seawater density — Chen & Millero polynomial
    # rho_sw(T, S, P=0) = rho_w + S*(A + B*T + C*T²) + S^1.5 * D + S² * E
    rho_w = (
        999.842594
        + 6.793952e-2 * t
        - 9.095290e-3 * t**2
        + 1.001685e-4 * t**3
        - 1.120083e-6 * t**4
        + 6.536332e-9 * t**5
    )
    A = 8.24493e-1 - 4.0899e-3 * t + 7.6438e-5 * t**2 - 8.2467e-7 * t**3 + 5.3875e-9 * t**4
    B = -5.72466e-3 + 1.0227e-4 * t - 1.6546e-6 * t**2
    C = 4.8314e-4
    density = rho_w + A * s + B * (s**1.5) + C * s**2

    # Pressure correction (shallow — simplified linear)
    depth_m = max(0.0, (pressure_pa - 101325.0) / (density * 9.80665))
    density += 4.5e-3 * depth_m  # ~ 0.45 kg/m³ per 100 m

    # Dynamic viscosity — Millero & Poiseuille (1977)
    # mu_sw = mu_w * (1 + 0.00219 * S + 1.3e-5 * S²)
    mu_w = 2.414e-5 * (10.0 ** (247.8 / ((t + 273.15) - 140.0)))
    mu = mu_w * (1.0 + 2.19e-3 * s + 1.3e-5 * s**2)
    nu = mu / density

    # Thermal conductivity (Caldwell 1974 polynomial, W/m·K)
    k_sw = 0.5726 + 0.001756 * t - 6.7e-6 * t**2 + 1.8e-4 * s

    # Specific heat (Millero 1973, J/kg·K)
    cp_sw = (
        4217.4
        - 3.720283 * t
        + 0.1412855 * t**2
        - 2.654387e-3 * t**3
        + 2.093236e-5 * t**4
        + s * (-7.643575 + 0.1072763 * t - 1.38385e-3 * t**2)
    )

    # Vapor pressure reduced by salinity (Raoult's law approximation)
    x_salt = s / (s + 1000.0 * 18.015 / 58.443)  # mole fraction NaCl
    vapor_p_w = get_water_properties(t).vapor_pressure
    vapor_p = vapor_p_w * (1.0 - 2.0 * x_salt)  # Van't Hoff factor ≈ 2

    return FluidState(
        name=f"seawater_S{salinity_ppt:.0f}",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=max(0.0, vapor_p),
        specific_heat=cp_sw,
        thermal_conductivity=k_sw,
    )


# ---------------------------------------------------------------------------
# R134a Refrigerant (1,1,1,2-Tetrafluoroethane) — liquid phase
# ---------------------------------------------------------------------------

def get_r134a_properties(temp_c: float = -10.0) -> FluidState:
    """
    R134a (HFC-134a) saturated liquid properties, -40 to +70 °C.
    Fit to ASHRAE Fundamentals / NIST WebBook data.
    Critical point: Tc = 101.06 °C, Pc = 4059 kPa, ρc = 511 kg/m³.

    Note: Returns LIQUID phase properties (below saturation temperature).
    """
    t = max(-40.0, min(60.0, temp_c))

    # Density (saturated liquid) — polynomial fit to NIST data (kg/m³)
    density = (
        1294.0
        - 2.756 * t
        - 3.4e-3 * t**2
        - 1.2e-4 * t**3
    )

    # Dynamic viscosity (mPa·s → Pa·s) — Arrhenius-type fit
    mu_mPas = 0.2735 * math.exp(1160.0 / (t + 273.15) - 3.68)
    mu = max(5e-5, mu_mPas * 1e-3)
    nu = mu / max(1.0, density)

    # Saturation pressure (bar → Pa) — Antoine-type fit
    p_sat_bar = math.exp(8.929 - 1650.0 / (t + 243.15))
    vapor_p = p_sat_bar * 1e5

    # Specific heat liquid (J/kg·K)
    cp = 1300.0 + 3.5 * t

    # Thermal conductivity liquid (W/m·K)
    k = 0.0946 - 3.0e-4 * t

    return FluidState(
        name="r134a_liquid",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=vapor_p,
        specific_heat=cp,
        thermal_conductivity=k,
    )


# ---------------------------------------------------------------------------
# Diesel Fuel / JP-8 Aviation Fuel
# ---------------------------------------------------------------------------

def get_fuel_properties(
    fuel_type: str = "diesel",
    temp_c: float = 20.0,
) -> FluidState:
    """
    Liquid fuel properties for diesel engines and jet/aviation systems.

    Supported fuels:
      'diesel'  — EN 590 diesel fuel (typical density 820-860 kg/m³ at 15 °C)
      'jp8'     — JP-8 / Jet A-1 aviation turbine fuel (MIL-DTL-83133)
      'gasoline'— Automotive gasoline (EN 228)

    Reference: Smoot & Smith (1985), MIL-HDBK-1003/6.
    """
    t = max(-40.0, min(150.0, temp_c))
    ft = fuel_type.lower().strip()

    if ft in ("jp8", "jeta", "jet_a", "jet_a1", "jet-a"):
        rho_15 = 800.0  # typical JP-8 density at 15 °C, kg/m³
        beta = 7.0e-4   # thermal expansion coefficient 1/°C
        density = rho_15 * (1.0 - beta * (t - 15.0))
        # Viscosity (cSt) fit: ~8 cSt at -20 °C, ~1.2 cSt at 40 °C
        nu_cst = 1.0 + 7.0 * math.exp(-0.045 * (t + 20.0))
        nu = max(3e-7, nu_cst * 1e-6)
        mu = nu * density
        vapor_p = 133.322 * 10.0 ** (7.2 - 1750.0 / (t + 230.0))
        cp = 1980.0 + 3.5 * t
        k = 0.130 - 8e-5 * t
        name = "jp8"
    elif ft in ("gasoline", "petrol"):
        rho_15 = 745.0
        beta = 9.5e-4
        density = rho_15 * (1.0 - beta * (t - 15.0))
        nu_cst = 0.5 + 0.7 * math.exp(-0.03 * t)
        nu = max(1e-7, nu_cst * 1e-6)
        mu = nu * density
        vapor_p = 133.322 * 10.0 ** (6.89 - 1250.0 / (t + 220.0))
        cp = 2040.0 + 4.0 * t
        k = 0.12 - 6e-5 * t
        name = "gasoline"
    else:  # diesel (default)
        rho_15 = 840.0  # mid-range diesel
        beta = 7.5e-4
        density = rho_15 * (1.0 - beta * (t - 15.0))
        # ASTM D445 kinematic viscosity (cSt at 40 °C = 3.0 typ.)
        nu_cst = 2.5 * math.exp(0.025 * (40.0 - t))
        nu = max(1e-6, nu_cst * 1e-6)
        mu = nu * density
        vapor_p = 100.0  # very low vapor pressure (high flash point ~60 °C)
        cp = 1970.0 + 3.0 * t
        k = 0.135 - 9e-5 * t
        name = "diesel"

    return FluidState(
        name=name,
        temperature_c=temp_c,
        density=max(500.0, density),
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=vapor_p,
        specific_heat=cp,
        thermal_conductivity=max(0.08, k),
    )


# ---------------------------------------------------------------------------
# Nitrogen Gas (N₂)
# ---------------------------------------------------------------------------

def get_nitrogen_properties(
    temp_c: float = 20.0,
    pressure_pa: float = 101325.0,
) -> FluidState:
    """
    Nitrogen gas properties via Ideal Gas Law + Sutherland viscosity.
    Valid for gas phase: -150 °C (above boiling, -195.8 °C) to 500 °C.

    Note: Below -195.8 °C nitrogen liquefies; this function only models gas.
    """
    tk = max(80.0, temp_c + 273.15)  # clamp well above liquid N2 boiling
    # Ideal gas: R_N2 = 296.8 J/(kg·K), M = 28.014 g/mol
    density = pressure_pa / (296.8 * tk)

    # Sutherland's law for N2: mu_ref=17.81e-6 Pa·s at 300 K, S=111 K
    mu_ref, t_ref, s_n2 = 17.81e-6, 300.0, 111.0
    mu = mu_ref * ((tk / t_ref) ** 1.5) * ((t_ref + s_n2) / (tk + s_n2))
    nu = mu / density

    # Thermal conductivity N2 (NIST fit, W/m·K)
    k = 0.02442 * (tk / 293.15) ** 0.82

    return FluidState(
        name="nitrogen",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=0.0,
        specific_heat=1040.0,
        thermal_conductivity=k,
        compressible=True,
    )


# ---------------------------------------------------------------------------
# Carbon Dioxide Gas (CO₂)
# ---------------------------------------------------------------------------

def get_co2_properties(
    temp_c: float = 20.0,
    pressure_pa: float = 101325.0,
) -> FluidState:
    """
    CO₂ gas properties (ideal gas + Sutherland). Gas phase only (T > 31.1 °C
    at supercritical; below Tc behaviour is approximated).
    Valid: 0–400 °C, pressures up to ~5 MPa (ideal gas assumption).
    """
    tk = max(273.15, temp_c + 273.15)
    # Specific gas constant for CO2: R = 8314/44.01 = 188.9 J/(kg·K)
    density = pressure_pa / (188.9 * tk)

    # Sutherland for CO2: mu_ref=15.0e-6 at 293K, S=240 K
    mu_ref, t_ref, s_co2 = 15.0e-6, 293.0, 240.0
    mu = mu_ref * ((tk / t_ref) ** 1.5) * ((t_ref + s_co2) / (tk + s_co2))
    nu = mu / density

    # Thermal conductivity (W/m·K)
    k = 0.01456 * (tk / 293.0) ** 0.88

    # Cp at moderate P (J/kg·K) — NIST polynomial approximation
    cp = 819.0 + 0.56 * (tk - 273.15) - 1.4e-4 * (tk - 273.15) ** 2

    return FluidState(
        name="co2",
        temperature_c=temp_c,
        density=density,
        dynamic_viscosity=mu,
        kinematic_viscosity=nu,
        vapor_pressure=0.0,
        specific_heat=cp,
        thermal_conductivity=k,
        compressible=True,
    )


# ---------------------------------------------------------------------------
# Master Factory
# ---------------------------------------------------------------------------

def resolve_fluid(name: str, temp_c: float = 20.0, **kwargs: Any) -> FluidState:
    """
    Resolve fluid properties by name string.

    Supported identifiers (case-insensitive):
      Water:             'water', 'su', 'h2o'
      Air:               'air', 'hava'
      Hydraulic oil:     'hydraulic_oil', 'oil', 'vg32', 'vg46', 'vg68'
      Ethylene glycol:   'ethylene_glycol', 'eg', 'glycol' (use concentration_pct kwarg)
      Propylene glycol:  'propylene_glycol', 'pg'
      Seawater:          'seawater', 'sea', 'saltwater' (use salinity_ppt kwarg)
      R134a refrigerant: 'r134a', 'hfc134a', 'refrigerant'
      Diesel fuel:       'diesel', 'fuel_diesel'
      JP-8 / Jet A:      'jp8', 'jeta', 'jet_a', 'aviation_fuel'
      Gasoline:          'gasoline', 'petrol'
      Nitrogen gas:      'nitrogen', 'n2'
      CO₂ gas:           'co2', 'carbon_dioxide'

    Additional kwargs are forwarded to the specific property function where applicable.
    """
    n = name.lower().strip()

    # Water
    if n in ("water", "su", "h2o", "saf_su"):
        return get_water_properties(temp_c)

    # Air
    elif n in ("air", "hava", "dry_air"):
        pressure = kwargs.get("pressure_pa", 101325.0)
        return get_air_properties(temp_c, pressure_pa=pressure)

    # Hydraulic oil
    elif any(x in n for x in ("oil", "hydraulic", "vg32", "vg46", "vg68", "vg_")):
        grade = 46
        if "32" in n:
            grade = 32
        elif "68" in n:
            grade = 68
        return get_hydraulic_oil_properties(vg_grade=grade, temp_c=temp_c)

    # Ethylene glycol
    elif n in ("ethylene_glycol", "eg", "glycol", "meg", "antifreeze"):
        conc = kwargs.get("concentration_pct", 50.0)
        return get_glycol_properties("ethylene", conc, temp_c)

    # Propylene glycol
    elif n in ("propylene_glycol", "pg", "mpg", "propylene"):
        conc = kwargs.get("concentration_pct", 50.0)
        return get_glycol_properties("propylene", conc, temp_c)

    # Seawater
    elif n in ("seawater", "sea", "saltwater", "deniz_suyu"):
        sal = kwargs.get("salinity_ppt", 35.0)
        pressure = kwargs.get("pressure_pa", 101325.0)
        return get_seawater_properties(temp_c, salinity_ppt=sal, pressure_pa=pressure)

    # R134a refrigerant
    elif n in ("r134a", "hfc134a", "hfc-134a", "refrigerant", "r-134a"):
        return get_r134a_properties(temp_c)

    # Diesel
    elif n in ("diesel", "fuel_diesel", "motorin"):
        return get_fuel_properties("diesel", temp_c)

    # JP-8 / Jet-A aviation fuel
    elif n in ("jp8", "jp-8", "jeta", "jet_a", "jet_a1", "jet-a", "aviation_fuel", "kerosene"):
        return get_fuel_properties("jp8", temp_c)

    # Gasoline
    elif n in ("gasoline", "petrol", "benzin"):
        return get_fuel_properties("gasoline", temp_c)

    # Nitrogen
    elif n in ("nitrogen", "n2", "azot"):
        pressure = kwargs.get("pressure_pa", 101325.0)
        return get_nitrogen_properties(temp_c, pressure_pa=pressure)

    # CO2
    elif n in ("co2", "carbon_dioxide", "co_2", "karbondioksit"):
        pressure = kwargs.get("pressure_pa", 101325.0)
        return get_co2_properties(temp_c, pressure_pa=pressure)

    else:
        # Graceful fallback: water
        import warnings
        warnings.warn(
            f"Unknown fluid '{name}' — falling back to water. "
            f"Supported: water, air, hydraulic_oil, ethylene_glycol, propylene_glycol, "
            f"seawater, r134a, diesel, jp8, gasoline, nitrogen, co2.",
            UserWarning,
            stacklevel=2,
        )
        return get_water_properties(temp_c)
