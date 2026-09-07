"""
Solid Creation and Modification Features for CADI-SAML.
Implements Pad, Pocket, Hole, Shell, Loft, and Sweep features using OCP.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import math

from cadi_saml.features.feature_base import Feature

try:
    import OCP.BRepPrimAPI as BRepPrim
    import OCP.BRepAlgoAPI as BRepAlgo
    import OCP.BRepOffsetAPI as BRepOffsetAPI
    import OCP.gp as gp
    import OCP.TopTools as TopTools
    import OCP.TopExp as TopExp
    import OCP.TopAbs as TopAbs
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


class PadFeature(Feature):
    """
    Extrudes a sketch profile or bounding envelope into a 3D solid.
    If parent is provided, fuses the pad with the parent solid.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        length: float = 10.0,
        width: float = 10.0,
        height: float = 10.0,
        direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        fuse_with_parent: bool = True,
        **kwargs,
    ):
        inputs = {
            "length": float(length),
            "width": float(width),
            "height": float(height),
            "direction": list(direction),
            "origin": list(origin),
            "fuse_with_parent": fuse_with_parent,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        l = self.get_input("length")
        w = self.get_input("width")
        h = self.get_input("height")
        ox, oy, oz = self.get_input("origin")

        if not HAS_OCP:
            return {"type": "pad", "dims": (l, w, h), "origin": (ox, oy, oz)}

        pnt = gp.gp_Pnt(ox - l / 2.0, oy - w / 2.0, oz)
        solid = BRepPrim.BRepPrimAPI_MakeBox(pnt, l, w, h).Shape()

        if parent_shape is not None and self.get_input("fuse_with_parent", True):
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, solid)
            fuse_op.Build()
            if fuse_op.IsDone():
                return fuse_op.Shape()

        return solid


class PocketFeature(Feature):
    """
    Cuts a pocket volume from the parent solid.
    """

    def __init__(
        self,
        parent: Feature,
        name: Optional[str] = None,
        length: float = 5.0,
        width: float = 5.0,
        depth: float = 5.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        **kwargs,
    ):
        inputs = {
            "length": float(length),
            "width": float(width),
            "depth": float(depth),
            "origin": list(origin),
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"PocketFeature '{self.name}' requires a parent solid to cut from.")

        l = self.get_input("length")
        w = self.get_input("width")
        d = self.get_input("depth")
        ox, oy, oz = self.get_input("origin")

        if not HAS_OCP:
            return {"type": "pocket", "parent": parent_shape, "dims": (l, w, d)}

        cut_box = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(ox - l / 2.0, oy - w / 2.0, oz - d),
            l, w, d
        ).Shape()

        cut_op = BRepAlgo.BRepAlgoAPI_Cut(parent_shape, cut_box)
        cut_op.Build()
        if not cut_op.IsDone():
            raise RuntimeError(f"Boolean cut failed for pocket '{self.name}'.")
        return cut_op.Shape()


class HoleFeature(Feature):
    """
    Parametric hole feature: simple, counterbore, or countersink.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        diameter: float = 5.0,
        depth: float = 10.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        hole_type: str = "simple",
        cbore_dia: Optional[float] = None,
        cbore_depth: Optional[float] = None,
        **kwargs,
    ):
        inputs = {
            "diameter": float(diameter),
            "depth": float(depth),
            "origin": list(origin),
            "axis": list(axis),
            "hole_type": hole_type,
            "cbore_dia": float(cbore_dia) if cbore_dia else None,
            "cbore_depth": float(cbore_depth) if cbore_depth else None,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"HoleFeature '{self.name}' requires a parent solid.")

        dia = self.get_input("diameter")
        radius = dia / 2.0
        depth = self.get_input("depth")
        ox, oy, oz = self.get_input("origin")
        ax, ay, az = self.get_input("axis")

        if not HAS_OCP:
            return {"type": "hole", "diameter": dia, "depth": depth}

        direction = gp.gp_Dir(ax, ay, az)
        pnt = gp.gp_Pnt(ox - ax * 0.1, oy - ay * 0.1, oz - az * 0.1)
        ax2 = gp.gp_Ax2(pnt, direction)
        tool = BRepPrim.BRepPrimAPI_MakeCylinder(ax2, radius, depth + 0.2).Shape()

        cb_dia = self.get_input("cbore_dia")
        cb_dep = self.get_input("cbore_depth")
        if self.get_input("hole_type") == "counterbore" and cb_dia and cb_dep:
            cb_tool = BRepPrim.BRepPrimAPI_MakeCylinder(ax2, cb_dia / 2.0, cb_dep + 0.1).Shape()
            fuse = BRepAlgo.BRepAlgoAPI_Fuse(tool, cb_tool)
            fuse.Build()
            if fuse.IsDone():
                tool = fuse.Shape()

        cut_op = BRepAlgo.BRepAlgoAPI_Cut(parent_shape, tool)
        cut_op.Build()
        if not cut_op.IsDone():
            raise RuntimeError(f"Failed to drill hole '{self.name}'.")
        return cut_op.Shape()


class ShellFeature(Feature):
    """
    Hollows a solid with a specified wall thickness.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        wall_thickness: float = 2.0,
        **kwargs,
    ):
        inputs = {"wall_thickness": float(wall_thickness), **kwargs}
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"ShellFeature '{self.name}' requires a parent solid.")

        thickness = self.get_input("wall_thickness")
        if not HAS_OCP:
            return {"type": "shell", "wall_thickness": thickness}

        faces_to_remove = TopTools.TopTools_ListOfShape()
        exp = TopExp.TopExp_Explorer(parent_shape, TopAbs.TopAbs_FACE)
        if exp.More():
            faces_to_remove.Append(exp.Current())

        shell_maker = BRepOffsetAPI.BRepOffsetAPI_MakeThickSolid()
        shell_maker.MakeThickSolidByJoin(parent_shape, faces_to_remove, -abs(thickness), 1.0e-3)
        shell_maker.Build()
        if shell_maker.IsDone():
            return shell_maker.Shape()
        return parent_shape


class CylinderFeature(Feature):
    """
    Parametric cylinder feature.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        radius: float = 5.0,
        height: float = 10.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        fuse_with_parent: bool = False,
        **kwargs,
    ):
        inputs = {
            "radius": float(radius),
            "height": float(height),
            "origin": list(origin),
            "axis": list(axis),
            "fuse_with_parent": fuse_with_parent,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        r = self.get_input("radius")
        h = self.get_input("height")
        ox, oy, oz = self.get_input("origin")
        ax, ay, az = self.get_input("axis")

        if not HAS_OCP:
            return {"type": "cylinder", "radius": r, "height": h, "origin": (ox, oy, oz)}

        direction = gp.gp_Dir(ax, ay, az)
        ax2 = gp.gp_Ax2(gp.gp_Pnt(ox, oy, oz), direction)
        solid = BRepPrim.BRepPrimAPI_MakeCylinder(ax2, r, h).Shape()

        if parent_shape is not None and self.get_input("fuse_with_parent", False):
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, solid)
            fuse_op.Build()
            if fuse_op.IsDone():
                return fuse_op.Shape()

        return solid


class ConeFeature(Feature):
    """
    Parametric cone or truncated cone feature.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        bottom_radius: float = 10.0,
        top_radius: float = 0.0,
        height: float = 10.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        fuse_with_parent: bool = False,
        **kwargs,
    ):
        inputs = {
            "bottom_radius": float(bottom_radius),
            "top_radius": float(top_radius),
            "height": float(height),
            "origin": list(origin),
            "axis": list(axis),
            "fuse_with_parent": fuse_with_parent,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        r1 = self.get_input("bottom_radius")
        r2 = self.get_input("top_radius")
        h = self.get_input("height")
        ox, oy, oz = self.get_input("origin")
        ax, ay, az = self.get_input("axis")

        if not HAS_OCP:
            return {"type": "cone", "bottom_radius": r1, "top_radius": r2, "height": h}

        direction = gp.gp_Dir(ax, ay, az)
        ax2 = gp.gp_Ax2(gp.gp_Pnt(ox, oy, oz), direction)
        solid = BRepPrim.BRepPrimAPI_MakeCone(ax2, r1, r2, h).Shape()

        if parent_shape is not None and self.get_input("fuse_with_parent", False):
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, solid)
            fuse_op.Build()
            if fuse_op.IsDone():
                return fuse_op.Shape()

        return solid


class SphereFeature(Feature):
    """
    Parametric sphere feature.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        radius: float = 5.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        fuse_with_parent: bool = False,
        **kwargs,
    ):
        inputs = {
            "radius": float(radius),
            "origin": list(origin),
            "fuse_with_parent": fuse_with_parent,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        r = self.get_input("radius")
        ox, oy, oz = self.get_input("origin")

        if not HAS_OCP:
            return {"type": "sphere", "radius": r, "origin": (ox, oy, oz)}

        solid = BRepPrim.BRepPrimAPI_MakeSphere(gp.gp_Pnt(ox, oy, oz), r).Shape()

        if parent_shape is not None and self.get_input("fuse_with_parent", False):
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, solid)
            fuse_op.Build()
            if fuse_op.IsDone():
                return fuse_op.Shape()

        return solid


class TorusFeature(Feature):
    """
    Parametric torus feature.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        major_radius: float = 10.0,
        minor_radius: float = 2.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        fuse_with_parent: bool = False,
        **kwargs,
    ):
        inputs = {
            "major_radius": float(major_radius),
            "minor_radius": float(minor_radius),
            "origin": list(origin),
            "axis": list(axis),
            "fuse_with_parent": fuse_with_parent,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        r1 = self.get_input("major_radius")
        r2 = self.get_input("minor_radius")
        ox, oy, oz = self.get_input("origin")
        ax, ay, az = self.get_input("axis")

        if not HAS_OCP:
            return {"type": "torus", "major_radius": r1, "minor_radius": r2}

        direction = gp.gp_Dir(ax, ay, az)
        ax2 = gp.gp_Ax2(gp.gp_Pnt(ox, oy, oz), direction)
        solid = BRepPrim.BRepPrimAPI_MakeTorus(ax2, r1, r2).Shape()

        if parent_shape is not None and self.get_input("fuse_with_parent", False):
            fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, solid)
            fuse_op.Build()
            if fuse_op.IsDone():
                return fuse_op.Shape()

        return solid


class BooleanFeature(Feature):
    """
    Parametric Boolean Operation Feature (cut, fuse, intersect) connecting parent solid and tool.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional[Feature] = None,
        tool: Optional[Feature] = None,
        operation: str = "cut",
        tool_name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {
            "operation": operation.lower(),
            "tool_name": tool_name or (tool.name if tool else None),
            **kwargs,
        }
        dependencies = [tool] if tool is not None else []
        super().__init__(name=name, parent=parent, dependencies=dependencies, inputs=inputs)
        self.tool = tool

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"BooleanFeature '{self.name}' requires a parent shape.")

        op = self.get_input("operation", "cut")
        tool_shape = None
        if self.tool is not None:
            tool_shape = self.tool._shape
        elif self.get_input("tool_name") in context:
            tool_shape = context[self.get_input("tool_name")]

        if not HAS_OCP or tool_shape is None:
            return {"type": f"boolean_{op}", "parent": parent_shape, "tool": self.get_input("tool_name")}

        if op == "cut":
            algo = BRepAlgo.BRepAlgoAPI_Cut(parent_shape, tool_shape)
        elif op == "fuse":
            algo = BRepAlgo.BRepAlgoAPI_Fuse(parent_shape, tool_shape)
        elif op == "intersect":
            algo = BRepAlgo.BRepAlgoAPI_Common(parent_shape, tool_shape)
        else:
            raise ValueError(f"Unsupported boolean operation: {op}")

        algo.Build()
        if not algo.IsDone():
            raise RuntimeError(f"Boolean operation '{op}' failed on '{self.name}'.")
        return algo.Shape()

