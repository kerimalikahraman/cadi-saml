"""
cadi_saml.kinematics.motion_solver
==================================
Kinematic forward motion solver and mechanism propagation engine.
Computes rotational angles, linear displacements, and 4x4 rigid body transformation matrices
for interconnected mechanical assemblies.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np

from .joints import JointType, PrismaticJoint, RevoluteJoint
from .relations import (
    BeltRelation,
    FourBarRelation,
    GearRelation,
    RackPinionRelation,
    RelationType,
    ScrewRelation,
    SliderCrankRelation,
    PlanetaryRelation,
)


@dataclass
class KinematicState:
    """Calculated kinematic state of an individual part."""
    part_name: str
    angle_deg: float = 0.0
    translation_mm: float = 0.0
    position: Optional[Tuple[float, float, float]] = None
    transform_matrix: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=np.float64))


def _rotation_matrix_axis_angle(axis: Tuple[float, float, float], angle_rad: float) -> np.ndarray:
    """Rodrigues' rotation matrix for arbitrary 3D axis."""
    ux, uy, uz = axis
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    one_c = 1.0 - cos_a

    R = np.array([
        [cos_a + ux * ux * one_c,       ux * uy * one_c - uz * sin_a, ux * uz * one_c + uy * sin_a, 0.0],
        [uy * ux * one_c + uz * sin_a, cos_a + uy * uy * one_c,       uy * uz * one_c - ux * sin_a, 0.0],
        [uz * ux * one_c - uy * sin_a, uz * uy * one_c + ux * sin_a, cos_a + uz * uz * one_c,       0.0],
        [0.0,                          0.0,                          0.0,                          1.0],
    ], dtype=np.float64)
    return R


def _translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
    T = np.eye(4, dtype=np.float64)
    T[0, 3] = tx
    T[1, 3] = ty
    T[2, 3] = tz
    return T


class KinematicMechanism:
    """
    Manages kinematic degrees of freedom, joints, and transmission mates.
    Propagates motion across the assembly graph.
    """

    def __init__(self):
        self.joints: Dict[str, Union[RevoluteJoint, PrismaticJoint]] = {}
        self.relations: List[Union[GearRelation, RackPinionRelation, BeltRelation, ScrewRelation, SliderCrankRelation, FourBarRelation, PlanetaryRelation]] = []

    def add_joint(self, joint: Union[RevoluteJoint, PrismaticJoint]) -> None:
        self.joints[joint.part_name] = joint

    def add_relation(self, relation: Union[GearRelation, RackPinionRelation, BeltRelation, ScrewRelation, SliderCrankRelation, FourBarRelation, PlanetaryRelation]) -> None:
        self.relations.append(relation)

    def solve(
        self,
        driver_part: str,
        driver_value: float = 0.0,
    ) -> Dict[str, KinematicState]:
        """
        Solves forward kinematics for the mechanism starting from the driver part.
        If driver has a RevoluteJoint, driver_value is interpreted as degrees.
        If driver has a PrismaticJoint, driver_value is interpreted as mm translation.
        """
        report = self.validate_mechanism(driver_part)
        if not report['valid']:
            raise ValueError('; '.join(report['errors']))
        if not math.isfinite(driver_value):
            raise ValueError('Driver value must be finite')
        states: Dict[str, KinematicState] = {}

        driver_joint = self.joints.get(driver_part)
        if isinstance(driver_joint, PrismaticJoint):
            states[driver_part] = KinematicState(
                part_name=driver_part,
                angle_deg=0.0,
                translation_mm=float(driver_value),
            )
        else:
            states[driver_part] = KinematicState(
                part_name=driver_part,
                angle_deg=float(driver_value),
                translation_mm=0.0,
            )

        queue = collections.deque([driver_part])
        visited: Set[str] = {driver_part}

        # BFS propagation across mechanical relations
        while queue:
            curr = queue.popleft()
            curr_state = states[curr]

            for rel in self.relations:
                if isinstance(rel, (GearRelation, BeltRelation)):
                    # Forward: curr is driver -> driven
                    if rel.driver_part == curr and rel.driven_part not in visited:
                        sign = -1.0 if rel.reverse else 1.0
                        driven_angle = curr_state.angle_deg * sign * rel.ratio
                        states[rel.driven_part] = KinematicState(
                            part_name=rel.driven_part,
                            angle_deg=driven_angle,
                            translation_mm=0.0,
                        )
                        visited.add(rel.driven_part)
                        queue.append(rel.driven_part)
                    # Backward: curr is driven -> driver
                    elif rel.driven_part == curr and rel.driver_part not in visited:
                        sign = -1.0 if rel.reverse else 1.0
                        ratio = rel.ratio if abs(rel.ratio) > 1e-9 else 1.0
                        driver_angle = curr_state.angle_deg / (sign * ratio)
                        states[rel.driver_part] = KinematicState(
                            part_name=rel.driver_part,
                            angle_deg=driver_angle,
                            translation_mm=0.0,
                        )
                        visited.add(rel.driver_part)
                        queue.append(rel.driver_part)

                elif isinstance(rel, RackPinionRelation):
                    if rel.pinion_part == curr and rel.rack_part not in visited:
                        rad = math.radians(curr_state.angle_deg)
                        sign = -1.0 if rel.reverse else 1.0
                        linear_disp = rad * rel.pitch_radius * sign
                        states[rel.rack_part] = KinematicState(
                            part_name=rel.rack_part,
                            angle_deg=0.0,
                            translation_mm=linear_disp,
                        )
                        visited.add(rel.rack_part)
                        queue.append(rel.rack_part)
                    elif rel.rack_part == curr and rel.pinion_part not in visited:
                        sign = -1.0 if rel.reverse else 1.0
                        pr = rel.pitch_radius if abs(rel.pitch_radius) > 1e-9 else 1.0
                        rad = curr_state.translation_mm / (pr * sign)
                        states[rel.pinion_part] = KinematicState(
                            part_name=rel.pinion_part,
                            angle_deg=math.degrees(rad),
                            translation_mm=0.0,
                        )
                        visited.add(rel.pinion_part)
                        queue.append(rel.pinion_part)

                elif isinstance(rel, ScrewRelation):
                    if rel.screw_part == curr and rel.nut_part not in visited:
                        disp = curr_state.angle_deg * (rel.pitch_mm / 360.0)
                        states[rel.nut_part] = KinematicState(
                            part_name=rel.nut_part,
                            angle_deg=0.0,
                            translation_mm=disp,
                        )
                        visited.add(rel.nut_part)
                        queue.append(rel.nut_part)

                    elif rel.nut_part == curr and rel.screw_part not in visited:
                        states[rel.screw_part] = KinematicState(part_name=rel.screw_part,
                            angle_deg=curr_state.translation_mm * 360 / rel.pitch_mm)
                        visited.add(rel.screw_part)
                        queue.append(rel.screw_part)

                elif isinstance(rel, SliderCrankRelation):
                    if rel.crank_part == curr:
                        piston_disp, conrod_angle, crankpin_xyz = rel.solve_for_crank_angle(curr_state.angle_deg)
                        if rel.piston_part not in visited:
                            p_joint = self.joints.get(rel.piston_part)
                            p_orig = p_joint.origin if p_joint else rel.crank_center
                            ax, ay, az = rel.slide_axis
                            nominal_disp_0 = rel.crank_radius + rel.conrod_length
                            delta_disp = piston_disp - nominal_disp_0
                            p_pos = (
                                p_orig[0] + ax * delta_disp,
                                p_orig[1] + ay * delta_disp,
                                p_orig[2] + az * delta_disp,
                            )
                            states[rel.piston_part] = KinematicState(
                                part_name=rel.piston_part,
                                angle_deg=0.0,
                                translation_mm=piston_disp,
                                position=p_pos,
                            )
                            visited.add(rel.piston_part)
                            queue.append(rel.piston_part)
                        if rel.conrod_part not in visited:
                            states[rel.conrod_part] = KinematicState(
                                part_name=rel.conrod_part,
                                angle_deg=conrod_angle,
                                translation_mm=0.0,
                                position=crankpin_xyz,
                            )
                            visited.add(rel.conrod_part)
                            queue.append(rel.conrod_part)

                elif isinstance(rel, PlanetaryRelation):
                    all_members = {rel.sun_part, rel.carrier_part, rel.ring_part} | set(rel.planet_parts)
                    if curr in all_members:
                        if curr == rel.sun_part:
                            speeds = rel.solve_speeds(omega_sun=curr_state.angle_deg)
                        elif curr == rel.carrier_part:
                            speeds = rel.solve_speeds(omega_carrier=curr_state.angle_deg)
                        elif curr == rel.ring_part:
                            speeds = rel.solve_speeds(omega_ring=curr_state.angle_deg)
                        else:
                            speeds = {}

                        carrier_angle = speeds.get(rel.carrier_part, 0.0)
                        carrier_rad = math.radians(carrier_angle)
                        cos_c = math.cos(carrier_rad)
                        sin_c = math.sin(carrier_rad)

                        for target_part, ang in speeds.items():
                            if target_part not in visited:
                                p_pos = None
                                if target_part in rel.planet_parts:
                                    p_joint = self.joints.get(target_part)
                                    if p_joint is not None:
                                        ox, oy, oz = p_joint.origin
                                        p_pos = (
                                            ox * cos_c - oy * sin_c,
                                            ox * sin_c + oy * cos_c,
                                            oz,
                                        )
                                states[target_part] = KinematicState(
                                    part_name=target_part,
                                    angle_deg=ang,
                                    translation_mm=0.0,
                                    position=p_pos,
                                )
                                visited.add(target_part)
                                queue.append(target_part)

        # Compute 4x4 spatial transformation matrices for all solved parts
        for part_name, state in states.items():
            joint = self.joints.get(part_name)
            if joint is None:
                continue

            ox, oy, oz = joint.origin
            ax, ay, az = joint.axis

            if isinstance(joint, RevoluteJoint):
                angle_rad = math.radians(state.angle_deg)
                T_to_origin = _translation_matrix(-ox, -oy, -oz)
                R = _rotation_matrix_axis_angle((ax, ay, az), angle_rad)
                T_from_origin = _translation_matrix(ox, oy, oz)
                if state.position is not None:
                    T_from_origin = _translation_matrix(*state.position)
                state.transform_matrix = T_from_origin @ R @ T_to_origin
            elif isinstance(joint, PrismaticJoint):
                tx = ax * state.translation_mm
                ty = ay * state.translation_mm
                tz = az * state.translation_mm
                if state.position is not None:
                    tx, ty, tz = np.asarray(state.position) - np.asarray(joint.origin)
                state.transform_matrix = _translation_matrix(tx, ty, tz)

        return states

    def solve_trajectory(
        self,
        driver_part: str,
        start_deg: float = 0.0,
        end_deg: float = 360.0,
        step_deg: float = 1.0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Solves complete motion cycle for all parts across a range of driver angles.
        Returns dict of part_name -> list of dicts with {angle_deg, translation_mm, pos: [x,y,z]}.
        """
        if not all(math.isfinite(x) for x in (start_deg, end_deg, step_deg)) or step_deg <= 0 or end_deg < start_deg:
            raise ValueError('Trajectory requires finite ascending bounds and positive step')
        if (end_deg - start_deg) / step_deg > 10000:
            raise ValueError('Trajectory exceeds 10001 sample budget')
        trajectory: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        cur = start_deg
        while cur <= end_deg + 1e-6:
            st = self.solve(driver_part, driver_value=cur)
            for p_name, p_state in st.items():
                joint = self.joints.get(p_name)
                default_pos = list(joint.origin) if joint else [0.0, 0.0, 0.0]
                pos = list(p_state.position) if p_state.position is not None else default_pos
                trajectory[p_name].append({
                    "angle_deg": round(p_state.angle_deg, 3),
                    "translation_mm": round(p_state.translation_mm, 3),
                    "pos": [round(coord, 3) for coord in pos],
                })
            cur += step_deg
        return dict(trajectory)

    def validate_mechanism(self, driver_part):
        from .inspection import validate_mechanism
        return validate_mechanism(self, driver_part)

    def solve_loop_closure(self, driver_part, value=0.0):
        from .inspection import solve_loop_closure
        return solve_loop_closure(self, driver_part, value)
