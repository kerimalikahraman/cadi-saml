"""
cadi_saml.macros.iris_nozzle
============================
Variable Exhaust Nozzle (Iris Mechanism) for jet engines and gas turbines.
Models convergent-divergent nozzle flaps (12 petals arranged at 30 deg intervals)
with local hinge axes, synchronized area control (throat diameter D8 / A8),
and thrust vectoring (pitch/yaw gimbal angles).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


@dataclass
class IrisNozzleMetrics:
    """Aerodynamic and geometric state telemetry for variable exhaust nozzle."""
    opening_angle_deg: float
    throat_diameter_mm: float
    throat_area_mm2: float
    inlet_area_mm2: float
    expansion_ratio: float
    pitch_angle_deg: float = 0.0
    yaw_angle_deg: float = 0.0
    vector_magnitude_deg: float = 0.0


class IrisNozzleMechanism:
    """
    Manages kinematic state, geometric evaluation, and thrust vectoring
    for a 12-petal variable iris nozzle.
    """

    def __init__(
        self,
        assembly: Assembly,
        num_petals: int = 12,
        base_radius: float = 160.0,
        petal_length: float = 130.0,
        nominal_opening_deg: float = 10.0,
        min_opening_deg: float = -5.0,
        max_opening_deg: float = 25.0,
    ):
        self.assembly = assembly
        self.num_petals = int(num_petals)
        self.base_radius = float(base_radius)
        self.petal_length = float(petal_length)
        self.nominal_opening_deg = float(nominal_opening_deg)
        self.min_opening_deg = float(min_opening_deg)
        self.max_opening_deg = float(max_opening_deg)
        self.petal_names: List[str] = [f"petal_{i+1}" for i in range(self.num_petals)]

    def compute_throat_diameter(self, opening_angle_deg: float) -> float:
        """
        Computes the physical throat diameter D8 at the trailing edge of the petals.
        Rigid-body rotation: D = 2 * (R_base + L_petal * sin(opening_angle)).
        Positive angle expands the nozzle; negative angle contracts it.
        """
        theta_rad = math.radians(opening_angle_deg)
        r_exit = self.base_radius + self.petal_length * math.sin(theta_rad)
        return max(10.0, 2.0 * r_exit)

    def compute_throat_area(self, opening_angle_deg: float) -> float:
        """
        Computes cross-sectional exit area A8.
        Uses exact regular N-gon area with N petals:
        A = 0.5 * N * R^2 * sin(2*pi / N).
        """
        d = self.compute_throat_diameter(opening_angle_deg)
        r = d / 2.0
        n = self.num_petals
        return 0.5 * n * (r ** 2) * math.sin(2.0 * math.pi / n)

    def evaluate_state(
        self,
        opening_angle_deg: float,
        pitch_deg: float = 0.0,
        yaw_deg: float = 0.0,
    ) -> IrisNozzleMetrics:
        """
        Evaluates physical nozzle geometry, throat area, and thrust vector angles
        without scaling the underlying parts.
        """
        d_throat = self.compute_throat_diameter(opening_angle_deg)
        a_throat = self.compute_throat_area(opening_angle_deg)
        inlet_d = 2.0 * self.base_radius
        a_inlet = math.pi * (self.base_radius ** 2)
        expansion_ratio = a_throat / max(1e-6, a_inlet)

        # Compound vector magnitude = sqrt(pitch^2 + yaw^2)
        vec_mag = math.hypot(pitch_deg, yaw_deg)

        return IrisNozzleMetrics(
            opening_angle_deg=opening_angle_deg,
            throat_diameter_mm=round(d_throat, 2),
            throat_area_mm2=round(a_throat, 2),
            inlet_area_mm2=round(a_inlet, 2),
            expansion_ratio=round(expansion_ratio, 4),
            pitch_angle_deg=round(pitch_deg, 2),
            yaw_angle_deg=round(yaw_deg, 2),
            vector_magnitude_deg=round(vec_mag, 2),
        )

    def solve_petal_hinge(self, petal_index: int) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Returns (origin_point, tangent_axis) for a specific petal index (0-based).
        The hinge axis is tangent to the mounting circle:
        u_tangent = (-sin(theta), cos(theta), 0.0).
        """
        step_rad = (2.0 * math.pi / self.num_petals) * petal_index
        ox = self.base_radius * math.cos(step_rad)
        oy = self.base_radius * math.sin(step_rad)
        oz = 0.0

        # Tangent vector perpendicular to radial vector (cos, sin, 0)
        # Tangent: (-sin, cos, 0)
        ax = -math.sin(step_rad)
        ay = math.cos(step_rad)
        az = 0.0

        return (ox, oy, oz), (ax, ay, az)


def build_variable_exhaust_nozzle(
    assembly: Optional[Assembly] = None,
    num_petals: int = 12,
    base_radius: float = 160.0,
    petal_length: float = 130.0,
    petal_thickness: float = 4.0,
    nominal_opening_deg: float = 10.0,
) -> Tuple[Assembly, IrisNozzleMechanism]:
    """
    Creates a complete 12-petal variable exhaust nozzle assembly.
    1. Generates master petal with aerodynamic curvature and hinge geometry.
    2. Duplicates 12 linked instances circularly around the engine axis.
    3. Defines local tangent hinge revolute joints for each petal.
    4. Connects all petals to an actuation driver via SynchronizedGroupRelation.
    5. Returns (assembly, mechanism).
    """
    from ..core.assembly import Assembly

    asm = assembly or Assembly("Jet_Engine_Variable_Nozzle", units="mm")

    # 1. Base Casing / Flange Ring (Fixed ground component)
    casing_thickness = 15.0
    casing_length = 50.0
    casing = asm.add_cylinder(
        "nozzle_casing",
        radius=base_radius + casing_thickness,
        height=casing_length,
        origin=(0.0, 0.0, -casing_length / 2.0),
    ).set_appearance(color=(0.25, 0.28, 0.32), material="Titanium Alloy Ti-6Al-4V")

    # Bore inner duct through casing
    duct_tool = asm.add_cylinder(
        "duct_bore_tool",
        radius=base_radius - 2.0,
        height=casing_length + 10.0,
        origin=(0.0, 0.0, -casing_length / 2.0),
    )
    asm.cut("nozzle_casing", "duct_bore_tool", keep_tool=False)

    # 2. Master Actuation Ring (Driver component)
    actuator_ring = asm.add_cylinder(
        "control_ring",
        radius=base_radius + casing_thickness + 12.0,
        height=14.0,
        origin=(0.0, 0.0, -10.0),
    ).set_appearance(color=(0.85, 0.45, 0.15), material="Aerospace Anodized Bronze")

    ring_bore = asm.add_cylinder(
        "ring_bore_tool",
        radius=base_radius + casing_thickness + 2.0,
        height=20.0,
        origin=(0.0, 0.0, -10.0),
    )
    asm.cut("control_ring", "ring_bore_tool", keep_tool=False)

    # 3. Master Petal Geometry
    # Width at base = 2 * R * sin(pi / N) + overlap margin
    petal_chord = 2.0 * base_radius * math.sin(math.pi / num_petals) + 12.0

    # Aerodynamic convergent divergent flap profile
    # Box shaped base blank with longitudinal taper
    master_petal = asm.add_box(
        "petal_1",
        length=petal_thickness,
        width=petal_chord,
        height=petal_length,
        origin=(base_radius, 0.0, petal_length / 2.0),
    ).set_appearance(color=(0.75, 0.78, 0.82), material="Inconel 718 High-Temp Nickel Superalloy")

    # Add hinge pin hole at the base of the master petal
    master_petal.add_hole(
        name="hinge_pin_hole",
        diameter=6.0,
        depth=petal_thickness + 2.0,
        position=(0.0, -petal_length / 2.0 + 8.0),
        face="top",
    )

    # 4. Circular Pattern of 12 Petals
    # Creates petal_2 ... petal_12 as linked instances
    petals = asm.pattern_circular(
        target_part="petal_1",
        count=num_petals,
        center=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        angle=360.0,
        create_instances=True,
        prefix="petal",
    )

    # 5. Kinematic Mechanism Setup
    mech = IrisNozzleMechanism(
        assembly=asm,
        num_petals=num_petals,
        base_radius=base_radius,
        petal_length=petal_length,
        nominal_opening_deg=nominal_opening_deg,
    )

    # Add driver joint for the control ring (Z-rotation or driver angle)
    asm.add_revolute_joint("control_ring", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

    # For each petal, attach local hinge joint
    driven_petal_names = []
    for i in range(num_petals):
        p_name = f"petal_{i+1}"
        origin, axis = mech.solve_petal_hinge(i)
        asm.add_revolute_joint(
            p_name,
            origin=origin,
            axis=axis,
            initial_angle=nominal_opening_deg,
        )
        driven_petal_names.append(p_name)

    # Couple control ring driver to all 12 petal hinges
    asm.add_synchronized_group(
        driver_part="control_ring",
        driven_parts=driven_petal_names,
        ratio=1.0,
        reverse=False,
    )

    return asm, mech
