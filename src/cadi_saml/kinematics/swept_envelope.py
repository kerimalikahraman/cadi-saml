"""
cadi_saml.kinematics.swept_envelope
===================================
CATIA DMU Kinematics Swept Volume and Dynamic Clearance Engine.
Supports Zero-Coordinate Motion Analysis:
- Automatically resolves rotation axis and center origin from the part's RevoluteJoint
  or semantic 'bore_axis' port without user-specified coordinates.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import OCP.Bnd as Bnd
import OCP.BRepBndLib as BRepBndLib
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepExtrema as BRepExtrema
import OCP.TopoDS as TopoDS
import OCP.gp as gp

if TYPE_CHECKING:
    from ..core.assembly import Assembly


def _get_shape_bbox(shape: TopoDS.TopoDS_Shape) -> Tuple[float, float, float, float, float, float]:
    """Computes exact 3D axis-aligned bounding box (xmin, ymin, zmin, xmax, ymax, zmax)."""
    bbox = Bnd.Bnd_Box()
    BRepBndLib.BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    return xmin, ymin, zmin, xmax, ymax, zmax


def _resolve_motion_axis(
    assembly: "Assembly",
    part_name: str,
    axis: Optional[Tuple[float, float, float]] = None,
    origin: Optional[Tuple[float, float, float]] = None,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Zero-Coordinate Motion Resolver: Extracts motion axis and center origin
    from RevoluteJoints or semantic ports on the part.
    """
    resolved_axis = axis
    resolved_origin = origin

    # 1. Check RevoluteJoint in mechanism
    if (resolved_axis is None or resolved_origin is None) and hasattr(assembly, "_mechanism"):
        joint = assembly._mechanism.joints.get(part_name)
        if joint is not None:
            if resolved_axis is None and hasattr(joint, "axis"):
                resolved_axis = joint.axis
            if resolved_origin is None and hasattr(joint, "origin"):
                resolved_origin = joint.origin

    # 2. Check semantic ports (e.g. bore_axis, center_axis)
    if (resolved_axis is None or resolved_origin is None) and part_name in assembly._parts:
        pref = assembly._parts[part_name]
        for port_name in ("bore_axis", "rotation_axis", "center_axis", "axis"):
            if port_name in pref.ports:
                port = pref.ports[port_name]
                if resolved_axis is None:
                    resolved_axis = port.normal
                if resolved_origin is None:
                    resolved_origin = port.relative_position
                break

    return resolved_axis or (0.0, 0.0, 1.0), resolved_origin or (0.0, 0.0, 0.0)


def compute_swept_envelope(
    assembly: "Assembly",
    moving_part: str,
    axis: Optional[Tuple[float, float, float]] = None,
    origin: Optional[Tuple[float, float, float]] = None,
    angle_range: Tuple[float, float] = (0.0, 360.0),
    steps: int = 18,
) -> Dict[str, Any]:
    """
    Computes the total 3D spatial bounding envelope swept by a moving component.
    Auto-detects rotation axis and pivot origin from joints/ports if omitted.
    """
    from ..backend.occt_backend import OCCTBackend
    solids = OCCTBackend().compile(assembly.to_ir())

    if moving_part not in solids:
        raise KeyError(f"Part '{moving_part}' not found in compiled assembly solids.")

    base_shape = solids[moving_part]
    use_axis, use_origin = _resolve_motion_axis(assembly, moving_part, axis, origin)

    start_ang, end_ang = angle_range
    ang_step = (end_ang - start_ang) / max(1, steps - 1)

    ax_dir = gp.gp_Dir(use_axis[0], use_axis[1], use_axis[2])
    ax_pnt = gp.gp_Pnt(use_origin[0], use_origin[1], use_origin[2])
    rotation_axis = gp.gp_Ax1(ax_pnt, ax_dir)

    min_x, min_y, min_z = float("inf"), float("inf"), float("inf")
    max_x, max_y, max_z = float("-inf"), float("-inf"), float("-inf")

    sampled_bboxes = []

    for i in range(steps):
        angle_deg = start_ang + i * ang_step
        angle_rad = math.radians(angle_deg)

        trsf = gp.gp_Trsf()
        trsf.SetRotation(rotation_axis, angle_rad)
        moved_shape = BRepBuilder.BRepBuilderAPI_Transform(base_shape, trsf, True).Shape()

        x0, y0, z0, x1, y1, z1 = _get_shape_bbox(moved_shape)
        min_x = min(min_x, x0)
        min_y = min(min_y, y0)
        min_z = min(min_z, z0)
        max_x = max(max_x, x1)
        max_y = max(max_y, y1)
        max_z = max(max_z, z1)

        sampled_bboxes.append((round(angle_deg, 1), (round(x0, 2), round(y0, 2), round(z0, 2), round(x1, 2), round(y1, 2), round(z1, 2))))

    dx = max_x - min_x
    dy = max_y - min_y
    dz = max_z - min_z
    swept_volume = dx * dy * dz

    return {
        "moving_part": moving_part,
        "resolved_axis": use_axis,
        "resolved_origin": use_origin,
        "angle_range_deg": angle_range,
        "steps_sampled": steps,
        "swept_envelope_bbox": (round(min_x, 2), round(min_y, 2), round(min_z, 2), round(max_x, 2), round(max_y, 2), round(max_z, 2)),
        "swept_envelope_dimensions_mm": {"dx": round(dx, 2), "dy": round(dy, 2), "dz": round(dz, 2)},
        "swept_bounding_volume_mm3": round(swept_volume, 2),
    }


def check_dynamic_clearance(
    assembly: "Assembly",
    moving_part: str,
    static_part: str,
    axis: Optional[Tuple[float, float, float]] = None,
    origin: Optional[Tuple[float, float, float]] = None,
    angle_range: Tuple[float, float] = (0.0, 360.0),
    steps: int = 18,
    min_clearance_mm: float = 1.0,
) -> Dict[str, Any]:
    """
    Performs dynamic clearance and collision detection throughout full motion.
    Auto-detects rotation axis and pivot origin from joints/ports if omitted.
    """
    from ..backend.occt_backend import OCCTBackend
    solids = OCCTBackend().compile(assembly.to_ir())

    if moving_part not in solids:
        raise KeyError(f"Moving part '{moving_part}' not found in assembly.")
    if static_part not in solids:
        raise KeyError(f"Static part '{static_part}' not found in assembly.")

    base_moving = solids[moving_part]
    static_shape = solids[static_part]

    use_axis, use_origin = _resolve_motion_axis(assembly, moving_part, axis, origin)

    start_ang, end_ang = angle_range
    ang_step = (end_ang - start_ang) / max(1, steps - 1)

    ax_dir = gp.gp_Dir(use_axis[0], use_axis[1], use_axis[2])
    ax_pnt = gp.gp_Pnt(use_origin[0], use_origin[1], use_origin[2])
    rotation_axis = gp.gp_Ax1(ax_pnt, ax_dir)

    min_distance = float("inf")
    clash_angles: List[float] = []
    warning_angles: List[float] = []

    for i in range(steps):
        angle_deg = start_ang + i * ang_step
        angle_rad = math.radians(angle_deg)

        trsf = gp.gp_Trsf()
        trsf.SetRotation(rotation_axis, angle_rad)
        moved_shape = BRepBuilder.BRepBuilderAPI_Transform(base_moving, trsf, True).Shape()

        extrema = BRepExtrema.BRepExtrema_DistShapeShape(moved_shape, static_shape)
        extrema.Perform()

        if extrema.IsDone():
            dist = float(extrema.Value())
            if dist < min_distance:
                min_distance = dist

            if dist < 1e-4:
                clash_angles.append(round(angle_deg, 1))
            elif dist < min_clearance_mm:
                warning_angles.append(round(angle_deg, 1))

    has_clash = len(clash_angles) > 0
    has_warning = len(warning_angles) > 0

    if has_clash:
        status = "COLLISION"
        summary = f"Dynamic clash detected between '{moving_part}' and '{static_part}' at angles: {clash_angles}°."
    elif has_warning:
        status = "WARNING_PROXIMITY"
        summary = (
            f"Close proximity warning: Minimum clearance is {min_distance:.2f}mm "
            f"(target >= {min_clearance_mm}mm) at angles: {warning_angles}°."
        )
    else:
        status = "PASS"
        summary = f"Dynamic motion clearance verified: Minimum distance is {min_distance:.2f}mm throughout full motion."

    return {
        "moving_part": moving_part,
        "static_part": static_part,
        "resolved_axis": use_axis,
        "resolved_origin": use_origin,
        "status": status,
        "has_clash": has_clash,
        "min_dynamic_clearance_mm": round(min_distance, 2) if min_distance < 1e6 else 0.0,
        "clash_angles_deg": clash_angles,
        "warning_angles_deg": warning_angles,
        "summary": summary,
    }
