"""
Mechanical Engineering Standard Calculation Formulas for CADI-SAML.
Implements shaft sizing, keyway stress, bolt preload (VDI 2230), bearing L10h life (ISO 281),
gear Lewis tooth bending, and pressure vessel sizing (ASME VIII / EN 13445).
"""

from typing import Any, Dict, Optional
import math


def calculate_shaft_diameter(
    torque_nm: float,
    allowable_shear_stress_mpa: float = 40.0,
    bending_moment_nm: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates minimum required shaft diameter under pure torsion or combined bending/torsion.
    Equivalent torque: T_eq = sqrt(M^2 + T^2)
    tau = (16 * T_eq) / (pi * d^3) <= tau_allow
    """
    t = float(torque_nm) * 1000.0  # N.mm
    m = float(bending_moment_nm) * 1000.0  # N.mm
    t_eq = math.sqrt(m**2 + t**2)
    tau_allow = float(allowable_shear_stress_mpa)  # MPa = N/mm2

    min_dia = math.pow((16.0 * t_eq) / (math.pi * tau_allow), 1.0 / 3.0)

    # Suggest next standard shaft diameter (DIN 748)
    std_sizes = [6, 8, 10, 12, 14, 15, 16, 18, 20, 22, 24, 25, 28, 30, 32, 35, 38, 40, 42, 45, 48, 50, 55, 60, 65, 70, 75, 80, 90, 100]
    rec_size = next((s for s in std_sizes if s >= min_dia), math.ceil(min_dia))

    return {
        "calculated_min_diameter_mm": round(min_dia, 2),
        "recommended_standard_diameter_mm": rec_size,
        "equivalent_torque_nm": round(t_eq / 1000.0, 2),
        "allowable_shear_stress_mpa": tau_allow,
    }


def calculate_keyway_stresses(
    torque_nm: float,
    shaft_dia_mm: float,
    key_width_mm: float,
    key_height_mm: float,
    key_length_mm: float,
    hub_depth_t2_mm: Optional[float] = None,
    allowable_pressure_mpa: float = 100.0,
    allowable_shear_mpa: float = 60.0,
) -> Dict[str, Any]:
    """
    Verifies shear stress and surface bearing pressure on parallel keys (DIN 6885-1).
    """
    d = float(shaft_dia_mm)
    ft = (2.0 * float(torque_nm) * 1000.0) / d  # Tangential force (N)
    b = float(key_width_mm)
    h = float(key_height_mm)
    l = float(key_length_mm)
    t2 = hub_depth_t2_mm or (h * 0.45)  # Contact height in hub

    # Shear stress: tau = Ft / (b * l)
    tau = ft / (b * l)
    # Compressive surface pressure: p = Ft / (t2 * l)
    p = ft / (t2 * l)

    return {
        "tangential_force_n": round(ft, 2),
        "shear_stress_mpa": round(tau, 2),
        "surface_pressure_mpa": round(p, 2),
        "shear_safe": tau <= allowable_shear_mpa,
        "pressure_safe": p <= allowable_pressure_mpa,
        "allowable_shear_mpa": allowable_shear_mpa,
        "allowable_pressure_mpa": allowable_pressure_mpa,
    }


def calculate_bearing_l10h_life(
    dynamic_load_rating_c_kn: float,
    equivalent_radial_load_p_kn: float,
    speed_rpm: float,
    bearing_type: str = "ball",
) -> Dict[str, Any]:
    """
    Calculates basic L10h rating life in operating hours according to ISO 281.
    """
    c = float(dynamic_load_rating_c_kn)
    p = float(equivalent_radial_load_p_kn)
    n = float(speed_rpm)

    # Life exponent: 3.0 for ball bearings, 10/3 for roller bearings
    exponent = 3.0 if "ball" in bearing_type.lower() else (10.0 / 3.0)

    l10_millions = math.pow(c / max(p, 1e-4), exponent)
    l10h_hours = (1.0e6 / (60.0 * max(n, 1e-4))) * l10_millions

    return {
        "bearing_type": bearing_type,
        "l10_million_revolutions": round(l10_millions, 2),
        "l10h_hours": round(l10h_hours, 1),
        "is_industrial_acceptable": l10h_hours >= 20000.0,  # Standard 20k hrs for industrial machinery
    }


def calculate_bolt_preload(
    nominal_dia_mm: float = 10.0,
    property_class: str = "8.8",
    friction_coeff: float = 0.14,
) -> Dict[str, Any]:
    """
    Estimates assembly clamp preload and tightening torque according to VDI 2230 guidelines.
    """
    # Nominal stress areas for metric coarse threads (ISO 965-1) in mm2
    area_map = {3: 5.03, 4: 8.78, 5: 14.2, 6: 20.1, 8: 36.6, 10: 58.0, 12: 84.3, 14: 115.0, 16: 157.0, 20: 245.0, 24: 353.0}
    d_int = int(round(nominal_dia_mm))
    as_area = area_map.get(d_int, math.pi * (nominal_dia_mm * 0.9)**2 / 4.0)

    # Yield strength from property class (e.g. 8.8 -> 800 * 0.8 = 640 MPa)
    parts = property_class.split(".")
    tensile = float(parts[0]) * 100.0
    yield_ratio = float(parts[1]) / 10.0 if len(parts) > 1 else 0.8
    rp02 = tensile * yield_ratio

    # 90% utilization of yield at tightening
    fm_preload_n = 0.9 * rp02 * as_area
    # Torque estimate: T = F_M * (0.16 * p + 0.58 * d2 * mu + r_head * mu) ~ F_M * d * k
    k_factor = 0.20 if friction_coeff >= 0.14 else 0.16
    torque_nm = (fm_preload_n * (nominal_dia_mm / 1000.0)) * k_factor

    return {
        "bolt": f"M{d_int}",
        "property_class": property_class,
        "stress_area_mm2": round(as_area, 2),
        "yield_strength_mpa": round(rp02, 1),
        "assembly_preload_kn": round(fm_preload_n / 1000.0, 2),
        "tightening_torque_nm": round(torque_nm, 1),
    }


def calculate_pressure_vessel_wall_thickness(
    internal_pressure_bar: float,
    internal_diameter_mm: float,
    allowable_stress_mpa: float = 120.0,
    joint_efficiency: float = 1.0,
    corrosion_allowance_mm: float = 1.0,
) -> Dict[str, Any]:
    """
    Calculates cylindrical pressure vessel shell thickness according to ASME Sec VIII Div 1 / EN 13445.
    t = (P * R) / (S * E - 0.6 * P) + c
    """
    p = float(internal_pressure_bar) * 0.1  # Convert bar to MPa
    r = float(internal_diameter_mm) / 2.0  # Inside radius (mm)
    s = float(allowable_stress_mpa)
    e = float(joint_efficiency)
    c = float(corrosion_allowance_mm)

    denom = (s * e) - (0.6 * p)
    if denom <= 0:
        raise ValueError("Pressure exceeds allowable stress limit.")

    t_nominal = (p * r) / denom
    t_total = t_nominal + c

    return {
        "design_pressure_bar": internal_pressure_bar,
        "inside_diameter_mm": internal_diameter_mm,
        "nominal_thickness_mm": round(t_nominal, 2),
        "corrosion_allowance_mm": c,
        "total_thickness_mm": round(t_total, 2),
        "recommended_plate_thickness_mm": math.ceil(t_total),
    }
