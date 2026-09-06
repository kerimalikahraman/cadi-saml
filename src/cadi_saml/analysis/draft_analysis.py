"""
cadi_saml.analysis.draft_analysis
=================================
Mold Tooling, Injection Molding & Casting Draft Angle Analysis.
Evaluates B-Rep face normals relative to mold opening/pull vectors,
classifying faces into:
- Positive Draft (clean ejection)
- Insufficient Draft (risk of sticking/drag lines)
- Undercut / Negative Draft (requires side-action slider/lifter)
- Parting Planes (top/bottom perpendicular faces)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import OCP.BRepAdaptor as BRepAdaptor
import OCP.BRepGProp as BRepGProp
import OCP.BRepLProp as BRepLProp
import OCP.GProp as GProp
import OCP.TopAbs as TopAbs
import OCP.TopExp as TopExp
import OCP.TopoDS as TopoDS
import OCP.gp as gp

if TYPE_CHECKING:
    from ..core.assembly import Assembly


def analyze_draft(
    assembly: Optional["Assembly"] = None,
    part_name: Optional[str] = None,
    shape: Optional[TopoDS.TopoDS_Shape] = None,
    pull_direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    min_draft_deg: float = 1.5,
) -> Dict[str, Any]:
    """
    Performs full 3D B-Rep draft angle and undercut analysis for mold tooling.

    Parameters:
      assembly: The Assembly instance (optional if shape is passed directly)
      part_name: Name of the part within the assembly to analyze
      shape: Direct TopoDS_Shape to analyze (optional if assembly & part_name provided)
      pull_direction: Mold draw direction vector (e.g. (0, 0, 1) along Z)
      min_draft_deg: Minimum permissible draft angle in degrees (typically 1.0° - 2.0°)
    """
    target_shape = None
    if shape is not None:
        target_shape = shape
    elif assembly is not None and part_name is not None:
        from ..backend.occt_backend import OCCTBackend
        solids = OCCTBackend().compile(assembly.to_ir())
        if part_name not in solids:
            raise KeyError(f"Part '{part_name}' not found in compiled assembly solids.")
        target_shape = solids[part_name]
    elif assembly is not None and len(assembly._parts) > 0:
        # If part_name omitted, check first part
        from ..backend.occt_backend import OCCTBackend
        first_name = list(assembly._parts.keys())[0]
        solids = OCCTBackend().compile(assembly.to_ir())
        target_shape = solids.get(first_name)
    else:
        raise ValueError("Either 'shape' or ('assembly' and 'part_name') must be provided.")

    if target_shape is None or target_shape.IsNull():
        raise ValueError("Invalid or null B-Rep shape for draft analysis.")

    # Normalize pull direction
    px, py, pz = pull_direction
    pmag = math.sqrt(px * px + py * py + pz * pz)
    if pmag < 1e-6:
        raise ValueError("Pull direction vector cannot be zero.")
    pv = (px / pmag, py / pmag, pz / pmag)

    min_sin = math.sin(math.radians(min_draft_deg))

    faces_positive: List[Dict[str, Any]] = []
    faces_insufficient: List[Dict[str, Any]] = []
    faces_undercut: List[Dict[str, Any]] = []
    faces_parting_top: List[Dict[str, Any]] = []
    faces_parting_bottom: List[Dict[str, Any]] = []

    exp = TopExp.TopExp_Explorer(target_shape, TopAbs.TopAbs_FACE)
    face_idx = 0

    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor.BRepAdaptor_Surface(face)

        # Midpoint UV
        u_mid = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
        v_mid = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0

        # Calculate Surface Area
        gprops = GProp.GProp_GProps()
        BRepGProp.BRepGProp.SurfaceProperties_s(face, gprops)
        area = float(gprops.Mass())

        # Evaluate Normal
        props = BRepLProp.BRepLProp_SLProps(surf, u_mid, v_mid, 1, 1e-6)
        if props.IsNormalDefined():
            norm = props.Normal()
            if face.Orientation() == TopAbs.TopAbs_REVERSED:
                norm.Reverse()

            nx, ny, nz = norm.X(), norm.Y(), norm.Z()
            dot = nx * pv[0] + ny * pv[1] + nz * pv[2]
            clamped_dot = max(-1.0, min(1.0, dot))
            draft_deg = math.degrees(math.asin(clamped_dot))

            face_data = {
                "face_index": face_idx,
                "area_mm2": round(area, 2),
                "normal": (round(nx, 4), round(ny, 4), round(nz, 4)),
                "draft_angle_deg": round(draft_deg, 2),
            }

            if clamped_dot >= 0.999:
                face_data["classification"] = "PARTING_TOP"
                faces_parting_top.append(face_data)
            elif clamped_dot <= -0.999:
                face_data["classification"] = "PARTING_BOTTOM"
                faces_parting_bottom.append(face_data)
            elif clamped_dot >= min_sin:
                face_data["classification"] = "POSITIVE_DRAFT"
                faces_positive.append(face_data)
            elif 0.0 <= clamped_dot < min_sin:
                face_data["classification"] = "INSUFFICIENT_DRAFT"
                faces_insufficient.append(face_data)
            else:
                face_data["classification"] = "UNDERCUT"
                faces_undercut.append(face_data)

        face_idx += 1
        exp.Next()

    has_undercuts = len(faces_undercut) > 0
    has_insufficient = len(faces_insufficient) > 0

    if not has_undercuts and not has_insufficient:
        status = "PASS"
        recommendation = "All faces have sufficient draft angle for clean injection mold ejection."
    elif has_undercuts:
        status = "FAIL_UNDERCUTS"
        recommendation = (
            f"Detected {len(faces_undercut)} undercut faces! Mold requires side-action "
            f"lifters or cam sliders, or redesign with positive draft."
        )
    else:
        status = "WARNING_DRAFT"
        recommendation = (
            f"Detected {len(faces_insufficient)} faces with draft < {min_draft_deg}°. "
            f"Add minimum {min_draft_deg}° taper to avoid surface drag marks."
        )

    return {
        "part_name": part_name or "evaluated_shape",
        "pull_direction": pv,
        "min_draft_deg": min_draft_deg,
        "total_faces_evaluated": face_idx,
        "status": status,
        "recommendation": recommendation,
        "undercuts_detected": has_undercuts,
        "summary": {
            "positive_draft_count": len(faces_positive),
            "insufficient_draft_count": len(faces_insufficient),
            "undercut_count": len(faces_undercut),
            "parting_top_count": len(faces_parting_top),
            "parting_bottom_count": len(faces_parting_bottom),
        },
        "undercut_faces": faces_undercut,
        "insufficient_draft_faces": faces_insufficient,
    }
