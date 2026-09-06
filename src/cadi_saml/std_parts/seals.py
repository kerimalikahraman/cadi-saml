"""
cadi_saml.std_parts.seals
=========================
Standard industrial elastomer seals:
- O-Rings (ISO 3601 / AS568)
- Radial Shaft Oil Seals (DIN 3760 Type A)
With semantic ports for shaft clearance, housing groove mounting, and face sealing.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from ..ir.nodes import PartNode, PortNode


# Common ISO 3601 / DIN 3771 O-Ring metric sizes (inner_dia, cross_section)
ORING_METRIC_TABLE: Dict[str, Dict[str, float]] = {
    "10x2": {"d1": 10.0, "d2": 2.0},
    "12x2.5": {"d1": 12.0, "d2": 2.5},
    "15x2.5": {"d1": 15.0, "d2": 2.5},
    "18x3": {"d1": 18.0, "d2": 3.0},
    "20x3": {"d1": 20.0, "d2": 3.0},
    "25x3": {"d1": 25.0, "d2": 3.0},
    "30x3.5": {"d1": 30.0, "d2": 3.5},
    "35x3.5": {"d1": 35.0, "d2": 3.5},
    "40x4": {"d1": 40.0, "d2": 4.0},
    "50x4": {"d1": 50.0, "d2": 4.0},
}

# Standard DIN 3760 Radial Shaft Oil Seal Dimensions (shaft d, housing D, width b)
SHAFT_SEAL_TABLE: Dict[str, Dict[str, float]] = {
    "15x30x7": {"d": 15.0, "D": 30.0, "b": 7.0},
    "17x35x7": {"d": 17.0, "D": 35.0, "b": 7.0},
    "20x35x7": {"d": 20.0, "D": 35.0, "b": 7.0},
    "20x40x7": {"d": 20.0, "D": 40.0, "b": 7.0},
    "25x42x7": {"d": 25.0, "D": 42.0, "b": 7.0},
    "25x52x7": {"d": 25.0, "D": 52.0, "b": 7.0},
    "30x52x8": {"d": 30.0, "D": 52.0, "b": 8.0},
    "35x62x8": {"d": 35.0, "D": 62.0, "b": 8.0},
    "40x62x8": {"d": 40.0, "D": 62.0, "b": 8.0},
}


class Seal:
    """Standard industrial sealing elements factory."""

    @staticmethod
    def oring(
        name: str,
        inner_dia: Optional[float] = None,
        cross_section: Optional[float] = None,
        standard_code: Optional[str] = None,
        material: str = "NBR70",
    ) -> PartNode:
        """
        Creates an elastomer O-ring solid (B-Rep Torus).
        Can be specified either by code (e.g. '25x3') or exact dimensions.
        """
        if standard_code:
            code_clean = standard_code.lower().replace(" ", "")
            if code_clean not in ORING_METRIC_TABLE:
                raise ValueError(
                    f"Unsupported O-ring standard code '{standard_code}'. Available: {list(ORING_METRIC_TABLE.keys())}"
                )
            d1 = ORING_METRIC_TABLE[code_clean]["d1"]
            d2 = ORING_METRIC_TABLE[code_clean]["d2"]
        else:
            if inner_dia is None or cross_section is None:
                raise ValueError("Must provide either standard_code or both inner_dia and cross_section.")
            d1 = float(inner_dia)
            d2 = float(cross_section)
            standard_code = f"ISO 3601 {d1:.1f}x{d2:.1f}"

        outer_dia = d1 + 2.0 * d2
        part = PartNode(
            name=name,
            part_type="standard",
            shape="oring",
            material=material,
            parameters={
                "inner_diameter": d1,
                "cross_section": d2,
                "outer_diameter": outer_dia,
                "standard_code": standard_code,
            },
        )

        # 1. Inner Bore Port (Shaft sealing contact)
        part.add_port(
            PortNode(
                name="bore",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=d1,
            )
        )

        # 2. Outer Perimeter Port (Housing groove contact)
        part.add_port(
            PortNode(
                name="groove",
                port_type="cylinder",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=outer_dia,
            )
        )

        # 3. Mid-plane center port
        part.add_port(
            PortNode(
                name="center",
                port_type="planar",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, 1.0),
                diameter=outer_dia,
            )
        )

        part.metadata = {
            "category": "Seal",
            "standard_code": standard_code,
            "material": material,
        }
        return part

    @staticmethod
    def radial_shaft_seal(
        name: str,
        shaft_dia: Optional[float] = None,
        outer_dia: Optional[float] = None,
        width: Optional[float] = None,
        code: Optional[str] = None,
        material: str = "NBR70",
    ) -> PartNode:
        """
        Creates a DIN 3760 rotary shaft lip seal.
        """
        if code:
            code_clean = code.lower().replace(" ", "")
            if code_clean not in SHAFT_SEAL_TABLE:
                raise ValueError(
                    f"Unsupported shaft seal code '{code}'. Available: {list(SHAFT_SEAL_TABLE.keys())}"
                )
            dims = SHAFT_SEAL_TABLE[code_clean]
            d = dims["d"]
            D = dims["D"]
            b = dims["b"]
            std_code = f"DIN 3760 {code}"
        else:
            if shaft_dia is None or outer_dia is None or width is None:
                raise ValueError("Must provide either code or shaft_dia, outer_dia, and width.")
            d = float(shaft_dia)
            D = float(outer_dia)
            b = float(width)
            std_code = f"DIN 3760 {int(d)}x{int(D)}x{int(b)}"

        part = PartNode(
            name=name,
            part_type="standard",
            shape="radial_shaft_seal",
            material=material,
            parameters={
                "shaft_diameter": d,
                "outer_diameter": D,
                "width": b,
                "standard_code": std_code,
            },
        )

        # 1. Shaft lip sealing contact (bore)
        part.add_port(
            PortNode(
                name="shaft_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, b / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=d,
            )
        )

        # 2. Housing bore seating surface (outer cylindrical face)
        part.add_port(
            PortNode(
                name="housing_seat",
                port_type="cylinder",
                relative_position=(0.0, 0.0, b / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=D,
            )
        )

        # 3. Front face (fluid/oil side)
        part.add_port(
            PortNode(
                name="front_face",
                port_type="planar",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=D,
            )
        )

        # 4. Rear face (air side)
        part.add_port(
            PortNode(
                name="rear_face",
                port_type="planar",
                relative_position=(0.0, 0.0, b),
                normal=(0.0, 0.0, 1.0),
                diameter=D,
            )
        )

        part.metadata = {
            "category": "Seal",
            "standard_code": std_code,
            "material": material,
        }
        return part
