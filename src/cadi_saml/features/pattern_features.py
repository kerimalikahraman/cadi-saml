"""
Pattern and Symmetry Transformation Features for CADI-SAML using OCP.
Implements LinearPattern, CircularPattern, and Mirror features.
"""

from typing import Any, Dict, List, Optional, Tuple
import math
from cadi_saml.features.feature_base import Feature

try:
    import OCP.gp as gp
    import OCP.BRepBuilderAPI as BRepBuilder
    import OCP.BRepAlgoAPI as BRepAlgo
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


class LinearPatternFeature(Feature):
    """
    Duplicates a target feature linearly along a 3D vector.
    """

    def __init__(
        self,
        parent: Feature,
        direction: Tuple[float, float, float] = (1.0, 0.0, 0.0),
        spacing: float = 10.0,
        count: int = 2,
        name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {
            "direction": list(direction),
            "spacing": float(spacing),
            "count": int(count),
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"LinearPatternFeature '{self.name}' requires a parent solid.")

        dx, dy, dz = self.get_input("direction")
        spacing = self.get_input("spacing")
        count = self.get_input("count")

        if not HAS_OCP or count <= 1:
            return parent_shape

        mag = math.sqrt(dx**2 + dy**2 + dz**2) or 1.0
        ux, uy, uz = dx / mag, dy / mag, dz / mag

        accum_shape = parent_shape
        for i in range(1, count):
            trsf = gp.gp_Trsf()
            trsf.SetTranslation_s(gp.gp_Vec(ux * spacing * i, uy * spacing * i, uz * spacing * i))
            copy_shape = BRepBuilder.BRepBuilderAPI_Transform(parent_shape, trsf, True).Shape()
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(accum_shape, copy_shape)
            fuse_op.Build()
            if fuse_op.IsDone():
                accum_shape = fuse_op.Shape()

        return accum_shape


class CircularPatternFeature(Feature):
    """
    Duplicates a feature radially around a central axis.
    """

    def __init__(
        self,
        parent: Feature,
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        count: int = 4,
        total_angle_deg: float = 360.0,
        name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {
            "axis": list(axis),
            "center": list(center),
            "count": int(count),
            "total_angle_deg": float(total_angle_deg),
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"CircularPatternFeature '{self.name}' requires a parent solid.")

        count = self.get_input("count")
        tot_ang = self.get_input("total_angle_deg")
        cx, cy, cz = self.get_input("center")
        ax, ay, az = self.get_input("axis")

        if not HAS_OCP or count <= 1:
            return parent_shape

        step_angle = math.radians(tot_ang / count if tot_ang < 360.0 else tot_ang / count)
        rot_axis = gp.gp_Ax1(gp.gp_Pnt(cx, cy, cz), gp.gp_Dir(ax, ay, az))

        accum_shape = parent_shape
        for i in range(1, count):
            trsf = gp.gp_Trsf()
            trsf.SetRotation_s(rot_axis, step_angle * i)
            copy_shape = BRepBuilder.BRepBuilderAPI_Transform(parent_shape, trsf, True).Shape()
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(accum_shape, copy_shape)
            fuse_op.Build()
            if fuse_op.IsDone():
                accum_shape = fuse_op.Shape()

        return accum_shape


class MirrorFeature(Feature):
    """
    Mirrors a feature or solid across a symmetry plane.
    """

    def __init__(
        self,
        parent: Feature,
        plane_normal: Tuple[float, float, float] = (1.0, 0.0, 0.0),
        point_on_plane: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {
            "plane_normal": list(plane_normal),
            "point_on_plane": list(point_on_plane),
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"MirrorFeature '{self.name}' requires a parent solid.")

        if not HAS_OCP:
            return parent_shape

        nx, ny, nz = self.get_input("plane_normal")
        px, py, pz = self.get_input("point_on_plane")

        ax2 = gp.gp_Ax2(gp.gp_Pnt(px, py, pz), gp.gp_Dir(nx, ny, nz))
        trsf = gp.gp_Trsf()
        trsf.SetMirror_s(ax2)

        mirrored_shape = BRepBuilder.BRepBuilderAPI_Transform(parent_shape, trsf, True).Shape()
        fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, mirrored_shape)
        fuse_op.Build()
        if fuse_op.IsDone():
            return fuse_op.Shape()
        return parent_shape
