"""
Converts 2D Sketch Geometry into OpenCASCADE B-Rep Wires and Planar Faces for CADI-SAML.
"""

from typing import Any, List, Optional
import math

from cadi_saml.sketch.entities import SketchPoint, SketchLine, SketchCircle, SketchArc

try:
    from OCC.Core.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Circ
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
    HAS_OCC = True
except ImportError:
    HAS_OCC = False


def sketch_to_occt_wire(lines: List[SketchLine], z_plane: float = 0.0) -> Any:
    """
    Builds a closed TopoDS_Wire from an ordered loop of SketchLine entities.
    """
    if not HAS_OCC or not lines:
        return None

    wire_maker = BRepBuilderAPI_MakeWire()
    for l in lines:
        p1 = gp_Pnt(l.start.x, l.start.y, z_plane)
        p2 = gp_Pnt(l.end.x, l.end.y, z_plane)
        edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
        wire_maker.Add(edge)

    wire_maker.Build()
    if wire_maker.IsDone():
        return wire_maker.Wire()
    return None


def sketch_to_occt_face(lines: List[SketchLine], z_plane: float = 0.0) -> Any:
    """
    Builds a planar TopoDS_Face from a closed loop of sketch lines.
    """
    if not HAS_OCC:
        return None

    wire = sketch_to_occt_wire(lines, z_plane=z_plane)
    if wire is not None:
        face_maker = BRepBuilderAPI_MakeFace(wire, True)
        face_maker.Build()
        if face_maker.IsDone():
            return face_maker.Face()
    return None
