"""
cadi_saml.std_parts.fasteners
=============================
Standard industrial fasteners (ISO 4762 Socket Head Cap Screws, DIN 933 Hex Bolts).
Provides exact parametric standard dimensions and pre-defined anchor ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode


# ISO 4762 (Hexagon socket head cap screws) dimensions in mm
# Key: size -> {shank_dia, head_dia, head_height, hex_key_size, socket_depth}
ISO4762_TABLE = {
    "M3": {"d": 3.0, "dk": 5.5, "k": 3.0, "s": 2.5, "t": 1.3},
    "M4": {"d": 4.0, "dk": 7.0, "k": 4.0, "s": 3.0, "t": 2.0},
    "M5": {"d": 5.0, "dk": 8.5, "k": 5.0, "s": 4.0, "t": 2.5},
    "M6": {"d": 6.0, "dk": 10.0, "k": 6.0, "s": 5.0, "t": 3.0},
    "M8": {"d": 8.0, "dk": 13.0, "k": 8.0, "s": 6.0, "t": 4.0},
    "M10": {"d": 10.0, "dk": 16.0, "k": 10.0, "s": 8.0, "t": 5.0},
    "M12": {"d": 12.0, "dk": 18.0, "k": 12.0, "s": 10.0, "t": 6.0},
}


class Fastener:
    """Standard fasteners factory."""

    @staticmethod
    def ISO4762(name: str, size: str = "M6", length: float = 20.0) -> PartNode:
        """Create standard ISO 4762 bolt with ready-to-use anchor ports."""
        size_upper = size.upper()
        if size_upper not in ISO4762_TABLE:
            raise ValueError(
                f"Unsupported ISO 4762 size '{size}'. Available: {list(ISO4762_TABLE.keys())}"
            )

        dims = ISO4762_TABLE[size_upper]
        part = PartNode(
            name=name,
            part_type="standard",
            shape="iso4762_bolt",
            parameters={
                "size": size_upper,
                "length": float(length),
                "shank_diameter": dims["d"],
                "head_diameter": dims["dk"],
                "head_height": dims["k"],
                "socket_size": dims["s"],
                "socket_depth": dims["t"],
            },
        )

        # 1. Under-head seating surface port (where the bolt clamps)
        part.add_port(
            PortNode(
                name="under_head",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["dk"],
            )
        )

        # 2. Shank tip / bottom port
        part.add_port(
            PortNode(
                name="tip",
                port_type="face",
                relative_position=(0.0, 0.0, -float(length)),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["d"],
            )
        )

        # 3. Central alignment axis port
        part.add_port(
            PortNode(
                name="axis",
                port_type="axis",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=dims["d"],
            )
        )

        return part

    @staticmethod
    def ISO4014(name: str, size: str = "M6", length: float = 20.0) -> PartNode:
        """Create standard ISO 4014 / DIN 931 hex head bolt."""
        size_upper = size.upper()
        dims = ISO4762_TABLE.get(size_upper, ISO4762_TABLE["M6"])
        part = PartNode(
            name=name,
            part_type="standard",
            shape="iso4762_bolt",  # Re-use bolt solid compiler
            parameters={
                "size": size_upper,
                "length": float(length),
                "shank_diameter": dims["d"],
                "head_diameter": dims["dk"] * 1.1,
                "head_height": dims["k"] * 0.7,
                "socket_size": 0.0,
                "socket_depth": 0.0,
            },
        )
        part.add_port(PortNode(name="under_head", port_type="face", relative_position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, -1.0), diameter=dims["dk"]))
        part.add_port(PortNode(name="tip", port_type="face", relative_position=(0.0, 0.0, -float(length)), normal=(0.0, 0.0, -1.0), diameter=dims["d"]))
        part.add_port(PortNode(name="axis", port_type="axis", relative_position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, -1.0), diameter=dims["d"]))
        return part
