"""
cadi_saml.std_parts.nuts
========================
Standard industrial nuts (DIN 934 Hexagon Nuts, DIN 985 Prevailing Torque / Nyloc Nuts).
Provides exact parametric standard dimensions and pre-defined anchor ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode


# DIN 934 (Hexagon nuts) dimensions in mm
# Key: size -> {d: thread_dia, s: width_across_flats, m: height}
DIN934_TABLE = {
    "M3": {"d": 3.0, "s": 5.5, "m": 2.4},
    "M4": {"d": 4.0, "s": 7.0, "m": 3.2},
    "M5": {"d": 5.0, "s": 8.0, "m": 4.0},
    "M6": {"d": 6.0, "s": 10.0, "m": 5.0},
    "M8": {"d": 8.0, "s": 13.0, "m": 6.5},
    "M10": {"d": 10.0, "s": 17.0, "m": 8.0},
    "M12": {"d": 12.0, "s": 19.0, "m": 10.0},
}

# DIN 985 (Nyloc lock nuts) dimensions in mm
DIN985_TABLE = {
    "M3": {"d": 3.0, "s": 5.5, "m": 4.0},
    "M4": {"d": 4.0, "s": 7.0, "m": 5.0},
    "M5": {"d": 5.0, "s": 8.0, "m": 5.0},
    "M6": {"d": 6.0, "s": 10.0, "m": 6.0},
    "M8": {"d": 8.0, "s": 13.0, "m": 8.0},
    "M10": {"d": 10.0, "s": 17.0, "m": 10.0},
    "M12": {"d": 12.0, "s": 19.0, "m": 12.0},
}


class Nut:
    """Standard nuts factory."""

    @staticmethod
    def DIN934(name: str, size: str = "M6") -> PartNode:
        """Create standard DIN 934 hex nut with ready-to-use anchor ports."""
        size_upper = size.upper()
        if size_upper not in DIN934_TABLE:
            raise ValueError(
                f"Unsupported DIN 934 size '{size}'. Available: {list(DIN934_TABLE.keys())}"
            )

        dims = DIN934_TABLE[size_upper]
        part = PartNode(
            name=name,
            part_type="standard",
            shape="hex_nut",
            parameters={
                "standard": "DIN934",
                "size": size_upper,
                "thread_diameter": dims["d"],
                "width_across_flats": dims["s"],
                "height": dims["m"],
            },
        )

        part.add_port(
            PortNode(
                name="bottom_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["s"],
            )
        )

        part.add_port(
            PortNode(
                name="top_face",
                port_type="face",
                relative_position=(0.0, 0.0, dims["m"]),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["s"],
            )
        )

        part.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, dims["m"] / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d"],
            )
        )

        part.add_port(
            PortNode(
                name="axis",
                port_type="axis",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d"],
            )
        )

        return part

    @staticmethod
    def DIN985(name: str, size: str = "M6") -> PartNode:
        """Create standard DIN 985 nyloc lock nut."""
        size_upper = size.upper()
        if size_upper not in DIN985_TABLE:
            raise ValueError(
                f"Unsupported DIN 985 size '{size}'. Available: {list(DIN985_TABLE.keys())}"
            )

        dims = DIN985_TABLE[size_upper]
        part = PartNode(
            name=name,
            part_type="standard",
            shape="hex_nut",
            parameters={
                "standard": "DIN985",
                "size": size_upper,
                "thread_diameter": dims["d"],
                "width_across_flats": dims["s"],
                "height": dims["m"],
            },
        )

        part.add_port(
            PortNode(
                name="bottom_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["s"],
            )
        )

        part.add_port(
            PortNode(
                name="top_face",
                port_type="face",
                relative_position=(0.0, 0.0, dims["m"]),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["s"],
            )
        )

        part.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, dims["m"] / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d"],
            )
        )

        part.add_port(
            PortNode(
                name="axis",
                port_type="axis",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d"],
            )
        )

        return part
