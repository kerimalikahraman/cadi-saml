"""
cadi_saml.std_parts.bearings
============================
Standard industrial ball bearings (Deep Groove Ball Bearings - SKF 608ZZ, 6000, 6200 series).
Provides precise inner/outer ring dimensions and shoulder ports.
"""

from __future__ import annotations

from typing import Any, Dict
from ..ir.nodes import PartNode, PortNode


# Standard Deep Groove Ball Bearing Dimensions (mm)
# Key: code -> {d: inner_dia, D: outer_dia, B: width}
BEARING_TABLE = {
    "608": {"d": 8.0, "D": 22.0, "B": 7.0},
    "608ZZ": {"d": 8.0, "D": 22.0, "B": 7.0},
    "6000": {"d": 10.0, "D": 26.0, "B": 8.0},
    "6001": {"d": 12.0, "D": 28.0, "B": 8.0},
    "6002": {"d": 15.0, "D": 32.0, "B": 9.0},
    "6200": {"d": 10.0, "D": 30.0, "B": 9.0},
    "6201": {"d": 12.0, "D": 32.0, "B": 10.0},
    "6202": {"d": 15.0, "D": 35.0, "B": 11.0},
    "6203": {"d": 17.0, "D": 40.0, "B": 12.0},
    "6204": {"d": 20.0, "D": 47.0, "B": 14.0},
    "6205": {"d": 25.0, "D": 52.0, "B": 15.0},
    "6206": {"d": 30.0, "D": 62.0, "B": 16.0},
}


class Bearing:
    """Standard bearing factory."""

    @staticmethod
    def SKF(name: str, code: str = "608ZZ") -> PartNode:
        """Create standard bearing with shaft hole and housing ports."""
        code_clean = code.upper()
        if code_clean not in BEARING_TABLE:
            raise ValueError(
                f"Unsupported bearing code '{code}'. Available: {list(BEARING_TABLE.keys())}"
            )

        dims = BEARING_TABLE[code_clean]
        part = PartNode(
            name=name,
            part_type="standard",
            shape="deep_groove_bearing",
            parameters={
                "code": code_clean,
                "inner_diameter": dims["d"],
                "outer_diameter": dims["D"],
                "width": dims["B"],
            },
        )

        # 1. Inner bore port (for shaft mounting)
        part.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, dims["B"] / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["d"],
            )
        )

        # 2. Outer cylinder port (for housing seating)
        part.add_port(
            PortNode(
                name="outer_rim",
                port_type="axis",
                relative_position=(0.0, 0.0, dims["B"] / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=dims["D"],
            )
        )

        # 3. Front face port
        part.add_port(
            PortNode(
                name="front_face",
                port_type="face",
                relative_position=(0.0, 0.0, dims["B"]),
                normal=(0.0, 0.0, 1.0),
            )
        )

        # 4. Back face port
        part.add_port(
            PortNode(
                name="back_face",
                port_type="face",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
            )
        )

        return part
