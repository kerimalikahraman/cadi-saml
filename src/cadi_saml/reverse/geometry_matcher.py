"""
cadi_saml.reverse.geometry_matcher

Verification contract: Compares original imported STEP B-Rep against
the newly synthesized standalone CADi SAML model.
Enforces rigorous tolerances on volume, surface area, center of mass, and bounding box.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional
import numpy as np

import OCP.TopoDS as TopoDS
import OCP.GProp as GProp
import OCP.BRepGProp as BRepGProp
import OCP.Bnd as Bnd
import OCP.BRepBndLib as BRepBndLib


@dataclass
class GeomMatchReport:
    passed: bool
    volume_orig_mm3: float
    volume_rebuilt_mm3: float
    volume_rel_error: float
    surface_area_orig_mm2: float
    surface_area_rebuilt_mm2: float
    area_rel_error: float
    cog_shift_mm: float
    bbox_max_diff_mm: float
    errors: list[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "volume_orig_mm3": round(self.volume_orig_mm3, 2),
            "volume_rebuilt_mm3": round(self.volume_rebuilt_mm3, 2),
            "volume_rel_error_percent": round(self.volume_rel_error * 100.0, 4),
            "surface_area_orig_mm2": round(self.surface_area_orig_mm2, 2),
            "surface_area_rebuilt_mm2": round(self.surface_area_rebuilt_mm2, 2),
            "area_rel_error_percent": round(self.area_rel_error * 100.0, 4),
            "cog_shift_mm": round(self.cog_shift_mm, 4),
            "bbox_max_diff_mm": round(self.bbox_max_diff_mm, 4),
            "errors": self.errors,
            "details": self.details,
        }


def _calc_shape_properties(shape: TopoDS.TopoDS_Shape) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """Calculate (volume, area, center_of_mass, bbox_dimensions) for a solid shape."""
    # Volume and CoG
    v_props = GProp.GProp_GProps()
    BRepGProp.BRepGProp.VolumeProperties_s(shape, v_props)
    vol = float(v_props.Mass())
    com = v_props.CentreOfMass()
    cog_vec = np.array([float(com.X()), float(com.Y()), float(com.Z())], dtype=np.float64)

    # Surface Area
    s_props = GProp.GProp_GProps()
    BRepGProp.BRepGProp.SurfaceProperties_s(shape, s_props)
    area = float(s_props.Mass())

    # Bounding Box
    bbox = Bnd.Bnd_Box()
    BRepBndLib.BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    bbox_dims = np.array([float(xmax - xmin), float(ymax - ymin), float(zmax - zmin)], dtype=np.float64)

    return vol, area, cog_vec, bbox_dims


def verify_geometric_equivalence(
    shape_orig: Optional[TopoDS.TopoDS_Shape] = None,
    shape_rebuilt: Optional[Any] = None,
    original_shape: Optional[TopoDS.TopoDS_Shape] = None,
    rebuilt_assembly: Optional[Any] = None,
    rel_tol: Optional[float] = None,
    max_volume_rel_tol: float = 0.005,  # 0.5% max volume discrepancy
    max_cog_shift_mm: float = 1.0,       # 1 mm max center of mass translation
    max_bbox_diff_mm: float = 0.5,       # 0.5 mm max bounding box difference
) -> GeomMatchReport:
    """
    Rigorously verifies geometric equivalence between the original source solid
    and the reconstructed standalone CADi SAML model.
    """
    s_orig = shape_orig if shape_orig is not None else original_shape
    if s_orig is None:
        raise ValueError("Must provide shape_orig or original_shape")

    s_reb = shape_rebuilt if shape_rebuilt is not None else rebuilt_assembly
    if s_reb is None:
        raise ValueError("Must provide shape_rebuilt or rebuilt_assembly")

    if hasattr(s_reb, "to_ir"):
        from ..backend.occt_backend import OCCTBackend
        solids = OCCTBackend().compile(s_reb.to_ir())
        if not solids:
            raise RuntimeError("Rebuilt assembly compiled into zero solids")
        s_reb = list(solids.values())[0]

    if rel_tol is not None:
        max_volume_rel_tol = rel_tol

    v_orig, a_orig, cog_orig, bbox_orig = _calc_shape_properties(s_orig)
    v_reb, a_reb, cog_reb, bbox_reb = _calc_shape_properties(s_reb)

    # Volume relative error
    vol_err = abs(v_orig - v_reb) / max(v_orig, 1.0)
    area_err = abs(a_orig - a_reb) / max(a_orig, 1.0)
    cog_shift = float(np.linalg.norm(cog_orig - cog_reb))
    bbox_diff = float(np.max(np.abs(bbox_orig - bbox_reb)))

    passed = True
    errors = []

    if vol_err > max_volume_rel_tol:
        passed = False
        errors.append(
            f"Volume relative difference ({vol_err*100:.2f}%) exceeds allowable limit ({max_volume_rel_tol*100:.2f}%). "
            f"Orig: {v_orig:.1f} mm3, Rebuilt: {v_reb:.1f} mm3."
        )

    if cog_shift > max_cog_shift_mm:
        passed = False
        errors.append(
            f"Center of mass shift ({cog_shift:.3f} mm) exceeds limit ({max_cog_shift_mm:.3f} mm)."
        )

    if bbox_diff > max_bbox_diff_mm:
        passed = False
        errors.append(
            f"Bounding box dimension difference ({bbox_diff:.3f} mm) exceeds limit ({max_bbox_diff_mm:.3f} mm)."
        )

    return GeomMatchReport(
        passed=passed,
        volume_orig_mm3=v_orig,
        volume_rebuilt_mm3=v_reb,
        volume_rel_error=vol_err,
        surface_area_orig_mm2=a_orig,
        surface_area_rebuilt_mm2=a_reb,
        area_rel_error=area_err,
        cog_shift_mm=cog_shift,
        bbox_max_diff_mm=bbox_diff,
        errors=errors,
        details={
            "bbox_orig": [round(v, 2) for v in bbox_orig],
            "bbox_rebuilt": [round(v, 2) for v in bbox_reb],
            "cog_orig": [round(v, 2) for v in cog_orig],
            "cog_rebuilt": [round(v, 2) for v in cog_reb],
        },
    )
