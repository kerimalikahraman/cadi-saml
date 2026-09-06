"""
cadi_saml.core.assembly_parts
==============================
PartReference, SafeEvaluator, and topological dependency analysis.
Enables fluent part configuration, provenance tracking, and formula evaluation.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from ..ir.nodes import PartNode

if TYPE_CHECKING:
    from .assembly import Assembly


class CircularDependencyError(ValueError):
    """Raised when parametric master variables contain a circular dependency loop."""
    pass


class SafeEvaluator:
    """AST-based whitelist evaluator for mathematical expressions in parametric variables."""

    ALLOWED_OPERATORS: Dict[type, Callable] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    ALLOWED_FUNCTIONS: Dict[str, Callable] = {
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "floor": math.floor,
        "ceil": math.ceil,
        "radians": math.radians,
        "degrees": math.degrees,
        "pi": lambda: math.pi,
    }

    @classmethod
    def evaluate(
        cls,
        expr: str,
        variables: Dict[str, Any],
        visiting: Optional[Set[str]] = None,
        call_chain: Optional[List[str]] = None,
    ) -> float:
        if visiting is None:
            visiting = set()
        if call_chain is None:
            call_chain = []

        cls.validate_static_dag(variables)

        try:
            tree = ast.parse(expr.strip(), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Syntax error in parametric formula '{expr}': {e}") from e

        return cls._eval_node(tree.body, variables, visiting, call_chain)

    @classmethod
    def validate_static_dag(cls, variables: Dict[str, Any]) -> None:
        cycle = cls.detect_cycles(variables)
        if cycle:
            chain = " -> ".join(cycle)
            raise CircularDependencyError(f"Static circular dependency detected in variable equations: {chain}")

    @classmethod
    def build_dependency_dag(cls, variables: Dict[str, Any]) -> Dict[str, Set[str]]:
        dag: Dict[str, Set[str]] = {k: set() for k in variables}
        for var_name, expr in variables.items():
            if isinstance(expr, str):
                try:
                    tree = ast.parse(expr.strip(), mode="eval")
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Name):
                            dep_name = node.id
                            if dep_name in variables and dep_name != var_name:
                                dag[var_name].add(dep_name)
                            elif dep_name == var_name:
                                dag[var_name].add(var_name)
                except Exception:
                    pass
        return dag

    @classmethod
    def detect_cycles(cls, variables: Dict[str, Any]) -> Optional[List[str]]:
        dag = cls.build_dependency_dag(variables)
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {k: WHITE for k in dag}

        def dfs(u: str, path: List[str]) -> Optional[List[str]]:
            colors[u] = GRAY
            for v in sorted(dag.get(u, [])):
                if v == u:
                    return [u, u]
                if colors.get(v, WHITE) == GRAY:
                    idx = path.index(v) if v in path else 0
                    return path[idx:] + [u, v]
                elif colors.get(v, WHITE) == WHITE:
                    res = dfs(v, path + [v])
                    if res:
                        return res
            colors[u] = BLACK
            return None

        for node in sorted(dag.keys()):
            if colors[node] == WHITE:
                cycle = dfs(node, [node])
                if cycle:
                    return cycle
        return None

    @classmethod
    def topological_sort(cls, variables: Dict[str, Any]) -> List[str]:
        cycle = cls.detect_cycles(variables)
        if cycle:
            raise CircularDependencyError(f"Cannot topologically sort circular variables: {' -> '.join(cycle)}")
        dag = cls.build_dependency_dag(variables)
        visited: Set[str] = set()
        order: List[str] = []

        def dfs(u: str):
            visited.add(u)
            for v in sorted(dag.get(u, [])):
                if v not in visited:
                    dfs(v)
            order.append(u)

        for k in sorted(dag.keys()):
            if k not in visited:
                dfs(k)
        return order

    @classmethod
    def _eval_node(
        cls,
        node: ast.AST,
        variables: Dict[str, Any],
        visiting: Set[str],
        call_chain: List[str],
    ) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported constant value: {node.value}")

        elif isinstance(node, ast.Name):
            name = node.id
            if name == "pi":
                return math.pi
            if name == "e":
                return math.e
            if name not in variables:
                raise KeyError(f"Undefined variable in formula: '{name}'")
            if name in visiting:
                cycle_chain = " -> ".join(call_chain + [name])
                raise CircularDependencyError(
                    f"Circular dependency detected in parametric formula: {cycle_chain}"
                )
            visiting.add(name)
            call_chain.append(name)
            val = variables[name]
            if isinstance(val, str):
                result = cls.evaluate(val, variables, visiting, call_chain)
            elif isinstance(val, (int, float)):
                result = float(val)
            else:
                raise ValueError(f"Variable '{name}' has non-numeric value: {val}")
            visiting.remove(name)
            call_chain.pop()
            return result

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed")
            left = cls._eval_node(node.left, variables, visiting, call_chain)
            right = cls._eval_node(node.right, variables, visiting, call_chain)
            return float(cls.ALLOWED_OPERATORS[op_type](left, right))

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError(f"Unary operator {op_type.__name__} is not allowed")
            operand = cls._eval_node(node.operand, variables, visiting, call_chain)
            return float(cls.ALLOWED_OPERATORS[op_type](operand))

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in cls.ALLOWED_FUNCTIONS:
                func = cls.ALLOWED_FUNCTIONS[node.func.id]
                args = [cls._eval_node(arg, variables, visiting, call_chain) for arg in node.args]
                return float(func(*args))
            raise ValueError(f"Function call '{getattr(node.func, 'id', str(node.func))}' is not permitted")

        else:
            raise ValueError(f"Unsupported expression construct: {type(node).__name__}")


class PartReference:
    """Wrapper around a PartNode enabling fluent port access and face selection."""

    def __init__(self, node: PartNode, assembly: Assembly):
        self._node = node
        self._assembly = assembly

    @property
    def name(self) -> str:
        return self._node.name

    @property
    def node(self) -> PartNode:
        return self._node

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._node.parameters

    @property
    def ports(self) -> Dict[str, Any]:
        return self._node.ports

    @property
    def spec_provenance(self) -> Dict[str, Dict[str, Any]]:
        return self._node.spec_provenance

    def track_provenance(
        self,
        parameter: str,
        source: str = "user",
        source_ref: Optional[str] = None,
        confidence: Optional[float] = None,
        original_value: Any = None,
        effective_value: Any = None,
        unit: str = "mm",
        transformation: str = "exact",
        details: Optional[Dict[str, Any]] = None,
    ) -> PartReference:
        self._node.track_provenance(
            parameter=parameter,
            source=source,
            source_ref=source_ref,
            confidence=confidence,
            original_value=original_value,
            effective_value=effective_value,
            unit=unit,
            transformation=transformation,
            details=details,
        )
        return self

    def port(self, port_name: str) -> str:
        """Returns selector formatted for port connection. Validates that the port is not stale."""
        port_node = self._node.get_port(port_name)
        if port_node and getattr(port_node, "status", "VALID") == "STALE":
            from .ports import StalePortError
            raise StalePortError(
                f"Port '{port_name}' on part '{self.name}' was invalidated by a subsequent geometric operation."
            )
        return f"{self.name}:port:{port_name}"

    def face(self, face_name: str) -> str:
        return f"{self.name}:face:{face_name}"

    def top_face(self) -> str:
        return self.face("top")

    def bottom_face(self) -> str:
        return self.face("bottom")

    def front_face(self) -> str:
        return self.face("front")

    def back_face(self) -> str:
        return self.face("back")

    def left_face(self) -> str:
        return self.face("left")

    def right_face(self) -> str:
        return self.face("right")

    def axis(self, axis_name: str = "z") -> str:
        return f"{self.name}:axis:{axis_name}"

    def add_fillet(self, edge: str, radius: float) -> PartReference:
        self._node.parameters.setdefault("fillets", []).append({"edge": edge, "radius": float(radius)})
        return self

    def add_chamfer(self, edge: str, distance: float) -> PartReference:
        self._node.parameters.setdefault("chamfers", []).append({"edge": edge, "distance": float(distance)})
        return self

    def add_hole(self, name: str, diameter: float, depth: float = 0.0, origin: tuple = (0.0, 0.0, 0.0), direction: tuple = (0.0, 0.0, -1.0)) -> PartReference:
        from .features import apply_hole
        apply_hole(self._assembly, self.name, diameter, depth, origin=origin, direction=direction)
        return self

    def add_pcd_holes(self, pcd: float, hole_diameter: float, num_holes: int = 4, depth: float = 0.0, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        from .features import apply_pcd_holes
        apply_pcd_holes(self._assembly, self.name, pcd, hole_diameter, num_holes, depth, origin=origin)
        return self

    def add_counterbore(self, cbore_dia: float, cbore_depth: float, hole_dia: float, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        from .features import apply_counterbore
        apply_counterbore(self._assembly, self.name, cbore_dia, cbore_depth, hole_dia, origin=origin)
        return self

    def add_countersink(self, csink_dia: float, angle_deg: float = 90.0, hole_dia: float = 6.0, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        from .features import apply_countersink
        apply_countersink(self._assembly, self.name, csink_dia, angle_deg, hole_dia, origin=origin)
        return self

    def add_keyway(self, keyway_name: Optional[str] = None, width: Optional[float] = None, depth: Optional[float] = None, length: float = 20.0, shaft_dia: float = 25.0, origin: tuple = (0.0, 0.0, 0.0), standard: Optional[str] = "DIN_6885_A") -> PartReference:
        """Cuts a standard parallel keyway (DIN 6885) into this shaft."""
        from ..standards.catalogs import lookup_din_6885
        from .features import apply_keyway
        std_b, std_h, std_t1, _ = lookup_din_6885(shaft_dia)
        w = float(width) if width is not None and width > 0 else std_b
        d = float(depth) if depth is not None and depth > 0 else std_t1
        apply_keyway(self._assembly, self.name, w, d, float(length), float(shaft_dia), origin=origin)
        return self

    def add_retaining_ring_groove(self, shaft_dia: float, groove_dia: float, width: float = 1.3, position_z: float = 10.0) -> PartReference:
        """Cuts an external snap ring groove (DIN 471) into this shaft."""
        from .features import apply_retaining_ring_groove
        apply_retaining_ring_groove(self._assembly, self.name, shaft_dia, groove_dia, width, position_z)
        return self

    def add_pocket(self, length: float, width: float, depth: float, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        """Cuts a rectangular milled pocket into this part."""
        from .features import apply_pocket
        apply_pocket(self._assembly, self.name, length, width, depth, origin=origin)
        return self

    def set_appearance(self, color: Tuple[float, float, float], material: Optional[str] = None) -> PartReference:
        self._node.color = color
        self._node.material = material
        return self
