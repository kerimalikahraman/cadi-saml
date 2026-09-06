"""
cadi_saml.std_parts.motorsport
==============================
Standard high-performance motorsport and Formula Student components:
- CenterlockNut: Center-lock wheel nut with 45° conical seat and safety pin hole
- BrakeRotor: Ventilated and slotted/drilled motorsport brake disc
- BrakeCaliper: 4-piston monobloc racing caliper
- DrivePin: Wheel hub torque drive pin
- HeimJoint: Spherical rod end / unibal joint for suspension wishbones
"""

from __future__ import annotations

import math
from typing import Optional, Tuple
from ..ir.nodes import PartNode, PortNode


class Motorsport:
    """Motorsport & Formula Student standard components factory."""

    @staticmethod
    def CenterlockNut(
        name: str,
        size: str = "M30",
        thread_diameter: float = 30.0,
        hex_size: float = 46.0,
        height: float = 24.0,
        taper_angle: float = 45.0,
        color: Tuple[float, float, float] = (0.85, 0.10, 0.15),  # Anodized Red
    ) -> PartNode:
        """
        Racing Center-Lock single wheel nut with 45° conical wheel seating skirt
        and safety locking pin through-hole.
        """
        node = PartNode(
            name=name,
            part_type="standard",
            shape="centerlock_nut",
            parameters={
                "size": size,
                "thread_diameter": float(thread_diameter),
                "hex_size": float(hex_size),
                "height": float(height),
                "taper_angle": float(taper_angle),
                "skirt_dia": float(hex_size) + 6.0,
            },
            color=color,
            material="AnodizedAluminum_7075_T6",
        )

        # Bottom conical seating port (mates to wheel centerlock insert)
        node.add_port(
            PortNode(
                name="taper_seat",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=hex_size + 4.0,
            )
        )
        # Center thread axis port
        node.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, height / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=float(thread_diameter),
            )
        )
        return node

    @staticmethod
    def DrivePin(
        name: str,
        pin_diameter: float = 12.0,
        pin_length: float = 20.0,
        thread_size: str = "M8",
        thread_length: float = 16.0,
        color: Tuple[float, float, float] = (0.75, 0.75, 0.78),
    ) -> PartNode:
        """Stepped high-tensile steel drive pin for hub torque transmission."""
        node = PartNode(
            name=name,
            part_type="standard",
            shape="drive_pin",
            parameters={
                "pin_diameter": float(pin_diameter),
                "pin_length": float(pin_length),
                "thread_diameter": 8.0 if "8" in thread_size else 10.0,
                "thread_length": float(thread_length),
            },
            color=color,
            material="HighTensileSteel_4140",
        )
        node.add_port(
            PortNode(
                name="shoulder",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=pin_diameter,
            )
        )
        return node

    @staticmethod
    def BrakeRotor(
        name: str,
        outer_diameter: float = 220.0,
        thickness: float = 4.5,
        inner_mount_diameter: float = 90.0,
        mount_pcd: float = 110.0,
        mount_holes_count: int = 5,
        mount_hole_dia: float = 8.2,
        ventilated_slots_count: int = 8,
        color: Tuple[float, float, float] = (0.65, 0.65, 0.70),
    ) -> PartNode:
        """
        Formula Student lightweight laser-cut stainless steel brake disc rotor
        with peripheral ventilation cooling slots and hub mount PCD.
        """
        node = PartNode(
            name=name,
            part_type="standard",
            shape="brake_rotor",
            parameters={
                "outer_diameter": float(outer_diameter),
                "thickness": float(thickness),
                "inner_diameter": float(inner_mount_diameter),
                "mount_pcd": float(mount_pcd),
                "mount_holes_count": int(mount_holes_count),
                "mount_hole_dia": float(mount_hole_dia),
                "slots_count": int(ventilated_slots_count),
            },
            color=color,
            material="StainlessSteel_420",
        )
        # Mounting face port
        node.add_port(
            PortNode(
                name="hub_mount_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=mount_pcd,
            )
        )
        node.add_port(
            PortNode(
                name="mount_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=mount_pcd,
            )
        )
        node.add_port(
            PortNode(
                name="front_face",
                port_type="face",
                relative_position=(0.0, 0.0, float(thickness)),
                normal=(0.0, 0.0, 1.0),
                diameter=outer_diameter,
            )
        )
        node.add_port(
            PortNode(
                name="center_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=float(inner_mount_diameter),
            )
        )
        return node

    @staticmethod
    def BrakeCaliper(
        name: str,
        length: float = 140.0,
        width: float = 75.0,
        height: float = 65.0,
        rotor_slot_width: float = 8.0,
        rotor_slot_depth: float = 38.0,
        mount_pitch: float = 84.0,
        mount_hole_dia: float = 10.2,
        color: Tuple[float, float, float] = (0.85, 0.10, 0.15),  # Racing Red
    ) -> PartNode:
        """4-Piston Monobloc billet aluminum racing brake caliper."""
        node = PartNode(
            name=name,
            part_type="standard",
            shape="brake_caliper",
            parameters={
                "length": float(length),
                "width": float(width),
                "height": float(height),
                "rotor_slot_width": float(rotor_slot_width),
                "rotor_slot_depth": float(rotor_slot_depth),
                "mount_pitch": float(mount_pitch),
                "mount_hole_dia": float(mount_hole_dia),
            },
            color=color,
            material="BilletAluminum_Al6061_T6",
        )
        node.add_port(
            PortNode(
                name="upright_mount",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=mount_pitch,
            )
        )
        return node

    @staticmethod
    def HeimJoint(
        name: str,
        thread_size: str = "M10",
        ball_bore: float = 10.0,
        ball_width: float = 14.0,
        shank_length: float = 45.0,
        head_diameter: float = 28.0,
        color: Tuple[float, float, float] = (0.80, 0.80, 0.82),
    ) -> PartNode:
        """Spherical rod end bearing (unibal / Heim joint) for suspension wishbones."""
        node = PartNode(
            name=name,
            part_type="standard",
            shape="heim_joint",
            parameters={
                "thread_size": thread_size,
                "thread_dia": 10.0 if "10" in thread_size else 8.0,
                "ball_bore": float(ball_bore),
                "ball_width": float(ball_width),
                "shank_length": float(shank_length),
                "head_diameter": float(head_diameter),
            },
            color=color,
            material="ChromolySteel_4130",
        )
        node.add_port(
            PortNode(
                name="ball_center",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 1.0, 0.0),
                diameter=ball_bore,
            )
        )
        return node
