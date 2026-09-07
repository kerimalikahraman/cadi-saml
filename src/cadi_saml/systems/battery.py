"""
cadi_saml.systems.battery

EV Battery Pack and Electromechanical Enclosure engineering module:
- Cell configuration (Cylindrical 21700/4680, Prismatic, Pouch)
- Series-Parallel (S-P) electrical array sizing (Nominal Voltage, Capacity kWh, Total Mass)
- Parametric enclosure tray, sealed perimeter flange, and top lid
- Integrated thermal cooling plate with fluid pressure drop calculation (coupled with flow simulation)
- Manual Service Disconnect (MSD) and High-Voltage (HV) connector clearance zones
- Fastener pattern generation and structural mounting tabs
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from ..core.assembly import Assembly
from ..simulation.flow.pipe_flow import analyze_pipe_flow


@dataclass
class CellSpecification:
    """Cell electrochemical and geometric characteristics."""
    cell_type: str = "21700"          # '21700', '4680', 'prismatic'
    diameter_mm: float = 21.0
    height_mm: float = 70.0
    nominal_voltage_v: float = 3.7
    capacity_ah: float = 5.0
    mass_grams: float = 70.0
    max_continuous_discharge_a: float = 15.0


@dataclass
class PackElectricalConfig:
    """Pack electrical topology (Series x Parallel)."""
    series_cells: int = 96      # ~355V nominal (standard 400V class)
    parallel_cells: int = 4     # 4P = 20Ah
    cell: CellSpecification = field(default_factory=CellSpecification)

    @property
    def total_cell_count(self) -> int:
        return self.series_cells * self.parallel_cells

    @property
    def nominal_voltage_v(self) -> float:
        return self.series_cells * self.cell.nominal_voltage_v

    @property
    def total_capacity_kwh(self) -> float:
        total_ah = self.parallel_cells * self.cell.capacity_ah
        return (self.nominal_voltage_v * total_ah) / 1000.0

    @property
    def total_cell_mass_kg(self) -> float:
        return (self.total_cell_count * self.cell.mass_grams) / 1000.0


class BatteryPackEnclosure:
    """
    Parametric electric vehicle battery pack enclosure and thermal management.
    """

    def __init__(
        self,
        name: str = "battery_pack_enclosure",
        electrical_config: Optional[PackElectricalConfig] = None,
        rows: int = 16,
        cols: int = 24,
        wall_thickness_mm: float = 4.0,
        cooling_channel_diameter_mm: float = 10.0,
    ):
        self.name = name
        self.config = electrical_config or PackElectricalConfig()
        self.rows = rows
        self.cols = cols
        self.wall_thickness = wall_thickness_mm
        self.cooling_dia = cooling_channel_diameter_mm

        # Cell spacing pitch
        self.pitch_x = self.config.cell.diameter_mm + 4.0
        self.pitch_y = self.config.cell.diameter_mm + 4.0

        # Calculate physical dimensions based on cell array
        self.internal_length = (self.cols * self.pitch_x) + 20.0
        self.internal_width = (self.rows * self.pitch_y) + 20.0
        self.internal_height = self.config.cell.height_mm + 35.0  # Room for busbars and BMS

        self.outer_length = self.internal_length + 2 * self.wall_thickness
        self.outer_width = self.internal_width + 2 * self.wall_thickness
        self.outer_height = self.internal_height + 2 * self.wall_thickness + 15.0  # Cooling floor

    @property
    def estimated_total_pack_mass_kg(self) -> float:
        """
        Total mass including cells, aluminum enclosure (density 2700 kg/m3),
        busbars, BMS, and coolant.
        """
        cell_mass = self.config.total_cell_mass_kg
        
        # Aluminum enclosure volume approximation
        vol_outer = (self.outer_length * self.outer_width * self.outer_height) * 1e-9  # m3
        vol_inner = (self.internal_length * self.internal_width * self.internal_height) * 1e-9
        enclosure_vol = max(0.005, vol_outer - vol_inner)
        enclosure_mass = enclosure_vol * 2700.0  # ~aluminum

        bms_busbars_mass = 15.0  # kg estimate
        coolant_mass = 8.0      # kg estimate

        return round(cell_mass + enclosure_mass + bms_busbars_mass + coolant_mass, 2)

    def analyze_thermal_cooling_flow(
        self,
        volumetric_flow_rate_lpm: float = 15.0,  # Liters per minute
        coolant_temperature_c: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Couples with the Phase 1 & 2 pipe flow simulation solver to calculate
        pressure loss across the battery bottom cold-plate serpentine channels.
        """
        # Flow in L/s
        q_l_s = volumetric_flow_rate_lpm / 60.0
        total_serpentine_length_mm = float(self.internal_length * (self.rows // 2))

        # Darcy-Weisbach flow analysis
        flow_study = analyze_pipe_flow(
            diameter_mm=self.cooling_dia,
            length_mm=total_serpentine_length_mm,
            flow_rate_l_s=q_l_s,
            fluid="water",
            temperature_c=coolant_temperature_c,
            material_roughness="smooth",
        )

        dp_bar = flow_study.pressure_drop_bar
        velocity = flow_study.velocity_m_s
        reynolds = flow_study.reynolds
        regime = flow_study.flow_regime

        # Heat rejection estimate (assuming 2 kW heat generation under high load)
        heat_gen_w = 2000.0
        cp_water = 4184.0  # J/kg*K
        mass_flow_kg_s = (q_l_s * 1.0)  # 1 L/s of water ~ 1 kg/s
        temp_rise_c = heat_gen_w / max(1e-4, mass_flow_kg_s * cp_water)

        return {
            "flow_rate_lpm": volumetric_flow_rate_lpm,
            "flow_velocity_m_s": round(velocity, 2),
            "reynolds_number": round(reynolds, 1),
            "flow_regime": regime,
            "pressure_drop_bar": round(dp_bar, 4),
            "pressure_drop_kpa": round(dp_bar * 100.0, 2),
            "coolant_temp_rise_c": round(temp_rise_c, 2),
            "cooling_pass_length_m": round(total_serpentine_length_mm / 1000.0, 2),
        }

    def get_keep_out_and_service_clearances(self) -> Dict[str, Any]:
        """
        Generates 3D bounding boxes for service access (MSD) and HV cabling.
        """
        # MSD is mounted on top face, front center
        msd_zone = {
            "name": "MSD_service_access",
            "center": (20.0, 0.0, self.outer_height / 2.0 + 80.0),
            "clearance_box": (120.0, 100.0, 150.0),  # L x W x H clearance
        }
        hv_connectors = {
            "name": "HV_output_cables",
            "center": (self.outer_length / 2.0 + 50.0, 0.0, 0.0),
            "clearance_box": (100.0, 150.0, 80.0),
        }
        return {
            "msd": msd_zone,
            "hv_terminals": hv_connectors,
        }

    def to_assembly(self, assembly_name: Optional[str] = None) -> Assembly:
        """
        Creates a parametric CADi SAML 3D Assembly containing the pack tray,
        cooling plate base, and lid with mounting holes.
        """
        asm = Assembly(assembly_name or self.name)

        # 1. Main Enclosure Tray (Box)
        tray = asm.add_box(
            name=f"{self.name}_tray",
            length=self.outer_length,
            width=self.outer_width,
            height=self.outer_height,
        )

        # 2. Mounting flange holes on perimeter
        flange_offset_x = (self.outer_length / 2.0) - 20.0
        flange_offset_y = (self.outer_width / 2.0) - 20.0

        tray.add_hole(name="mount_hole_1", diameter=8.5, depth=self.wall_thickness * 2, position=(flange_offset_x, flange_offset_y))
        tray.add_hole(name="mount_hole_2", diameter=8.5, depth=self.wall_thickness * 2, position=(-flange_offset_x, flange_offset_y))
        tray.add_hole(name="mount_hole_3", diameter=8.5, depth=self.wall_thickness * 2, position=(flange_offset_x, -flange_offset_y))
        tray.add_hole(name="mount_hole_4", diameter=8.5, depth=self.wall_thickness * 2, position=(-flange_offset_x, -flange_offset_y))

        # 3. Top Cover / Lid
        lid = asm.add_box(
            name=f"{self.name}_lid",
            length=self.outer_length,
            width=self.outer_width,
            height=self.wall_thickness,
        )
        lid.translate(0.0, 0.0, self.outer_height / 2.0 + (self.wall_thickness / 2.0))

        return asm
