"""
cadi_saml.std_parts.motors
==========================
Standard industrial stepper motors (NEMA 17, NEMA 23).
Provides exact mounting hole patterns, shaft protrusion, pilot boss, and anchor ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode, HoleNode


class Motor:
    """Standard stepper motors factory."""

    @staticmethod
    def NEMA17(name: str, body_length: float = 40.0, shaft_length: float = 24.0) -> PartNode:
        """
        Create NEMA 17 stepper motor (42.3mm x 42.3mm frame).
        Standard 31mm square hole pattern (4x M3), 5mm shaft, 22mm pilot boss.
        """
        bl = float(body_length)
        sl = float(shaft_length)
        part = PartNode(
            name=name,
            part_type="standard",
            shape="nema_stepper",
            parameters={
                "frame": "NEMA17",
                "width": 42.3,
                "body_length": bl,
                "shaft_diameter": 5.0,
                "shaft_length": sl,
                "pilot_diameter": 22.0,
                "pilot_height": 2.0,
                "hole_pitch": 31.0,  # Center-to-center distance
                "hole_diameter": 3.0,
                "hole_depth": 4.5,
            },
        )

        # 1. Front face (mounting flange)
        part.add_port(
            PortNode(
                name="mount_face",
                port_type="face",
                relative_position=(0.0, 0.0, bl),
                normal=(0.0, 0.0, 1.0),
            )
        )

        # 2. Back face
        part.add_port(
            PortNode(
                name="back_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
            )
        )

        # 3. Shaft tip port
        part.add_port(
            PortNode(
                name="shaft_tip",
                port_type="face",
                relative_position=(0.0, 0.0, bl + sl),
                normal=(0.0, 0.0, 1.0),
                diameter=5.0,
            )
        )

        # 4. Shaft axis
        part.add_port(
            PortNode(
                name="shaft_axis",
                port_type="axis",
                relative_position=(0.0, 0.0, bl),
                normal=(0.0, 0.0, 1.0),
                diameter=5.0,
            )
        )

        # 5. Pilot boss face
        part.add_port(
            PortNode(
                name="pilot",
                port_type="face",
                relative_position=(0.0, 0.0, bl + 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=22.0,
            )
        )

        # 6. Four M3 mounting holes
        half_pitch = 31.0 / 2.0
        hole_coords = [
            ("h1", half_pitch, half_pitch),
            ("h2", -half_pitch, half_pitch),
            ("h3", -half_pitch, -half_pitch),
            ("h4", half_pitch, -half_pitch),
        ]
        for h_name, x, y in hole_coords:
            part.add_port(
                PortNode(
                    name=f"mount_{h_name}",
                    port_type="hole",
                    relative_position=(x, y, bl),
                    normal=(0.0, 0.0, 1.0),
                    diameter=3.0,
                )
            )

        return part

    @staticmethod
    def NEMA23(name: str, body_length: float = 56.0, shaft_length: float = 21.0) -> PartNode:
        """
        Create NEMA 23 stepper motor (57mm x 57mm frame).
        Standard 47.14mm square hole pattern (4x 5mm holes), 6.35mm shaft, 38.1mm pilot boss.
        """
        bl = float(body_length)
        sl = float(shaft_length)
        part = PartNode(
            name=name,
            part_type="standard",
            shape="nema_stepper",
            parameters={
                "frame": "NEMA23",
                "width": 57.0,
                "body_length": bl,
                "shaft_diameter": 6.35,
                "shaft_length": sl,
                "pilot_diameter": 38.1,
                "pilot_height": 1.6,
                "hole_pitch": 47.14,
                "hole_diameter": 5.0,
                "hole_depth": 5.0,
            },
        )

        part.add_port(
            PortNode(
                name="mount_face",
                port_type="face",
                relative_position=(0.0, 0.0, bl),
                normal=(0.0, 0.0, 1.0),
            )
        )
        part.add_port(
            PortNode(
                name="shaft_tip",
                port_type="face",
                relative_position=(0.0, 0.0, bl + sl),
                normal=(0.0, 0.0, 1.0),
                diameter=6.35,
            )
        )
        part.add_port(
            PortNode(
                name="shaft_axis",
                port_type="axis",
                relative_position=(0.0, 0.0, bl),
                normal=(0.0, 0.0, 1.0),
                diameter=6.35,
            )
        )

        return part
