"""
cadi_saml.systems.electrical

Electromechanical, wire harness, and electrical cabinet enclosure module:
- Wire harness routing, wire gauge ampacity, and voltage drop validation
- Minimum cable bend radius enforcement (R_bend >= 6 * D_cable)
- Parametric industrial electrical cabinet with standard TS 35 DIN rails
- Modular electrical components (MCBs, contactors, 24V power supplies, terminal blocks)
- Thermal heat dissipation and cooling airflow estimation
- 3D CAD assembly generation for electrical panels and cable trays
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from ..core.assembly import Assembly


# Copper resistivity at 20°C: ohm * mm^2 / m
COPPER_RESISTIVITY = 0.0175


@dataclass
class CableSpecification:
    """Wire and cable physical and electrical specifications."""
    name: str
    cross_section_mm2: float = 2.5       # mm^2
    outer_diameter_mm: float = 3.6       # mm
    rated_current_a: float = 24.0        # Max continuous ampacity in air
    voltage_rating_v: float = 600.0      # Insulation dielectric voltage
    conductor_material: str = "copper"

    @property
    def min_bend_radius_mm(self) -> float:
        """Standard industrial minimum bend radius is 6x outer diameter."""
        return 6.0 * self.outer_diameter_mm

    @property
    def resistance_per_meter_ohm(self) -> float:
        """Resistance in ohms per meter at standard temperature."""
        return COPPER_RESISTIVITY / max(0.01, self.cross_section_mm2)


@dataclass
class WireHarnessRoute:
    """Physical 3D routed path for an electrical wire harness."""
    name: str
    cable: CableSpecification
    waypoints: List[Tuple[float, float, float]]  # List of 3D points [p0, p1, p2, ...]
    operating_current_a: float = 16.0
    supply_voltage_v: float = 230.0

    @property
    def total_length_m(self) -> float:
        if len(self.waypoints) < 2:
            return 0.0
        total_mm = 0.0
        for i in range(len(self.waypoints) - 1):
            p0 = np.array(self.waypoints[i])
            p1 = np.array(self.waypoints[i + 1])
            total_mm += float(np.linalg.norm(p1 - p0))
        return total_mm / 1000.0

    def analyze_voltage_drop(self) -> Dict[str, Any]:
        """
        Calculates loop resistance, voltage drop, and percentage drop:
        Loop length is 2x one-way cable length (out and return conductors).
        Standard requirement: voltage drop must be <= 3.0% for branch circuits.
        """
        loop_length_m = 2.0 * self.total_length_m
        loop_resistance_ohm = loop_length_m * self.cable.resistance_per_meter_ohm
        v_drop_v = self.operating_current_a * loop_resistance_ohm
        drop_percent = (v_drop_v / max(1.0, self.supply_voltage_v)) * 100.0
        is_safe = (drop_percent <= 3.0) and (self.operating_current_a <= self.cable.rated_current_a)

        return {
            "harness_name": self.name,
            "total_length_m": round(self.total_length_m, 2),
            "operating_current_a": self.operating_current_a,
            "rated_current_a": self.cable.rated_current_a,
            "loop_resistance_ohm": round(loop_resistance_ohm, 4),
            "voltage_drop_v": round(v_drop_v, 2),
            "voltage_drop_percent": round(drop_percent, 2),
            "compliant_with_3pct_rule": drop_percent <= 3.0,
            "ampacity_ok": self.operating_current_a <= self.cable.rated_current_a,
            "is_safe": is_safe,
        }

    def verify_bend_radii(self) -> Dict[str, Any]:
        """
        Checks angles at consecutive waypoints to verify no bend exceeds allowable radius.
        """
        min_r = self.cable.min_bend_radius_mm
        violations = []

        for i in range(1, len(self.waypoints) - 1):
            p_prev = np.array(self.waypoints[i - 1])
            p_curr = np.array(self.waypoints[i])
            p_next = np.array(self.waypoints[i + 1])

            v1 = p_curr - p_prev
            v2 = p_next - p_curr
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)

            if n1 > 1e-4 and n2 > 1e-4:
                cos_ang = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
                turn_deg = math.degrees(math.acos(cos_ang))
                
                # Check segment lengths: if a sharp 90-deg turn has legs shorter than min_bend_radius
                if turn_deg > 45.0 and (n1 < min_r or n2 < min_r):
                    violations.append({
                        "waypoint_index": i,
                        "point": (round(float(p_curr[0]), 1), round(float(p_curr[1]), 1), round(float(p_curr[2]), 1)),
                        "turn_angle_deg": round(turn_deg, 1),
                        "required_clearance_mm": round(min_r, 1),
                    })

        return {
            "passed": len(violations) == 0,
            "min_bend_radius_mm": round(min_r, 1),
            "violations_count": len(violations),
            "violations": violations,
        }


@dataclass
class DINComponent:
    """Modular industrial component mounted on TS 35 DIN rail."""
    name: str
    component_type: str  # 'mcb', 'contactor', 'power_supply', 'terminal_block'
    width_mm: float      # Standard DIN modular width (1 TE / pole = 18 mm)
    height_mm: float = 85.0
    depth_mm: float = 65.0
    power_loss_watts: float = 2.0  # Heat generated under load


class DINRailEnclosure:
    """
    Parametric industrial control cabinet with DIN rails and mounted electrical devices.
    """

    def __init__(
        self,
        name: str = "control_cabinet",
        width_mm: float = 600.0,
        height_mm: float = 800.0,
        depth_mm: float = 300.0,
        wall_thickness_mm: float = 2.0,
        num_din_rails: int = 3,
    ):
        self.name = name
        self.width = width_mm
        self.height = height_mm
        self.depth = depth_mm
        self.wall_thickness = wall_thickness_mm
        self.num_din_rails = num_din_rails

        self.rail_components: Dict[int, List[DINComponent]] = {i: [] for i in range(num_din_rails)}

    def add_component(self, rail_index: int, component: DINComponent) -> None:
        """Mounts an electrical component onto specified DIN rail (0 to num_rails-1)."""
        if rail_index not in self.rail_components:
            raise IndexError(f"Rail index {rail_index} out of range (0-{self.num_din_rails-1})")
        self.rail_components[rail_index].append(component)

    def calculate_rail_space_occupancy(self) -> Dict[str, Any]:
        """
        Calculates usable vs occupied horizontal width for each DIN rail.
        Rail length is cabinet inner width minus 80mm side duct clearance.
        """
        usable_width_mm = self.width - 2 * self.wall_thickness - 80.0
        rails_summary = []

        total_components = 0
        total_power_loss_w = 0.0

        for r_idx, comps in self.rail_components.items():
            used_w = sum(c.width_mm for c in comps)
            power_w = sum(c.power_loss_watts for c in comps)
            total_components += len(comps)
            total_power_loss_w += power_w

            rails_summary.append({
                "rail_index": r_idx + 1,
                "used_width_mm": round(used_w, 1),
                "usable_width_mm": round(usable_width_mm, 1),
                "occupancy_percent": round((used_w / max(1.0, usable_width_mm)) * 100.0, 1),
                "overflow": used_w > usable_width_mm,
                "component_count": len(comps),
            })

        return {
            "cabinet_name": self.name,
            "usable_rail_width_mm": round(usable_width_mm, 1),
            "total_component_count": total_components,
            "total_internal_heat_loss_watts": round(total_power_loss_w, 1),
            "rails": rails_summary,
            "all_rails_fit": all(not r["overflow"] for r in rails_summary),
        }

    def estimate_cabinet_cooling_airflow(
        self,
        ambient_temperature_c: float = 30.0,
        max_internal_temperature_c: float = 45.0,
    ) -> Dict[str, Any]:
        """
        Calculates required forced-ventilation fan airflow (m^3/h) to keep
        cabinet temperature below maximum allowable internal rating:
        V_dot = (3.1 * P_loss) / Delta_T [m^3/h]
        """
        heat_summary = self.calculate_rail_space_occupancy()
        p_loss_w = heat_summary["total_internal_heat_loss_watts"]
        delta_t = max(2.0, max_internal_temperature_c - ambient_temperature_c)

        # Standard thermal formula for air at sea level: Q = m_dot * cp * dT -> V_dot ~ 3.1 * P / dT
        required_airflow_m3_h = (3.1 * p_loss_w) / delta_t
        required_airflow_cfm = required_airflow_m3_h * 0.588578  # CFM

        return {
            "total_heat_loss_watts": p_loss_w,
            "ambient_temp_c": ambient_temperature_c,
            "max_internal_temp_c": max_internal_temperature_c,
            "delta_t_c": delta_t,
            "required_airflow_m3_per_hour": round(required_airflow_m3_h, 2),
            "required_airflow_cfm": round(required_airflow_cfm, 2),
            "fan_recommended": p_loss_w > 50.0,
        }

    def to_assembly(self, assembly_name: Optional[str] = None) -> Assembly:
        """
        Generates 3D CAD Assembly of the enclosure shell, DIN rails, and mounted components.
        """
        asm = Assembly(assembly_name or self.name)

        # 1. Outer Box Enclosure
        enclosure = asm.add_box(
            name=f"{self.name}_shell",
            length=self.width,
            width=self.depth,
            height=self.height,
        )

        # 2. DIN Rails (TS 35: 35mm wide x 7.5mm deep steel profiles)
        rail_z_positions = np.linspace(-self.height / 3.0, self.height / 3.0, self.num_din_rails)
        rail_length = self.width - 2 * self.wall_thickness - 40.0

        for i, z_pos in enumerate(rail_z_positions):
            # Add DIN rail bar
            asm.add_box(
                name=f"{self.name}_din_rail_{i+1}",
                length=rail_length,
                width=35.0,
                height=7.5,
                origin=(0.0, -self.depth / 2.0 + 30.0, float(z_pos)),
            )

            # Add component blocks along the rail
            curr_x = -rail_length / 2.0 + 20.0
            for j, comp in enumerate(self.rail_components.get(i, [])):
                comp_mid_x = curr_x + (comp.width_mm / 2.0)
                asm.add_box(
                    name=f"{self.name}_r{i+1}_{comp.name}_{j+1}",
                    length=comp.width_mm,
                    width=comp.depth_mm,
                    height=comp.height_mm,
                    origin=(float(comp_mid_x), -self.depth / 2.0 + 30.0 + comp.depth_mm / 2.0, float(z_pos)),
                )
                curr_x += comp.width_mm + 2.0

        return asm
