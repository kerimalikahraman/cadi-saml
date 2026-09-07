"""
cadi_saml.reverse.feature_classifier

Topological and geometric B-Rep feature recognition.
Decomposes raw STEP solids into parametric base primitives (Box, Cylinder),
internal holes (through/blind), PCD bolt patterns, and external bosses.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import numpy as np

import OCP.TopoDS as TopoDS
import OCP.TopExp as TopExp
import OCP.TopAbs as TopAbs
import OCP.BRepAdaptor as BRepAdaptor
import OCP.GeomAbs as GeomAbs
import OCP.Bnd as Bnd
import OCP.BRepBndLib as BRepBndLib
import OCP.GProp as GProp
import OCP.BRepGProp as BRepGProp
import OCP.BRepTools as BRepTools
import OCP.gp as gp


def _to_np(p: Any) -> np.ndarray:
    return np.array([float(p.X()), float(p.Y()), float(p.Z())], dtype=np.float64)


@dataclass
class RecognizedBaseSolid:
    base_type: str  # "box", "cylinder", "freeform"
    parameters: Dict[str, float]
    bounding_box: Tuple[float, float, float, float, float, float]
    total_volume_mm3: float
    center_of_mass: Tuple[float, float, float]


@dataclass
class RecognizedHole:
    hole_id: str
    diameter: float
    radius: float
    depth: float
    axis: Tuple[float, float, float]
    position: Tuple[float, float, float]
    is_through: bool
    confidence: float = 1.0


@dataclass
class RecognizedPCDPattern:
    pattern_id: str
    count: int
    hole_diameter: float
    pcd_diameter: float
    center: Tuple[float, float, float]
    axis: Tuple[float, float, float]
    hole_ids: List[str]


@dataclass
class ClassifiedFeatures:
    base_solid: RecognizedBaseSolid
    holes: List[RecognizedHole] = field(default_factory=list)
    pcd_patterns: List[RecognizedPCDPattern] = field(default_factory=list)
    planar_face_count: int = 0
    cylindrical_face_count: int = 0
    other_face_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_solid": {
                "type": self.base_solid.base_type,
                "parameters": self.base_solid.parameters,
                "bounding_box": [round(v, 2) for v in self.base_solid.bounding_box],
                "total_volume_mm3": round(self.base_solid.total_volume_mm3, 2),
                "center_of_mass": [round(v, 2) for v in self.base_solid.center_of_mass],
            },
            "holes": [
                {
                    "id": h.hole_id,
                    "diameter": round(h.diameter, 2),
                    "depth": round(h.depth, 2),
                    "is_through": h.is_through,
                    "position": [round(v, 2) for v in h.position],
                    "axis": [round(v, 2) for v in h.axis],
                }
                for h in self.holes
            ],
            "pcd_patterns": [
                {
                    "id": p.pattern_id,
                    "count": p.count,
                    "hole_diameter": round(p.hole_diameter, 2),
                    "pcd_diameter": round(p.pcd_diameter, 2),
                    "center": [round(v, 2) for v in p.center],
                    "axis": [round(v, 2) for v in p.axis],
                }
                for p in self.pcd_patterns
            ],
            "face_counts": {
                "planar": self.planar_face_count,
                "cylindrical": self.cylindrical_face_count,
                "other": self.other_face_count,
            },
        }


class BRepFeatureClassifier:
    """Classifies B-Rep shapes into parametric engineering features."""

    def __init__(self, shape: TopoDS.TopoDS_Shape, tolerance: float = 1e-4):
        self.shape = shape
        self.tolerance = tolerance

    def classify(self) -> ClassifiedFeatures:
        # 1. Mass properties & Bounding Box
        vol_props = GProp.GProp_GProps()
        BRepGProp.BRepGProp.VolumeProperties_s(self.shape, vol_props)
        vol = float(vol_props.Mass())
        com_pnt = vol_props.CentreOfMass()
        com = (float(com_pnt.X()), float(com_pnt.Y()), float(com_pnt.Z()))

        bbox = Bnd.Bnd_Box()
        BRepBndLib.BRepBndLib.Add_s(self.shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dx = float(xmax - xmin)
        dy = float(ymax - ymin)
        dz = float(zmax - zmin)

        # 2. Iterate faces and categorize
        planar_faces = []
        cylindrical_faces = []
        other_faces = 0

        exp = TopExp.TopExp_Explorer(self.shape, TopAbs.TopAbs_FACE)
        f_idx = 0
        while exp.More():
            face = TopoDS.TopoDS.Face_s(exp.Current())
            adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
            stype = adaptor.GetType()

            if stype == GeomAbs.GeomAbs_Plane:
                pln = adaptor.Plane()
                normal = _to_np(pln.Axis().Direction())
                if face.Orientation() == TopAbs.TopAbs_REVERSED:
                    normal = -normal
                loc = _to_np(pln.Location())
                planar_faces.append({"index": f_idx, "normal": normal, "pos": loc})
            elif stype == GeomAbs.GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                r = float(cyl.Radius())
                axis = _to_np(cyl.Axis().Direction())
                loc = _to_np(cyl.Location())
                
                # Check normal direction to determine if inner cavity (hole) or outer cylinder
                u0, u1, v0, v1 = BRepTools.BRepTools.UVBounds_s(face)
                pnt = gp.gp_Pnt()
                du = gp.gp_Vec()
                dv = gp.gp_Vec()
                adaptor.D1((u0 + u1) / 2.0, (v0 + v1) / 2.0, pnt, du, dv)
                outward = np.cross(_to_np(du), _to_np(dv))
                if face.Orientation() == TopAbs.TopAbs_REVERSED:
                    outward = -outward
                
                # Radial vector from cylinder axis to surface point
                axis_to_pt = _to_np(pnt) - loc
                radial = axis_to_pt - np.dot(axis_to_pt, axis) * axis
                is_inner = bool(np.dot(outward, radial) < 0)

                f_bbox = Bnd.Bnd_Box()
                BRepBndLib.BRepBndLib.Add_s(face, f_bbox)
                fx0, fy0, fz0, fx1, fy1, fz1 = f_bbox.Get()
                h_axis = np.abs(np.array([fx1 - fx0, fy1 - fy0, fz1 - fz0]))
                face_height = float(np.dot(h_axis, np.abs(axis)))
                if face_height <= 1e-4:
                    face_height = float(abs(v1 - v0))

                cylindrical_faces.append({
                    "index": f_idx,
                    "radius": r,
                    "diameter": r * 2.0,
                    "axis": axis,
                    "loc": loc,
                    "height": face_height,
                    "is_inner": is_inner,
                })
            else:
                other_faces += 1

            f_idx += 1
            exp.Next()

        # 3. Detect Base Solid Type
        # If dominant shape is cylinder or box
        box_vol = dx * dy * dz
        cyl_vol_z = math.pi * ((dx / 2.0) ** 2) * dz
        
        # Check if base is cylindrical (outer cylinder present with radius ~ dx/2 or dy/2)
        outer_cyls = [c for c in cylindrical_faces if not c["is_inner"]]
        if outer_cyls and abs(dx - dy) < 1.0:
            # Cylinder base
            max_r = max(c["radius"] for c in outer_cyls)
            base_type = "cylinder"
            base_params = {
                "radius": round(max_r, 3),
                "diameter": round(max_r * 2.0, 3),
                "height": round(dz, 3),
                "length": round(dx, 3),
                "width": round(dy, 3),
            }
        else:
            base_type = "box"
            base_params = {
                "length": round(dx, 3),
                "width": round(dy, 3),
                "height": round(dz, 3),
            }

        base_solid = RecognizedBaseSolid(
            base_type=base_type,
            parameters=base_params,
            bounding_box=(xmin, ymin, zmin, xmax, ymax, zmax),
            total_volume_mm3=vol,
            center_of_mass=com,
        )

        # 4. Extract Holes (inner cylindrical surfaces)
        holes: List[RecognizedHole] = []
        inner_cyls = [c for c in cylindrical_faces if c["is_inner"]]

        # Group cylindrical faces that share the same axis and location (split faces)
        grouped_holes = []
        for c in inner_cyls:
            matched = False
            for grp in grouped_holes:
                ref = grp[0]
                if (abs(c["diameter"] - ref["diameter"]) < 0.05 and
                    abs(np.dot(c["axis"], ref["axis"])) > 0.99 and
                    np.linalg.norm(c["loc"] - ref["loc"]) < 0.5):
                    grp.append(c)
                    matched = True
                    break
            if not matched:
                grouped_holes.append([c])

        for i, grp in enumerate(grouped_holes):
            h_data = grp[0]
            dia = float(h_data["diameter"])
            rad = float(h_data["radius"])
            axis = (float(h_data["axis"][0]), float(h_data["axis"][1]), float(h_data["axis"][2]))
            pos = (float(h_data["loc"][0]), float(h_data["loc"][1]), float(h_data["loc"][2]))
            
            # Through hole check: height close to solid dimension along axis
            axis_arr = np.abs(np.array(axis))
            dim_along_axis = float(np.dot(np.array([dx, dy, dz]), axis_arr))
            depth = max(float(c["height"]) for c in grp)
            is_through = abs(depth - dim_along_axis) < 1.0 or depth >= (dim_along_axis - 0.5)
            if is_through:
                depth = dim_along_axis

            holes.append(RecognizedHole(
                hole_id=f"hole_{i+1}",
                diameter=round(dia, 3),
                radius=round(rad, 3),
                depth=round(depth, 3),
                axis=axis,
                position=pos,
                is_through=is_through,
            ))

        # 5. Extract PCD Bolt Patterns (from holes sharing the same diameter and circular radius)
        patterns: List[RecognizedPCDPattern] = []
        if len(holes) >= 3:
            # Group by diameter and axis
            d_groups: Dict[Tuple[float, Tuple[float, float, float]], List[RecognizedHole]] = {}
            for h in holes:
                key = (round(h.diameter, 1), (round(abs(h.axis[0]), 2), round(abs(h.axis[1]), 2), round(abs(h.axis[2]), 2)))
                d_groups.setdefault(key, []).append(h)

            pat_idx = 1
            for key, grp in d_groups.items():
                if len(grp) >= 3:
                    # Check distance from overall bounding box center in plane perpendicular to axis
                    pts = np.array([h.position for h in grp])
                    axis_vec = np.array(grp[0].axis)
                    center_guess = np.mean(pts, axis=0)
                    radii = np.linalg.norm(pts - center_guess, axis=1)
                    mean_r = float(np.mean(radii))
                    if mean_r > 5.0 and np.std(radii) < 0.5:
                        # Valid circle PCD
                        patterns.append(RecognizedPCDPattern(
                            pattern_id=f"pcd_pattern_{pat_idx}",
                            count=len(grp),
                            hole_diameter=grp[0].diameter,
                            pcd_diameter=round(mean_r * 2.0, 2),
                            center=(float(center_guess[0]), float(center_guess[1]), float(center_guess[2])),
                            axis=grp[0].axis,
                            hole_ids=[h.hole_id for h in grp],
                        ))
                        pat_idx += 1

        return ClassifiedFeatures(
            base_solid=base_solid,
            holes=holes,
            pcd_patterns=patterns,
            planar_face_count=len(planar_faces),
            cylindrical_face_count=len(cylindrical_faces),
            other_face_count=other_faces,
        )
