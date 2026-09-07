"""
cadi_saml.systems.chassis

Vehicle chassis and spaceframe engineering module:
- Parametric longitudinal rails, crossmembers, roll hoops, and mounting brackets
- Section definitions (rectangular box tubing, round pipe, I/C channel)
- Automated static axle weight & Center of Gravity (CoG) estimation
- Torsional stiffness and bending load case generation for FEA
- Keep-out envelope validation (clearance for battery, powertrain, and suspension)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from ..core.assembly import Assembly, PartReference


@dataclass
class StructuralProfile:
    """Defines a structural beam profile section."""
    profile_type: str = "box"  # 'box', 'tube', 'c_channel'
    width: float = 50.0        # mm (outer)
    height: float = 50.0       # mm (outer)
    wall_thickness: float = 3.0 # mm
    material: str = "Structural_Steel"  # density ~7850 kg/m^3, E=210 GPa

    @property
    def cross_section_area_mm2(self) -> float:
        t = self.wall_thickness
        if self.profile_type == "box":
            return (self.width * self.height) - ((self.width - 2 * t) * (self.height - 2 * t))
        elif self.profile_type == "tube":
            r_out = self.width / 2.0
            r_in = max(0.1, r_out - t)
            return math.pi * (r_out**2 - r_in**2)
        else:
            # Simple approximation for channel
            return (self.width * t) + 2.0 * (self.height - t) * t

    @property
    def mass_per_meter_kg(self) -> float:
        density_kg_mm3 = 7.85e-6 if "steel" in self.material.lower() else 2.7e-6
        return self.cross_section_area_mm2 * 1000.0 * density_kg_mm3


@dataclass
class ChassisMember:
    """Represents a single structural chassis beam or rail."""
    name: str
    start_pt: Tuple[float, float, float]
    end_pt: Tuple[float, float, float]
    profile: StructuralProfile
    role: str = "rail"  # 'longitudinal', 'crossmember', 'brace', 'suspension_mount'

    @property
    def length_mm(self) -> float:
        p0 = np.array(self.start_pt)
        p1 = np.array(self.end_pt)
        return float(np.linalg.norm(p1 - p0))

    @property
    def center_point(self) -> Tuple[float, float, float]:
        p0 = np.array(self.start_pt)
        p1 = np.array(self.end_pt)
        mid = (p0 + p1) / 2.0
        return (float(mid[0]), float(mid[1]), float(mid[2]))

    @property
    def mass_kg(self) -> float:
        return (self.length_mm / 1000.0) * self.profile.mass_per_meter_kg


@dataclass
class KeepOutZone:
    """3D bounding volume reserved for components (must not be breached by frame members)."""
    name: str
    bounding_box: Tuple[float, float, float, float, float, float] # (xmin, ymin, zmin, xmax, ymax, zmax)


class ChassisFrame:
    """
    Parametric chassis / spaceframe manager.
    Coordinates main rails, crossmembers, axle loads, and FEA load cases.
    """

    def __init__(
        self,
        name: str = "chassis_frame",
        wheelbase_mm: float = 2700.0,
        track_width_mm: float = 1600.0,
        frame_width_mm: float = 1000.0,
        nominal_ground_clearance_mm: float = 180.0,
    ):
        self.name = name
        self.wheelbase = wheelbase_mm
        self.track_width = track_width_mm
        self.frame_width = frame_width_mm
        self.ground_clearance = nominal_ground_clearance_mm

        self.members: List[ChassisMember] = []
        self.keep_out_zones: List[KeepOutZone] = []
        self.hardpoints: Dict[str, Tuple[float, float, float]] = {}

        # Default standard profiles
        self.main_profile = StructuralProfile(profile_type="box", width=80.0, height=60.0, wall_thickness=3.5)
        self.cross_profile = StructuralProfile(profile_type="box", width=60.0, height=50.0, wall_thickness=3.0)
        self.brace_profile = StructuralProfile(profile_type="tube", width=40.0, height=40.0, wall_thickness=2.5)

    def add_member(
        self,
        name: str,
        start_pt: Tuple[float, float, float],
        end_pt: Tuple[float, float, float],
        profile: Optional[StructuralProfile] = None,
        role: str = "rail",
    ) -> ChassisMember:
        """Adds a structural member between two 3D spatial points."""
        prof = profile or self.cross_profile
        member = ChassisMember(name=name, start_pt=start_pt, end_pt=end_pt, profile=prof, role=role)
        self.members.append(member)
        return member

    def add_keep_out_zone(
        self,
        name: str,
        xmin: float, ymin: float, zmin: float,
        xmax: float, ymax: float, zmax: float,
    ) -> KeepOutZone:
        """Defines a protected clearance zone (e.g. for battery pack or engine)."""
        zone = KeepOutZone(name=name, bounding_box=(xmin, ymin, zmin, xmax, ymax, zmax))
        self.keep_out_zones.append(zone)
        return zone

    def build_ladder_frame(
        self,
        num_crossmembers: int = 5,
        overhang_front_mm: float = 700.0,
        overhang_rear_mm: float = 800.0,
    ) -> None:
        """
        Synthesizes a full parameterized automotive ladder chassis:
        - 2 longitudinal main rails
        - Front & rear bumper crossmembers
        - Intermediate battery / powertrain crossmembers
        """
        y_left = self.frame_width / 2.0
        y_right = -self.frame_width / 2.0
        z_rail = self.ground_clearance + 150.0  # Rail height above ground

        x_front = -overhang_front_mm
        x_rear = self.wheelbase + overhang_rear_mm
        total_length = x_rear - x_front

        # 1. Main Longitudinal Rails
        self.add_member(
            name="rail_left",
            start_pt=(x_front, y_left, z_rail),
            end_pt=(x_rear, y_left, z_rail),
            profile=self.main_profile,
            role="longitudinal",
        )
        self.add_member(
            name="rail_right",
            start_pt=(x_front, y_right, z_rail),
            end_pt=(x_rear, y_right, z_rail),
            profile=self.main_profile,
            role="longitudinal",
        )

        # 2. Crossmembers evenly distributed
        x_steps = np.linspace(x_front, x_rear, max(3, num_crossmembers))
        for i, x in enumerate(x_steps):
            c_name = f"crossmember_{i+1}"
            if i == 0:
                c_name = "bumper_front"
            elif i == len(x_steps) - 1:
                c_name = "bumper_rear"
            elif i == 1:
                c_name = "front_axle_crossmember"
            elif i == len(x_steps) - 2:
                c_name = "rear_axle_crossmember"

            self.add_member(
                name=c_name,
                start_pt=(float(x), y_left, z_rail),
                end_pt=(float(x), y_right, z_rail),
                profile=self.cross_profile,
                role="crossmember",
            )

        # 3. Register Key Reference Hardpoints
        self.hardpoints["front_axle_center"] = (0.0, 0.0, self.ground_clearance + 100.0)
        self.hardpoints["rear_axle_center"] = (self.wheelbase, 0.0, self.ground_clearance + 100.0)
        self.hardpoints["frame_center"] = (self.wheelbase / 2.0, 0.0, z_rail)

    def calculate_mass_and_cog(self) -> Tuple[float, Tuple[float, float, float]]:
        """
        Calculates total structural frame mass and center of gravity coordinates.
        Returns (total_mass_kg, (cog_x, cog_y, cog_z)).
        """
        if not self.members:
            return 0.0, (0.0, 0.0, 0.0)

        total_mass = 0.0
        weighted_sum = np.zeros(3)

        for m in self.members:
            mass = m.mass_kg
            c_pt = np.array(m.center_point)
            total_mass += mass
            weighted_sum += mass * c_pt

        cog = weighted_sum / max(1e-6, total_mass)
        return float(total_mass), (float(cog[0]), float(cog[1]), float(cog[2]))

    def calculate_axle_load_distribution(
        self,
        additional_payload_kg: float = 0.0,
        payload_cog_x: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates front and rear axle static load distribution under gravity.
        Wheelbase is measured from front axle (X=0) to rear axle (X=wheelbase).
        """
        frame_mass, frame_cog = self.calculate_mass_and_cog()
        total_mass = frame_mass + additional_payload_kg

        if additional_payload_kg > 0 and payload_cog_x is not None:
            combined_cog_x = (frame_mass * frame_cog[0] + additional_payload_kg * payload_cog_x) / total_mass
        else:
            combined_cog_x = frame_cog[0]

        # Moment balance about front axle (x=0):
        # Rear Axle Force * Wheelbase = Total Weight * CoG_X
        # Front Axle Force = Total Weight - Rear Axle Force
        rear_ratio = combined_cog_x / max(1.0, self.wheelbase)
        rear_ratio = max(0.0, min(1.0, rear_ratio))
        front_ratio = 1.0 - rear_ratio

        g = 9.81
        total_weight_N = total_mass * g
        front_load_N = total_weight_N * front_ratio
        rear_load_N = total_weight_N * rear_ratio

        return {
            "total_mass_kg": round(total_mass, 2),
            "frame_mass_kg": round(frame_mass, 2),
            "cog_x_mm": round(combined_cog_x, 1),
            "front_axle_load_N": round(front_load_N, 2),
            "rear_axle_load_N": round(rear_load_N, 2),
            "front_weight_percent": round(front_ratio * 100.0, 1),
            "rear_weight_percent": round(rear_ratio * 100.0, 1),
        }

    def generate_torsional_stiffness_load_case(
        self,
        applied_torque_kNm: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Generates boundary conditions and torque load sets for chassis FEA torsional stiffness testing:
        - Rear suspension hardpoints clamped (Fixed in XYZ).
        - Front suspension hardpoints subjected to opposing vertical forces (+F on left, -F on right).
        Torque = F * track_width.
        """
        track_m = self.track_width / 1000.0
        torque_Nm = applied_torque_kNm * 1000.0
        # F * track_m = torque_Nm -> F = torque_Nm / track_m
        force_N = torque_Nm / max(0.1, track_m)

        return {
            "test_type": "torsional_stiffness",
            "applied_torque_kNm": applied_torque_kNm,
            "force_per_side_N": round(force_N, 2),
            "boundary_conditions": {
                "rear_left_mount": {"constraint": "fixed", "position": (self.wheelbase, self.frame_width / 2.0, self.ground_clearance + 150.0)},
                "rear_right_mount": {"constraint": "fixed", "position": (self.wheelbase, -self.frame_width / 2.0, self.ground_clearance + 150.0)},
                "front_left_load": {"force_vector_N": (0.0, 0.0, force_N), "position": (0.0, self.track_width / 2.0, self.ground_clearance + 100.0)},
                "front_right_load": {"force_vector_N": (0.0, 0.0, -force_N), "position": (0.0, -self.track_width / 2.0, self.ground_clearance + 100.0)},
            },
            "acceptance_criteria": {
                "min_torsional_stiffness_kNm_per_deg": 10.0,  # Road vehicle minimum
            }
        }

    def verify_clearances(self) -> Dict[str, Any]:
        """
        Checks all members against defined keep-out zones to ensure no interference.
        Returns pass/fail status with offending members if any.
        """
        interferences = []
        for zone in self.keep_out_zones:
            zx0, zy0, zz0, zx1, zy1, zz1 = zone.bounding_box
            for m in self.members:
                cx, cy, cz = m.center_point
                # Check if member midpoint is inside the keep out zone
                if (zx0 <= cx <= zx1) and (zy0 <= cy <= zy1) and (zz0 <= cz <= zz1):
                    interferences.append({
                        "zone": zone.name,
                        "member": m.name,
                        "member_center": (round(cx, 1), round(cy, 1), round(cz, 1)),
                    })

        return {
            "passed": len(interferences) == 0,
            "interference_count": len(interferences),
            "details": interferences,
        }

    def to_assembly(self, assembly_name: Optional[str] = None) -> Assembly:
        """
        Generates a parametric 3D CADi SAML Assembly solid representation
        of all chassis structural members.
        """
        asm = Assembly(assembly_name or self.name)
        
        for m in self.members:
            length = m.length_mm
            w = m.profile.width
            h = m.profile.height
            
            # Create box primitive along the member
            p0 = np.array(m.start_pt)
            p1 = np.array(m.end_pt)
            mid = (p0 + p1) / 2.0

            part = asm.add_box(
                name=m.name,
                length=length,
                width=w,
                height=h,
            )
            # Position at midpoint
            part.translate(float(mid[0]), float(mid[1]), float(mid[2]))

        return asm
