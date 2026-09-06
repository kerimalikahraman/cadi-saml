"""
Geometry Query and Introspection API for CADI-SAML.
Enables LLMs and agents to query B-Rep topological features, measure distances, and inspect properties.
"""

from typing import Any, Dict, List, Optional, Tuple
import math

try:
    import OCP.GProp as GProp
    import OCP.BRepGProp as BRepGProp
    import OCP.BRepBndLib as BRepBndLib
    import OCP.Bnd as Bnd
    import OCP.TopExp as TopExp
    import OCP.TopAbs as TopAbs
    import OCP.BRepAdaptor as BRepAdaptor
    import OCP.GeomAbs as GeomAbs
    import OCP.BRepExtrema as BRepExtrema
    import OCP.gp as gp
    import OCP.TopoDS as TopoDS
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


def inspect_part_geometry(shape: Any, name: str = "part") -> Dict[str, Any]:
    """Calculates volumetric, bounding, and topological properties of a B-Rep shape."""
    if not HAS_OCP or shape is None or shape.IsNull():
        return {"name": name, "status": "no_geometry", "volume_mm3": 0.0, "face_count": 0}

    vol_props = GProp.GProp_GProps()
    BRepGProp.BRepGProp.VolumeProperties_s(shape, vol_props)
    vol = vol_props.Mass()
    com = vol_props.CentreOfMass()

    surf_props = GProp.GProp_GProps()
    BRepGProp.BRepGProp.SurfaceProperties_s(shape, surf_props)
    surf_area = surf_props.Mass()

    bbox = Bnd.Bnd_Box()
    BRepBndLib.BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dx = xmax - xmin
    dy = ymax - ymin
    dz = zmax - zmin

    # Count faces
    num_faces = 0
    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    while exp.More():
        num_faces += 1
        exp.Next()

    return {
        "name": name,
        "volume_mm3": round(vol, 4),
        "surface_area_mm2": round(surf_area, 4),
        "center_of_mass": (round(com.X(), 4), round(com.Y(), 4), round(com.Z(), 4)),
        "bounding_box": {
            "min": (round(xmin, 4), round(ymin, 4), round(zmin, 4)),
            "max": (round(xmax, 4), round(ymax, 4), round(zmax, 4)),
            "dx": round(dx, 4),
            "dy": round(dy, 4),
            "dz": round(dz, 4),
        },
        "face_count": num_faces,
        "is_manifold": vol > 1e-6,
    }


def find_faces(
    shape: Any,
    normal: Optional[Tuple[float, float, float]] = None,
    face_type: Optional[str] = None,
    tolerance_deg: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Finds and filters faces on a solid by normal direction or geometric surface type.
    """
    if not HAS_OCP or shape is None or shape.IsNull():
        return []

    matched_faces: List[Dict[str, Any]] = []
    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    idx = 0

    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        surf_type = adaptor.GetType()

        type_str = "other"
        if surf_type == GeomAbs.GeomAbs_Plane:
            type_str = "plane"
        elif surf_type == GeomAbs.GeomAbs_Cylinder:
            type_str = "cylinder"
        elif surf_type == GeomAbs.GeomAbs_Sphere:
            type_str = "sphere"
        elif surf_type == GeomAbs.GeomAbs_Torus:
            type_str = "torus"

        face_normal = None
        if surf_type == GeomAbs.GeomAbs_Plane:
            pln = adaptor.Plane()
            axis = pln.Axis().Direction()
            face_normal = (round(axis.X(), 4), round(axis.Y(), 4), round(axis.Z(), 4))

        matched = True
        if face_type and type_str != face_type.lower():
            matched = False

        if normal and face_normal:
            mag = math.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2) or 1.0
            nx, ny, nz = normal[0]/mag, normal[1]/mag, normal[2]/mag
            dot = face_normal[0]*nx + face_normal[1]*ny + face_normal[2]*nz
            dot = max(-1.0, min(1.0, dot))
            ang_deg = math.degrees(math.acos(dot))
            if ang_deg > tolerance_deg:
                matched = False

        if matched:
            matched_faces.append({
                "face_index": idx,
                "type": type_str,
                "normal": face_normal,
            })

        idx += 1
        exp.Next()

    return matched_faces


def find_holes(shape: Any, diameter: Optional[float] = None, tolerance_mm: float = 0.5) -> List[Dict[str, Any]]:
    """
    Detects cylindrical boreholes and internal hole features on a solid.
    """
    if not HAS_OCP or shape is None or shape.IsNull():
        return []

    holes: List[Dict[str, Any]] = []
    exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    idx = 0

    while exp.More():
        face = TopoDS.TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs.GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            radius = cyl.Radius()
            dia = radius * 2.0
            loc = cyl.Location()
            axis = cyl.Axis().Direction()

            matches = True
            if diameter is not None and abs(dia - diameter) > tolerance_mm:
                matches = False

            if matches:
                holes.append({
                    "hole_index": idx,
                    "diameter": round(dia, 4),
                    "radius": round(radius, 4),
                    "center": (round(loc.X(), 4), round(loc.Y(), 4), round(loc.Z(), 4)),
                    "axis": (round(axis.X(), 4), round(axis.Y(), 4), round(axis.Z(), 4)),
                })
        idx += 1
        exp.Next()

    return holes


def measure_parts_distance(shape_a: Any, shape_b: Any) -> Dict[str, Any]:
    """
    Measures exact closest Euclidean distance and closest point pairs between two shapes.
    """
    if not HAS_OCP or shape_a is None or shape_b is None or shape_a.IsNull() or shape_b.IsNull():
        return {"distance": float("inf"), "closest_points": []}

    extrema = BRepExtrema.BRepExtrema_DistShapeShape(shape_a, shape_b)
    extrema.Perform()

    if not extrema.IsDone() or extrema.NbSolution() == 0:
        return {"distance": float("inf"), "closest_points": []}

    dist = extrema.Value()
    p1 = extrema.PointOnShape1(1)
    p2 = extrema.PointOnShape2(1)

    return {
        "distance": round(dist, 4),
        "point_a": (round(p1.X(), 4), round(p1.Y(), 4), round(p1.Z(), 4)),
        "point_b": (round(p2.X(), 4), round(p2.Y(), 4), round(p2.Z(), 4)),
        "is_touching": dist < 1e-4,
    }
