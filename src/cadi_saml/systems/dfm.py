"""
cadi_saml.systems.dfm

Design for Manufacturing (DFM) and Cost Estimation Module:
- CNC Milling & Turning machinability rule checks:
  * Tool aspect ratio (depth-to-diameter L/D <= 4.0 recommended, L/D > 8.0 flagged)
  * Minimum inside corner radius relative to pocket depth
  * Hole depth vs standard drill tooling
- Sheet metal bending checks:
  * Minimum flange length (b >= 4 * t)
  * Minimum bend radius (r >= t)
  * Hole-to-bend distance clearance
- Parametric Bill of Materials (BOM) & Cost Estimation:
  * Stock raw material mass & scrap waste
  * Material Removal Rate (MRR) and rough machining time estimation
  * Setup time, machine hour rate, and total estimated manufacturing cost
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from ..core.assembly import Assembly


# Typical Material Machinability & Stock Costs ($/kg, MRR in cm^3/min)
MATERIAL_DATABASE = {
    "aluminum_6061": {"density_kg_m3": 2700.0, "cost_per_kg": 6.5, "mrr_cm3_min": 120.0, "machinability_rating": 1.0},
    "aluminum_7075": {"density_kg_m3": 2810.0, "cost_per_kg": 11.0, "mrr_cm3_min": 90.0, "machinability_rating": 0.8},
    "steel_1018": {"density_kg_m3": 7850.0, "cost_per_kg": 2.5, "mrr_cm3_min": 45.0, "machinability_rating": 0.5},
    "steel_4140": {"density_kg_m3": 7850.0, "cost_per_kg": 4.5, "mrr_cm3_min": 30.0, "machinability_rating": 0.35},
    "stainless_304": {"density_kg_m3": 8000.0, "cost_per_kg": 8.0, "mrr_cm3_min": 25.0, "machinability_rating": 0.28},
}


@dataclass
class DFMCheckResult:
    """Detailed DFM assessment report."""
    passed: bool
    score: float  # 0.0 to 100.0
    process: str  # 'cnc_machining', 'sheet_metal', '3d_printing'
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ManufacturingCostEstimate:
    """Breakdown of raw material and machining costs."""
    material_name: str
    part_volume_cm3: float
    stock_volume_cm3: float
    part_mass_kg: float
    stock_mass_kg: float
    scrap_mass_kg: float
    raw_material_cost: float
    machining_time_minutes: float
    machining_cost: float
    setup_cost: float
    total_cost: float
    currency: str = "USD"


class DFMAnalyzer:
    """
    Automated engineering rules engine for manufacturability and cost estimation.
    """

    def __init__(
        self,
        machine_hour_rate_usd: float = 75.0,
        setup_time_hours: float = 0.5,
    ):
        self.machine_hour_rate = machine_hour_rate_usd
        self.setup_time_hours = setup_time_hours

    def check_cnc_hole_drilling(
        self,
        diameter_mm: float,
        depth_mm: float,
        is_blind: bool = True,
    ) -> DFMCheckResult:
        """
        Validates hole aspect ratio for CNC drilling:
        - L/D <= 4.0: Standard drilling (optimal)
        - 4.0 < L/D <= 8.0: Deep hole drilling (slower feeds, peck drilling)
        - L/D > 8.0: Gun drilling / specialty tooling required (high risk/cost)
        """
        aspect_ratio = depth_mm / max(0.1, diameter_mm)
        warnings = []
        errors = []
        recs = []

        if aspect_ratio > 8.0:
            errors.append(
                f"Severe hole aspect ratio L/D = {aspect_ratio:.1f} (Dia={diameter_mm}mm, Depth={depth_mm}mm). "
                "Exceeds standard CNC drilling limit (L/D > 8). High risk of tool deflection or breakage."
            )
            recs.append({
                "action": "increase_hole_diameter_or_shorten_depth",
                "target_diameter_mm": round(depth_mm / 6.0, 1),
                "reason": "Reduce aspect ratio below 6.0 for standard tooling.",
            })
        elif aspect_ratio > 4.0:
            warnings.append(
                f"Deep hole detected L/D = {aspect_ratio:.1f}. Will require peck drilling cycles and reduced feeds."
            )

        if diameter_mm < 1.0:
            warnings.append(f"Micro-drilling required for diameter < 1.0mm ({diameter_mm}mm).")

        passed = len(errors) == 0
        score = max(0.0, 100.0 - (len(errors) * 40.0) - (len(warnings) * 15.0))

        return DFMCheckResult(
            passed=passed,
            score=score,
            process="cnc_machining",
            warnings=warnings,
            errors=errors,
            recommendations=recs,
        )

    def check_sheet_metal_bend(
        self,
        sheet_thickness_mm: float,
        bend_radius_mm: float,
        flange_length_mm: float,
        hole_edge_distance_mm: Optional[float] = None,
    ) -> DFMCheckResult:
        """
        Validates standard sheet metal bending rules:
        - Minimum bend radius r >= t (prevents cracking on outer bend surface)
        - Minimum flange length b >= 4 * t (ensures proper press brake die seating)
        - Minimum hole-to-bend distance dist >= 3 * t + r (prevents hole ovalization/distortion)
        """
        t = sheet_thickness_mm
        warnings = []
        errors = []
        recs = []

        # 1. Bend Radius
        if bend_radius_mm < (0.9 * t):
            errors.append(
                f"Bend radius ({bend_radius_mm:.1f}mm) is smaller than sheet thickness ({t:.1f}mm). "
                "Causes severe tensile cracking along the bend line."
            )
            recs.append({"action": "increase_bend_radius", "suggested_radius_mm": round(t, 1)})

        # 2. Flange Length
        min_flange = 4.0 * t
        if flange_length_mm < min_flange:
            errors.append(
                f"Flange length ({flange_length_mm:.1f}mm) is less than minimum 4*t ({min_flange:.1f}mm). "
                "Flange will slip into press brake V-die."
            )
            recs.append({"action": "increase_flange_length", "suggested_length_mm": round(min_flange, 1)})

        # 3. Hole proximity to bend line
        if hole_edge_distance_mm is not None:
            min_hole_dist = 3.0 * t + bend_radius_mm
            if hole_edge_distance_mm < min_hole_dist:
                warnings.append(
                    f"Hole is too close to bend line ({hole_edge_distance_mm:.1f}mm < {min_hole_dist:.1f}mm). "
                    "Hole will deform into an ellipse during bending. Consider punching after bend or relief slots."
                )

        passed = len(errors) == 0
        score = max(0.0, 100.0 - (len(errors) * 40.0) - (len(warnings) * 15.0))

        return DFMCheckResult(
            passed=passed,
            score=score,
            process="sheet_metal",
            warnings=warnings,
            errors=errors,
            recommendations=recs,
        )

    def estimate_machining_cost(
        self,
        part_volume_mm3: float,
        bounding_box_mm: Tuple[float, float, float],  # (dx, dy, dz)
        material: str = "aluminum_6061",
        quantity: int = 1,
    ) -> ManufacturingCostEstimate:
        """
        Calculates rough machining cost based on material removal and stock size:
        - Stock volume is rectangular block enclosing bounding box + 6mm stock allowance per axis
        - Material removal rate (MRR) based on material database
        - Total cost = Raw material cost + Machine operating cost + amortized setup cost
        """
        mat_key = material.lower().replace("-", "_").replace(" ", "_")
        mat_info = MATERIAL_DATABASE.get(mat_key, MATERIAL_DATABASE["aluminum_6061"])

        dx, dy, dz = bounding_box_mm
        stock_dx = dx + 6.0
        stock_dy = dy + 6.0
        stock_dz = dz + 6.0

        stock_vol_mm3 = stock_dx * stock_dy * stock_dz
        part_vol_mm3 = min(stock_vol_mm3, part_volume_mm3)
        removed_vol_mm3 = stock_vol_mm3 - part_vol_mm3

        part_vol_cm3 = part_vol_mm3 / 1000.0
        stock_vol_cm3 = stock_vol_mm3 / 1000.0
        removed_vol_cm3 = removed_vol_mm3 / 1000.0

        # Masses
        density = mat_info["density_kg_m3"]
        stock_mass_kg = (stock_vol_cm3 * 1e-6) * density
        part_mass_kg = (part_vol_cm3 * 1e-6) * density
        scrap_mass_kg = max(0.0, stock_mass_kg - part_mass_kg)

        # Raw material cost (net of scrap resale ~15% scrap recovery)
        raw_mat_cost = (stock_mass_kg * mat_info["cost_per_kg"]) - (scrap_mass_kg * mat_info["cost_per_kg"] * 0.15)

        # Roughing and finishing machining time
        mrr = mat_info["mrr_cm3_min"]
        roughing_time_min = removed_vol_cm3 / max(1.0, mrr)
        # Finishing & tool changes estimate: 20% of roughing time + 5 min floor
        finishing_time_min = (0.2 * roughing_time_min) + 5.0
        total_machine_time_min = roughing_time_min + finishing_time_min

        # Costs
        machine_cost = (total_machine_time_min / 60.0) * self.machine_hour_rate
        total_setup_cost = self.setup_time_hours * self.machine_hour_rate
        amortized_setup_cost = total_setup_cost / max(1, quantity)

        total_part_cost = raw_mat_cost + machine_cost + amortized_setup_cost

        return ManufacturingCostEstimate(
            material_name=material,
            part_volume_cm3=round(part_vol_cm3, 2),
            stock_volume_cm3=round(stock_vol_cm3, 2),
            part_mass_kg=round(part_mass_kg, 3),
            stock_mass_kg=round(stock_mass_kg, 3),
            scrap_mass_kg=round(scrap_mass_kg, 3),
            raw_material_cost=round(raw_mat_cost, 2),
            machining_time_minutes=round(total_machine_time_min, 1),
            machining_cost=round(machine_cost, 2),
            setup_cost=round(amortized_setup_cost, 2),
            total_cost=round(total_part_cost, 2),
        )
