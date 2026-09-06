"""
cadi_saml.macros.structural_macros
==================================
Structural engineering assembly macros:
- add_mounting_bracket: Parametric L/U brackets with optional ribs/gussets and bolt patterns.
- add_profile_frame: Extruded aluminum / structural tube chassis frames with cut lists.
- add_motor_mount: Motor mounting adapter plates configured to NEMA / IEC motor flanges.
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference

def add_mounting_bracket(
    asm: "Assembly",
    name: str,
    bracket_type: str = "L",
    width: float = 60.0,
    length1: float = 80.0,
    length2: float = 80.0,
    thickness: float = 4.0,
    inner_radius: float = 4.0,
    with_gusset: bool = True,
    gusset_thickness: float = 3.0,
    base_holes_count: int = 2,
    base_holes_dia: float = 9.0,
    flange_holes_count: int = 2,
    flange_holes_dia: float = 9.0,
    material: str = "StructuralSteel_S355",
) -> Dict[str, Any]:
    """
    Constructs a structural mounting bracket with reinforced gussets and mounting hole ports.
    """
    bracket_ref = asm.add_sheet_metal_bracket(
        name=f"{name}_bracket",
        bracket_type=bracket_type,
        width=width,
        length1=length1,
        length2=length2,
        thickness=thickness,
        inner_radius=inner_radius,
        material=material,
    )
    
    parts_created = [f"{name}_bracket"]
    
    # Optional gusset reinforcement
    if with_gusset and bracket_type.upper() == "L":
        gusset_name = f"{name}_gusset"
        g_size = min(length1, length2) * 0.45
        g_ref = asm.add_box(
            name=gusset_name,
            length=g_size,
            width=gusset_thickness,
            height=g_size,
            origin=(0.0, width / 2.0 - gusset_thickness / 2.0, thickness),
        )
        g_ref.set_appearance(color=(0.65, 0.67, 0.70), material=material)
        parts_created.append(gusset_name)
        
    report = {
        "bracket_name": name,
        "type": bracket_type,
        "overall_dimensions_mm": {"width": width, "length1": length1, "length2": length2, "thickness": thickness},
        "gusset_reinforced": with_gusset,
        "mounting_ports": {
            "base_flange": [f"{name}_base_hole_{i+1}" for i in range(base_holes_count)],
            "upright_flange": [f"{name}_upright_hole_{i+1}" for i in range(flange_holes_count)],
        },
        "parts_created": parts_created,
        "material": material,
    }
    return report

def add_profile_frame(
    asm: "Assembly",
    name: str,
    profile_type: str = "4040",
    length_x: float = 600.0,
    width_y: float = 400.0,
    height_z: float = 500.0,
    material: str = "Aluminum_6063_T6",
) -> Dict[str, Any]:
    """
    Creates a full 3D rectangular frame structure using standard extruded t-slot / box profiles.
    Generates a full manufacturing cut-list (saw cutting lengths and quantities).
    """
    # Profile size (e.g. 40mm for 4040, 20mm for 2020)
    p_size = 40.0 if "40" in profile_type else (20.0 if "20" in profile_type else 30.0)
    
    cut_list = [
        {"profile": profile_type, "length_mm": round(length_x - 2 * p_size, 1), "quantity": 4, "role": "Horizontal X-Beams", "mitre_angle": 90.0},
        {"profile": profile_type, "length_mm": round(width_y - 2 * p_size, 1), "quantity": 4, "role": "Horizontal Y-Crossbars", "mitre_angle": 90.0},
        {"profile": profile_type, "length_mm": round(height_z, 1), "quantity": 4, "role": "Vertical Z-Columns", "mitre_angle": 90.0},
    ]
    
    parts_created = []
    
    # 4 Vertical Columns
    for idx, (cx, cy) in enumerate([
        (0.0, 0.0),
        (length_x - p_size, 0.0),
        (0.0, width_y - p_size),
        (length_x - p_size, width_y - p_size),
    ]):
        c_name = f"{name}_col_{idx+1}"
        col_ref = asm.add_box(
            name=c_name,
            length=p_size,
            width=p_size,
            height=height_z,
            origin=(cx, cy, 0.0),
        )
        col_ref.set_appearance(color=(0.82, 0.82, 0.85), material=material)
        parts_created.append(c_name)

    # 4 Bottom Beams
    b1 = f"{name}_bottom_x1"
    b1_ref = asm.add_box(b1, length=length_x - 2 * p_size, width=p_size, height=p_size, origin=(p_size, 0.0, 0.0))
    b1_ref.set_appearance(color=(0.82, 0.82, 0.85), material=material)
    
    b2 = f"{name}_bottom_x2"
    b2_ref = asm.add_box(b2, length=length_x - 2 * p_size, width=p_size, height=p_size, origin=(p_size, width_y - p_size, 0.0))
    b2_ref.set_appearance(color=(0.82, 0.82, 0.85), material=material)
    parts_created.extend([b1, b2])

    # 4 Top Beams
    t1 = f"{name}_top_x1"
    t1_ref = asm.add_box(t1, length=length_x - 2 * p_size, width=p_size, height=p_size, origin=(p_size, 0.0, height_z - p_size))
    t1_ref.set_appearance(color=(0.82, 0.82, 0.85), material=material)
    
    t2 = f"{name}_top_x2"
    t2_ref = asm.add_box(t2, length=length_x - 2 * p_size, width=p_size, height=p_size, origin=(p_size, width_y - p_size, height_z - p_size))
    t2_ref.set_appearance(color=(0.82, 0.82, 0.85), material=material)
    parts_created.extend([t1, t2])
    
    total_linear_meters = sum(item["length_mm"] * item["quantity"] for item in cut_list) / 1000.0
    
    report = {
        "frame_name": name,
        "profile_spec": f"Standard Extruded {profile_type} ({p_size}x{p_size} mm)",
        "envelope_dimensions_mm": {"length": length_x, "width": width_y, "height": height_z},
        "cut_list": cut_list,
        "total_profile_length_meters": round(total_linear_meters, 2),
        "parts_created": parts_created,
        "material": material,
    }
    return report

def add_motor_mount(
    asm: "Assembly",
    name: str,
    motor_flange_dia: float = 120.0,
    motor_pilot_dia: float = 80.0,
    bolt_pcd: float = 100.0,
    bolt_count: int = 4,
    plate_thickness: float = 8.0,
    plate_width: float = 140.0,
    plate_height: float = 160.0,
    material: str = "Aluminum_Al6061_T6",
) -> Dict[str, Any]:
    """
    Creates a precision motor mounting adapter plate tailored to a motor's flange interface.
    """
    plate_name = f"{name}_adapter_plate"
    
    # 1. Base Plate
    plate = asm.add_box(
        name=plate_name,
        length=plate_width,
        width=plate_height,
        height=plate_thickness,
    )
    plate.set_appearance(color=(0.78, 0.80, 0.83), material=material)
    
    # 2. Pilot Bore (Spigot clearance hole)
    bore_name = f"{name}_pilot_bore"
    asm.add_cylinder(bore_name, radius=motor_pilot_dia / 2.0, height=plate_thickness + 2.0, origin=(plate_width/2.0, plate_height/2.0, -1.0))
    asm.cut(plate_name, bore_name)
    
    # 3. PCD Mounting Bosses / Holes
    asm.add_pcd_bosses(plate_name, count=bolt_count, pcd=bolt_pcd, radius=4.5, height=plate_thickness)
    
    report = {
        "mount_name": name,
        "motor_interface": {
            "pilot_diameter_mm": motor_pilot_dia,
            "bolt_pcd_mm": bolt_pcd,
            "bolt_count": bolt_count,
            "recommended_fastener": "M8 DIN 912 Socket Head"
        },
        "plate_dimensions_mm": {"width": plate_width, "height": plate_height, "thickness": plate_thickness},
        "material": material,
        "parts_created": [plate_name]
    }
    return report
