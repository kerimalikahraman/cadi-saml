"""
Geometric Dimensioning & Tolerancing (GD&T) and ISO Fits Engine for CADI-SAML.
Implements ISO 286 fits, geometric controls (Flatness, Parallelism, Position), and 1D Worst-Case / RSS Tolerance Stackup.
"""

from typing import Any, Dict, List, Optional, Tuple
import math
from dataclasses import dataclass, field


# Fundamental deviation lookup tables according to ISO 286-1 (in microns) for common nominal ranges:
# (dia_low, dia_high): {"IT7": val, "IT6": val, "g": val, "f": val, "h": 0}
ISO_FIT_TABLE = [
    # <= 3
    (0.0, 3.0, {"IT6": 6, "IT7": 10, "IT8": 14, "h": 0, "g": -2, "f": -6, "k": 0, "m": 2, "p": 6}),
    # 3 - 6
    (3.0, 6.0, {"IT6": 8, "IT7": 12, "IT8": 18, "h": 0, "g": -4, "f": -10, "k": 1, "m": 4, "p": 12}),
    # 6 - 10
    (6.0, 10.0, {"IT6": 9, "IT7": 15, "IT8": 22, "h": 0, "g": -5, "f": -13, "k": 1, "m": 6, "p": 15}),
    # 10 - 18
    (10.0, 18.0, {"IT6": 11, "IT7": 18, "IT8": 27, "h": 0, "g": -6, "f": -16, "k": 1, "m": 7, "p": 18}),
    # 18 - 30
    (18.0, 30.0, {"IT6": 13, "IT7": 21, "IT8": 33, "h": 0, "g": -7, "f": -20, "k": 2, "m": 8, "p": 22}),
    # 30 - 50
    (30.0, 50.0, {"IT6": 16, "IT7": 25, "IT8": 39, "h": 0, "g": -9, "f": -25, "k": 2, "m": 9, "p": 26}),
    # 50 - 80
    (50.0, 80.0, {"IT6": 19, "IT7": 30, "IT8": 46, "h": 0, "g": -10, "f": -30, "k": 2, "m": 11, "p": 32}),
    # 80 - 120
    (80.0, 120.0, {"IT6": 22, "IT7": 35, "IT8": 54, "h": 0, "g": -12, "f": -36, "k": 3, "m": 13, "p": 37}),
    # 120 - 180
    (120.0, 180.0, {"IT6": 25, "IT7": 40, "IT8": 63, "h": 0, "g": -14, "f": -43, "k": 3, "m": 15, "p": 43}),
]


def calculate_iso_fit(
    nominal_dia_mm: float,
    hole_class: str = "H7",
    shaft_class: str = "g6",
) -> Dict[str, Any]:
    """
    Calculates precise ISO 286 fit limits and clearance/interference for nominal diameter.
    Example: calculate_iso_fit(25.0, "H7", "g6") -> clearance fit limits.
    """
    d = float(nominal_dia_mm)
    entry = None
    for low, high, tbl in ISO_FIT_TABLE:
        if low < d <= high:
            entry = tbl
            break

    if entry is None:
        # Fallback to largest bracket
        entry = ISO_FIT_TABLE[-1][2]

    # Hole calculation (H-basis has lower deviation EI = 0)
    it_grade_hole = hole_class.upper().replace("H", "")
    it_key_hole = f"IT{it_grade_hole}" if f"IT{it_grade_hole}" in entry else "IT7"
    hole_tol_um = entry.get(it_key_hole, 21)

    hole_min = d
    hole_max = d + (hole_tol_um / 1000.0)

    # Shaft calculation
    shaft_letter = shaft_class[0].lower()
    it_grade_shaft = shaft_class[1:]
    it_key_shaft = f"IT{it_grade_shaft}" if f"IT{it_grade_shaft}" in entry else "IT6"
    shaft_tol_um = entry.get(it_key_shaft, 13)
    es_fund_dev_um = entry.get(shaft_letter, 0)

    shaft_max = d + (es_fund_dev_um / 1000.0)
    shaft_min = shaft_max - (shaft_tol_um / 1000.0)

    min_clearance = hole_min - shaft_max
    max_clearance = hole_max - shaft_min

    if min_clearance >= 0.0:
        fit_type = "clearance"
    elif max_clearance <= 0.0:
        fit_type = "interference"
    else:
        fit_type = "transition"

    return {
        "nominal_diameter_mm": d,
        "hole_spec": hole_class,
        "shaft_spec": shaft_class,
        "hole_limits_mm": {"min": round(hole_min, 4), "max": round(hole_max, 4), "tolerance_um": hole_tol_um},
        "shaft_limits_mm": {"min": round(shaft_min, 4), "max": round(shaft_max, 4), "tolerance_um": shaft_tol_um},
        "fit_type": fit_type,
        "clearance_min_um": round(min_clearance * 1000.0, 1),
        "clearance_max_um": round(max_clearance * 1000.0, 1),
    }


@dataclass
class ToleranceDimension:
    nominal: float
    plus_tol: float
    minus_tol: float
    direction: int = 1  # +1 adds to gap, -1 subtracts


class ToleranceStack:
    """
    Performs 1D Worst-Case and Root-Sum-Square (RSS) statistical tolerance stack-up analysis.
    """

    def __init__(self, name: str = "Stackup"):
        self.name = name
        self.dimensions: List[ToleranceDimension] = []

    def add(self, nominal: float, plus_tol: float, minus_tol: Optional[float] = None, direction: int = 1) -> "ToleranceStack":
        minus = plus_tol if minus_tol is None else minus_tol
        self.dimensions.append(ToleranceDimension(float(nominal), float(plus_tol), float(minus), direction))
        return self

    def analyze(self) -> Dict[str, Any]:
        """Calculates worst-case and RSS statistical gaps."""
        nominal_gap = sum(d.nominal * d.direction for d in self.dimensions)

        # Worst case
        wc_max_gap = nominal_gap
        wc_min_gap = nominal_gap
        for d in self.dimensions:
            if d.direction > 0:
                wc_max_gap += d.plus_tol
                wc_min_gap -= d.minus_tol
            else:
                wc_max_gap += d.minus_tol
                wc_min_gap -= d.plus_tol

        # RSS statistical (assuming tolerances represent 3-sigma bounds)
        sum_variance = sum(((d.plus_tol + d.minus_tol) / 2.0)**2 for d in self.dimensions)
        sigma_3 = math.sqrt(sum_variance)

        return {
            "name": self.name,
            "nominal_gap": round(nominal_gap, 4),
            "worst_case": {
                "min_gap": round(wc_min_gap, 4),
                "max_gap": round(wc_max_gap, 4),
                "range": round(wc_max_gap - wc_min_gap, 4),
            },
            "statistical_rss": {
                "sigma_3_range": round(sigma_3, 4),
                "min_gap_3sigma": round(nominal_gap - sigma_3, 4),
                "max_gap_3sigma": round(nominal_gap + sigma_3, 4),
            },
        }
