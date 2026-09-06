"""
cadi_saml.backend.occt_primitives
==================================
OpenCASCADE B-Rep primitive shape generators.
Provides clean topological construction of standard solids: box, cylinder, sphere, cone, pipe.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

try:
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeSphere,
        BRepPrimAPI_MakeCone,
        BRepPrimAPI_MakeTorus,
    )
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


def make_box_primitive(
    length: float,
    width: float,
    height: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Any:
    """Builds a solid Box with given dimensions and origin corner."""
    if not HAS_OCP:
        raise RuntimeError("OpenCASCADE (OCP) is required for geometric modeling.")
    pnt = gp_Pnt(float(origin[0]), float(origin[1]), float(origin[2]))
    return BRepPrimAPI_MakeBox(pnt, float(length), float(width), float(height)).Solid()


def make_cylinder_primitive(
    radius: float,
    height: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> Any:
    """Builds an axial cylinder solid."""
    if not HAS_OCP:
        raise RuntimeError("OpenCASCADE (OCP) is required for geometric modeling.")
    pnt = gp_Pnt(float(origin[0]), float(origin[1]), float(origin[2]))
    dir_vec = gp_Dir(float(direction[0]), float(direction[1]), float(direction[2]))
    ax = gp_Ax2(pnt, dir_vec)
    return BRepPrimAPI_MakeCylinder(ax, float(radius), float(height)).Solid()


def make_sphere_primitive(
    radius: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Any:
    """Builds a solid sphere centered at origin."""
    if not HAS_OCP:
        raise RuntimeError("OpenCASCADE (OCP) is required for geometric modeling.")
    pnt = gp_Pnt(float(origin[0]), float(origin[1]), float(origin[2]))
    return BRepPrimAPI_MakeSphere(pnt, float(radius)).Solid()


def make_cone_primitive(
    r1: float,
    r2: float,
    height: float,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> Any:
    """Builds a conical solid or truncated cone."""
    if not HAS_OCP:
        raise RuntimeError("OpenCASCADE (OCP) is required for geometric modeling.")
    pnt = gp_Pnt(float(origin[0]), float(origin[1]), float(origin[2]))
    dir_vec = gp_Dir(float(direction[0]), float(direction[1]), float(direction[2]))
    ax = gp_Ax2(pnt, dir_vec)
    return BRepPrimAPI_MakeCone(ax, float(r1), float(r2), float(height)).Solid()
