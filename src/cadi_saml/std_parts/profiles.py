"""
cadi_saml.std_parts.profiles
============================
Standard aluminum extrusion profiles (V-Slot / T-Slot 2020, 2040).
Provides exact parametric cross-section dimensions, center bore, and slot anchor ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode


class Profile:
    """Standard aluminum extrusion profiles factory."""

    @staticmethod
    def VSlot2020(name: str, length: float = 200.0) -> PartNode:
        """Create 20x20mm V-Slot aluminum profile with slot and end-face ports."""
        l = float(length)
        part = PartNode(
            name=name,
            part_type="standard",
            shape="vslot_profile",
            parameters={
                "type": "2020",
                "width_x": 20.0,
                "width_y": 20.0,
                "length": l,
                "center_bore_dia": 4.2,  # Ready for M5 tap
                "slot_width": 6.0,
            },
        )

        # End faces
        part.add_port(
            PortNode(
                name="start_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=20.0,
            )
        )

        part.add_port(
            PortNode(
                name="end_face",
                port_type="face",
                relative_position=(0.0, 0.0, l),
                normal=(0.0, 0.0, 1.0),
                diameter=20.0,
            )
        )

        # Center bore axis
        part.add_port(
            PortNode(
                name="center_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, l / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=4.2,
            )
        )

        # 4 T-Slot mounting faces
        part.add_port(
            PortNode(
                name="slot_right",
                port_type="face",
                relative_position=(10.0, 0.0, l / 2.0),
                normal=(1.0, 0.0, 0.0),
            )
        )
        part.add_port(
            PortNode(
                name="slot_left",
                port_type="face",
                relative_position=(-10.0, 0.0, l / 2.0),
                normal=(-1.0, 0.0, 0.0),
            )
        )
        part.add_port(
            PortNode(
                name="slot_front",
                port_type="face",
                relative_position=(0.0, 10.0, l / 2.0),
                normal=(0.0, 1.0, 0.0),
            )
        )
        part.add_port(
            PortNode(
                name="slot_back",
                port_type="face",
                relative_position=(0.0, -10.0, l / 2.0),
                normal=(0.0, -1.0, 0.0),
            )
        )

        return part

    @staticmethod
    def VSlot2040(name: str, length: float = 200.0) -> PartNode:
        """Create 20x40mm V-Slot aluminum profile."""
        l = float(length)
        part = PartNode(
            name=name,
            part_type="standard",
            shape="vslot_profile",
            parameters={
                "type": "2040",
                "width_x": 40.0,
                "width_y": 20.0,
                "length": l,
                "center_bore_dia": 4.2,
                "slot_width": 6.0,
            },
        )

        part.add_port(
            PortNode(
                name="start_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
            )
        )
        part.add_port(
            PortNode(
                name="end_face",
                port_type="face",
                relative_position=(0.0, 0.0, l),
                normal=(0.0, 0.0, 1.0),
            )
        )

        return part
