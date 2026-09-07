"""
cadi_saml.systems

Integrated automotive system-level engineering layer:
- Chassis spaceframes & ladder rails (cadi_saml.systems.chassis)
- Kinematics-validated hardpoint suspension (cadi_saml.systems.suspension)
- Thermal-coupled EV battery pack enclosure (cadi_saml.systems.battery)
- Unified VehiclePlatform integrating structural frame, suspensions, and powertrain
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple, Any
import numpy as np

from .chassis import ChassisFrame, StructuralProfile
from .suspension import DoubleWishboneSuspension, SuspensionHardpoints
from .battery import BatteryPackEnclosure, PackElectricalConfig
from .electrical import CableSpecification, WireHarnessRoute, DINComponent, DINRailEnclosure
from .dfm import DFMAnalyzer, DFMCheckResult, ManufacturingCostEstimate
from .propulsion import GasMixture, RocketNozzle, NozzleAeroState
from ..core.assembly import Assembly


class VehiclePlatform:
    """
    Top-level coordinated vehicle platform synthesizing chassis, front/rear
    suspensions, and battery pack assembly with packaging & weight balance checks.
    """

    def __init__(
        self,
        name: str = "vehicle_platform",
        wheelbase_mm: float = 2800.0,
        track_width_mm: float = 1620.0,
        frame_width_mm: float = 1050.0,
        nominal_ground_clearance_mm: float = 190.0,
    ):
        self.name = name
        self.wheelbase = wheelbase_mm
        self.track_width = track_width_mm
        self.frame_width = frame_width_mm
        self.ground_clearance = nominal_ground_clearance_mm

        # Subsystems
        self.chassis = ChassisFrame(
            name=f"{name}_chassis",
            wheelbase_mm=wheelbase_mm,
            track_width_mm=track_width_mm,
            frame_width_mm=frame_width_mm,
            nominal_ground_clearance_mm=nominal_ground_clearance_mm,
        )
        self.front_suspension = DoubleWishboneSuspension(name=f"{name}_front_suspension")
        self.rear_suspension = DoubleWishboneSuspension(name=f"{name}_rear_suspension")
        self.battery_pack = BatteryPackEnclosure(name=f"{name}_battery_pack")

        # Automatically construct default ladder frame
        self.chassis.build_ladder_frame()

        # Register battery keep-out zone under the frame
        bat_l = self.battery_pack.outer_length
        bat_w = self.battery_pack.outer_width
        bat_h = self.battery_pack.outer_height
        cx = self.wheelbase / 2.0
        self.battery_pack_position = (cx, 0.0, self.ground_clearance + (bat_h / 2.0))

    def evaluate_vehicle_mass_and_balance(self) -> Dict[str, Any]:
        """
        Synthesizes total vehicle platform weight, combined Center of Gravity (CoG),
        and front/rear axle static distribution.
        """
        frame_mass, frame_cog = self.chassis.calculate_mass_and_cog()
        bat_mass = self.battery_pack.estimated_total_pack_mass_kg
        bat_cog = self.battery_pack_position

        # Front & rear suspension corner mass estimates (approx 45kg per corner x 2 = 90kg per axle)
        susp_front_mass = 90.0
        susp_rear_mass = 90.0
        susp_front_cog = (0.0, 0.0, self.ground_clearance + 150.0)
        susp_rear_cog = (self.wheelbase, 0.0, self.ground_clearance + 150.0)

        total_mass = frame_mass + bat_mass + susp_front_mass + susp_rear_mass

        cog_x = (
            frame_mass * frame_cog[0]
            + bat_mass * bat_cog[0]
            + susp_front_mass * susp_front_cog[0]
            + susp_rear_mass * susp_rear_cog[0]
        ) / total_mass

        cog_y = (
            frame_mass * frame_cog[1]
            + bat_mass * bat_cog[1]
            + susp_front_mass * susp_front_cog[1]
            + susp_rear_mass * susp_rear_cog[1]
        ) / total_mass

        cog_z = (
            frame_mass * frame_cog[2]
            + bat_mass * bat_cog[2]
            + susp_front_mass * susp_front_cog[2]
            + susp_rear_mass * susp_rear_cog[2]
        ) / total_mass

        # Weight distribution
        rear_ratio = cog_x / max(1.0, self.wheelbase)
        front_ratio = 1.0 - rear_ratio
        g = 9.81
        total_weight_N = total_mass * g

        return {
            "total_platform_mass_kg": round(total_mass, 2),
            "chassis_mass_kg": round(frame_mass, 2),
            "battery_pack_mass_kg": round(bat_mass, 2),
            "suspensions_mass_kg": round(susp_front_mass + susp_rear_mass, 2),
            "cog_coordinates_mm": (round(cog_x, 1), round(cog_y, 1), round(cog_z, 1)),
            "front_weight_percent": round(front_ratio * 100.0, 1),
            "rear_weight_percent": round(rear_ratio * 100.0, 1),
            "front_axle_load_N": round(total_weight_N * front_ratio, 2),
            "rear_axle_load_N": round(total_weight_N * rear_ratio, 2),
            "ideal_balance_within_limits": 45.0 <= (front_ratio * 100.0) <= 55.0,
        }

    def verify_design_contracts(self) -> Dict[str, Any]:
        """
        Unified verification contract:
        1. Chassis clearances & interferences
        2. Front & Rear suspension kinematics (camber gain, bump steer, scrub radius)
        3. Battery thermal cooling flow pressure loss
        4. Static weight balance check
        """
        chassis_res = self.chassis.verify_clearances()
        front_susp_res = self.front_suspension.verify_kinematics()
        rear_susp_res = self.rear_suspension.verify_kinematics()
        cooling_res = self.battery_pack.analyze_thermal_cooling_flow()
        balance_res = self.evaluate_vehicle_mass_and_balance()

        all_passed = (
            chassis_res["passed"]
            and front_susp_res["passed"]
            and rear_susp_res["passed"]
            and cooling_res["pressure_drop_bar"] < 2.0
            and balance_res["ideal_balance_within_limits"]
        )

        return {
            "passed": all_passed,
            "chassis_clearances": chassis_res,
            "front_suspension": front_susp_res,
            "rear_suspension": rear_susp_res,
            "battery_cooling": cooling_res,
            "mass_balance": balance_res,
        }

    def _merge_sub_assembly(
        self,
        target_asm: Assembly,
        sub_asm: Assembly,
        offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        dx, dy, dz = offset
        for name, pref in sub_asm._parts.items():
            if dx != 0.0 or dy != 0.0 or dz != 0.0:
                pref.translate(dx, dy, dz)
            unique_name = name
            count = 1
            while unique_name in target_asm._parts:
                unique_name = f"{name}_{count}"
                count += 1
            pref._node.name = unique_name
            target_asm._ir.add_part(pref._node)
            target_asm._parts[unique_name] = pref

    def to_assembly(self, assembly_name: Optional[str] = None) -> Assembly:
        """
        Assembles all platform components into a unified 3D CADi SAML model.
        """
        master_asm = Assembly(assembly_name or self.name)

        # 1. Add Chassis
        self._merge_sub_assembly(master_asm, self.chassis.to_assembly())

        # 2. Add Battery Pack
        self._merge_sub_assembly(master_asm, self.battery_pack.to_assembly(), offset=self.battery_pack_position)

        # 3. Add Front Suspension
        self._merge_sub_assembly(master_asm, self.front_suspension.to_assembly())

        # 4. Add Rear Suspension (translated to rear axle X=wheelbase)
        self._merge_sub_assembly(
            master_asm,
            self.rear_suspension.to_assembly(f"{self.name}_rear_suspension"),
            offset=(self.wheelbase, 0.0, 0.0),
        )

        return master_asm


__all__ = [
    "ChassisFrame",
    "StructuralProfile",
    "DoubleWishboneSuspension",
    "SuspensionHardpoints",
    "BatteryPackEnclosure",
    "PackElectricalConfig",
    "VehiclePlatform",
    "CableSpecification",
    "WireHarnessRoute",
    "DINComponent",
    "DINRailEnclosure",
    "DFMAnalyzer",
    "DFMCheckResult",
    "ManufacturingCostEstimate",
    "GasMixture",
    "RocketNozzle",
    "NozzleAeroState",
]
