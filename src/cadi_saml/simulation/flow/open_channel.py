"""
cadi_saml.simulation.flow.open_channel

Open channel flow analysis using Manning's equation.
Handles uniform flow in circular, rectangular, trapezoidal, and triangular
cross-sections. Computes normal depth, critical depth, Froude number, and
specific energy.

Theory
------
Manning's equation (uniform flow):
    Q = (1/n) · A · R_h^(2/3) · S^(1/2)

where:
    n   = Manning's roughness coefficient [s/m^(1/3)]
    A   = cross-sectional area of flow [m²]
    R_h = hydraulic radius = A / P [m]  (P = wetted perimeter)
    S   = channel bottom slope [m/m]

Critical flow:  Fr = V / sqrt(g·D_h) = 1   (D_h = A/T, T = top width)
  - Subcritical:  Fr < 1
  - Supercritical: Fr > 1

Reference
---------
  Chaudhry, M.H. (2008). Open-Channel Hydraulics. Springer.
  Manning, R. (1891). Trans. Inst. Civ. Eng. Ireland 20, 161-207.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Manning's roughness coefficients (n) — typical values
# ---------------------------------------------------------------------------

MANNING_N: Dict[str, float] = {
    # Natural channels
    "natural_clean": 0.030,
    "natural_irregular": 0.045,
    "natural_weedy": 0.060,
    "natural_rocky": 0.080,
    # Engineered channels
    "concrete_smooth": 0.013,
    "concrete_rough": 0.017,
    "asphalt": 0.016,
    "brick": 0.015,
    "corrugated_metal": 0.024,
    "gravel": 0.025,
    "earth_clean": 0.022,
    "earth_irregular": 0.030,
    # Pipes (partially full)
    "cast_iron": 0.013,
    "steel_welded": 0.012,
    "pvc": 0.010,
    "hdpe": 0.011,
    "concrete_pipe": 0.015,
}


# ---------------------------------------------------------------------------
# Section geometry helpers
# ---------------------------------------------------------------------------

def _rect_section(width_m: float, depth_m: float):
    """Rectangular channel section."""
    A = width_m * depth_m
    P = width_m + 2.0 * depth_m
    T = width_m
    return A, P, T


def _trap_section(bottom_width_m: float, depth_m: float, side_slope_h_per_v: float):
    """
    Trapezoidal channel section.
    side_slope_h_per_v: horizontal distance per unit vertical (z=H/V).
    """
    z = side_slope_h_per_v
    A = (bottom_width_m + z * depth_m) * depth_m
    P = bottom_width_m + 2.0 * depth_m * math.sqrt(1.0 + z ** 2)
    T = bottom_width_m + 2.0 * z * depth_m
    return A, P, T


def _triangular_section(depth_m: float, side_slope_h_per_v: float):
    """Triangular V-channel section."""
    z = side_slope_h_per_v
    A = z * depth_m ** 2
    P = 2.0 * depth_m * math.sqrt(1.0 + z ** 2)
    T = 2.0 * z * depth_m
    return A, P, T


def _circular_section(diameter_m: float, depth_m: float):
    """
    Circular pipe section (partially full).
    depth_m: water depth (0 ≤ depth ≤ diameter).
    """
    d = diameter_m
    y = min(depth_m, d)
    if y <= 0.0:
        return 0.0, 1e-9, 0.0
    if y >= d:
        # Full pipe
        A = math.pi * d ** 2 / 4.0
        P = math.pi * d
        T = 0.0  # Closed top — use diameter as surrogate
        return A, P, d

    r = d / 2.0
    theta = 2.0 * math.acos((r - y) / r)  # central angle [rad]
    A = r ** 2 * (theta - math.sin(theta)) / 2.0
    P = r * theta
    T = 2.0 * math.sqrt(y * (d - y))  # top width
    return A, P, T


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OpenChannelResult:
    """Result of Manning's uniform open channel flow analysis."""
    section_type: str
    flow_rate_m3_s: float
    normal_depth_m: float
    velocity_m_s: float
    froude_number: float
    flow_regime: str          # 'SUBCRITICAL', 'CRITICAL', 'SUPERCRITICAL'
    area_m2: float
    wetted_perimeter_m: float
    hydraulic_radius_m: float
    hydraulic_depth_m: float  # A / T (top width)
    top_width_m: float
    specific_energy_m: float  # H = y + V²/(2g)
    slope: float
    manning_n: float
    critical_depth_m: Optional[float] = None
    critical_velocity_m_s: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_type": self.section_type,
            "flow_rate_m3_s": round(self.flow_rate_m3_s, 5),
            "normal_depth_m": round(self.normal_depth_m, 4),
            "velocity_m_s": round(self.velocity_m_s, 4),
            "froude_number": round(self.froude_number, 4),
            "flow_regime": self.flow_regime,
            "area_m2": round(self.area_m2, 6),
            "wetted_perimeter_m": round(self.wetted_perimeter_m, 4),
            "hydraulic_radius_m": round(self.hydraulic_radius_m, 4),
            "specific_energy_m": round(self.specific_energy_m, 4),
            "critical_depth_m": round(self.critical_depth_m, 4) if self.critical_depth_m else None,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Normal depth solver (bisection)
# ---------------------------------------------------------------------------

def _manning_q(A: float, P: float, S: float, n: float) -> float:
    """Manning's discharge for given section geometry."""
    if P <= 0 or n <= 0:
        return 0.0
    Rh = A / P
    return (1.0 / n) * A * (Rh ** (2.0 / 3.0)) * math.sqrt(max(0.0, S))


def _solve_normal_depth(
    target_q: float,
    slope: float,
    n: float,
    section_type: str,
    **section_kwargs,
) -> float:
    """Bisection solver for normal depth given target discharge."""
    lo, hi = 1e-5, 100.0

    def q_at_depth(y: float) -> float:
        if section_type == "rectangular":
            A, P, T = _rect_section(section_kwargs["width_m"], y)
        elif section_type == "trapezoidal":
            A, P, T = _trap_section(section_kwargs["bottom_width_m"], y, section_kwargs["side_slope"])
        elif section_type == "triangular":
            A, P, T = _triangular_section(y, section_kwargs["side_slope"])
        elif section_type == "circular":
            A, P, T = _circular_section(section_kwargs["diameter_m"], y)
        else:
            A, P, T = _rect_section(section_kwargs.get("width_m", 1.0), y)
        return _manning_q(A, P, slope, n)

    if q_at_depth(hi) < target_q:
        return hi  # Flow depth beyond search range

    for _ in range(80):
        mid = (lo + hi) / 2.0
        if q_at_depth(mid) < target_q:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < 1e-7:
            break

    return (lo + hi) / 2.0


def _solve_critical_depth(
    flow_rate_m3_s: float,
    section_type: str,
    g: float = 9.80665,
    **section_kwargs,
) -> Optional[float]:
    """
    Find critical depth where Fr = 1:  Q² / g = A³ / T
    Uses bisection.
    """
    def residual(y: float) -> float:
        if section_type == "rectangular":
            A, P, T = _rect_section(section_kwargs["width_m"], y)
        elif section_type == "trapezoidal":
            A, P, T = _trap_section(section_kwargs["bottom_width_m"], y, section_kwargs["side_slope"])
        elif section_type == "triangular":
            A, P, T = _triangular_section(y, section_kwargs["side_slope"])
        elif section_type == "circular":
            A, P, T = _circular_section(section_kwargs["diameter_m"], y)
        else:
            A, P, T = _rect_section(section_kwargs.get("width_m", 1.0), y)
        if T <= 0 or A <= 0:
            return -flow_rate_m3_s ** 2
        return A ** 3 / max(1e-10, T) - flow_rate_m3_s ** 2 / g

    lo, hi = 1e-5, 50.0
    if residual(hi) < 0:
        return None  # Critical depth beyond range

    for _ in range(80):
        mid = (lo + hi) / 2.0
        if residual(mid) < 0:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < 1e-7:
            break

    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def analyze_open_channel_flow(
    flow_rate_m3_s: float,
    slope: float,
    manning_n: float | str = "concrete_smooth",
    section_type: str = "rectangular",
    width_m: Optional[float] = 1.0,
    bottom_width_m: Optional[float] = None,
    side_slope: float = 1.0,
    diameter_m: Optional[float] = None,
    g: float = 9.80665,
) -> OpenChannelResult:
    """
    Analyze uniform open channel flow using Manning's equation.

    Parameters
    ----------
    flow_rate_m3_s : Volumetric discharge [m³/s]
    slope          : Longitudinal channel bed slope [m/m] (dimensionless)
    manning_n      : Manning roughness coefficient (float) or material key (str)
    section_type   : 'rectangular' | 'trapezoidal' | 'triangular' | 'circular'
    width_m        : Channel width for rectangular section [m]
    bottom_width_m : Bottom width for trapezoidal section [m]
    side_slope     : Side slope z = H/V for trapezoidal/triangular sections
    diameter_m     : Pipe inner diameter for circular section [m]
    g              : Gravitational acceleration [m/s²]

    Returns
    -------
    OpenChannelResult with normal depth, velocity, Froude number, and more.
    """
    # --- Resolve Manning n ------------------------------------------------
    if isinstance(manning_n, str):
        n = MANNING_N.get(manning_n.lower(), 0.013)
    else:
        n = float(manning_n)

    if n <= 0:
        raise ValueError(f"Manning n must be positive, got {n}.")
    if slope < 0:
        raise ValueError(f"Slope must be non-negative, got {slope}.")
    if flow_rate_m3_s <= 0:
        raise ValueError(f"Flow rate must be positive, got {flow_rate_m3_s}.")

    warnings_list: List[str] = []

    # --- Section kwargs ---------------------------------------------------
    section_kwargs: Dict[str, Any] = {}
    stype = section_type.lower().strip()

    if stype == "rectangular":
        w = width_m or 1.0
        section_kwargs = {"width_m": w}
    elif stype == "trapezoidal":
        bw = bottom_width_m or width_m or 1.0
        section_kwargs = {"bottom_width_m": bw, "side_slope": side_slope}
    elif stype == "triangular":
        section_kwargs = {"side_slope": side_slope}
    elif stype == "circular":
        d = diameter_m or (width_m or 1.0)
        section_kwargs = {"diameter_m": d}
    else:
        warnings_list.append(f"Unknown section type '{section_type}', defaulting to rectangular.")
        stype = "rectangular"
        section_kwargs = {"width_m": width_m or 1.0}

    # --- Solve normal depth -----------------------------------------------
    yn = _solve_normal_depth(flow_rate_m3_s, slope, n, stype, **section_kwargs)

    # --- Evaluate section properties at normal depth ----------------------
    if stype == "rectangular":
        A, P, T = _rect_section(section_kwargs["width_m"], yn)
    elif stype == "trapezoidal":
        A, P, T = _trap_section(section_kwargs["bottom_width_m"], yn, section_kwargs["side_slope"])
    elif stype == "triangular":
        A, P, T = _triangular_section(yn, section_kwargs["side_slope"])
    elif stype == "circular":
        A, P, T = _circular_section(section_kwargs["diameter_m"], yn)
    else:
        A, P, T = _rect_section(section_kwargs.get("width_m", 1.0), yn)

    Rh = A / max(1e-9, P)
    V = flow_rate_m3_s / max(1e-9, A)
    Dh = A / max(1e-9, T)  # hydraulic depth
    Fr = V / math.sqrt(max(1e-12, g * Dh))

    if Fr < 0.95:
        regime = "SUBCRITICAL"
    elif Fr > 1.05:
        regime = "SUPERCRITICAL"
    else:
        regime = "CRITICAL"

    E = yn + V ** 2 / (2.0 * g)  # specific energy

    # --- Critical depth ---------------------------------------------------
    yc = _solve_critical_depth(flow_rate_m3_s, stype, g=g, **section_kwargs)
    vc = None
    if yc is not None:
        if stype == "rectangular":
            Ac, _, _ = _rect_section(section_kwargs["width_m"], yc)
        elif stype == "trapezoidal":
            Ac, _, _ = _trap_section(section_kwargs["bottom_width_m"], yc, section_kwargs["side_slope"])
        elif stype == "triangular":
            Ac, _, _ = _triangular_section(yc, section_kwargs["side_slope"])
        elif stype == "circular":
            Ac, _, _ = _circular_section(section_kwargs["diameter_m"], yc)
        else:
            Ac = section_kwargs.get("width_m", 1.0) * yc
        vc = flow_rate_m3_s / max(1e-9, Ac)

    if slope == 0:
        warnings_list.append("Slope=0: no gravity-driven flow; Manning's equation yields Q=0.")
    if Fr > 2.0:
        warnings_list.append(f"High Froude number Fr={Fr:.2f}: flow is strongly supercritical — hydraulic jump may occur.")

    return OpenChannelResult(
        section_type=stype,
        flow_rate_m3_s=flow_rate_m3_s,
        normal_depth_m=round(yn, 5),
        velocity_m_s=round(V, 4),
        froude_number=round(Fr, 4),
        flow_regime=regime,
        area_m2=round(A, 6),
        wetted_perimeter_m=round(P, 5),
        hydraulic_radius_m=round(Rh, 5),
        hydraulic_depth_m=round(Dh, 5),
        top_width_m=round(T, 4),
        specific_energy_m=round(E, 5),
        slope=slope,
        manning_n=n,
        critical_depth_m=round(yc, 5) if yc else None,
        critical_velocity_m_s=round(vc, 4) if vc else None,
        warnings=warnings_list,
    )
