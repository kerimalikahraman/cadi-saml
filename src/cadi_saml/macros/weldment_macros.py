"""
cadi_saml.macros.weldment_macros
================================
Structural weldment accessories with Zero-Coordinate Semantic Placement:
- Gusset reinforcement plates placed between two connected profiles (e.g. between=('beam', 'column'))
- Profile end caps snapped directly to profile extremities (e.g. on_profile='column_1', side='top')
Equipped with semantic weld faces and mounting ports.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.assembly import Assembly


def add_gusset(
    assembly: "Assembly",
    name: str,
    between: Optional[Tuple[str, str]] = None,
    d1: Optional[float] = None,
    d2: Optional[float] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    thickness: float = 4.0,
    chamfer: Optional[float] = None,
    chamfer_size: Optional[float] = None,
    origin: Optional[Tuple[float, float, float]] = None,
    normal: Optional[Tuple[float, float, float]] = None,
    material: str = "S355J2",
) -> Dict[str, Any]:
    """
    Creates a structural reinforcement gusset plate with corner weld relief chamfer.
    Supports ZERO-COORDINATE placement between two profiles via between=('part1', 'part2').
    """
    dim_1 = float(d1 if d1 is not None else (width if width is not None else 50.0))
    dim_2 = float(d2 if d2 is not None else (height if height is not None else 50.0))
    raw_ch = float(chamfer if chamfer is not None else (chamfer_size if chamfer_size is not None else 10.0))

    # Automatic zero-coordinate resolution from connected profiles
    resolved_origin = origin or (0.0, 0.0, 0.0)
    resolved_normal = normal or (0.0, 0.0, 1.0)

    if between and len(between) == 2:
        p1_name, p2_name = between
        if p1_name in assembly._parts and p2_name in assembly._parts:
            p1_ref = assembly._parts[p1_name]
            p2_ref = assembly._parts[p2_name]
            o1 = p1_ref.parameters.get("origin", (0.0, 0.0, 0.0))
            o2 = p2_ref.parameters.get("origin", (0.0, 0.0, 0.0))
            # Corner intersection heuristic between orthogonal structural elements
            resolved_origin = (max(o1[0], o2[0]), max(o1[1], o2[1]), min(o1[2], o2[2]))
            resolved_normal = (0.0, 1.0, 0.0) if abs(o1[1] - o2[1]) < 1e-3 else (0.0, 0.0, 1.0)

    # Define 2D polygon profile with corner relief
    ch = min(raw_ch, min(dim_1, dim_2) * 0.4)
    points = [
        (0.0, ch),
        (0.0, dim_2),
        (dim_1, 0.0),
        (ch, 0.0),
    ]

    from ..ir.nodes import CrossSection
    cs = CrossSection(
        shape="polygon",
        parameters={"points": points},
        center=(resolved_origin[0], resolved_origin[1], resolved_origin[2]),
        normal=resolved_normal,
    )

    p2 = (resolved_origin[0], resolved_origin[1], resolved_origin[2] + thickness)
    cs2 = CrossSection(
        shape="polygon",
        parameters={"points": points},
        center=p2,
        normal=resolved_normal,
    )

    part_ref = assembly.add_loft(name=name, sections=[cs, cs2])
    part_ref.set_appearance(color=(0.3, 0.3, 0.35), material=material)

    part_ref.add_port(
        name="weld_face_vertical",
        port_type="planar",
        position=(resolved_origin[0], resolved_origin[1] + dim_2 / 2.0, resolved_origin[2] + thickness / 2.0),
        normal=(-1.0, 0.0, 0.0),
        diameter=dim_2,
    )
    part_ref.add_port(
        name="weld_face_horizontal",
        port_type="planar",
        position=(resolved_origin[0] + dim_1 / 2.0, resolved_origin[1], resolved_origin[2] + thickness / 2.0),
        normal=(0.0, -1.0, 0.0),
        diameter=dim_1,
    )

    return {
        "name": name,
        "d1_mm": dim_1,
        "d2_mm": dim_2,
        "thickness_mm": thickness,
        "chamfer_mm": ch,
        "material": material,
        "between_parts": between,
        "part_reference": part_ref,
    }


def add_end_cap(
    assembly: "Assembly",
    name: str,
    on_profile: Optional[str] = None,
    profile_part: Optional[str] = None,
    side: str = "end",
    width_x: Optional[float] = None,
    width_y: Optional[float] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    thickness: float = 3.0,
    corner_radius: float = 2.0,
    origin: Optional[Tuple[float, float, float]] = None,
    material: str = "Al6061",
) -> Dict[str, Any]:
    """
    Creates a protective structural end cap.
    Supports ZERO-COORDINATE placement directly on profile ends via on_profile='col_1'.
    """
    target_prof = on_profile or profile_part
    wx = float(width_x if width_x is not None else (width if width is not None else 40.0))
    wy = float(width_y if width_y is not None else (height if height is not None else 40.0))
    resolved_origin = origin or (0.0, 0.0, 0.0)

    if target_prof and target_prof in assembly._parts:
        p_ref = assembly._parts[target_prof]
        p_params = p_ref.node.parameters
        wx = float(p_params.get("width_x") or p_params.get("width") or p_params.get("length") or wx)
        wy = float(p_params.get("width_y") or p_params.get("height") or wy)
        prof_origin = p_params.get("origin", (0.0, 0.0, 0.0))
        prof_len = float(p_params.get("length") or p_params.get("height") or 100.0)

        # Snap to end face along dominant extrusion axis Z or X
        if side.lower() in ("end", "top"):
            resolved_origin = (prof_origin[0], prof_origin[1], prof_origin[2] + prof_len)
        else:
            resolved_origin = (prof_origin[0], prof_origin[1], prof_origin[2] - thickness)

    cap_ref = assembly.add_box(
        name=name,
        length=wx,
        width=wy,
        height=thickness,
        origin=(resolved_origin[0] - wx / 2.0, resolved_origin[1] - wy / 2.0, resolved_origin[2]),
    )
    cap_ref.set_appearance(color=(0.15, 0.15, 0.18), material=material)

    if corner_radius > 0.1:
        cap_ref.add_fillet(radius=corner_radius, edges="vertical")

    cap_ref.add_port(
        name="mount_face",
        port_type="planar",
        position=(resolved_origin[0], resolved_origin[1], resolved_origin[2]),
        normal=(0.0, 0.0, -1.0),
        diameter=min(wx, wy),
    )

    return {
        "name": name,
        "width_x_mm": wx,
        "width_y_mm": wy,
        "thickness_mm": thickness,
        "corner_radius_mm": corner_radius,
        "on_profile": target_prof,
        "material": material,
        "part_reference": cap_ref,
    }
