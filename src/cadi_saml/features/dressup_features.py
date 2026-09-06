"""
Dress-up Features for CADI-SAML.
Implements Fillet and Chamfer features using OCP.
"""

from typing import Any, Dict, List, Optional, Tuple
from cadi_saml.features.feature_base import Feature

try:
    import OCP.BRepFilletAPI as BRepFilletAPI
    import OCP.TopExp as TopExp
    import OCP.TopAbs as TopAbs
    import OCP.TopoDS as TopoDS
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


class FilletFeature(Feature):
    """
    Rounds edges of parent solid.
    """

    def __init__(
        self,
        parent: Feature,
        radius: float = 1.0,
        edge_filter: Optional[str] = "all",
        name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {
            "radius": float(radius),
            "edge_filter": edge_filter,
            **kwargs,
        }
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"FilletFeature '{self.name}' requires a parent solid.")

        r = self.get_input("radius")
        if not HAS_OCP:
            return {"type": "fillet", "radius": r, "parent": parent_shape}

        fillet_op = BRepFilletAPI.BRepFilletAPI_MakeFillet(parent_shape)
        exp = TopExp.TopExp_Explorer(parent_shape, TopAbs.TopAbs_EDGE)
        count = 0
        while exp.More():
            edge = TopoDS.TopoDS.Edge_s(exp.Current())
            try:
                fillet_op.Add(r, edge)
                count += 1
            except Exception:
                pass
            exp.Next()

        if count > 0:
            try:
                fillet_op.Build()
                if fillet_op.IsDone():
                    return fillet_op.Shape()
            except Exception:
                pass

        return parent_shape


class ChamferFeature(Feature):
    """
    Applies planar chamfer bevel to parent solid edges.
    """

    def __init__(
        self,
        parent: Feature,
        distance: float = 1.0,
        name: Optional[str] = None,
        **kwargs,
    ):
        inputs = {"distance": float(distance), **kwargs}
        super().__init__(name=name, parent=parent, inputs=inputs)

    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        if parent_shape is None:
            raise ValueError(f"ChamferFeature '{self.name}' requires a parent solid.")

        d = self.get_input("distance")
        if not HAS_OCP:
            return {"type": "chamfer", "distance": d, "parent": parent_shape}

        chamfer_op = BRepFilletAPI.BRepFilletAPI_MakeChamfer(parent_shape)
        exp = TopExp.TopExp_Explorer(parent_shape, TopAbs.TopAbs_EDGE)
        count = 0
        while exp.More():
            edge = TopoDS.TopoDS.Edge_s(exp.Current())
            try:
                chamfer_op.Add(d, edge)
                count += 1
            except Exception:
                pass
            exp.Next()

        if count > 0:
            try:
                chamfer_op.Build()
                if chamfer_op.IsDone():
                    return chamfer_op.Shape()
            except Exception:
                pass

        return parent_shape
