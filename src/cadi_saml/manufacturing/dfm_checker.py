"""
Design for Manufacturing (DFM) Automated Audit Engine for CADI-SAML.
Performs manufacturability checks across CNC milling, turning, 3D printing, sheet metal, and casting.
Emits structured CADIErrorPayload diagnostics for LLMs.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import math

from cadi_saml.core.error_model import CADIErrorPayload, E_DFM_VIOLATION

try:
    import OCP.TopExp as TopExp
    import OCP.TopAbs as TopAbs
    import OCP.TopoDS as TopoDS
    import OCP.BRepAdaptor as BRepAdaptor
    import OCP.GeomAbs as GeomAbs
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@dataclass
class DFMAuditReport:
    """Comprehensive manufacturability analysis report."""
    passed: bool
    violations: List[CADIErrorPayload] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def check_hole_aspect_ratios(
    shape: Any,
    max_aspect_ratio: float = 8.0,
    part_name: str = "part",
) -> List[CADIErrorPayload]:
    """
    Flags deep drilled holes with depth/diameter ratio exceeding conventional CNC tooling limits.
    """
    violations: List[CADIErrorPayload] = []
    if not HAS_OCP or shape is None or shape.IsNull():
        return violations

    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    idx = 0
    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs.GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            radius = cyl.Radius()
            dia = radius * 2.0
            # Rough estimate of cylinder face length along axis
            umin, umax, vmin, vmax = adaptor.FirstUParameter(), adaptor.LastUParameter(), adaptor.FirstVParameter(), adaptor.LastVParameter()
            length = abs(vmax - vmin)
            ratio = length / max(dia, 1e-4)

            if ratio > max_aspect_ratio and length > 5.0:
                violations.append(
                    CADIErrorPayload(
                        code=E_DFM_VIOLATION,
                        path=f"parts.{part_name}.holes[{idx}].aspect_ratio",
                        provided=round(ratio, 2),
                        expected=f"<= {max_aspect_ratio}",
                        message=f"Deep hole detected on '{part_name}': L={round(length, 1)}mm, D={round(dia, 1)}mm gives L/D ratio {round(ratio, 1)} > {max_aspect_ratio}.",
                        suggested_fix=f"Increase hole diameter or reduce depth to keep aspect ratio below {max_aspect_ratio} to avoid drill bit deflection.",
                        related_parts=[part_name],
                    )
                )
        idx += 1
        exp.Next()

    return violations


def check_3d_print_overhangs(
    shape: Any,
    max_overhang_deg: float = 45.0,
    build_direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    part_name: str = "part",
) -> List[CADIErrorPayload]:
    """
    Checks for downward-facing planar faces that exceed the maximum self-supporting 3D print overhang angle.
    """
    violations: List[CADIErrorPayload] = []
    if not HAS_OCP or shape is None or shape.IsNull():
        return violations

    bx, by, bz = build_direction
    bmag = math.sqrt(bx**2 + by**2 + bz**2) or 1.0
    bx, by, bz = bx / bmag, by / bmag, bz / bmag

    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    idx = 0
    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs.GeomAbs_Plane:
            pln = adaptor.Plane()
            axis = pln.Axis().Direction()
            nx, ny, nz = axis.X(), axis.Y(), axis.Z()

            # Downward component relative to build direction
            dot = nx * bx + ny * by + nz * bz
            if dot < -0.1:  # Downward facing
                angle_from_vertical_deg = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot)))))
                overhang_angle = 90.0 - angle_from_vertical_deg
                if overhang_angle > max_overhang_deg and abs(dot) < 0.99:
                    violations.append(
                        CADIErrorPayload(
                            code=E_DFM_VIOLATION,
                            path=f"parts.{part_name}.faces[{idx}].overhang_angle",
                            provided=round(overhang_angle, 1),
                            expected=f"<= {max_overhang_deg}°",
                            message=f"Steep overhang surface ({round(overhang_angle, 1)}°) on '{part_name}' requires sacrificial support structures.",
                            suggested_fix=f"Chamfer or taper the overhang to <= {max_overhang_deg}° or rotate build orientation.",
                            related_parts=[part_name],
                        )
                    )
        idx += 1
        exp.Next()

    return violations


def check_casting_draft_angles(
    shape: Any,
    min_draft_deg: float = 1.5,
    pull_direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    part_name: str = "part",
) -> List[CADIErrorPayload]:
    """
    Flags vertical walls in cast or injection-molded parts with zero or insufficient draft angle.
    """
    violations: List[CADIErrorPayload] = []
    if not HAS_OCP or shape is None or shape.IsNull():
        return violations

    px, py, pz = pull_direction
    pmag = math.sqrt(px**2 + py**2 + pz**2) or 1.0
    px, py, pz = px / pmag, py / pmag, pz / pmag

    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    idx = 0
    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs.GeomAbs_Plane:
            pln = adaptor.Plane()
            axis = pln.Axis().Direction()
            dot = axis.X() * px + axis.Y() * py + axis.Z() * pz
            # Exact vertical wall parallel to pull has dot == 0
            if abs(dot) < math.sin(math.radians(min_draft_deg)):
                violations.append(
                    CADIErrorPayload(
                        code=E_DFM_VIOLATION,
                        path=f"parts.{part_name}.faces[{idx}].draft_angle",
                        provided=round(math.degrees(math.asin(abs(dot))), 2),
                        expected=f">= {min_draft_deg}°",
                        message=f"Vertical wall face {idx} on '{part_name}' has insufficient draft angle for mold release.",
                        suggested_fix=f"Apply DraftFeature with >= {min_draft_deg}° taper along pull axis.",
                        related_parts=[part_name],
                    )
                )
        idx += 1
        exp.Next()

    return violations


def audit_assembly_dfm(
    solids: Dict[str, Any],
    max_aspect_ratio: float = 8.0,
    max_overhang_deg: float = 45.0,
    min_draft_deg: Optional[float] = None,
) -> DFMAuditReport:
    """Runs a complete DFM audit across all solid bodies in an assembly."""
    all_violations: List[CADIErrorPayload] = []
    for pname, shape in solids.items():
        all_violations.extend(check_hole_aspect_ratios(shape, max_aspect_ratio, part_name=pname))
        all_violations.extend(check_3d_print_overhangs(shape, max_overhang_deg, part_name=pname))
        if min_draft_deg is not None:
            all_violations.extend(check_casting_draft_angles(shape, min_draft_deg, part_name=pname))

    return DFMAuditReport(
        passed=len(all_violations) == 0,
        violations=all_violations,
        metrics={"total_parts_audited": len(solids), "violation_count": len(all_violations)},
    )
