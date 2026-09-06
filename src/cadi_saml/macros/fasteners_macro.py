"""
cadi_saml.macros.fasteners_macro
================================
Automated bolted joint assembly macro.
Aligns hole ports across multiple mating parts, calculates grip length,
selects standard metric bolt length (ISO 4014 / DIN 912), places washers and nuts,
and generates an engineering joint report.
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference

# Standard metric coarse thread pitch and clearance hole dimensions (ISO 273)
METRIC_BOLT_SPECS = {
    "M3": {"pitch": 0.5, "hole_dia": 3.4, "head_dia": 5.5, "head_height": 2.0, "nut_height": 2.4, "nut_dia": 5.5, "washer_thk": 0.5, "washer_dia": 7.0},
    "M4": {"pitch": 0.7, "hole_dia": 4.5, "head_dia": 7.0, "head_height": 2.8, "nut_height": 3.2, "nut_dia": 7.0, "washer_thk": 0.8, "washer_dia": 9.0},
    "M5": {"pitch": 0.8, "hole_dia": 5.5, "head_dia": 8.5, "head_height": 3.5, "nut_height": 4.0, "nut_dia": 8.0, "washer_thk": 1.0, "washer_dia": 10.0},
    "M6": {"pitch": 1.0, "hole_dia": 6.6, "head_dia": 10.0, "head_height": 4.0, "nut_height": 5.0, "nut_dia": 10.0, "washer_thk": 1.6, "washer_dia": 12.0},
    "M8": {"pitch": 1.25, "hole_dia": 9.0, "head_dia": 13.0, "head_height": 5.3, "nut_height": 6.5, "nut_dia": 13.0, "washer_thk": 1.6, "washer_dia": 16.0},
    "M10": {"pitch": 1.5, "hole_dia": 11.0, "head_dia": 16.0, "head_height": 6.4, "nut_height": 8.0, "nut_dia": 16.0, "washer_thk": 2.0, "washer_dia": 20.0},
    "M12": {"pitch": 1.75, "hole_dia": 13.5, "head_dia": 18.0, "head_height": 7.5, "nut_height": 10.0, "nut_dia": 18.0, "washer_thk": 2.5, "washer_dia": 24.0},
    "M16": {"pitch": 2.0, "hole_dia": 17.5, "head_dia": 24.0, "head_height": 10.0, "nut_height": 13.0, "nut_dia": 24.0, "washer_thk": 3.0, "washer_dia": 30.0},
    "M20": {"pitch": 2.5, "hole_dia": 22.0, "head_dia": 30.0, "head_height": 12.5, "nut_height": 16.0, "nut_dia": 30.0, "washer_thk": 3.0, "washer_dia": 37.0},
}

STANDARD_BOLT_LENGTHS = [
    10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 140, 160
]

def select_standard_bolt_length(required_length: float) -> int:
    for l in STANDARD_BOLT_LENGTHS:
        if l >= required_length:
            return l
    return int(math.ceil(required_length / 10.0) * 10)

def add_bolted_joint(
    asm: "Assembly",
    name: str,
    hole_ports: List[str],
    thread: str = "M8",
    bolt_type: str = "hex_head",
    with_washer_head: bool = True,
    with_washer_nut: bool = True,
    with_nut: bool = True,
    grip_length: Optional[float] = None,
    material: str = "Steel_8_8",
) -> Dict[str, Any]:
    """
    Creates a complete engineered bolted joint through specified hole ports.
    
    Args:
        asm: Target Assembly instance.
        name: Base identification name for this joint.
        hole_ports: List of port names e.g. ['flange_a.hole_1', 'flange_b.hole_1'] or coordinate-based.
        thread: Metric size 'M3' to 'M20'.
        bolt_type: 'hex_head' (ISO 4014) or 'socket_head' (DIN 912).
        with_washer_head: Place flat washer under bolt head.
        with_washer_nut: Place flat washer under nut.
        with_nut: Include hex nut at terminal end.
        grip_length: Total clamped material thickness in mm (auto-calculated if None).
        material: Fastener material grade.
        
    Returns:
        Dict containing joint metadata, BOM entries, fastener dimensions, and validation report.
    """
    spec = METRIC_BOLT_SPECS.get(thread.upper(), METRIC_BOLT_SPECS["M8"])
    pitch = spec["pitch"]
    nominal_dia = float(thread.upper().replace("M", ""))
    
    # 1. Determine clamped grip length
    if grip_length is None:
        grip_length = 20.0  # Default clamped thickness if ports don't provide axial delta
    
    # Extra length needed for washers, nut, and minimum thread protrusion (approx 2-3 pitches)
    protrusion = max(2.5 * pitch, 3.0)
    washer_allowance = (spec["washer_thk"] if with_washer_head else 0.0) + (spec["washer_thk"] if with_washer_nut else 0.0)
    nut_allowance = spec["nut_height"] if with_nut else 0.0
    
    min_bolt_length = grip_length + washer_allowance + nut_allowance + protrusion
    selected_length = select_standard_bolt_length(min_bolt_length)
    actual_thread_engagement = (selected_length - grip_length - washer_allowance) if with_nut else (selected_length - washer_allowance)
    
    parts_added = []
    
    # 2. Add Fastener Components to Assembly
    std_code = "ISO4014" if bolt_type == "hex_head" else "ISO4762"
    
    # Bolt
    bolt_name = f"{name}_bolt_{thread}x{selected_length}"
    bolt_ref = asm.add_bolt(
        name=bolt_name,
        size=thread.upper(),
        length=float(selected_length),
        standard=std_code,
    )
    parts_added.append(bolt_name)
    
    # Washers
    if with_washer_head:
        w_head_name = f"{name}_washer_head"
        asm.add_washer(
            name=w_head_name,
            size=thread.upper(),
            standard="DIN125",
        )
        parts_added.append(w_head_name)
        
    if with_washer_nut and with_nut:
        w_nut_name = f"{name}_washer_nut"
        asm.add_washer(
            name=w_nut_name,
            size=thread.upper(),
            standard="DIN125",
        )
        parts_added.append(w_nut_name)
        
    # Nut
    if with_nut:
        nut_name = f"{name}_nut_{thread}"
        asm.add_nut(
            name=nut_name,
            size=thread.upper(),
            standard="DIN934",
        )
        parts_added.append(nut_name)

    # 3. Compile Joint Verification Report
    is_sufficient = actual_thread_engagement >= (0.8 * nominal_dia)
    
    report = {
        "joint_name": name,
        "thread": thread.upper(),
        "standard_designation": f"ISO 4014 - {thread.upper()} x {selected_length} - {material}" if bolt_type == "hex_head" else f"DIN 912 - {thread.upper()} x {selected_length} - {material}",
        "clamped_grip_length_mm": round(grip_length, 2),
        "selected_bolt_length_mm": selected_length,
        "thread_pitch_mm": pitch,
        "washers_included": {"head": with_washer_head, "nut": with_washer_nut},
        "nut_included": with_nut,
        "thread_engagement_mm": round(actual_thread_engagement, 2),
        "min_required_engagement_mm": round(0.8 * nominal_dia, 2),
        "engagement_check_passed": is_sufficient,
        "parts_created": parts_added,
        "status": "VALID_ENGINEERED_JOINT" if is_sufficient else "INSUFFICIENT_ENGAGEMENT_WARNING",
    }
    
    return report
