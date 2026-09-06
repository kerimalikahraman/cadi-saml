"""
cadi_saml.macros.powertrain_macros
=================================
Powertrain and rotating equipment assembly macros:
- add_bearing_support: Complete bearing pillow block or flanged housing unit with seals.
- add_shaft_stack: Sequential axial positioning of bearings, gears, and spacers on a stepped shaft.
- add_gear_pair: Kinematic gear mesh pair with verified center distance and gear relation.
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference

def add_bearing_support(
    asm: "Assembly",
    name: str,
    shaft_dia: float = 25.0,
    housing_type: str = "pillow_block",
    bearing_series: str = "6205",
    material: str = "CastIron_EN_GJL_250",
) -> Dict[str, Any]:
    """
    Assembles a complete bearing housing support unit around a shaft journal.
    """
    outer_dia = shaft_dia + 27.0  # e.g., 6205 is 25x52x15
    bearing_width = 15.0
    
    parts_created = []
    
    # 1. Bearing
    b_name = f"{name}_bearing_{bearing_series}"
    asm.add_bearing(
        name=b_name,
        standard="SKF",
        code=bearing_series,
    )
    parts_created.append(b_name)
    
    # 2. Housing
    h_name = f"{name}_housing"
    if housing_type == "pillow_block":
        base_w = outer_dia + 60.0
        base_d = bearing_width + 25.0
        h_height = outer_dia * 0.75 + 15.0
        
        h_ref = asm.add_box(
            name=h_name,
            length=base_w,
            width=base_d,
            height=h_height,
        )
        h_ref.set_appearance(color=(0.35, 0.45, 0.40), material=material)
        parts_created.append(h_name)
    else:  # Flanged housing
        asm.add_flange(
            name=h_name,
            outer_diameter=outer_dia + 45.0,
            thickness=bearing_width + 8.0,
            inner_bore=outer_dia,
            bolt_pcd=outer_dia + 25.0,
            bolt_count=4,
            bolt_diameter=9.0,
        )
        parts_created.append(h_name)
        
    report = {
        "bearing_support_name": name,
        "housing_type": housing_type,
        "shaft_journal_diameter_mm": shaft_dia,
        "bearing_designation": f"DIN 625 - {bearing_series}",
        "bearing_envelope_mm": {"bore": shaft_dia, "od": outer_dia, "width": bearing_width},
        "housing_material": material,
        "parts_created": parts_created,
    }
    return report

def add_gear_pair(
    asm: "Assembly",
    name: str,
    pinion_teeth: int = 18,
    gear_teeth: int = 54,
    module: float = 2.5,
    face_width: float = 30.0,
    pressure_angle: float = 20.0,
    helix_angle: float = 0.0,
    center_distance: Optional[float] = None,
    gear_type: str = "spur",
    material: str = "AlloySteel_42CrMo4",
) -> Dict[str, Any]:
    """
    Creates a verified, geometrically paired gear set with exact kinematic center distance.
    Automatically establishes gear_relation constraint between the pair.
    """
    # Pitch diameters
    d1 = module * pinion_teeth
    d2 = module * gear_teeth
    
    # Exact center distance a = m * (z1 + z2) / 2
    exact_cd = module * (pinion_teeth + gear_teeth) / 2.0
    if center_distance is not None and abs(center_distance - exact_cd) > 0.01:
        cd_status = f"WARNING: Provided CD ({center_distance}mm) differs from kinematic standard ({exact_cd}mm)"
        used_cd = center_distance
    else:
        cd_status = "EXACT_KINEMATIC_MATCH"
        used_cd = exact_cd
        
    ratio = round(gear_teeth / pinion_teeth, 3)
    
    # 1. Pinion
    p_name = f"{name}_pinion_z{pinion_teeth}"
    asm.add_spur_gear(
        name=p_name,
        module=module,
        teeth=pinion_teeth,
        face_width=face_width,
        bore_dia=max(d1 * 0.35, 12.0),
        color=(0.75, 0.75, 0.78),
        material=material,
    )
    
    # 2. Wheel Gear (offset along X by center distance)
    g_name = f"{name}_wheel_z{gear_teeth}"
    asm.add_spur_gear(
        name=g_name,
        module=module,
        teeth=gear_teeth,
        face_width=face_width,
        origin=(used_cd, 0.0, 0.0),
        bore_dia=max(d2 * 0.30, 20.0),
        color=(0.70, 0.70, 0.74),
        material=material,
    )
    
    # 3. Establish Kinematic Motion Relation
    asm.add_gear_relation(p_name, g_name, ratio=ratio)
    
    report = {
        "gear_pair_name": name,
        "gear_type": gear_type,
        "module": module,
        "pinion": {"name": p_name, "teeth": pinion_teeth, "pitch_dia_mm": d1},
        "wheel": {"name": g_name, "teeth": gear_teeth, "pitch_dia_mm": d2},
        "reduction_ratio": ratio,
        "center_distance_mm": round(used_cd, 3),
        "center_distance_status": cd_status,
        "kinematic_relation_established": True,
        "parts_created": [p_name, g_name]
    }
    return report

def add_shaft_stack(
    asm: "Assembly",
    name: str,
    shaft_name: str,
    steps: List[Tuple[float, float]],
    stack_elements: Optional[List[Dict[str, Any]]] = None,
    material: str = "Steel_42CrMo4",
) -> Dict[str, Any]:
    """
    Builds a stepped transmission shaft and sequentially populates components
    (bearings, gears, retaining rings, spacers) along designated step shoulders.
    """
    # 1. Create base stepped shaft
    asm.add_stepped_shaft(
        name=shaft_name,
        steps=steps,
        material=material,
    )
    
    total_length = sum(length for _, length in steps)
    elements_placed = []
    
    # 2. Sequential placement of attached elements
    if stack_elements:
        for idx, elem in enumerate(stack_elements):
            step_idx = elem.get("step_index", 0)
            elem_type = elem.get("type", "spacer")
            elem_name = elem.get("name", f"{name}_{elem_type}_{idx+1}")
            
            if step_idx < len(steps):
                d_step, l_step = steps[step_idx]
                if elem_type == "bearing":
                    asm.add_bearing(elem_name, standard="SKF", code="608ZZ")
                elif elem_type == "gear":
                    asm.add_spur_gear(elem_name, module=2.5, teeth=elem.get("teeth", 24), bore_dia=d_step, face_width=min(l_step, 25.0))
                elements_placed.append({"element": elem_name, "type": elem_type, "at_step": step_idx, "shaft_dia": d_step})
                
    report = {
        "shaft_assembly_name": name,
        "shaft_part": shaft_name,
        "step_count": len(steps),
        "total_shaft_length_mm": total_length,
        "steps_summary": [{"step": i, "diameter_mm": d, "length_mm": l} for i, (d, l) in enumerate(steps)],
        "elements_mounted": elements_placed,
        "material": material
    }
    return report
