"""
cadi_saml.std_parts.washers
===========================
Standard industrial washers (DIN 125 Plain Washers, DIN 127 Spring Washers).
Provides exact parametric standard dimensions and pre-defined anchor ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode


# DIN 125 Form A (Plain washers) dimensions in mm
# Key: size -> {d1: inner_dia, d2: outer_dia, s: thickness}
DIN125_TABLE = {
    "M3": {"d1": 3.2, "d2": 7.0, "s": 0.5},
    "M4": {"d1": 4.3, "d2": 9.0, "s": 0.8},
    "M5": {"d1": 5.3, "d2": 10.0, "s": 1.0},
    "M6": {"d1": 6.4, "d2": 12.0, "s": 1.6},
    "M8": {"d1": 8.4, "d2": 16.0, "s": 1.6},
    "M10": {"d1": 10.5, "d2": 20.0, "s": 2.0},
    "M12": {"d1": 13.0, "d2": 24.0, "s": 2.5},
}


class Washer:
    """Standard washers factory."""

    @staticmethod
    def DIN125(name: str, size: str = "M6") -> PartNode:
        """Create standard DIN 125 plain washer with ready-to-use anchor ports."""
        size_upper = size.upper()
        if size_upper not in DIN125_TABLE:
            raise ValueError(
                f"Unsupported DIN 125 size '{size}'. Available: {list(DIN125_TABLE.keys())}"
            )

        dims = DIN125_TABLE[size_upper]
        part = PartNode(
            name=name,
            part_type="standard",
            shape="plain_washer",
            parameters={
                "standard": "DIN125",
                "size": size_upper,
                "inner_diameter": dims["d1"],
                "outer_diameter": dims["d2"],
                "thickness": dims["s"],
            },
        )

        part.add_port(
            PortNode(
                name="bottom_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["d2"],
            )
        )

        part.add_port(
            PortNode(
                name="top_face",
                port_type="face",
                relative_position=(0.0, 0.0, dims["s"]),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d2"],
            )
        )

        part.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, dims["s"] / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d1"],
            )
        )

        part.add_port(
            PortNode(
                name="axis",
                port_type="axis",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d1"],
            )
        )

        return part
