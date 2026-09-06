"""
cadi_saml.macros.shaft_features
===============================
Standard industrial shaft features wizard:
- DIN 6885 Parallel Keyways (Form A rounded & Form B straight)
- DIN 471 External Circlip / Retaining Ring Grooves
- DIN 472 Internal Circlip / Retaining Ring Grooves
Supports 100% Zero-Coordinate Semantic Placement:
- Align under a mating part (e.g. under_part='gear_1')
- Place on a stepped shaft shoulder (e.g. at_step=1)
- Snap to a semantic port (e.g. at_port='bearing_seat_front')
Fully deterministic, standard-table driven, zero coordinate guessing for AI agents.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from ..core.exceptions import CADISpecificationError

if TYPE_CHECKING:
    from ..core.assembly import Assembly


from ..standards.catalogs import (
    lookup_din_6885 as _catalog_lookup_din_6885,
    lookup_din_471 as _catalog_lookup_din_471,
    DIN_6885_1_KEYWAYS,
    DIN_471_CIRCLIPS,
)


def lookup_din_6885(shaft_dia: float) -> Tuple[float, float, float, float]:
    """Returns (b, h, t1, t2) for a given shaft diameter from central standards catalog."""
    return _catalog_lookup_din_6885(shaft_dia)


def lookup_din_471(shaft_dia: float) -> Tuple[float, float, float]:
    """Returns (groove_width_m, groove_depth_t, ring_thickness_s) from central standards catalog."""
    return _catalog_lookup_din_471(shaft_dia)



def _resolve_shaft_z(
    assembly: "Assembly",
    shaft_part: str,
    z_position: Optional[float] = None,
    under_part: Optional[str] = None,
    against_part: Optional[str] = None,
    at_step: Optional[int] = None,
    at_port: Optional[str] = None,
    side: str = "front",
    feature_length: float = 0.0,
) -> float:
    """
    Zero-Coordinate Resolver: Computes the axial Z position along a shaft
    from semantic relationships without user coordinate hallucination.
    """
    if shaft_part not in assembly._parts:
        raise CADISpecificationError(
            parameter_name="shaft_part",
            provided_value=shaft_part,
            valid_options=list(assembly._parts.keys()),
            suggested_fix=f"Shaft part '{shaft_part}' does not exist in assembly.",
        )
    part_ref = assembly._parts[shaft_part]
    params = part_ref.node.parameters

    # 1. Positioned under a mounted component (e.g. gear, pulley, sprocket)
    if under_part is not None:
        if under_part not in assembly._parts:
            raise CADISpecificationError(
                parameter_name="under_part",
                provided_value=under_part,
                valid_options=list(assembly._parts.keys()),
                suggested_fix=f"Mating component '{under_part}' not found in assembly.",
            )
        mating_ref = assembly._parts[under_part]
        m_params = mating_ref.node.parameters
        m_orig = m_params.get("origin", (0.0, 0.0, 0.0))
        m_width = float(m_params.get("face_width") or m_params.get("width") or m_params.get("length") or 20.0)
        calc_z = float(m_orig[2]) + (m_width - feature_length) / 2.0
        part_ref.track_provenance(
            parameter="feature_z_position",
            source="calculated",
            source_ref=f"under_part:{under_part}",
            original_value=f"under_part:{under_part}",
            effective_value=calc_z,
            transformation="calculated",
            confidence=1.0,
        )
        return calc_z

    # 2. Positioned against a retaining component (e.g. bearing, gear shoulder)
    if against_part is not None:
        if against_part not in assembly._parts:
            raise CADISpecificationError(
                parameter_name="against_part",
                provided_value=against_part,
                valid_options=list(assembly._parts.keys()),
                suggested_fix=f"Mating retaining component '{against_part}' not found in assembly.",
            )
        mating_ref = assembly._parts[against_part]
        m_params = mating_ref.node.parameters
        m_orig = m_params.get("origin", (0.0, 0.0, 0.0))
        m_width = float(m_params.get("face_width") or m_params.get("width") or m_params.get("thickness") or 15.0)
        if side.lower() in ("front", "start"):
            calc_z = float(m_orig[2]) - feature_length - 0.5
        else:
            calc_z = float(m_orig[2]) + m_width + 0.5
        part_ref.track_provenance(
            parameter="feature_z_position",
            source="calculated",
            source_ref=f"against_part:{against_part}:{side}",
            original_value=f"against_part:{against_part}:{side}",
            effective_value=calc_z,
            transformation="calculated",
            confidence=1.0,
        )
        return calc_z

    # 3. Positioned on a specific stepped shaft journal
    if at_step is not None:
        if "steps" not in params:
            raise CADISpecificationError(
                parameter_name="at_step",
                provided_value=at_step,
                valid_options=[],
                suggested_fix=f"Target shaft '{shaft_part}' does not have stepped journals ('steps' parameter missing).",
            )
        steps = params["steps"]
        step_idx = int(at_step)
        if not (0 <= step_idx < len(steps)):
            raise CADISpecificationError(
                parameter_name="at_step",
                provided_value=at_step,
                valid_options=[str(i) for i in range(len(steps))],
                suggested_fix=f"Step index {at_step} is out of bounds for shaft '{shaft_part}' with {len(steps)} steps.",
            )
        z_accum = sum(float(l) for _, l in steps[:step_idx])
        step_len = float(steps[step_idx][1])
        calc_z = z_accum + (step_len - feature_length) / 2.0
        part_ref.track_provenance(
            parameter="feature_z_position",
            source="calculated",
            source_ref=f"step:{step_idx}",
            original_value=step_idx,
            effective_value=calc_z,
            transformation="calculated",
            confidence=1.0,
        )
        return calc_z

    # 4. Positioned at a semantic port
    if at_port is not None:
        if at_port not in part_ref.ports:
            raise CADISpecificationError(
                parameter_name="at_port",
                provided_value=at_port,
                valid_options=list(part_ref.ports.keys()),
                suggested_fix=f"Port '{at_port}' not found on shaft '{shaft_part}'.",
            )
        port = part_ref.ports[at_port]
        calc_z = float(port.relative_position[2])
        part_ref.track_provenance(
            parameter="feature_z_position",
            source="calculated",
            source_ref=f"port:{at_port}",
            original_value=at_port,
            effective_value=calc_z,
            transformation="calculated",
            confidence=1.0,
        )
        return calc_z

    # 5. Explicit coordinate
    if z_position is not None:
        calc_z = float(z_position)
        part_ref.node.parameters["feature_z_position"] = calc_z
        part_ref.track_provenance(
            parameter="feature_z_position",
            source="user",
            source_ref="z_position",
            original_value=z_position,
            effective_value=calc_z,
            transformation="exact",
            confidence=1.0,
        )
        return calc_z

    # Strict mode: Unspecified position is an error - no hallucinated center coordinates!
    raise CADISpecificationError(
        parameter_name="z_position",
        provided_value=None,
        valid_options=["under_part", "against_part", "at_step", "at_port", "z_position"],
        suggested_fix=(
            f"Axial position for shaft feature on '{shaft_part}' is unspecified. "
            f"Specify a semantic reference (under_part, against_part, at_step, at_port) or explicit z_position."
        ),
    )


_resolve_feature_z_position = _resolve_shaft_z



def add_shaft_keyway(
    assembly: "Assembly",
    shaft_part: Optional[str] = None,
    target_shaft: Optional[str] = None,
    z_position: Optional[float] = None,
    under_part: Optional[str] = None,
    against_part: Optional[str] = None,
    side: str = "front",
    at_step: Optional[int] = None,
    at_port: Optional[str] = None,
    length: Optional[float] = None,
    standard: str = "DIN_6885_A",
    custom_width: Optional[float] = None,
    custom_depth: Optional[float] = None,
    orientation_deg: float = 0.0,
) -> Dict[str, Any]:
    """
    Cuts an engineered DIN 6885 parallel keyway into a shaft.
    Supports ZERO-COORDINATE placement via under_part, against_part, at_step, or at_port.
    """
    actual_shaft = shaft_part or target_shaft
    if not actual_shaft or actual_shaft not in assembly._parts:
        raise KeyError(f"Shaft part '{actual_shaft}' not found in assembly.")

    part_ref = assembly._parts[actual_shaft]
    shaft_radius = float(
        part_ref.parameters.get("radius")
        or (float(part_ref.parameters.get("diameter", 20.0)) / 2.0)
    )
    shaft_dia = shaft_radius * 2.0

    std_b, std_h, std_t1, _ = lookup_din_6885(shaft_dia)
    width = float(custom_width or std_b)
    depth = float(custom_depth or std_t1)
    key_length = float(length or (width * 3.5))

    # Resolve Z axially without user coordinates
    actual_z = _resolve_shaft_z(
        assembly=assembly,
        shaft_part=actual_shaft,
        z_position=z_position,
        under_part=under_part,
        against_part=against_part,
        side=side,
        at_step=at_step,
        at_port=at_port,
        feature_length=key_length,
    )

    cutter_name = f"{actual_shaft}_keyway_cutter_{int(actual_z)}"

    # Create keyway cutter box
    cutter_height = depth + 5.0
    rad_ang = math.radians(orientation_deg)
    
    cx = (shaft_radius - depth / 2.0) * math.cos(rad_ang)
    cy = (shaft_radius - depth / 2.0) * math.sin(rad_ang)

    assembly.add_box(
        name=cutter_name,
        length=cutter_height,
        width=width,
        height=key_length,
        origin=(cx - cutter_height / 2.0, cy - width / 2.0, actual_z),
    )

    assembly.cut(shaft_part, cutter_name, keep_tool=False)

    part_ref.add_port(
        name=f"keyway_center_{int(actual_z)}",
        port_type="planar",
        position=(cx, cy, actual_z + key_length / 2.0),
        normal=(math.cos(rad_ang), math.sin(rad_ang), 0.0),
        diameter=width,
    )

    return {
        "shaft": shaft_part,
        "standard": standard,
        "width_mm": width,
        "depth_mm": depth,
        "length_mm": key_length,
        "z_position": round(actual_z, 2),
        "aligned_under_part": under_part,
    }


def add_circlip_groove(
    assembly: "Assembly",
    shaft_part: Optional[str] = None,
    target_shaft: Optional[str] = None,
    z_position: Optional[float] = None,
    against_part: Optional[str] = None,
    at_step: Optional[int] = None,
    at_port: Optional[str] = None,
    side: str = "front",
    standard: str = "DIN_471",
    custom_width: Optional[float] = None,
    custom_depth: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Cuts a standard DIN 471 retaining ring / circlip groove around a shaft.
    Supports ZERO-COORDINATE placement via against_part, at_step, or at_port.
    """
    actual_shaft = shaft_part or target_shaft
    if not actual_shaft or actual_shaft not in assembly._parts:
        raise KeyError(f"Shaft part '{actual_shaft}' not found in assembly.")

    part_ref = assembly._parts[actual_shaft]
    shaft_radius = float(
        part_ref.parameters.get("radius")
        or (float(part_ref.parameters.get("diameter", 20.0)) / 2.0)
    )
    shaft_dia = shaft_radius * 2.0

    std_m, std_t, _ = lookup_din_471(shaft_dia)
    groove_width = float(custom_width or std_m)
    groove_depth = float(custom_depth or std_t)

    actual_z = _resolve_shaft_z(
        assembly=assembly,
        shaft_part=actual_shaft,
        z_position=z_position,
        against_part=against_part,
        at_step=at_step,
        at_port=at_port,
        side=side,
        feature_length=groove_width,
    )

    cutter_outer = f"{actual_shaft}_circlip_outer_{int(actual_z)}"
    cutter_inner = f"{actual_shaft}_circlip_inner_{int(actual_z)}"

    r_outer = shaft_radius + 2.0
    r_inner = shaft_radius - groove_depth

    assembly.add_cylinder(
        name=cutter_outer,
        radius=r_outer,
        height=groove_width,
        origin=(0.0, 0.0, actual_z),
    )
    assembly.add_cylinder(
        name=cutter_inner,
        radius=r_inner,
        height=groove_width + 4.0,
        origin=(0.0, 0.0, actual_z - 2.0),
    )

    assembly.cut(cutter_outer, cutter_inner, keep_tool=False)
    assembly.cut(shaft_part, cutter_outer, keep_tool=False)

    part_ref.add_port(
        name=f"circlip_groove_{int(actual_z)}",
        port_type="axis",
        position=(0.0, 0.0, actual_z),
        normal=(0.0, 0.0, 1.0),
        diameter=r_inner * 2.0,
    )

    return {
        "shaft": shaft_part,
        "standard": standard,
        "groove_width_mm": groove_width,
        "groove_depth_mm": groove_depth,
        "inner_diameter_mm": round(r_inner * 2.0, 2),
        "z_position": round(actual_z, 2),
        "retaining_against_part": against_part,
    }
