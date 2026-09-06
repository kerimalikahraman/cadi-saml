"""
cadi_saml.std_parts.couplings
=============================
Standard shaft couplings:
- Rigid Flange Coupling (DIN 115)
- Flexible Jaw Coupling (Rotex / Lovejoy elastomer spider type)
- Oldham Coupling (Parallel misalignment type)
Equipped with dual shaft ports and torque transmission mates.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional
from ..ir.nodes import PartNode, PortNode


# Common flexible jaw coupling standard size parameters
JAW_COUPLING_TABLE: Dict[str, Dict[str, float]] = {
    "size_19": {"d_min": 6.0, "d_max": 19.0, "D": 40.0, "L": 66.0},
    "size_24": {"d_min": 10.0, "d_max": 24.0, "D": 55.0, "L": 78.0},
    "size_28": {"d_min": 14.0, "d_max": 28.0, "D": 65.0, "L": 90.0},
    "size_38": {"d_min": 18.0, "d_max": 38.0, "D": 80.0, "L": 114.0},
}


class Coupling:
    """Standard mechanical shaft couplings factory."""

    @staticmethod
    def rigid_flange(
        name: str,
        shaft1_dia: float = 20.0,
        shaft2_dia: float = 20.0,
        outer_dia: float = 75.0,
        length: float = 60.0,
        flange_thickness: float = 12.0,
        bolt_count: int = 4,
        bolt_pcd: float = 55.0,
        bolt_dia: float = 8.0,
        material: str = "C45E",
    ) -> PartNode:
        """
        Creates a DIN 115 heavy-duty rigid flange shaft coupling.
        Features counter-bored bolt holes and precision split/sleeve hubs.
        """
        from ..core.exceptions import CADISpecificationError
        s1 = float(shaft1_dia)
        s2 = float(shaft2_dia)
        od = float(outer_dia)
        bd = float(bolt_dia)
        pcd = float(bolt_pcd)
        if s1 >= od or s2 >= od:
            raise CADISpecificationError(
                f"Shaft diameter ({max(s1, s2)} mm) cannot be >= coupling outer diameter ({od} mm).",
                parameter="shaft_diameter",
                suggested_fix=f"Specify outer diameter at least twice the shaft diameter (e.g. outer_diameter={max(s1, s2) * 2:.1f})."
            )
        if bd >= (od - pcd) or bd >= pcd:
            raise CADISpecificationError(
                f"Bolt diameter ({bd} mm) is excessively large for flange envelope (OD: {od} mm, PCD: {pcd} mm).",
                parameter="bolt_diameter",
                suggested_fix="Choose a standard DIN 115 bolt size (e.g. bolt_dia=8.0 mm)."
            )
        part = PartNode(
            name=name,
            part_type="standard",
            shape="rigid_flange_coupling",
            material=material,
            parameters={
                "shaft1_diameter": float(shaft1_dia),
                "shaft2_diameter": float(shaft2_dia),
                "outer_diameter": float(outer_dia),
                "length": float(length),
                "flange_thickness": float(flange_thickness),
                "bolt_count": int(bolt_count),
                "bolt_pcd": float(bolt_pcd),
                "bolt_dia": float(bolt_dia),
                "hub_diameter": float(outer_dia * 0.6),
            },
        )

        # 1. Shaft 1 Input Bore Port (at z=0 facing -Z)
        part.add_port(
            PortNode(
                name="hub1_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=float(shaft1_dia),
            )
        )

        # 2. Shaft 2 Output Bore Port (at z=length facing +Z)
        part.add_port(
            PortNode(
                name="hub2_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, float(length)),
                normal=(0.0, 0.0, 1.0),
                diameter=float(shaft2_dia),
            )
        )

        # 3. Flange interface plane (at mid-length)
        part.add_port(
            PortNode(
                name="flange_interface",
                port_type="planar",
                relative_position=(0.0, 0.0, float(length) / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=float(outer_dia),
            )
        )

        part.metadata = {
            "category": "Coupling",
            "standard_code": f"DIN 115 d1={int(shaft1_dia)}/d2={int(shaft2_dia)}",
            "material": material,
        }
        return part

    @staticmethod
    def flexible_jaw(
        name: str,
        shaft1_dia: float = 14.0,
        shaft2_dia: float = 14.0,
        outer_dia: float = 55.0,
        length: float = 78.0,
        size_code: Optional[str] = None,
        spider_material: str = "Polyurethane_92A",
        material: str = "Al7075_T6",
    ) -> PartNode:
        """
        Creates a high-precision flexible jaw / spider coupling (Rotex type).
        Dampens torsional vibration and accommodates angular/axial shaft misalignments.
        """
        if size_code:
            code_clean = size_code.lower()
            if code_clean not in JAW_COUPLING_TABLE:
                raise ValueError(
                    f"Unsupported jaw coupling size '{size_code}'. Available: {list(JAW_COUPLING_TABLE.keys())}"
                )
            dims = JAW_COUPLING_TABLE[code_clean]
            outer_dia = dims["D"]
            length = dims["L"]
            std_code = f"Rotex {size_code.upper()} d1={int(shaft1_dia)}/d2={int(shaft2_dia)}"
        else:
            std_code = f"Jaw Coupling OD={int(outer_dia)} L={int(length)}"

        part = PartNode(
            name=name,
            part_type="standard",
            shape="flexible_jaw_coupling",
            material=material,
            parameters={
                "shaft1_diameter": float(shaft1_dia),
                "shaft2_diameter": float(shaft2_dia),
                "outer_diameter": float(outer_dia),
                "length": float(length),
                "spider_thickness": float(length * 0.22),
                "spider_material": spider_material,
            },
        )

        # Hub 1 Bore Port
        part.add_port(
            PortNode(
                name="hub1_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=float(shaft1_dia),
            )
        )

        # Hub 2 Bore Port
        part.add_port(
            PortNode(
                name="hub2_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, float(length)),
                normal=(0.0, 0.0, 1.0),
                diameter=float(shaft2_dia),
            )
        )

        # Coupling Center Port
        part.add_port(
            PortNode(
                name="center",
                port_type="planar",
                relative_position=(0.0, 0.0, float(length) / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=float(outer_dia),
            )
        )

        part.metadata = {
            "category": "Coupling",
            "standard_code": std_code,
            "material": material,
        }
        return part

    @staticmethod
    def oldham(
        name: str,
        shaft1_dia: float = 12.0,
        shaft2_dia: float = 12.0,
        outer_dia: float = 35.0,
        length: float = 45.0,
        material: str = "Al6061",
    ) -> PartNode:
        """
        Creates an Oldham coupling for handling pure parallel radial offset between shafts.
        """
        std_code = f"Oldham OD={int(outer_dia)} d1={int(shaft1_dia)}/d2={int(shaft2_dia)}"
        part = PartNode(
            name=name,
            part_type="standard",
            shape="oldham_coupling",
            material=material,
            parameters={
                "shaft1_diameter": float(shaft1_dia),
                "shaft2_diameter": float(shaft2_dia),
                "outer_diameter": float(outer_dia),
                "length": float(length),
                "disc_thickness": float(length * 0.25),
            },
        )

        # Hub 1 & 2 Bore Ports
        part.add_port(
            PortNode(
                name="hub1_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, 0.0),
                normal=(0.0, 0.0, -1.0),
                diameter=float(shaft1_dia),
            )
        )
        part.add_port(
            PortNode(
                name="hub2_bore",
                port_type="hole",
                relative_position=(0.0, 0.0, float(length)),
                normal=(0.0, 0.0, 1.0),
                diameter=float(shaft2_dia),
            )
        )
        part.add_port(
            PortNode(
                name="center",
                port_type="planar",
                relative_position=(0.0, 0.0, float(length) / 2.0),
                normal=(0.0, 0.0, 1.0),
                diameter=float(outer_dia),
            )
        )

        part.metadata = {
            "category": "Coupling",
            "standard_code": std_code,
            "material": material,
        }
        return part


# Backward-compatible and macro alias
CouplingBuilder = Coupling

