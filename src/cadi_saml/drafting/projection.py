"""
cadi_saml.drafting.projection
=============================
OpenCASCADE HLR (Hidden Line Removal) projection engine.
Projects 3D shapes onto 2D view planes (Front, Top, Right, Isometric, etc.)
and extracts visible and hidden edge curves as 2D polylines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape


class ProjectorView(str, Enum):
    FRONT = "front"
    TOP = "top"
    RIGHT = "right"
    LEFT = "left"
    BACK = "back"
    BOTTOM = "bottom"
    ISO = "iso"


@dataclass
class HLRProjectionResult:
    """Extracted 2D curves for a single orthographic or perspective projection view."""
    view_name: str
    visible_segments: List[List[Tuple[float, float]]] = field(default_factory=list)
    hidden_segments: List[List[Tuple[float, float]]] = field(default_factory=list)
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0

    @property
    def width(self) -> float:
        return max(0.001, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        return max(0.001, self.max_y - self.min_y)


class HLRViewExtractor:
    """
    Extracts 2D hidden-line-removed vector geometry from 3D TopoDS_Shape models.
    """

    STANDARD_AXES: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = {
        # view_name: (Normal direction towards eye, Horizontal X direction on screen)
        "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
        "top": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
        "right": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        "left": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
        "back": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
        "bottom": ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
        "iso": ((1.0, 1.0, 1.0), (1.0, -1.0, 0.0)),
    }

    @classmethod
    def get_projector(cls, view_name: str) -> HLRAlgo_Projector:
        v = view_name.lower().strip()
        if v not in cls.STANDARD_AXES:
            v = "iso"
        norm_dir, x_dir = cls.STANDARD_AXES[v]

        normal = gp_Dir(*norm_dir)
        x_axis = gp_Dir(*x_dir)
        ax2 = gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), normal, x_axis)
        return HLRAlgo_Projector(ax2)

    @classmethod
    def extract_view(
        cls,
        shape: TopoDS_Shape,
        view_name: str = "iso",
        curve_samples: int = 24,
    ) -> HLRProjectionResult:
        """
        Runs OpenCASCADE HLR on the given shape for the specified view.
        Returns extracted visible and hidden 2D polyline segments and bounding box.
        """
        projector = cls.get_projector(view_name)

        algo = HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(projector)
        algo.Update()
        algo.Hide()

        hlr_to_shape = HLRBRep_HLRToShape(algo)

        # Compounds:
        # VCompound: visible sharp edges
        # Rg1LineVCompound: visible smooth edges (tangent lines)
        # HCompound: hidden sharp edges
        # Rg1LineHCompound: hidden smooth edges
        visible_shapes = [
            hlr_to_shape.VCompound(),
            hlr_to_shape.Rg1LineVCompound(),
            hlr_to_shape.OutLineVCompound(),
        ]
        hidden_shapes = [
            hlr_to_shape.HCompound(),
            hlr_to_shape.Rg1LineHCompound(),
            hlr_to_shape.OutLineHCompound(),
        ]

        visible_segs = []
        for s in visible_shapes:
            if s and not s.IsNull():
                visible_segs.extend(cls._extract_segments_from_compound(s, curve_samples))

        hidden_segs = []
        for s in hidden_shapes:
            if s and not s.IsNull():
                hidden_segs.extend(cls._extract_segments_from_compound(s, curve_samples))

        # Calculate bounding box
        all_pts = []
        for seg in visible_segs + hidden_segs:
            all_pts.extend(seg)

        if all_pts:
            xs = [p[0] for p in all_pts]
            ys = [p[1] for p in all_pts]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        else:
            min_x = min_y = max_x = max_y = 0.0

        return HLRProjectionResult(
            view_name=view_name,
            visible_segments=visible_segs,
            hidden_segments=hidden_segs,
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
        )

    @classmethod
    def _extract_segments_from_compound(
        cls,
        compound_shape: TopoDS_Shape,
        curve_samples: int,
    ) -> List[List[Tuple[float, float]]]:
        segments: List[List[Tuple[float, float]]] = []
        exp = TopExp_Explorer(compound_shape, TopAbs_EDGE)

        while exp.More():
            edge = TopoDS.Edge(exp.Current())
            try:
                adaptor = BRepAdaptor_Curve(edge)
                t0 = adaptor.FirstParameter()
                t1 = adaptor.LastParameter()

                if abs(t1 - t0) < 1e-7:
                    exp.Next()
                    continue

                if adaptor.GetType() == GeomAbs_Line:
                    p0 = adaptor.Value(t0)
                    p1 = adaptor.Value(t1)
                    segments.append([(p0.X(), p0.Y()), (p1.X(), p1.Y())])
                else:
                    # Discretize curved edge
                    num_pts = max(6, curve_samples)
                    poly = []
                    dt = (t1 - t0) / (num_pts - 1)
                    for i in range(num_pts):
                        t = t0 + i * dt
                        pt = adaptor.Value(t)
                        poly.append((pt.X(), pt.Y()))
                    segments.append(poly)
            except Exception:
                pass
            exp.Next()

        return segments
