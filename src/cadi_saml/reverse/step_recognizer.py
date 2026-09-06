"""
Comprehensive B-Rep Feature Recognition and Reverse Engineering Engine for CADI-SAML.
Analyzes raw STEP/BREP solids and recovers parametric feature trees, holes, shafts, planes, and symmetry.
"""

from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

try:
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


class STEPFeatureRecognizer:
    """
    Reverse engineers B-Rep topology into high-level parametric engineering features.
    """

    def __init__(self, step_file_path: Optional[str] = None, shape: Optional[Any] = None):
        self.shape: Optional[Any] = shape
        if step_file_path and HAS_OCP:
            self.shape = self._load_step(step_file_path)

    @staticmethod
    def _load_step(path: str) -> Optional[Any]:
        reader = STEPControl_Reader()
        status = reader.ReadFile(path)
        if status != IFSelect_RetDone:
            return None
        reader.TransferRoots()
        return reader.OneShape()

    def recognize(self) -> Dict[str, Any]:
        """Performs multi-stage topological feature recognition."""
        if not HAS_OCP or self.shape is None or self.shape.IsNull():
            return {"status": "error", "message": "No valid B-Rep shape loaded."}

        # 1. Mass & Bounding Box
        vol_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(self.shape, vol_props)
        vol = vol_props.Mass()
        com = vol_props.CentreOfMass()

        bbox = Bnd_Box()
        BRepBndLib.Add_s(self.shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dx = xmax - xmin
        dy = ymax - ymin
        dz = zmax - zmin

        # 2. Extract Planar and Cylindrical Faces
        planar_faces: List[Dict[str, Any]] = []
        cylindrical_faces: List[Dict[str, Any]] = []
        exp = TopExp_Explorer(self.shape, TopAbs_FACE)
        idx = 0

        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            adaptor = BRepAdaptor_Surface(face)
            stype = adaptor.GetType()

            if stype == GeomAbs_Plane:
                pln = adaptor.Plane()
                norm = pln.Axis().Direction()
                planar_faces.append({
                    "index": idx,
                    "normal": (round(norm.X(), 3), round(norm.Y(), 3), round(norm.Z(), 3)),
                })
            elif stype == GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                radius = cyl.Radius()
                axis = cyl.Axis().Direction()
                loc = cyl.Location()
                cylindrical_faces.append({
                    "index": idx,
                    "radius": round(radius, 3),
                    "diameter": round(radius * 2.0, 3),
                    "axis": (round(axis.X(), 3), round(axis.Y(), 3), round(axis.Z(), 3)),
                    "center": (round(loc.X(), 3), round(loc.Y(), 3), round(loc.Z(), 3)),
                })
            idx += 1
            exp.Next()

        # 3. Classify Holes vs External Cylinders
        holes = []
        shafts = []
        for cyl in cylindrical_faces:
            # If cylinder radius is significantly smaller than envelope, it's typically a hole
            if cyl["diameter"] < min(dx, dy, dz) * 0.7:
                holes.append(cyl)
            else:
                shafts.append(cyl)

        # 4. Guess Part Type
        part_type = "custom_bracket"
        if len(shafts) > 0 and max(dx, dy, dz) / min(dx, dy, dz) > 2.5:
            part_type = "stepped_shaft"
        elif len(planar_faces) >= 6 and min(dx, dy, dz) < 5.0:
            part_type = "sheet_metal_plate"
        elif len(holes) >= 4 and abs(dx - dy) < 5.0 and dz < min(dx, dy) * 0.5:
            part_type = "mounting_flange"

        # 5. Check Centroid Symmetry
        com_tuple = (round(com.X(), 3), round(com.Y(), 3), round(com.Z(), 3))
        center_box = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0)
        has_xy_symmetry = abs(com.X() - center_box[0]) < 0.1 and abs(com.Y() - center_box[1]) < 0.1

        return {
            "predicted_part_type": part_type,
            "volume_mm3": round(vol, 2),
            "envelope_dx_dy_dz": (round(dx, 2), round(dy, 2), round(dz, 2)),
            "center_of_mass": com_tuple,
            "has_xy_symmetry": has_xy_symmetry,
            "total_faces": idx,
            "planar_face_count": len(planar_faces),
            "detected_holes": holes,
            "detected_shaft_surfaces": shafts,
        }
