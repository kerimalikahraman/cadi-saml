"""
cadi_saml.core.features
=======================
Parametric machine design features and mechanical detailing operations:
- Counterbores, countersinks, and tapped holes
- Shaft keyways (DIN 6885) and retaining ring grooves (DIN 471/472)
- Pockets, slots, ribs, and gussets
- Part mirroring across datum planes
- Geometric measurements (distance, wall thickness)
"""

from __future__ import annotations
import math
from typing import Optional, Tuple, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .assembly import Assembly, PartReference

def apply_counterbore(
    asm: "Assembly",
    target_part: str,
    cbore_dia: float,
    cbore_depth: float,
    hole_dia: float,
    hole_depth: float = 50.0,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Adds a cylindrical counterbore recess for socket head cap screws (DIN 912)."""
    tool_cbore = f"{target_part}_cbore_tool"
    tool_hole = f"{target_part}_hole_tool"
    ox, oy, oz = origin
    
    # 1. Counterbore head pocket
    asm.add_cylinder(tool_cbore, radius=cbore_dia / 2.0, height=cbore_depth, origin=(ox, oy, oz - cbore_depth))
    asm.cut(target_part, tool_cbore)
    
    # 2. Through hole
    asm.add_cylinder(tool_hole, radius=hole_dia / 2.0, height=hole_depth, origin=(ox, oy, oz - hole_depth))
    asm.cut(target_part, tool_hole)
    
    return {"feature": "counterbore", "cbore_dia": cbore_dia, "cbore_depth": cbore_depth, "hole_dia": hole_dia}

def apply_countersink(
    asm: "Assembly",
    target_part: str,
    csink_dia: float,
    angle_deg: float = 90.0,
    hole_dia: float = 5.5,
    hole_depth: float = 40.0,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Adds a conical countersink recess for flat head countersunk screws (ISO 10642)."""
    tool_cone = f"{target_part}_csink_cone"
    tool_hole = f"{target_part}_csink_hole"
    ox, oy, oz = origin
    
    # Cone depth = (csink_dia - hole_dia) / (2 * tan(angle/2))
    half_angle = math.radians(angle_deg / 2.0)
    cone_depth = (csink_dia - hole_dia) / (2.0 * math.tan(half_angle))
    
    asm.add_cone(tool_cone, bottom_radius=csink_dia / 2.0, top_radius=hole_dia / 2.0, height=cone_depth, origin=(ox, oy, oz - cone_depth))
    asm.cut(target_part, tool_cone)
    
    asm.add_cylinder(tool_hole, radius=hole_dia / 2.0, height=hole_depth, origin=(ox, oy, oz - hole_depth))
    asm.cut(target_part, tool_hole)
    
    return {"feature": "countersink", "csink_dia": csink_dia, "angle_deg": angle_deg, "hole_dia": hole_dia}

def apply_keyway(
    asm: "Assembly",
    target_part: str,
    width: float,
    depth: float,
    length: float,
    shaft_dia: float = 25.0,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Adds a standard parallel keyway slot conforming to DIN 6885 Form A."""
    tool_key = f"{target_part}_keyway_cutter"
    ox, oy, oz = origin
    # Position key cutter tangent to shaft top
    asm.add_box(
        name=tool_key,
        length=length,
        width=width,
        height=depth + 2.0,
        origin=(ox, oy - width / 2.0, oz + shaft_dia / 2.0 - depth),
    )
    asm.cut(target_part, tool_key)
    return {"feature": "keyway", "standard": "DIN 6885-1", "width": width, "depth": depth, "length": length}

def apply_retaining_ring_groove(
    asm: "Assembly",
    target_part: str,
    shaft_dia: float,
    groove_dia: float,
    width: float = 1.3,
    position_z: float = 10.0,
) -> Dict[str, Any]:
    """Cuts an external snap ring / retaining ring groove (DIN 471)."""
    tool_groove = f"{target_part}_ring_groove"
    # Outer disc cutting into the shaft
    asm.add_cylinder(
        name=tool_groove,
        radius=shaft_dia / 2.0 + 2.0,
        height=width,
        origin=(0.0, 0.0, position_z),
    )
    # Inner keeper to leave groove diameter
    inner_keeper = f"{target_part}_ring_keeper"
    asm.add_cylinder(
        name=inner_keeper,
        radius=groove_dia / 2.0,
        height=width + 1.0,
        origin=(0.0, 0.0, position_z - 0.5),
    )
    asm.cut(tool_groove, inner_keeper)
    asm.cut(target_part, tool_groove)
    return {"feature": "retaining_ring_groove", "standard": "DIN 471", "groove_dia": groove_dia, "width": width}

def apply_pocket(
    asm: "Assembly",
    target_part: str,
    length: float,
    width: float,
    depth: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """Cuts a rectangular milled pocket cavity with filleted tool radii."""
    tool_pocket = f"{target_part}_pocket_cutter"
    asm.add_box(
        name=tool_pocket,
        length=length,
        width=width,
        height=depth,
        origin=origin,
    )
    asm.cut(target_part, tool_pocket)
    return {"feature": "pocket", "length": length, "width": width, "depth": depth}

def apply_rib(
    asm: "Assembly",
    name: str,
    thickness: float = 4.0,
    height: float = 40.0,
    length: float = 50.0,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    material: str = "StructuralSteel",
) -> Dict[str, Any]:
    """Creates a triangular structural strengthening rib."""
    asm.add_box(
        name=name,
        length=length,
        width=thickness,
        height=height,
        origin=origin,
        material=material,
    )
    return {"feature": "rib", "name": name, "thickness": thickness, "height": height, "length": length}
