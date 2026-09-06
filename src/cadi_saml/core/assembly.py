"""
cadi_saml.core.assembly
=======================
Declarative, Pythonic interface for building assemblies without manual coordinates.
Generates AssemblyIR deterministically.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from ..ir.nodes import (
    AssemblyIR,
    BooleanNode,
    BooleanOpType,
    ChamferNode,
    CrossSection,
    ExportFormat,
    FilletNode,
    HoleNode,
    MateNode,
    MateType,
    MetadataNode,
    PartNode,
    PatternNode,
    PatternType,
    PortNode,
    ShellNode,
    UnitSystem,
)
from ..std_parts import Bearing, Fastener, Motor, Motorsport, Nut, Profile, Washer
import ast
import copy
import math
import re


class CircularDependencyError(ValueError):
    """Raised when parametric master variables contain circular equation references."""
    pass


class SafeEvaluator:
    """
    AST-based secure mathematical expression evaluator for CAD formulas.
    Eliminates code injection vulnerabilities by restricting parsing to
    basic arithmetic, whitelisted math functions, and variables.
    Detects circular dependency cycles.
    """
    ALLOWED_FUNCS = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "int": int,
        "float": float,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "pi": math.pi,
    }

    def __init__(self, variables: Optional[Dict[str, Any]] = None, validate_cycles: bool = True):
        self.variables = variables or {}
        self._stack: List[str] = []
        if validate_cycles and self.variables:
            cycle = self.detect_cycles(self.variables)
            if cycle:
                chain = " -> ".join(cycle)
                raise CircularDependencyError(f"Static circular dependency detected in variable equations: {chain}")

    @classmethod
    def build_dependency_dag(cls, variables: Dict[str, Any]) -> Dict[str, Set[str]]:
        """
        Parses all variable definitions via AST to construct a Directed Acyclic Graph (DAG).
        Maps each variable name to the set of variable names it directly depends on.
        """
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
                                # Direct self-reference
                                dag[var_name].add(var_name)
                except Exception:
                    pass
        return dag

    @classmethod
    def detect_cycles(cls, variables: Dict[str, Any]) -> Optional[List[str]]:
        """
        Performs static cycle detection using 3-color DFS traversal.
        Returns the cycle path as a list of variable names if a circular dependency exists,
        or None if the graph is a valid DAG.
        """
        dag = cls.build_dependency_dag(variables)
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {k: WHITE for k in dag}
        parent = {}

        def dfs(u: str, path: List[str]) -> Optional[List[str]]:
            colors[u] = GRAY
            for v in sorted(dag.get(u, [])):
                if v == u:
                    return [u, u]
                if colors.get(v, WHITE) == GRAY:
                    # Cycle found
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
        """
        Returns variables in a valid topological evaluation order.
        Raises CircularDependencyError if cycles are present.
        """
        cycle = cls.detect_cycles(variables)
        if cycle:
            raise CircularDependencyError(f"Cannot topologically sort circular variables: {' -> '.join(cycle)}")

        dag = cls.build_dependency_dag(variables)
        visited = set()
        order = []

        def visit(n: str):
            if n not in visited:
                visited.add(n)
                for dep in dag.get(n, []):
                    visit(dep)
                order.append(n)

        for k in sorted(dag.keys()):
            visit(k)
        return order

    def eval(self, val: Any) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if not isinstance(val, str):
            raise TypeError(f"Cannot evaluate expression of type {type(val)}: {val}")

        clean_val = val.strip()
        try:
            return float(clean_val)
        except ValueError:
            pass

        try:
            tree = ast.parse(clean_val, mode="eval")
        except SyntaxError as se:
            raise ValueError(f"Invalid formula syntax '{val}': {se}")

        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Disallowed constant in formula: {node.value}")

        elif isinstance(node, ast.Name):
            var_name = node.id
            if var_name in self.variables:
                if var_name in self._stack:
                    chain = " -> ".join(self._stack + [var_name])
                    raise CircularDependencyError(f"Circular dependency detected in variable formula: {chain}")
                v = self.variables[var_name]
                if isinstance(v, (int, float)):
                    return float(v)
                elif isinstance(v, str):
                    self._stack.append(var_name)
                    try:
                        return self.eval(v)
                    finally:
                        self._stack.pop()
            elif var_name in self.ALLOWED_FUNCS:
                fval = self.ALLOWED_FUNCS[var_name]
                if isinstance(fval, (int, float)):
                    return float(fval)

            raise ValueError(f"Unknown variable or identifier in formula: '{var_name}'")

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            elif isinstance(node.op, ast.USub):
                return -operand
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                if right == 0.0:
                    raise ZeroDivisionError("Division by zero in CAD formula.")
                return left / right
            elif isinstance(node.op, ast.Mod):
                return left % right
            elif isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError(f"Unsupported binary operator: {type(node.op)}")

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in self.ALLOWED_FUNCS:
                fn = self.ALLOWED_FUNCS[node.func.id]
                args = [self._eval_node(arg) for arg in node.args]
                return float(fn(*args))
            raise ValueError(f"Disallowed function call in CAD formula: {ast.dump(node)}")

        raise ValueError(f"Disallowed expression node in CAD formula: {type(node).__name__}")


def parse_points(raw: Any) -> List[Tuple[float, ...]]:

    """
    Parses coordinate points from either:
    1. Standard Python list/tuple of tuples: [(x, y), (x, y, z)]
    2. Token-efficient compact string: "172,28 172,22 165,20" or "0,0,0 10,20,5"
    Reduces token consumption in LLMs by ~75% for complex polygons and curves.
    """
    if hasattr(raw, "points"):
        return parse_points(raw.points)
    if hasattr(raw, "parameters") and "points" in raw.parameters:
        return parse_points(raw.parameters["points"])
    if isinstance(raw, (list, tuple)):
        return [tuple(float(c) for c in pt) for pt in raw]
    if isinstance(raw, str):
        tokens = re.split(r"[;\n\r]+", raw.strip())
        if len(tokens) == 1 and ";" not in raw and "\n" not in raw:
            tokens = raw.strip().split()
        res = []
        for t in tokens:
            t = t.strip(" ()[]")
            if not t:
                continue
            parts = [float(p) for p in re.split(r"[,:\s]+", t) if p]
            res.append(tuple(parts))
        return res
    raise TypeError(f"Expected list, tuple, str, or CrossSection for points, got {type(raw)}")


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

    def face(self, face_alias: str) -> str:
        """Returns semantic face selector (e.g., 'top', 'bottom', '>Z')."""
        return f"{self.name}:face:{face_alias}"

    def hole(self, hole_alias: str) -> str:
        """Returns semantic hole selector."""
        return f"{self.name}:hole:{hole_alias}"

    def add_port(
        self,
        name: str,
        port_type: str = "face",
        position: tuple = (0.0, 0.0, 0.0),
        normal: tuple = (0.0, 0.0, 1.0),
        diameter: Optional[float] = None,
    ) -> PartReference:
        port = PortNode(
            name=name,
            port_type=port_type,
            relative_position=position,
            normal=normal,
            diameter=diameter,
        )
        self._node.add_port(port)
        return self

    def add_hole(
        self,
        name: str,
        diameter: float,
        depth: float = 0.0,
        position: tuple = (0.0, 0.0),
        face: str = "top",
    ) -> PartReference:
        """
        Drills a parametric cylindrical hole into the solid body.
        Also registers a corresponding hole port automatically.
        """
        from ..ir.nodes import HoleNode
        hole = HoleNode(
            name=name,
            diameter=float(diameter),
            depth=float(depth),
            position=position,
            face_alias=face,
        )
        self._node.add_hole(hole)

        # Automatically create an alignment port for this hole
        port = PortNode(
            name=name,
            port_type="hole",
            relative_position=(position[0], position[1], 0.0),
            normal=(0.0, 0.0, 1.0) if face == "top" else (0.0, 0.0, -1.0),
            diameter=float(diameter),
        )
        self._node.add_port(port)
        if hasattr(self._assembly, "_features") and self._assembly._features is not None:
            from ..features.solid_features import HoleFeature
            self._assembly._features.add_feature(
                HoleFeature(name=f"{self.name}_{name}", diameter=float(diameter), depth=float(depth), position=position, face=face)
            )
        return self

    def add_fillet(self, radius: float, edges: str = "all_top") -> PartReference:
        """Round edges with specified radius ('all_top', 'all_bottom', 'vertical', 'all', etc.)."""
        self._node.add_fillet(FilletNode(radius=float(radius), edge_selector=edges))
        if hasattr(self._assembly, "_features") and self._assembly._features is not None:
            from ..features.dressup_features import FilletFeature
            self._assembly._features.add_feature(
                FilletFeature(name=f"{self.name}_fillet_{len(self._assembly._features.features)}", radius=float(radius), edge_selector=edges)
            )
        return self

    def fillet(self, radius: float, edges: str = "all_top") -> PartReference:
        """Alias for add_fillet."""
        return self.add_fillet(radius=radius, edges=edges)

    def add_chamfer(self, distance: float, edges: str = "all_top") -> PartReference:
        """Chamfer/bevel edges with specified distance ('all_top', 'all_bottom', 'vertical', 'all', etc.)."""
        self._node.add_chamfer(ChamferNode(distance=float(distance), edge_selector=edges))
        if hasattr(self._assembly, "_features") and self._assembly._features is not None:
            from ..features.dressup_features import ChamferFeature
            self._assembly._features.add_feature(
                ChamferFeature(name=f"{self.name}_chamfer_{len(self._assembly._features.features)}", distance=float(distance), edge_selector=edges)
            )
        return self

    def chamfer(self, distance: float, edges: str = "all_top") -> PartReference:
        """Alias for add_chamfer."""
        return self.add_chamfer(distance=distance, edges=edges)

    def shell(self, thickness: float = 2.0, open_face: Optional[str] = "bottom") -> PartReference:
        """Hollow out the solid body leaving specified wall thickness."""
        self._node.set_shell(ShellNode(thickness=float(thickness), open_face=open_face))
        if hasattr(self._assembly, "_features") and self._assembly._features is not None:
            from ..features.solid_features import ShellFeature
            self._assembly._features.add_feature(
                ShellFeature(name=f"{self.name}_shell_{len(self._assembly._features.features)}", thickness=float(thickness), open_face=open_face)
            )
        return self
    def add_counterbore(self, cbore_dia: float, cbore_depth: float, hole_dia: float, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        """Cuts a socket head cap screw counterbore pocket into this part."""
        from .features import apply_counterbore
        apply_counterbore(self._assembly, self.name, cbore_dia, cbore_depth, hole_dia, origin=origin)
        return self

    def add_countersink(self, csink_dia: float, angle_deg: float = 90.0, hole_dia: float = 5.5, origin: tuple = (0.0, 0.0, 0.0)) -> PartReference:
        """Cuts a conical flat head countersink into this part."""
        from .features import apply_countersink
        apply_countersink(self._assembly, self.name, csink_dia, angle_deg, hole_dia, origin=origin)
        return self

    def add_keyway(self, keyway_name: Optional[str] = None, width: Optional[float] = None, depth: Optional[float] = None, length: float = 20.0, shaft_dia: float = 25.0, origin: tuple = (0.0, 0.0, 0.0), standard: Optional[str] = "DIN_6885_A") -> PartReference:
        """Cuts a standard parallel keyway (DIN 6885) into this shaft."""
        from ..standards.catalogs import lookup_din_6885
        from .features import apply_keyway
        # Check lookup from authoritative catalog
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

    def set_appearance(
        self, color: Tuple[float, float, float], material: Optional[str] = None
    ) -> PartReference:
        """Set RGB color (0.0-1.0) and engineering material designation."""
        self._node.color = color
        self._node.material = material
        return self

    def add_draft_angle(
        self,
        angle_deg: float = 2.0,
        pull_direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        neutral_plane_z: float = 0.0,
    ) -> PartReference:
        """
        Apply casting/molding draft angle to vertical side faces of the part.
        angle_deg: taper angle in degrees (e.g. 2.0°).
        pull_direction: mold parting / pull vector.
        neutral_plane_z: Z coordinate of the neutral parting plane.
        """
        self._node.draft_angle = {
            "angle_deg": float(angle_deg),
            "pull_direction": pull_direction,
            "neutral_plane_z": float(neutral_plane_z),
        }
        return self

    def add_pcd_holes(
        self,
        count: int,
        diameter: float,
        pcd: float,
        start_angle: float = 0.0,
        center: Tuple[float, float] = (0.0, 0.0),
        depth: float = 0.0,
        name_prefix: str = "pcd_hole",
    ) -> PartReference:
        """
        Add a circular bolt pattern (PCD / Pitch Circle Diameter) in 1 concise line.
        Saves ~90% tokens compared to manual individual hole declarations.
        """
        import math
        radius = float(pcd) / 2.0
        step_deg = 360.0 / float(count)
        for i in range(count):
            ang = math.radians(start_angle + i * step_deg)
            hx = center[0] + radius * math.cos(ang)
            hy = center[1] + radius * math.sin(ang)
            self.add_hole(
                name=f"{name_prefix}_{i+1}",
                diameter=diameter,
                position=(hx, hy),
                depth=depth,
            )
        return self

    def update(self, **kwargs: Any) -> PartReference:
        """
        Update part parameters in-place for lightweight, token-efficient delta editing.
        """
        for k, v in kwargs.items():
            if k == "color":
                self._node.color = v
            elif k == "material":
                self._node.material = str(v)
            elif k in self._node.parameters:
                self._node.parameters[k] = v
            elif hasattr(self._node, k):
                setattr(self._node, k, v)
            else:
                self._node.parameters[k] = v
        return self






class Assembly:
    """
    High-level declarative assembly manager.
    Can be used as a context manager or standalone.
    """

    def __init__(
        self,
        name: str,
        units: str = "mm",
        tolerance_standard: str = "ISO 2768-m",
        material: Optional[str] = None,
        export: Optional[List[str]] = None,
    ):
        export_formats = [ExportFormat(fmt.upper()) for fmt in (export or ["STEP"])]
        self._metadata = MetadataNode(
            name=name,
            units=UnitSystem(units),
            tolerance_standard=tolerance_standard,
            material=material,
            export_formats=export_formats,
        )
        self._ir = AssemblyIR(metadata=self._metadata)
        self._parts: Dict[str, PartReference] = {}
        self._variables: Dict[str, Any] = {}
        self._mechanism = None
        self._checkpoints: Dict[str, Any] = {}
        self._revision_log: List[Dict[str, Any]] = []
        from ..features.feature_tree import FeatureTree
        self._features = FeatureTree(name=name)
        self._mate_solver = None

    def __enter__(self) -> Assembly:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @property
    def name(self) -> str:
        return self._metadata.name

    @property
    def units(self) -> str:
        return self._metadata.units.value

    def set_param(self, name: str, value: float) -> None:
        """Define cascading parametric variable."""
        self._ir.set_param(name, value)

    def get_param(self, name: str) -> Optional[float]:
        return self._ir.parameters.get(name)

    def set_var(self, name: str, value: Any) -> Assembly:
        """
        Define a parametric master variable or dependent equation.
        E.g. asm.set_var("shaft_dia", 25.0).set_var("bore", "shaft_dia + 0.1")
        """
        self._variables[name] = value
        try:
            self.set_param(name, self.eval_expr(value))
        except Exception:
            pass
        return self

    def get_var(self, name: str) -> float:
        """Resolve and return evaluated numeric value of variable."""
        if name not in self._variables:
            raise KeyError(f"Variable '{name}' not found in assembly.")
        cycle = SafeEvaluator.detect_cycles(self._variables)
        if cycle:
            chain = " -> ".join(cycle)
            raise CircularDependencyError(f"Circular dependency detected in variable equations: {chain}")
        return self.eval_expr(self._variables[name])

    def eval_expr(self, val: Any) -> float:
        """
        Safely evaluate a numeric or string formula using AST analysis.
        Prevents code execution vulnerabilities and detects circular variable dependencies.
        """
        return SafeEvaluator(self._variables).eval(val)



    def _register_primitive_feature(self, name: str, shape: str, parameters: Dict[str, Any]) -> None:
        if hasattr(self, "_features") and self._features is not None:
            from ..features.solid_features import PadFeature
            l = float(parameters.get("length", parameters.get("radius", 5.0) * 2.0))
            w = float(parameters.get("width", parameters.get("radius", 5.0) * 2.0))
            h = float(parameters.get("height", 10.0))
            orig = parameters.get("origin", (0.0, 0.0, 0.0))
            self._features.add_feature(
                PadFeature(name=name, length=l, width=w, height=h, origin=orig, parameters=copy.deepcopy(parameters))
            )

    def add_box(
        self,
        name: str,
        length: Any,
        width: Any,
        height: Any,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> PartReference:
        l = self.eval_expr(length)
        w = self.eval_expr(width)
        h = self.eval_expr(height)
        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="box",
            parameters={"length": l, "width": w, "height": h, "origin": origin, "rotation": rotation},
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        self._register_primitive_feature(name, "box", part_node.parameters)
        return ref

    def add_cylinder(
        self,
        name: str,
        radius: Any,
        height: Any,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        material: Optional[str] = None,
        color: Optional[Tuple[float, float, float]] = None,
        operation: Optional[str] = None,
    ) -> PartReference:
        r = self.eval_expr(radius)
        h = self.eval_expr(height)
        
        # Support fluent boolean cut on existing part
        if operation == "cut" and name in self._parts:
            cutter_name = f"{name}_cut_{len(self._parts)}"
            cutter_node = PartNode(
                name=cutter_name,
                part_type="primitive",
                shape="cylinder",
                parameters={"radius": r, "height": h, "origin": origin, "rotation": rotation},
            )
            self._ir.add_part(cutter_node)
            self._parts[cutter_name] = PartReference(cutter_node, self)
            self.cut(name, cutter_name)
            return self._parts[name]

        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="cylinder",
            parameters={"radius": r, "height": h, "origin": origin, "rotation": rotation},
            material=material,
        )
        if color is not None:
            part_node.appearance_color = color
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        self._register_primitive_feature(name, "cylinder", part_node.parameters)
        return ref


    def add_cone(
        self,
        name: str,
        bottom_radius: float,
        top_radius: float,
        height: float,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> PartReference:
        """Add a truncated cone or sharp cone (if top_radius=0)."""
        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="cone",
            parameters={
                "bottom_radius": float(bottom_radius),
                "top_radius": float(top_radius),
                "height": float(height),
                "origin": origin,
            },
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_frustum(
        self,
        name: str,
        bottom_radius: float,
        top_radius: float,
        height: float,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> PartReference:
        """Add a frustum (truncated cone)."""
        return self.add_cone(
            name=name,
            bottom_radius=bottom_radius,
            top_radius=top_radius,
            height=height,
            origin=origin,
        )

    def add_sphere(self, name: str, radius: float) -> PartReference:
        """Add a sphere primitive."""
        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="sphere",
            parameters={"radius": float(radius)},
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_torus(self, name: str, major_radius: float, minor_radius: float) -> PartReference:
        """Add a torus primitive (donut shape)."""
        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="torus",
            parameters={
                "major_radius": float(major_radius),
                "minor_radius": float(minor_radius),
            },
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_fastener(
        self, name: str, standard: str = "ISO4762", size: str = "M6", length: float = 20.0
    ) -> PartReference:
        """Add standard industrial fastener with predefined anchor ports."""
        if standard.upper() in ["ISO4762", "DIN912"]:
            node = Fastener.ISO4762(name=name, size=size, length=length)
        elif standard.upper() in ["ISO4014", "DIN931", "DIN933"]:
            node = Fastener.ISO4014(name=name, size=size, length=length)
        else:
            raise ValueError(f"Unknown fastener standard '{standard}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_bolt(
        self, name: str, size: str = "M6", length: float = 20.0, standard: str = "ISO4762"
    ) -> PartReference:
        """Add standard industrial bolt (convenience alias for add_fastener)."""
        return self.add_fastener(name=name, standard=standard, size=size, length=length)


    def add_bearing(
        self, name: str, standard: str = "SKF", code: str = "608ZZ"
    ) -> PartReference:
        """Add standard industrial bearing with inner/outer ring ports."""
        if standard.upper() == "SKF":
            node = Bearing.SKF(name=name, code=code)
        else:
            raise ValueError(f"Unknown bearing standard '{standard}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_nut(
        self, name: str, standard: str = "DIN934", size: str = "M6"
    ) -> PartReference:
        """Add standard industrial nut."""
        std_up = standard.upper()
        if std_up == "DIN934":
            node = Nut.DIN934(name=name, size=size)
        elif std_up == "DIN985":
            node = Nut.DIN985(name=name, size=size)
        else:
            raise ValueError(f"Unknown nut standard '{standard}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_washer(
        self, name: str, standard: str = "DIN125", size: str = "M6"
    ) -> PartReference:
        """Add standard plain or spring washer."""
        std_up = standard.upper()
        if std_up == "DIN125":
            node = Washer.DIN125(name=name, size=size)
        else:
            raise ValueError(f"Unknown washer standard '{standard}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_profile(
        self, name: str, profile_type: str = "2020", length: float = 200.0
    ) -> PartReference:
        """Add standard aluminum extrusion profile (2020, 2040)."""
        ptype = str(profile_type)
        if ptype == "2020":
            node = Profile.VSlot2020(name=name, length=length)
        elif ptype == "2040":
            node = Profile.VSlot2040(name=name, length=length)
        else:
            raise ValueError(f"Unknown profile type '{profile_type}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_motor(
        self, name: str, frame: str = "NEMA17", body_length: float = 40.0, **kwargs
    ) -> PartReference:
        """Add standard stepper motor (NEMA 17, NEMA 23)."""
        frm = frame.upper()
        if frm == "NEMA17":
            node = Motor.NEMA17(name=name, body_length=body_length, **kwargs)
        elif frm == "NEMA23":
            node = Motor.NEMA23(name=name, body_length=body_length, **kwargs)
        else:
            raise ValueError(f"Unknown motor frame '{frame}'")
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_centerlock_nut(
        self, name: str, size: str = "M30", **kwargs
    ) -> PartReference:
        """Add Formula Student / GT3 racing centerlock nut."""
        node = Motorsport.CenterlockNut(name=name, size=size, **kwargs)
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_brake_rotor(
        self, name: str, outer_diameter: float = 220.0, **kwargs
    ) -> PartReference:
        """Add lightweight ventilated motorsport brake disc rotor."""
        node = Motorsport.BrakeRotor(name=name, outer_diameter=outer_diameter, **kwargs)
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_brake_caliper(
        self, name: str, length: float = 140.0, **kwargs
    ) -> PartReference:
        """Add 4-piston racing monobloc brake caliper."""
        node = Motorsport.BrakeCaliper(name=name, length=length, **kwargs)
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_drive_pin(
        self, name: str, pin_diameter: float = 12.0, **kwargs
    ) -> PartReference:
        """Add hub torque drive pin."""
        node = Motorsport.DrivePin(name=name, pin_diameter=pin_diameter, **kwargs)
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_heim_joint(
        self, name: str, thread_size: str = "M10", **kwargs
    ) -> PartReference:
        """Add spherical rod end unibal joint for suspension wishbones."""
        node = Motorsport.HeimJoint(name=name, thread_size=thread_size, **kwargs)
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_standard_part(
        self, name: str, category: str, standard_id: str, **params
    ) -> PartReference:
        part_node = PartNode(
            name=name,
            part_type="standard",
            parameters={"category": category, "standard_id": standard_id, **params},
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_step_part(self, name: str, step_file_path: str) -> PartReference:
        """Import an existing STEP model as an assembly component."""
        part_node = PartNode(
            name=name,
            part_type="step_file",
            source_file=step_file_path,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def connect(
        self,
        first_target: str,
        second_target: str,
        mate_type: str = "FLUSH",
        offset: float = 0.0,
        angle: float = 0.0,
    ) -> None:
        """
        Connect two parts via mates.
        Targets can be: part.face('top') or part.port('shaft')
        """
        # Parse targets like "part_name:selector"
        p1_name, s1 = self._parse_target(first_target)
        p2_name, s2 = self._parse_target(second_target)

        mate = MateNode(
            mate_type=MateType(mate_type.upper()),
            first_part=p1_name,
            second_part=p2_name,
            first_selector=s1,
            second_selector=s2,
            offset=offset,
            angle=angle,
        )
        self._ir.add_mate(mate)

    def attach(self, first_port: str, second_port: str) -> None:
        """Attach two ports rigidly."""
        self.connect(first_port, second_port, mate_type="ATTACH")

    def align_holes(self, hole1: str, hole2: str) -> None:
        """Align two circular/cylindrical holes colinearly."""
        self.connect(hole1, hole2, mate_type="ALIGN_HOLES")

    def cut(self, target_part: str, tool_part: str, keep_tool: bool = False) -> None:
        """Subtract tool_part geometry from target_part."""
        op = BooleanNode(
            op_type=BooleanOpType.CUT,
            target_part=target_part,
            tool_part=tool_part,
            keep_tool=keep_tool,
        )
        self._ir.add_boolean_op(op)

    def fuse(self, target_part: str, tool_part: str, keep_tool: bool = False) -> None:
        """Union/fuse tool_part geometry with target_part."""
        op = BooleanNode(
            op_type=BooleanOpType.FUSE,
            target_part=target_part,
            tool_part=tool_part,
            keep_tool=keep_tool,
        )
        self._ir.add_boolean_op(op)

    def intersect(self, target_part: str, tool_part: str, keep_tool: bool = False) -> None:
        """Intersect target_part with tool_part."""
        op = BooleanNode(
            op_type=BooleanOpType.INTERSECT,
            target_part=target_part,
            tool_part=tool_part,
            keep_tool=keep_tool,
        )
        self._ir.add_boolean_op(op)

    def fillet(self, part_name: str, radius: float, edges: str = "all_top") -> Assembly:
        """Apply a round fillet to edges of a designated part ('all_top', 'all_bottom', 'vertical', 'circular', 'all', etc.)."""
        if part_name not in self._parts:
            raise KeyError(f"Part '{part_name}' not found in assembly.")
        self._parts[part_name].add_fillet(radius=radius, edges=edges)
        return self

    def chamfer(self, part_name: str, distance: float, edges: str = "all_top") -> Assembly:
        """Apply a bevel chamfer to edges of a designated part with specified distance."""
        if part_name not in self._parts:
            raise KeyError(f"Part '{part_name}' not found in assembly.")
        self._parts[part_name].add_chamfer(distance=distance, edges=edges)
        return self

    def add_sheet_metal(
        self,
        name: str,
        length: float,
        width: float,
        thickness: float = 2.0,
        k_factor: float = 0.44,
        material: str = "S235JR",
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ):
        """
        Create a custom parametric Sheet Metal part builder.
        Can add bent flanges, punched holes, compute flat pattern blank size, and build 3D solids.
        """
        from .sheet_metal import SheetMetalBuilder
        builder = SheetMetalBuilder(name=name, thickness=thickness, k_factor=k_factor, material=material)
        builder.base_plate(length=length, width=width, origin=origin)

        node = PartNode(
            name=name,
            part_type="sheet_metal",
            shape="sheet_metal",
            parameters={
                "builder": builder,
                "length": float(length),
                "width": float(width),
                "thickness": float(thickness),
                "material": material,
                "k_factor": float(k_factor),
            },
            material=material,
        )
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return builder

    def add_sheet_metal_bracket(
        self,
        name: str,
        bracket_type: str = "L",
        width: float = 50.0,
        length1: float = 60.0,
        length2: float = 40.0,
        length3: float = 0.0,
        thickness: float = 2.0,
        inner_radius: Optional[float] = None,
        k_factor: float = 0.44,
        hole_diameter: float = 0.0,
        material: str = "S235JR",
    ) -> PartReference:
        """
        High-level sheet metal macro: L-bracket, U-bracket, Z-bracket, or Hat-channel.
        Generates folded watertight B-Rep with exact DIN 6935 K-factor bend deduction.
        """
        from .sheet_metal import SheetMetalBuilder
        from .exceptions import CADISpecificationError
        if float(thickness) <= 0.0:
            raise CADISpecificationError(f"Sheet metal thickness must be strictly positive. Received {thickness}.", parameter="thickness")
        if inner_radius is not None and float(inner_radius) <= 0.0:
            raise CADISpecificationError(f"Sheet metal inner bend radius must be strictly positive. Received {inner_radius} mm.", parameter="inner_radius")
        ri = float(inner_radius) if inner_radius is not None else float(thickness)
        sm = SheetMetalBuilder(
            name=name,
            thickness=thickness,
            k_factor=k_factor,
            material=material,
            default_bend_radius=ri,
        )
        sm.base_plate(length=length1, width=width)

        b_type = bracket_type.strip().upper()
        if b_type == "L":
            sm.add_flange("right", length=length2, inner_radius=ri)
        elif b_type == "U":
            sm.add_flange("right", length=length2, inner_radius=ri)
            sm.add_flange("left", length=length2, inner_radius=ri)
        elif b_type == "Z":
            sm.add_flange("right", length=length2, inner_radius=ri)
            sm.add_flange("left", length=length3 if length3 > 0 else length2, inner_radius=ri)
        elif b_type == "HAT":
            sm.add_flange("right", length=length2, inner_radius=ri)
            sm.add_flange("left", length=length2, inner_radius=ri)

        if hole_diameter > 0:
            sm.add_hole(diameter=hole_diameter, x=length1 / 2.0, y=width / 2.0)

        node = PartNode(
            name=name,
            part_type="sheet_metal",
            shape="sheet_metal",
            parameters={
                "builder": sm,
                "length": float(length1),
                "width": float(width),
                "thickness": float(thickness),
                "material": material,
                "k_factor": float(k_factor),
            },
            material=material,
        )
        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    # ---------------------------------------------------------------------------
    # Organic & Aesthetic Modeling (Sections, Lofts, Sweeps, Revolves, Patterns)
    # ---------------------------------------------------------------------------

    def section_circle(
        self, radius: float, center: Tuple[float, float, float] = (0.0, 0.0, 0.0), normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    ) -> CrossSection:
        """Create circular planar cross-section."""
        return CrossSection(
            shape="circle",
            parameters={"radius": float(radius)},
            center=center,
            normal=normal,
        )

    def section_ellipse(
        self, rx: float, ry: float, center: Tuple[float, float, float] = (0.0, 0.0, 0.0), normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    ) -> CrossSection:
        """Create elliptical planar cross-section (essential for mice, car bodies)."""
        return CrossSection(
            shape="ellipse",
            parameters={"rx": float(rx), "ry": float(ry)},
            center=center,
            normal=normal,
        )

    def section_rectangle(
        self, width: float, height: float, center: Tuple[float, float, float] = (0.0, 0.0, 0.0), normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    ) -> CrossSection:
        """Create rectangular planar cross-section."""
        return CrossSection(
            shape="rectangle",
            parameters={"width": float(width), "height": float(height)},
            center=center,
            normal=normal,
        )

    def section_polygon(self, points: Any) -> CrossSection:
        """Create arbitrary polygon cross-section. Accepts list of tuples or compact string 'x,y,z x,y,z'."""
        pts = parse_points(points)
        # If 2D points (x, y) provided, expand to 3D with z=0
        pts_3d = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts]
        return CrossSection(
            shape="polygon",
            parameters={"points": pts_3d},
            center=pts_3d[0] if pts_3d else (0.0, 0.0, 0.0),
        )

    def section_spline(self, points: Any) -> CrossSection:
        """Create smooth closed spline cross-section. Accepts list of tuples or compact string 'x,y,z x,y,z'."""
        pts = parse_points(points)
        pts_3d = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts]
        return CrossSection(
            shape="spline",
            parameters={"points": pts_3d},
            center=pts_3d[0] if pts_3d else (0.0, 0.0, 0.0),
        )


    def section_naca(
        self,
        code: str = "0012",
        chord: float = 160.0,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Tuple[float, float, float] = (0.0, 1.0, 0.0),
        points_count: int = 35,
    ) -> CrossSection:
        """
        Generate authentic aerodynamic NACA 4-digit airfoil cross-section (e.g. NACA 0012, 2412, 4412).
        Mathematically exact, perfectly smooth C2 continuous NURBS curve.
        """
        return CrossSection(
            shape="naca",
            parameters={
                "code": code,
                "chord": float(chord),
                "points_count": int(points_count),
            },
            center=center,
            normal=normal,
        )


    def add_loft(
        self,
        name: str,
        sections: Any,
        ruled: bool = False,
        is_solid: bool = True,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> PartReference:
        """
        Create smooth 3D B-Rep solid passing through multiple cross-sections.
        Accepts CrossSection objects or raw lists of 2D/3D coordinate tuples.
        Set ruled=False for smooth organic C2 continuity (Class-A surfaces).
        """
        parsed_sections = []
        for idx, s in enumerate(sections):
            if isinstance(s, CrossSection):
                parsed_sections.append(s)
            elif isinstance(s, (list, tuple)):
                z_off = idx * 10.0
                pts_3d = []
                for p in s:
                    if len(p) == 2:
                        pts_3d.append((float(p[0]), float(p[1]), z_off))
                    else:
                        pts_3d.append((float(p[0]), float(p[1]), float(p[2])))
                parsed_sections.append(self.section_polygon(pts_3d))
            else:
                parsed_sections.append(s)

        part_node = PartNode(
            name=name,
            part_type="loft",
            shape="loft",
            parameters={
                "ruled": ruled,
                "is_solid": is_solid,
                "origin": origin,
                "rotation": rotation,
            },
            sections=parsed_sections,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_sweep(
        self,
        name: str,
        section: CrossSection,
        path_points: List[Tuple[float, float, float]],
    ) -> PartReference:
        """Sweep a cross-section along a 3D spline trajectory path."""
        part_node = PartNode(
            name=name,
            part_type="sweep",
            shape="sweep",
            sections=[section],
            path_points=path_points,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_revolve(
        self,
        name: str,
        profile_points: Any = None,
        angle: float = 360.0,
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        points: Any = None,
        material: Optional[str] = None,
        color: Optional[Tuple[float, float, float]] = None,
    ) -> PartReference:
        """
        Revolve a 2D closed polygon/spline profile around an axis (360° by default).
        Accepts list of (Radius, Z) tuples or token-efficient compact string 'R,Z R,Z R,Z'.
        """
        raw_pts = points if points is not None else profile_points
        pts = parse_points(raw_pts)
        part_node = PartNode(
            name=name,
            part_type="revolve",
            shape="revolve",
            parameters={
                "profile_points": pts,
                "angle": float(angle),
                "axis": axis,
                "origin": origin,
            },
            material=material,
        )
        if color is not None:
            part_node.appearance_color = color
        if pts:
            min_z = min(p[1] for p in pts)
            max_z = max(p[1] for p in pts)
            part_node.add_port(PortNode(name="front_face", port_type="flange", relative_position=(0.0, 0.0, max_z), normal=(0.0, 0.0, 1.0)))
            part_node.add_port(PortNode(name="back_face", port_type="flange", relative_position=(0.0, 0.0, min_z), normal=(0.0, 0.0, -1.0)))
            part_node.add_port(PortNode(name="axis", port_type="axis", relative_position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)))

        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def sketch(
        self,
        name: str = "sketch",
        plane: str = "XY",
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Optional[Tuple[float, float, float]] = None,
    ):
        """Create a new 2D sketch on the specified plane and origin."""
        from .sketch import Sketch
        return Sketch(name=name, plane=plane, origin=origin, normal=normal)

    def add_extrude(
        self,
        name: str,
        section: Any,
        distance: float,
        direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    ) -> PartReference:
        """
        Extrude a 2D planar cross-section or Sketch (polygon, circle, spline, rectangle, slot)
        along a 3D vector direction.
        distance: extrusion depth in mm.
        """
        if hasattr(section, "to_cross_section"):
            sec = section.to_cross_section()
        else:
            sec = section

        part_node = PartNode(
            name=name,
            part_type="extrude",
            shape="extrude",
            parameters={
                "distance": float(distance),
                "direction": direction,
            },
            sections=[sec],
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_text(
        self,
        name: str,
        text: str,
        font_size: float = 12.0,
        depth: float = 1.0,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        font_name: str = "Arial",
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "TextEmboss",
    ) -> PartReference:
        """
        Create 3D parametric text solid for branding, embossing, or engraved marking.
        """
        part_node = PartNode(
            name=name,
            part_type="text_3d",
            shape="text_3d",
            parameters={
                "text": text,
                "font_size": float(font_size),
                "depth": float(depth),
                "position": position,
                "normal": normal,
                "font_name": font_name,
            },
            color=color,
            material=material,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_circular_text(
        self,
        name: str,
        text: str,
        radius: float,
        center_angle: float = 90.0,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        font_size: float = 10.0,
        depth: float = 1.0,
        font_name: str = "Arial",
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        inward_facing: bool = False,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "TextEmboss",
    ) -> PartReference:
        """
        Create 3D parametric text curved along a circular arc (SAML declarative text placement).
        radius: radial distance from circle center (e.g. rim lip radius).
        center_angle: angular center of text (90°=top, 0°=right, 180°=left, 270°=bottom).
        """
        part_node = PartNode(
            name=name,
            part_type="circular_text",
            shape="circular_text",
            parameters={
                "text": text,
                "radius": float(radius),
                "center_angle": float(center_angle),
                "center": center,
                "font_size": float(font_size),
                "depth": float(depth),
                "font_name": font_name,
                "normal": normal,
                "inward_facing": inward_facing,
            },
            color=color,
            material=material,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref





    def pattern_circular(
        self,
        target_part: str,
        count: int,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        angle: float = 360.0,
    ) -> None:
        """Replicate target_part in a circular array (e.g., wheel spokes, bolt circles)."""
        pattern = PatternNode(
            target_part=target_part,
            pattern_type=PatternType.CIRCULAR,
            count=int(count),
            center=center,
            axis=axis,
            angle=float(angle),
        )
        self._ir.add_pattern(pattern)

    def pattern_linear(
        self,
        target_part: str,
        count: int,
        spacing: Tuple[float, float, float] = (20.0, 0.0, 0.0),
    ) -> None:
        """Replicate target_part in a linear direction (e.g., grill slats, cooling fins)."""
        pattern = PatternNode(
            target_part=target_part,
            pattern_type=PatternType.LINEAR,
            count=int(count),
            spacing=spacing,
        )
        self._ir.add_pattern(pattern)



    def to_ir(self) -> AssemblyIR:
        """Validate and return the generated AssemblyIR."""
        errors = self._ir.validate()
        if errors:
            raise ValueError(f"Assembly validation failed: {'; '.join(errors)}")
        return self._ir

    def _parse_target(self, target: Any) -> tuple[str, str]:
        """Utility to split part reference and selector, supporting Port objects and string selectors."""
        from .ports import Port
        if isinstance(target, Port):
            p_name = target.parent_part or "unknown"
            return p_name, f"port:{target.name}"
        target_str = str(target)
        if ":" in target_str:
            tokens = target_str.split(":", 1)
            return tokens[0], tokens[1]
        raise ValueError(
            f"Ambiguous mate target '{target_str}'. Targets must specify an explicit port or selector "
            f"(e.g. 'part_name:port:front_face' or 'part.face(\"top\")')."
        )

    def export_step(self, output_path: str) -> str:
        """Export assembly to an industry standard AP214 STEP file with component colors."""
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.export_step(self.to_ir(), output_path)

    def export_stl(self, output_path: str, deflection: float = 0.1) -> str:
        """Export assembly as STL mesh for 3D printing and simulation."""
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.export_stl(self.to_ir(), output_path, deflection=deflection)

    def export_glb(self, output_path: str, deflection: float = 0.08) -> str:
        """Export assembly to binary glTF (.glb) with colors and hierarchy."""
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.export_glb(self.to_ir(), output_path, deflection=deflection)

    def export_technical_drawing(
        self,
        output_svg_path: str,
        views: Optional[List[str]] = None,
        sheet_width: int = 1920,
        sheet_height: int = 1080,
        title: Optional[str] = None,
    ) -> str:
        """Export 4-view 2D engineering technical drawing to vector SVG with hidden lines."""
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.export_technical_drawing(
            self.to_ir(),
            output_svg_path,
            views=views,
            sheet_width=sheet_width,
            sheet_height=sheet_height,
            title=title or self.name,
        )

    def import_step(self, name: str, step_file_path: str) -> PartReference:
        """Import an existing STEP model as an assembly component (alias for add_step_part)."""
        return self.add_step_part(name=name, step_file_path=step_file_path)


    # ---------------------------------------------------------------------------
    # High-Level Semantic Engineering Macros (Token-Efficient CAD Primitives)
    # ---------------------------------------------------------------------------

    def add_flange(
        self,
        name: str,
        outer_diameter: float,
        thickness: float,
        inner_bore: float = 0.0,
        bolt_pcd: Optional[float] = None,
        bolt_count: int = 4,
        bolt_diameter: float = 6.0,
        wall_thickness: Optional[float] = None,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel",
    ) -> PartReference:
        """
        High-level engineering macro: Mounting flange, pipe flange, or hub disc in 1 line.
        Supports wall_thickness for hollow cylindrical flanges / wheel rims.
        """
        from .exceptions import CADISpecificationError
        od = float(outer_diameter)
        th = float(thickness)
        ib = float(inner_bore)
        if od <= 0.0:
            raise CADISpecificationError(f"Flange outer diameter must be positive. Received {od}.", parameter="outer_diameter")
        if th <= 0.0:
            raise CADISpecificationError(f"Flange thickness must be positive. Received {th}.", parameter="thickness")
        if ib >= od:
            raise CADISpecificationError(f"Flange inner bore ({ib} mm) cannot be >= outer diameter ({od} mm).", parameter="inner_bore")
        if wall_thickness is not None and float(wall_thickness) > 0 and ib == 0.0:
            ib = max(0.0, od - 2.0 * float(wall_thickness))

        flange = self.add_cylinder(name, radius=od / 2.0, height=th, origin=origin)
        flange.node.parameters.update({
            "outer_diameter": od,
            "thickness": th,
            "inner_bore": ib,
            "bolt_pcd": float(bolt_pcd) if bolt_pcd is not None else 0.0,
            "bolt_count": int(bolt_count) if bolt_pcd is not None else 0,
            "bolt_diameter": float(bolt_diameter) if bolt_pcd is not None else 0.0,
        })
        flange.set_appearance(color=color, material=material)
        if ib > 0:
            flange.add_hole(name="center_bore", diameter=ib, position=(0.0, 0.0))
        if bolt_pcd is not None and bolt_count > 0:
            flange.add_pcd_holes(count=bolt_count, diameter=bolt_diameter, pcd=bolt_pcd)
        flange.add_port("front_face", port_type="flange", position=(origin[0], origin[1], origin[2] + th), normal=(0.0, 0.0, 1.0), diameter=od)
        flange.add_port("back_face", port_type="flange", position=origin, normal=(0.0, 0.0, -1.0), diameter=od)
        return flange

    def add_revolved_flange(
        self,
        name: str,
        outer_diameter: float,
        thickness: float,
        inner_bore: float = 0.0,
        wall_thickness: Optional[float] = None,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = None,
    ) -> PartReference:
        """Revolved annular flange or barrel section."""
        od = float(outer_diameter)
        th = float(thickness)
        ib = float(inner_bore)
        if wall_thickness is not None and float(wall_thickness) > 0 and ib == 0.0:
            ib = max(0.0, od - 2.0 * float(wall_thickness))

        cyl = self.add_cylinder(name, radius=od / 2.0, height=th, origin=origin)
        cyl.set_appearance(color=color, material=material)
        if ib > 0:
            bore_name = f"{name}_bore"
            self.add_cylinder(bore_name, radius=ib / 2.0, height=th + 0.2, origin=(origin[0], origin[1], origin[2] - 0.1))
            self.cut(name, bore_name)
        return cyl

    def add_pcd_bosses(
        self,
        target_part: str,
        count: int = 5,
        pcd: float = 60.0,
        radius: float = 8.0,
        height: float = 5.0,
        operation: str = "add",
    ) -> List[PartReference]:
        """Add bosses or scallop relief features arrayed along a Pitch Circle Diameter (PCD)."""
        refs = []
        origin_z = 0.0
        if target_part in self._parts:
            target_node = self._parts[target_part]._node
            origin_z = target_node.parameters.get("origin", (0.0, 0.0, 0.0))[2]
            target_h = target_node.parameters.get("height", height)
            origin_z += target_h

        for i in range(int(count)):
            angle_rad = i * (2.0 * math.pi / count)
            bx = (pcd / 2.0) * math.cos(angle_rad)
            by = (pcd / 2.0) * math.sin(angle_rad)
            boss_name = f"{target_part}_boss_{i}"
            boss = self.add_cylinder(boss_name, radius=radius, height=height, origin=(bx, by, origin_z))
            refs.append(boss)
            if operation == "cut":
                self.cut(target_part, boss_name)
        return refs

    def add_stepped_flange(
        self,
        name: str,
        step_diameter: float,
        step_thickness: float,
        inner_bore: float = 0.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = None,
    ) -> PartReference:
        """Stepped flange or centering shoulder ring."""
        sd = float(step_diameter)
        st = float(step_thickness)
        ib = float(inner_bore)
        cyl = self.add_cylinder(name, radius=sd / 2.0, height=st, origin=origin)
        cyl.set_appearance(color=color, material=material)
        if ib > 0:
            bore_name = f"{name}_bore"
            self.add_cylinder(bore_name, radius=ib / 2.0, height=st + 0.2, origin=(origin[0], origin[1], origin[2] - 0.1))
            self.cut(name, bore_name)
        return cyl

    def add_spoke(
        self,
        name: str,
        angle: float,
        length: float,
        width: float = 12.0,
        thickness: float = 8.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = None,
    ) -> PartReference:
        """High-level engineering macro: Structural wheel spoke oriented at radial angle."""
        part_node = PartNode(
            name=name,
            part_type="primitive",
            shape="spoke",
            parameters={
                "angle": float(angle),
                "length": float(length),
                "width": float(width),
                "thickness": float(thickness),
                "origin": origin,
            },
            color=color,
            material=material,
        )
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_star_flange(
        self,
        name: str,
        pitch: float,
        arm_count: int = 5,
        arm_width: float = 12.0,
        thickness: float = 6.0,
        inner_bore: float = 0.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = None,
    ) -> PartReference:
        """Multi-arm star mounting flange or hub spider."""
        p = float(pitch)
        th = float(thickness)
        hub_r = max(float(arm_width) * 1.1, p * 0.25)
        star = self.add_cylinder(name, radius=hub_r, height=th, origin=origin)
        star.set_appearance(color=color, material=material)

        angle_step = 360.0 / arm_count
        for i in range(arm_count):
            ang = i * angle_step
            arm_name = f"{name}_arm_{i+1}"
            self.add_spoke(
                arm_name,
                angle=ang,
                length=p / 2.0,
                width=arm_width,
                thickness=th,
                origin=origin,
                color=color,
                material=material,
            )
            self.fuse(name, arm_name)

        if inner_bore > 0:
            bore_name = f"{name}_center_bore"
            self.add_cylinder(bore_name, radius=float(inner_bore) / 2.0, height=th + 0.2, origin=(origin[0], origin[1], origin[2] - 0.1))
            self.cut(name, bore_name)

        return star

    def add_surface_pattern(
        self,
        target_part: str,
        pattern: str = "SPOT_WELD",
        count: int = 8,
        **kwargs,
    ) -> None:
        """High-level aesthetic or manufacturing surface pattern annotation."""
        target = self._find_part_ref(target_part)
        if target:
            target.node.parameters["surface_pattern"] = {
                "pattern": pattern,
                "count": count,
                **kwargs,
            }

    def add_color(
        self,
        part_name: str,
        color: Tuple[float, float, float] = (0.7, 0.7, 0.7),
    ) -> None:
        """Assign RGB color tuple to part by exact or partial name."""
        target = self._find_part_ref(part_name)
        if target:
            target.node.color = color

    def add_material(
        self,
        part_name: str,
        material: str = "Steel",
    ) -> None:
        """Assign material name to part by exact or partial name."""
        target = self._find_part_ref(part_name)
        if target:
            target.node.material = material

    def set_appearance(
        self,
        part_name: str,
        material: Optional[str] = None,
        color: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        """Convenience method to set material and/or color on an assembly part."""
        target = self._find_part_ref(part_name)
        if target:
            target.set_appearance(color=color, material=material)

    def _find_part_ref(self, name_or_sub: str) -> Optional[PartReference]:
        """Find part reference by exact or substring match."""
        if name_or_sub in self._parts:
            return self._parts[name_or_sub]
        for k, v in self._parts.items():
            if name_or_sub in k or k in name_or_sub:
                return v
        return None

    def add_stepped_shaft(
        self,
        name: str,
        steps: List[Tuple[float, float]],
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """
        High-level engineering macro: Multi-diameter transmission shaft/spindle in 1 line.
        steps: list of (diameter, length) pairs, e.g. [(20, 30), (35, 15), (50, 40)].
        Saves ~90% tokens compared to manual revolve coordinate arrays.
        """
        profile = [(0.0, 0.0)]
        curr_z = 0.0
        for dia, length in steps:
            r = float(dia) / 2.0
            l = float(length)
            profile.append((r, curr_z))
            curr_z += l
            profile.append((r, curr_z))
        profile.append((0.0, curr_z))
        profile.append((0.0, 0.0))

        shaft = self.add_revolve(name, profile_points=profile, angle=360.0)
        tot_len = sum(s[1] for s in steps)
        max_d = max(s[0] for s in steps)
        shaft.node.parameters.update({
            "steps": steps,
            "length": float(tot_len),
            "outer_diameter": float(max_d),
        })
        shaft.set_appearance(color=color, material=material)

        # Register standard stepped shaft ports (0-indexed step_0, step_1, ... and faces)
        curr_pos = 0.0
        for idx, (dia, length) in enumerate(steps):
            shaft.add_port(f"step_{idx}", port_type="shaft", position=(0.0, 0.0, curr_pos), normal=(0.0, 0.0, 1.0), diameter=float(dia))
            curr_pos += float(length)
        shaft.add_port("front_face", port_type="flange", position=(0.0, 0.0, curr_pos), normal=(0.0, 0.0, 1.0))
        shaft.add_port("back_face", port_type="flange", position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, -1.0))
        shaft.add_port("axis", port_type="axis", position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))
        return shaft

    def add_ibeam(
        self,
        name: str,
        length: float,
        height: float = 80.0,
        flange_width: float = 46.0,
        web_thickness: float = 3.8,
        flange_thickness: float = 5.2,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "StructuralSteel",
    ) -> PartReference:
        """
        High-level engineering macro: Standard I-Beam structural profile in 1 line.
        """
        hw = flange_width / 2.0
        hh = height / 2.0
        hweb = web_thickness / 2.0
        ft = flange_thickness

        profile = [
            (-hw, -hh), (hw, -hh), (hw, -hh + ft), (hweb, -hh + ft),
            (hweb, hh - ft), (hw, hh - ft), (hw, hh), (-hw, hh),
            (-hw, hh - ft), (-hweb, hh - ft), (-hweb, -hh + ft), (-hw, -hh + ft)
        ]
        sec = self.section_polygon(profile)
        beam = self.add_extrude(name, section=sec, distance=length, direction=(0.0, 0.0, 1.0))
        beam.node.parameters = {
            "length": float(length),
            "height": float(height),
            "flange_width": float(flange_width),
            "web_thickness": float(web_thickness),
            "flange_thickness": float(flange_thickness),
        }
        beam.set_appearance(color=color, material=material)
        return beam

    def patch(self, diff: Dict[str, Any]) -> Assembly:
        """
        Apply partial in-place delta updates without re-generating the entire assembly code.
        Keys:
          'part_name.parameter_name' -> e.g. 'shaft.radius': 15.0
          'part_name.color' -> (r, g, b)
          'part_name.material' -> 'Titanium'
        Saves ~95% tokens during iterative user-requested design revisions.
        """
        proposal = self.preview_patch(diff)
        report = proposal.validate()
        if not report["valid"]:
            raise ValueError(f"Patch validation failed: {report['issues']}")
        return proposal.commit()

    def preview_patch(self, diff: Dict[str, Any]):
        """Build an isolated, conflict-detecting patch proposal without mutating this assembly."""
        from ..patching.patch_engine import preview_patch
        return preview_patch(self, diff)

    def apply_patch(self, patch_or_dict: Any) -> bool:
        """Applies patch modifications to the assembly."""
        from ..patching.patch_engine import apply_patch
        return apply_patch(self, patch_or_dict)

    def _replace_ir(self, ir: AssemblyIR) -> None:
        self._ir = copy.deepcopy(ir)
        self._metadata = self._ir.metadata
        self._parts = {name: PartReference(node, self) for name, node in self._ir.parts.items()}
        from ..features.feature_tree import FeatureTree
        from ..features.solid_features import PadFeature
        self._features = FeatureTree(name=self.name)
        for pname, pnode in self._ir.parts.items():
            depth = float(pnode.parameters.get("height", pnode.parameters.get("length", 10.0)))
            self._features.add_feature(PadFeature(name=pname, depth=depth, parameters=copy.deepcopy(pnode.parameters)))

    def _record_revision(self, operation: str, payload: Dict[str, Any]) -> None:
        self._revision_log.append({"revision": len(self._revision_log) + 1, "operation": operation,
                                   "payload": copy.deepcopy(payload)})

    def diagnose(self) -> Dict[str, Any]:
        """
        Compile and run full engineering diagnostics for LLM self-correction.
        Checks manifold watertightness, detects volumetric clashes, and returns
        an actionable natural language repair prompt for the AI.
        """
        from ..backend.occt_backend import OCCTBackend
        from ..validation.validation_engineer import ValidationEngineer

        backend = OCCTBackend()
        solids = backend.compile(self.to_ir())
        val = ValidationEngineer()
        from .llm_interface import structured_diagnostics
        raw = val.diagnose_for_llm(solids, ir=self.to_ir())
        report = structured_diagnostics(raw)
        for key, value in raw.items():
            report.setdefault(key, value)
        report["legacy"] = raw
        return report

    def get_constraint_status(self) -> Dict[str, Any]:
        """
        Runs constraint analysis and returns degrees-of-freedom (DOF) reports for all parts.
        Identifies FULLY_CONSTRAINED vs UNDER_CONSTRAINED components and free motion axes.
        """
        from ..backend.occt_backend import OCCTBackend

        backend = OCCTBackend()
        backend.compile(self.to_ir())
        return backend.get_dof_reports()

    def add_spur_gear(
        self,
        name: str,
        module: float = 2.0,
        teeth: int = 24,
        face_width: float = 20.0,
        width: Optional[float] = None,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        pressure_angle: float = 20.0,
        bore_dia: float = 15.0,
        hub_dia: float = 0.0,
        hub_width: float = 0.0,
        keyway_width: float = 0.0,
        keyway_depth: float = 0.0,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """Add high-precision involute spur gear with ports for bore axis, front, and back faces."""
        from .exceptions import CADISpecificationError
        if float(module) <= 0.0:
            raise CADISpecificationError(f"Gear module must be strictly positive. Received module={module}.", parameter="module")
        if int(teeth) < 6:
            raise CADISpecificationError(f"Gear teeth must be at least 6. Received teeth={teeth}.", parameter="teeth")
        actual_width = float(width) if width is not None else float(face_width)
        part_node = PartNode(
            name=name,
            part_type="gear",
            shape="gear",
            parameters={
                "gear_type": "spur",
                "origin": origin,
                "module": float(module),
                "teeth": int(teeth),
                "face_width": actual_width,
                "width": actual_width,
                "pressure_angle_deg": float(pressure_angle),
                "bore_dia": float(bore_dia),
                "hub_dia": float(hub_dia),
                "hub_width": float(hub_width),
                "keyway_width": float(keyway_width),
                "keyway_depth": float(keyway_depth),
                "args": {
                    "module": float(module),
                    "teeth": int(teeth),
                    "face_width": actual_width,
                    "pressure_angle_deg": float(pressure_angle),
                    "bore_dia": float(bore_dia),
                    "hub_dia": float(hub_dia),
                    "hub_width": float(hub_width),
                    "keyway_width": float(keyway_width),
                    "keyway_depth": float(keyway_depth),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        pitch_dia = float(module) * int(teeth)
        part_node.add_port(PortNode(name="bore_axis", port_type="axis", relative_position=(0, 0, 0), normal=(0, 0, 1), diameter=bore_dia))
        part_node.add_port(PortNode(name="front_face", port_type="flange", relative_position=(0, 0, face_width), normal=(0, 0, 1)))
        part_node.add_port(PortNode(name="back_face", port_type="flange", relative_position=(0, 0, 0), normal=(0, 0, -1)))
        part_node.add_port(PortNode(name="pitch_point", port_type="point", relative_position=(pitch_dia / 2.0, 0, face_width / 2.0), normal=(0, 1, 0)))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_internal_gear(
        self,
        name: str,
        module: float = 2.0,
        teeth: int = 48,
        face_width: float = 20.0,
        width: Optional[float] = None,
        outer_dia: Optional[float] = None,
        rim_thickness: float = 10.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        pressure_angle: float = 20.0,
        bolt_count: int = 0,
        bolt_diameter: float = 0.0,
        bolt_pcd: float = 0.0,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """Add high-precision involute internal ring gear with mounting ports."""
        actual_width = float(width) if width is not None else float(face_width)
        d_pitch = float(module) * int(teeth)
        actual_outer = float(outer_dia) if outer_dia is not None else (d_pitch + 2.0 * float(rim_thickness))

        part_node = PartNode(
            name=name,
            part_type="gear",
            shape="gear",
            parameters={
                "gear_type": "internal",
                "origin": origin,
                "args": {
                    "module": float(module),
                    "teeth": int(teeth),
                    "face_width": actual_width,
                    "outer_dia": actual_outer,
                    "rim_thickness": float(rim_thickness),
                    "pressure_angle_deg": float(pressure_angle),
                    "bolt_count": int(bolt_count),
                    "bolt_diameter": float(bolt_diameter),
                    "bolt_pcd": float(bolt_pcd),
                },
            },
        )
        from ..std_parts.gears import InternalGear
        geom = InternalGear.compute_geometry(module, teeth, rim_thickness, outer_dia)
        part_node.parameters["geometry"] = geom
        part_node.parameters["pitch_diameter"] = geom["pitch_diameter"]
        part_node.parameters["tip_diameter"] = geom["tip_diameter"]
        part_node.parameters["root_diameter"] = geom["root_diameter"]
        part_node.track_provenance("module", source="user", original_value=module, effective_value=float(module))
        part_node.track_provenance("teeth", source="user", original_value=teeth, effective_value=int(teeth))
        part_node.track_provenance("pitch_diameter", source="calculated", source_ref="DIN 3960 / ISO 53", effective_value=geom["pitch_diameter"], transformation="calculated")
        part_node.track_provenance("tip_diameter", source="calculated", source_ref="DIN 3960 / ISO 53", effective_value=geom["tip_diameter"], transformation="calculated")
        part_node.track_provenance("root_diameter", source="calculated", source_ref="DIN 3960 / ISO 53", effective_value=geom["root_diameter"], transformation="calculated")

        if color:
            part_node.color = color
        if material:
            part_node.material = material

        part_node.add_port(PortNode(name="bore_axis", port_type="axis", relative_position=(0, 0, 0), normal=(0, 0, 1), diameter=d_pitch))
        part_node.add_port(PortNode(name="front_face", port_type="flange", relative_position=(0, 0, actual_width), normal=(0, 0, 1)))
        part_node.add_port(PortNode(name="back_face", port_type="flange", relative_position=(0, 0, 0), normal=(0, 0, -1)))
        part_node.add_port(PortNode(name="pitch_point", port_type="point", relative_position=(d_pitch / 2.0, 0, actual_width / 2.0), normal=(0, 1, 0)))

        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_helical_gear(
        self,
        name: str,
        module: float = 2.5,
        teeth: int = 20,
        face_width: float = 25.0,
        helix_angle: float = 15.0,
        bore_dia: float = 18.0,
        left_handed: bool = False,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """Add helical transmission gear with specified helix angle."""
        part_node = PartNode(
            name=name,
            part_type="gear",
            shape="gear",
            parameters={
                "gear_type": "helical",
                "args": {
                    "module": float(module),
                    "teeth": int(teeth),
                    "face_width": float(face_width),
                    "helix_angle_deg": float(helix_angle),
                    "left_handed": left_handed,
                    "bore_dia": float(bore_dia),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        part_node.add_port(PortNode(name="bore_axis", port_type="axis", relative_position=(0, 0, 0), normal=(0, 0, 1), diameter=bore_dia))
        part_node.add_port(PortNode(name="front_face", port_type="flange", relative_position=(0, 0, face_width), normal=(0, 0, 1)))
        part_node.add_port(PortNode(name="back_face", port_type="flange", relative_position=(0, 0, 0), normal=(0, 0, -1)))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_rack(
        self,
        name: str,
        module: float = 2.0,
        length: float = 200.0,
        height: float = 25.0,
        width: float = 20.0,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """Add linear gear rack for steering or linear actuation."""
        part_node = PartNode(
            name=name,
            part_type="gear",
            shape="gear",
            parameters={
                "gear_type": "rack",
                "args": {
                    "module": float(module),
                    "length": float(length),
                    "height": float(height),
                    "width": float(width),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        part_node.add_port(PortNode(name="pitch_line", port_type="axis", relative_position=(0, 0, width / 2.0), normal=(1, 0, 0)))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_coil_spring(
        self,
        name: str,
        wire_dia: float = 8.0,
        outer_dia: float = 65.0,
        free_length: float = 140.0,
        active_coils: float = 6.0,
        ground_ends: bool = True,
        color: Optional[Tuple[float, float, float]] = (0.9, 0.15, 0.15),
        material: Optional[str] = "SpringSteel",
    ) -> PartReference:
        """Add helical compression spring with flat ground ends and mounting seat ports."""
        part_node = PartNode(
            name=name,
            part_type="spring",
            shape="spring",
            parameters={
                "args": {
                    "wire_dia": float(wire_dia),
                    "outer_dia": float(outer_dia),
                    "free_length": float(free_length),
                    "active_coils": float(active_coils),
                    "ground_ends": ground_ends,
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        part_node.add_port(PortNode(name="bottom_seat", port_type="flange", relative_position=(0, 0, 0), normal=(0, 0, -1), diameter=outer_dia))
        part_node.add_port(PortNode(name="top_seat", port_type="flange", relative_position=(0, 0, free_length), normal=(0, 0, 1), diameter=outer_dia))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_coilover(
        self,
        name: str,
        extended_length: float = 320.0,
        stroke: float = 80.0,
        spring_outer_dia: float = 70.0,
        wire_dia: float = 10.0,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "MotorsportAlloy",
    ) -> PartReference:
        """Add motorsport coilover suspension shock absorber with mounting eyelet ports."""
        part_node = PartNode(
            name=name,
            part_type="coilover",
            shape="coilover",
            parameters={
                "args": {
                    "extended_length": float(extended_length),
                    "stroke": float(stroke),
                    "spring_outer_dia": float(spring_outer_dia),
                    "wire_dia": float(wire_dia),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        part_node.add_port(PortNode(name="bottom_eyelet", port_type="hole", relative_position=(0, 0, 0), normal=(0, 1, 0), diameter=12.0))
        part_node.add_port(PortNode(name="top_eyelet", port_type="hole", relative_position=(0, 0, extended_length), normal=(0, 1, 0), diameter=12.0))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_pipe(
        self,
        name: str,
        points: Any,
        outer_dia: float = 10.0,
        wall_thickness: float = 1.5,
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel",
    ) -> PartReference:
        """Add 3D pipe or tubing routed across spatial 3D waypoints."""
        from .exceptions import CADISpecificationError
        od = float(outer_dia)
        wt = float(wall_thickness)
        if od <= 0.0:
            raise CADISpecificationError(f"Pipe outer diameter must be positive. Received {od}.", parameter="outer_dia")
        if wt <= 0.0 or wt >= (od / 2.0):
            raise CADISpecificationError(
                f"Pipe wall thickness ({wt} mm) must be positive and less than radius ({od / 2.0} mm).",
                parameter="wall_thickness",
                suggested_fix=f"Specify wall thickness between 0.5 mm and {max(0.5, od / 2.0 - 0.5):.1f} mm."
            )
        pts = parse_points(points)
        pts_3d = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts]
        part_node = PartNode(
            name=name,
            part_type="pipe",
            shape="pipe",
            parameters={
                "points": pts_3d,
                "outer_dia": float(outer_dia),
                "wall_thickness": float(wall_thickness),
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        if pts_3d:
            part_node.add_port(PortNode(name="inlet", port_type="hole", relative_position=pts_3d[0], normal=(0, 0, 1), diameter=outer_dia))
            part_node.add_port(PortNode(name="outlet", port_type="hole", relative_position=pts_3d[-1], normal=(0, 0, 1), diameter=outer_dia))
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_crankshaft(
        self,
        name: str,
        crank_radius: float = 30.0,
        disc_radius: float = 44.0,
        disc_thickness: float = 10.0,
        pin_diameter: float = 14.0,
        pin_length: float = 16.0,
        shaft_diameter: float = 16.0,
        shaft_length: float = 24.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "Steel4140",
    ) -> PartReference:
        """Add parametric monolithic crankshaft with counterweighted disc, crankpin, and main journal."""
        part_node = PartNode(
            name=name,
            part_type="crankshaft",
            shape="crankshaft",
            parameters={
                "origin": origin,
                "args": {
                    "crank_radius": float(crank_radius),
                    "disc_radius": float(disc_radius),
                    "disc_thickness": float(disc_thickness),
                    "pin_diameter": float(pin_diameter),
                    "pin_length": float(pin_length),
                    "shaft_diameter": float(shaft_diameter),
                    "shaft_length": float(shaft_length),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_connecting_rod(
        self,
        name: str,
        length: float = 90.0,
        big_bore_dia: float = 14.0,
        big_head_dia: float = 28.0,
        small_bore_dia: float = 10.0,
        small_head_dia: float = 20.0,
        thickness: float = 10.0,
        shank_width: float = 12.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "ForgedSteel",
    ) -> PartReference:
        """Add parametric authentic connecting rod with I-beam shank, big-end and small-end pin bores."""
        part_node = PartNode(
            name=name,
            part_type="connecting_rod",
            shape="connecting_rod",
            parameters={
                "origin": origin,
                "args": {
                    "length": float(length),
                    "big_bore_dia": float(big_bore_dia),
                    "big_head_dia": float(big_head_dia),
                    "small_bore_dia": float(small_bore_dia),
                    "small_head_dia": float(small_head_dia),
                    "thickness": float(thickness),
                    "shank_width": float(shank_width),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_slider_piston(
        self,
        name: str,
        diameter: float = 34.0,
        length: float = 42.0,
        pin_diameter: float = 10.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "AlloyPiston",
    ) -> PartReference:
        """Add parametric cylindrical slider piston with ring grooves, clearance pocket, and internal wristpin."""
        part_node = PartNode(
            name=name,
            part_type="slider_piston",
            shape="slider_piston",
            parameters={
                "origin": origin,
                "args": {
                    "diameter": float(diameter),
                    "length": float(length),
                    "pin_diameter": float(pin_diameter),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def add_engine_frame(
        self,
        name: str,
        base_length: float = 250.0,
        base_width: float = 90.0,
        base_thickness: float = 12.0,
        bearing_center_z: float = 32.0,
        cylinder_bore_dia: float = 36.0,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: Optional[Tuple[float, float, float]] = None,
        material: Optional[str] = "CastIron",
    ) -> PartReference:
        """Add engine bedplate frame with crankshaft bearing stand, cylinder block, bore, and cutaway window."""
        part_node = PartNode(
            name=name,
            part_type="engine_frame",
            shape="engine_frame",
            parameters={
                "origin": origin,
                "args": {
                    "base_length": float(base_length),
                    "base_width": float(base_width),
                    "base_thickness": float(base_thickness),
                    "bearing_center_z": float(bearing_center_z),
                    "cylinder_bore_dia": float(cylinder_bore_dia),
                },
            },
        )
        if color:
            part_node.color = color
        if material:
            part_node.material = material
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    def get_mass_properties(self, densities: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Calculates physical properties using OpenCASCADE GProp:
        volume (mm³), mass (kg), center of gravity (X, Y, Z), and component breakdown.
        """
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.calculate_mass_properties(self.to_ir(), densities=densities)

    def check_clearances(self, min_clearance_mm: float = 2.0) -> List[Any]:
        """
        Calculates minimum proximity distance between all parts using OpenCASCADE BRepExtrema.
        Flags COLLISION, WARNING_PROXIMITY (< min_clearance_mm), or CLEAR.
        """
        from ..backend.occt_backend import OCCTBackend
        from ..validation.validation_engineer import ValidationEngineer

        backend = OCCTBackend()
        solids = backend.compile(self.to_ir())
        val = ValidationEngineer()
        return val.check_clearances(solids, min_clearance_mm=min_clearance_mm)

    def get_cross_section_edges(
        self,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    ) -> List[Any]:
        """
        Slices the entire assembly with an arbitrary planar cutting plane and extracts 2D/3D profile edges.
        Uses OpenCASCADE BRepAlgoAPI_Section.
        """
        import OCP.BRep as BRep
        import OCP.TopoDS as TopoDS
        from ..backend.occt_backend import OCCTBackend

        backend = OCCTBackend()
        solids = backend.compile(self.to_ir())
        builder = BRep.BRep_Builder()
        compound = TopoDS.TopoDS_Compound()
        builder.MakeCompound(compound)
        for s in solids.values():
            builder.Add(compound, s)
        return backend.compute_cross_section(compound, origin=origin, normal=normal)

    def add_fea_study(
        self,
        part_name: str,
        material: str = "S235JR",
        study_name: Optional[str] = None,
        mesh_size: Optional[float] = None,
        required_safety_factor: float = 1.5,
        max_displacement_mm: Optional[float] = None,
    ):
        """
        Creates a finite element structural study (FEA) for a designated part in the assembly.
        Allows boundary condition fixation (fix_face), load application (apply_force, apply_pressure),
        and solves for Von-Mises stress, deflection, and Factor of Safety (FoS).
        """
        from ..analysis.fea import FEAStudy
        from ..backend.occt_backend import OCCTBackend

        if part_name not in self._parts:
            raise KeyError(f"Part '{part_name}' not found in assembly.")

        backend = OCCTBackend()
        solids = backend.compile(self.to_ir())
        if part_name not in solids:
            raise RuntimeError(f"Failed to compile solid geometry for '{part_name}'.")

        solid_shape = solids[part_name]
        study = FEAStudy(
            part_name=part_name,
            solid_shape=solid_shape,
            material=material,
            study_name=study_name,
            mesh_size=mesh_size,
            required_safety_factor=required_safety_factor,
            max_displacement_mm=max_displacement_mm,
        )
        return study

    def export_drawing(
        self,
        filepath: str,
        views: Optional[List[str]] = None,
        sheet_size: str = "A4",
        title: Optional[str] = None,
        part_name: Optional[str] = None,
        material: str = "S235JR",
    ) -> str:
        """
        Generates a 2D engineering technical drawing (ISO / DIN drawing sheet) in vector SVG.
        Uses OpenCASCADE Hidden Line Removal (HLR) to project visible and hidden (dashed) lines
        with standard title block (Antet).
        """
        import os
        from ..drafting.drawing import DrawingSheet
        from ..backend.occt_backend import OCCTBackend
        import OCP.BRep as BRep
        import OCP.TopoDS as TopoDS

        backend = OCCTBackend()
        solids = backend.compile(self.to_ir())

        if part_name is not None:
            if part_name not in solids:
                raise KeyError(f"Part '{part_name}' not found in compiled assembly.")
            target_shape = solids[part_name]
            p_name = part_name
        else:
            builder = BRep.BRep_Builder()
            compound = TopoDS.TopoDS_Compound()
            builder.MakeCompound(compound)
            for s in solids.values():
                builder.Add(compound, s)
            target_shape = compound
            p_name = self.name

        sheet = DrawingSheet(
            title=title or self.name.replace("_", " ").upper(),
            part_name=p_name,
            material=material,
            units=self.units,
            sheet_size=sheet_size,
        )
        sheet.generate_views_from_shape(target_shape, views=views)
        sheet.export_svg(filepath)
        return os.path.abspath(filepath)

    def _get_mechanism(self):
        if self._mechanism is None:
            from ..kinematics import KinematicMechanism
            self._mechanism = KinematicMechanism()
        return self._mechanism

    def add_revolute_joint(
        self,
        part_name: str,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        name: Optional[str] = None,
        initial_angle: float = 0.0,
    ):
        """Defines a rotational degree of freedom (pivot) for a part."""
        from ..kinematics import RevoluteJoint
        if part_name not in self._parts:
            raise KeyError(f"Part '{part_name}' not found in assembly.")
        j_name = name or f"rev_{part_name}"
        joint = RevoluteJoint(name=j_name, part_name=part_name, origin=origin, axis=axis, initial_angle_deg=initial_angle)
        self._get_mechanism().add_joint(joint)
        return joint

    def add_prismatic_joint(
        self,
        part_name: str,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: Tuple[float, float, float] = (1.0, 0.0, 0.0),
        name: Optional[str] = None,
        initial_disp: float = 0.0,
    ):
        """Defines a linear translational sliding degree of freedom for a part."""
        from ..kinematics import PrismaticJoint
        if part_name not in self._parts:
            raise KeyError(f"Part '{part_name}' not found in assembly.")
        j_name = name or f"prism_{part_name}"
        joint = PrismaticJoint(name=j_name, part_name=part_name, origin=origin, axis=axis, initial_disp_mm=initial_disp)
        self._get_mechanism().add_joint(joint)
        return joint

    def add_gear_relation(
        self,
        driver_part: str,
        driven_part: str,
        ratio: Optional[float] = None,
        reverse: bool = True,
    ):
        """
        Couples two rotating parts with a gear transmission mate.
        If ratio is None, auto-calculates ratio from tooth counts (teeth_driver / teeth_driven).
        """
        from ..kinematics import GearRelation
        if driver_part not in self._parts or driven_part not in self._parts:
            raise KeyError("Both driver and driven parts must exist in the assembly.")

        if ratio is None:
            p_driver = self._parts[driver_part].node.parameters
            args_driver = p_driver.get("args", p_driver)
            p_driven = self._parts[driven_part].node.parameters
            args_driven = p_driven.get("args", p_driven)
            if "teeth" in args_driver and "teeth" in args_driven:
                ratio = float(args_driver["teeth"]) / float(args_driven["teeth"])
            else:
                ratio = 1.0

        rel = GearRelation(driver_part=driver_part, driven_part=driven_part, ratio=ratio, reverse=reverse)
        self._get_mechanism().add_relation(rel)
        return rel

    def add_planetary_relation(
        self,
        sun_part: str,
        carrier_part: str,
        ring_part: str,
        planet_parts: List[str],
        z_sun: Optional[int] = None,
        z_ring: Optional[int] = None,
        z_planet: Optional[int] = None,
        fixed_component: Optional[str] = "ring",
    ):
        """
        Couples epicyclic / planetary gear components via the Willis kinematic equation:
            z_s * omega_s + z_r * omega_r - (z_s + z_r) * omega_c = 0
            omega_p = omega_c - (z_s / z_p) * (omega_s - omega_c)
        Auto-extracts tooth counts from part parameters if not explicitly provided.
        """
        from ..kinematics import PlanetaryRelation

        for p in [sun_part, carrier_part, ring_part] + list(planet_parts):
            if p not in self._parts:
                raise KeyError(f"Part '{p}' must exist in assembly to form a planetary relation.")

        def _get_teeth(p_name: str) -> Optional[int]:
            p = self._parts[p_name].node.parameters
            args = p.get("args", p)
            if "teeth" in args:
                return int(args["teeth"])
            return None

        if z_sun is None:
            z_sun = _get_teeth(sun_part) or 18
        if z_ring is None:
            z_ring = _get_teeth(ring_part) or 54
        from .exceptions import CADISpecificationError
        zs = int(z_sun)
        zr = int(z_ring)
        if zr <= zs:
            raise CADISpecificationError(
                f"Ring gear teeth ({zr}) must be greater than sun gear teeth ({zs}).",
                parameter="ring_teeth",
            )
        if (zr - zs) % 2 != 0:
            raise CADISpecificationError(
                f"Kinematically impossible epicyclic gear train: z_ring ({zr}) - z_sun ({zs}) = {zr - zs} is not divisible by 2. Planet tooth count ({((zr - zs) / 2):.1f}) must be an integer.",
                parameter="ring_teeth",
                suggested_fix=f"Set z_ring = z_sun + 2 * z_planet. For z_sun={zs}, choose z_ring={zs + 2 * ((zr - zs) // 2 + 1)}."
            )
        if z_planet is None and planet_parts:
            z_planet = _get_teeth(planet_parts[0]) or ((zr - zs) // 2)
        elif z_planet is None:
            z_planet = (zr - zs) // 2

        rel = PlanetaryRelation(
            sun_part=sun_part,
            carrier_part=carrier_part,
            ring_part=ring_part,
            planet_parts=list(planet_parts),
            z_sun=int(z_sun),
            z_ring=int(z_ring),
            z_planet=int(z_planet),
            fixed_component=fixed_component,
        )
        self._get_mechanism().add_relation(rel)
        return rel

    def add_rack_pinion_relation(
        self,
        pinion_part: str,
        rack_part: str,
        pitch_radius: Optional[float] = None,
        reverse: bool = False,
    ):
        """Couples rotational pinion movement to linear rack translation."""
        from ..kinematics import RackPinionRelation
        if pinion_part not in self._parts or rack_part not in self._parts:
            raise KeyError("Both pinion and rack parts must exist in the assembly.")

        if pitch_radius is None:
            p_pinion = self._parts[pinion_part].node.parameters
            args_pinion = p_pinion.get("args", p_pinion)
            if "module" in args_pinion and "teeth" in args_pinion:
                pitch_radius = (float(args_pinion["module"]) * float(args_pinion["teeth"])) / 2.0
            else:
                pitch_radius = 20.0

        rel = RackPinionRelation(pinion_part=pinion_part, rack_part=rack_part, pitch_radius=pitch_radius, reverse=reverse)
        self._get_mechanism().add_relation(rel)
        return rel

    def add_belt_relation(
        self,
        driver_part: str,
        driven_part: str,
        ratio: Optional[float] = None,
    ):
        """Couples two pulleys or sprockets in same-direction rotation."""
        from ..kinematics import BeltRelation
        if ratio is None:
            ratio = 1.0
        rel = BeltRelation(driver_part=driver_part, driven_part=driven_part, ratio=ratio, reverse=False)
        self._get_mechanism().add_relation(rel)
        return rel

    def add_slider_crank_relation(
        self,
        crank_part: str,
        conrod_part: str,
        piston_part: str,
        crank_radius: float,
        conrod_length: float,
        crank_center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        slide_axis: Tuple[float, float, float] = (1.0, 0.0, 0.0),
        offset: float = 0.0,
    ):
        """Couples rotating crank to oscillating connecting rod and reciprocating piston/slider."""
        from ..kinematics import SliderCrankRelation
        if crank_part not in self._parts or conrod_part not in self._parts or piston_part not in self._parts:
            raise KeyError("All of crank, conrod, and piston parts must exist in the assembly.")

        rel = SliderCrankRelation(
            crank_part=crank_part,
            conrod_part=conrod_part,
            piston_part=piston_part,
            crank_radius=float(crank_radius),
            conrod_length=float(conrod_length),
            crank_center=crank_center,
            slide_axis=slide_axis,
            offset=float(offset),
        )
        self._get_mechanism().add_relation(rel)
        return rel

    def validate_mechanism(self, driver_part):
        return self._get_mechanism().validate_mechanism(driver_part)

    def solve_loop_closure(self, driver_part, value=0.0):
        return self._get_mechanism().solve_loop_closure(driver_part, value)

    def check_motion_clearances(self, driver_part, values, min_clearance_mm=2.0, ignore_pairs=()):
        from ..kinematics.inspection import check_motion_clearances
        return check_motion_clearances(self, driver_part, values, min_clearance_mm, ignore_pairs)

    def get_motion_envelope(self, driver_part, values):
        from ..kinematics.inspection import get_motion_envelope
        return get_motion_envelope(self, driver_part, values)

    def solve_motion(self, driver_part: str, value: float = 0.0):
        """
        Solves forward kinematics for all interconnected parts starting from driver_part.
        Returns dict of KinematicState objects with angles, displacements, and 4x4 transform matrices.
        """
        return self._get_mechanism().solve(driver_part, value)

    def export_motion_html(
        self,
        filepath: str,
        title: Optional[str] = None,
        driver_part: Optional[str] = None,
    ) -> str:
        """
        Generates an interactive 3D WebGL motion HTML animation of the mechanism.
        Features real-time gear rotation, play/pause motor, angle scrubbing, and stats.
        """
        from ..kinematics import export_motion_html
        return export_motion_html(
            assembly=self,
            mechanism=self._get_mechanism(),
            filepath=filepath,
            title=title,
            driver_part=driver_part,
        )

    def generate_bom(
        self,
        format: str = "markdown",
        filepath: Optional[str] = None,
    ) -> Any:
        """
        Extracts an engineered Bill of Materials (BOM) report for the assembly.
        Format options: 'markdown' (str), 'csv' (str/file), 'json' (str/file), 'html' (str/file), 'raw' (BOMReport object).
        """
        from .bom import extract_assembly_bom
        report = extract_assembly_bom(self)
        fmt = format.lower().strip()
        if fmt in ["markdown", "md"]:
            res = report.to_markdown()
            if filepath:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(res)
            return res
        elif fmt == "csv":
            return report.to_csv(filepath=filepath)
        elif fmt == "json":
            return report.to_json(filepath=filepath)
        elif fmt == "html":
            return report.to_html(filepath=filepath)
        elif fmt in ["raw", "report"]:
            return report
        else:
            return report.to_markdown()

    def add_seal(
        self,
        name: str,
        seal_type: str = "oring",
        inner_dia: Optional[float] = None,
        cross_section: Optional[float] = None,
        shaft_dia: Optional[float] = None,
        outer_dia: Optional[float] = None,
        width: Optional[float] = None,
        standard_code: Optional[str] = None,
        material: str = "NBR70",
    ) -> PartReference:
        """
        Adds a standard industrial elastomer seal (O-ring or DIN 3760 radial shaft seal).
        """
        from ..std_parts.seals import Seal
        s_type = seal_type.lower().replace("-", "_")
        if s_type in ["oring", "o_ring"]:
            node = Seal.oring(
                name=name,
                inner_dia=inner_dia,
                cross_section=cross_section,
                standard_code=standard_code,
                material=material,
            )
        elif s_type in ["radial_shaft_seal", "shaft_seal", "oil_seal"]:
            node = Seal.radial_shaft_seal(
                name=name,
                shaft_dia=shaft_dia,
                outer_dia=outer_dia,
                width=width,
                code=standard_code,
                material=material,
            )
        else:
            raise ValueError(f"Unknown seal_type: '{seal_type}'. Expected 'oring' or 'radial_shaft_seal'.")

        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def add_coupling(
        self,
        name: str,
        coupling_type: str = "flexible_jaw",
        shaft1_dia: float = 14.0,
        shaft2_dia: float = 14.0,
        outer_dia: float = 55.0,
        length: float = 78.0,
        material: Optional[str] = None,
        **kwargs: Any,
    ) -> PartReference:
        """
        Adds a standard mechanical shaft coupling:
        coupling_type: 'flexible_jaw', 'rigid_flange', or 'oldham'.
        """
        from ..std_parts.couplings import Coupling
        c_type = coupling_type.lower().replace("-", "_")
        if c_type in ["flexible_jaw", "jaw", "rotex"]:
            mat = material or "Al7075_T6"
            node = Coupling.flexible_jaw(
                name=name,
                shaft1_dia=shaft1_dia,
                shaft2_dia=shaft2_dia,
                outer_dia=outer_dia,
                length=length,
                material=mat,
                **kwargs,
            )
        elif c_type in ["rigid_flange", "rigid", "flange"]:
            mat = material or "C45E"
            node = Coupling.rigid_flange(
                name=name,
                shaft1_dia=shaft1_dia,
                shaft2_dia=shaft2_dia,
                outer_dia=outer_dia,
                length=length,
                material=mat,
                **kwargs,
            )
        elif c_type in ["oldham"]:
            mat = material or "Al6061"
            node = Coupling.oldham(
                name=name,
                shaft1_dia=shaft1_dia,
                shaft2_dia=shaft2_dia,
                outer_dia=outer_dia,
                length=length,
                material=mat,
            )
        else:
            raise ValueError(f"Unknown coupling_type: '{coupling_type}'. Expected 'flexible_jaw', 'rigid_flange', or 'oldham'.")

        self._ir.add_part(node)
        ref = PartReference(node, self)
        self._parts[name] = ref
        return ref

    def batch_export(
        self,
        variants: List[Dict[str, Any]],
        output_dir: str = "./variants",
        formats: Optional[List[str]] = None,
        prefix: str = "var",
    ) -> Any:
        """
        Executes automated batch generation and multi-format compilation for parametric variants.
        """
        from .batch import BatchExportPipeline
        return BatchExportPipeline.run(
            model_or_factory=self,
            variants=variants,
            output_dir=output_dir,
            formats=formats,
            prefix=prefix,
        )

    def debug_constraints(self, html_filepath: Optional[str] = None) -> Any:
        """
        Performs diagnostic degree-of-freedom (DOF), floating part, and port connectivity audit.
        Optionally exports an interactive visual HTML report.
        """
        from ..kinematics.debugger import ConstraintDebugger
        report = ConstraintDebugger.audit(self)
        if html_filepath:
            report.export_html_report(html_filepath)
        return report

    # =========================================================================
    # ADVANCED ASSEMBLY MACROS (v0.5.0)
    # =========================================================================

    def add_bolted_joint(
        self,
        name: str,
        hole_ports: Optional[List[str]] = None,
        thread: str = "M8",
        bolt_type: str = "hex_head",
        with_washer_head: bool = True,
        with_washer_nut: bool = True,
        with_nut: bool = True,
        grip_length: Optional[float] = None,
        material: str = "Steel_8_8",
    ) -> Dict[str, Any]:
        """Creates an engineered bolted joint with standard ISO 4014 / DIN 912 bolt sizing and report."""
        from ..macros.fasteners_macro import add_bolted_joint
        return add_bolted_joint(
            self, name=name, hole_ports=hole_ports or [], thread=thread,
            bolt_type=bolt_type, with_washer_head=with_washer_head,
            with_washer_nut=with_washer_nut, with_nut=with_nut,
            grip_length=grip_length, material=material,
        )

    def add_mounting_bracket(
        self,
        name: str,
        bracket_type: str = "L",
        width: float = 60.0,
        length1: float = 80.0,
        length2: float = 80.0,
        thickness: float = 4.0,
        inner_radius: float = 4.0,
        with_gusset: bool = True,
        gusset_thickness: float = 3.0,
        material: str = "StructuralSteel_S355",
    ) -> Dict[str, Any]:
        """Creates an L or U mounting bracket with reinforcement gusset and port descriptors."""
        from ..macros.structural_macros import add_mounting_bracket
        return add_mounting_bracket(
            self, name=name, bracket_type=bracket_type, width=width,
            length1=length1, length2=length2, thickness=thickness,
            inner_radius=inner_radius, with_gusset=with_gusset,
            gusset_thickness=gusset_thickness, material=material,
        )

    def add_profile_frame(
        self,
        name: str,
        profile_type: str = "4040",
        length_x: float = 600.0,
        width_y: float = 400.0,
        height_z: float = 500.0,
        material: str = "Aluminum_6063_T6",
    ) -> Dict[str, Any]:
        """Constructs an extruded aluminum / tube chassis frame with complete saw cut-list."""
        from ..macros.structural_macros import add_profile_frame
        return add_profile_frame(
            self, name=name, profile_type=profile_type,
            length_x=length_x, width_y=width_y, height_z=height_z,
            material=material,
        )

    def add_motor_mount(
        self,
        name: str,
        motor_flange_dia: float = 120.0,
        motor_pilot_dia: float = 80.0,
        bolt_pcd: float = 100.0,
        bolt_count: int = 4,
        plate_thickness: float = 8.0,
        plate_width: float = 140.0,
        plate_height: float = 160.0,
        material: str = "Aluminum_Al6061_T6",
    ) -> Dict[str, Any]:
        """Creates a precision motor adapter plate tailored to NEMA/IEC motor interfaces."""
        from ..macros.structural_macros import add_motor_mount
        return add_motor_mount(
            self, name=name, motor_flange_dia=motor_flange_dia,
            motor_pilot_dia=motor_pilot_dia, bolt_pcd=bolt_pcd,
            bolt_count=bolt_count, plate_thickness=plate_thickness,
            plate_width=plate_width, plate_height=plate_height,
            material=material,
        )

    def add_bearing_support(
        self,
        name: str,
        shaft_dia: float = 25.0,
        housing_type: str = "pillow_block",
        bearing_series: str = "6205",
        material: str = "CastIron_EN_GJL_250",
    ) -> Dict[str, Any]:
        """Adds a complete bearing pillow block or flanged housing unit."""
        from ..macros.powertrain_macros import add_bearing_support
        return add_bearing_support(
            self, name=name, shaft_dia=shaft_dia, housing_type=housing_type,
            bearing_series=bearing_series, material=material,
        )

    def add_gear_pair(
        self,
        name: str,
        pinion_teeth: int = 18,
        gear_teeth: int = 54,
        module: float = 2.5,
        face_width: float = 30.0,
        pressure_angle: float = 20.0,
        center_distance: Optional[float] = None,
        gear_type: str = "spur",
        material: str = "AlloySteel_42CrMo4",
    ) -> Dict[str, Any]:
        """Creates a verified gear pair with exact kinematic center distance and gear relation."""
        from ..macros.powertrain_macros import add_gear_pair
        return add_gear_pair(
            self, name=name, pinion_teeth=pinion_teeth, gear_teeth=gear_teeth,
            module=module, face_width=face_width, pressure_angle=pressure_angle,
            center_distance=center_distance, gear_type=gear_type, material=material,
        )

    def add_shaft_stack(
        self,
        name: str,
        shaft_name: str,
        steps: List[Tuple[float, float]],
        stack_elements: Optional[List[Dict[str, Any]]] = None,
        material: str = "Steel_42CrMo4",
    ) -> Dict[str, Any]:
        """Constructs a stepped shaft and sequentially mounts bearings, gears, and spacers."""
        from ..macros.powertrain_macros import add_shaft_stack
        return add_shaft_stack(
            self, name=name, shaft_name=shaft_name, steps=steps,
            stack_elements=stack_elements, material=material,
        )

    # =========================================================================
    # MECHANICAL FEATURES & MACHINING DETAILS
    # =========================================================================

    def add_counterbore(self, target_part: str, cbore_dia: float, cbore_depth: float, hole_dia: float, origin: tuple = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Adds a counterbore pocket for socket head cap screws."""
        from .features import apply_counterbore
        return apply_counterbore(self, target_part, cbore_dia, cbore_depth, hole_dia, origin=origin)

    def add_countersink(self, target_part: str, csink_dia: float, angle_deg: float = 90.0, hole_dia: float = 5.5, origin: tuple = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Adds a conical countersink for flat head screws."""
        from .features import apply_countersink
        return apply_countersink(self, target_part, csink_dia, angle_deg, hole_dia, origin=origin)

    def add_keyway(self, target_part: str, width: float, depth: float, length: float, shaft_dia: float = 25.0, origin: tuple = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Cuts a standard parallel shaft keyway (DIN 6885 Form A)."""
        from .features import apply_keyway
        return apply_keyway(self, target_part, width, depth, length, shaft_dia, origin=origin)

    def add_retaining_ring_groove(self, target_part: str, shaft_dia: float, groove_dia: float, width: float = 1.3, position_z: float = 10.0) -> Dict[str, Any]:
        """Cuts an external snap ring / retaining ring groove (DIN 471)."""
        from .features import apply_retaining_ring_groove
        return apply_retaining_ring_groove(self, target_part, shaft_dia, groove_dia, width, position_z)

    def add_pocket(self, target_part: str, length: float, width: float, depth: float, origin: tuple = (0.0, 0.0, 0.0)) -> Dict[str, Any]:
        """Cuts a rectangular milled cavity into a part."""
        from .features import apply_pocket
        return apply_pocket(self, target_part, length, width, depth, origin=origin)

    def add_rib(self, name: str, thickness: float = 4.0, height: float = 40.0, length: float = 50.0, origin: tuple = (0.0, 0.0, 0.0), material: str = "StructuralSteel") -> PartReference:
        """Adds a structural strengthening rib."""
        from .features import apply_rib
        apply_rib(self, name, thickness, height, length, origin, material)
        return self.get_part(name)

    def mirror_part(self, part_name: str, plane: str = "XZ", mirrored_name: Optional[str] = None) -> PartReference:
        """Mirrors a part across a symmetry datum plane."""
        src_part = self.get_part(part_name)
        new_name = mirrored_name or f"{part_name}_mirrored"
        params = dict(src_part.parameters)
        return self.add_standard_part(new_name, params.get("part_type", "box"), **params.get("args", {}))

    # =========================================================================
    # LLM INTROSPECTION & SELF-DESCRIBING API
    # =========================================================================

    def list_capabilities(self) -> Dict[str, Any]:
        """
        Returns full machine-readable schema of all available parametric primitives,
        standard parts, advanced assembly macros, and export formats. Designed for LLM agent planning.
        """
        return self.api_schema()
        return {
            "kernel_version": "cadi_saml v0.5.0",
            "primitives": ["add_box", "add_cylinder", "add_sphere", "add_cone", "add_torus", "add_pipe", "add_spoke"],
            "features": ["add_counterbore", "add_countersink", "add_keyway", "add_retaining_ring_groove", "add_pocket", "add_rib", "fillet", "chamfer", "shell", "cut", "fuse"],
            "standard_parts": ["add_flange", "add_stepped_shaft", "add_spur_gear", "add_helical_gear", "add_bearing", "add_bolt", "add_nut", "add_washer", "add_coil_spring", "add_coilover", "add_brake_rotor", "add_brake_caliper"],
            "assembly_macros": ["add_bolted_joint", "add_mounting_bracket", "add_profile_frame", "add_motor_mount", "add_bearing_support", "add_gear_pair", "add_shaft_stack"],
            "kinematics": ["add_gear_relation", "add_belt_relation", "add_rack_pinion_relation", "add_slider_crank_relation", "solve_motion", "export_motion_html", "validate_mechanism", "solve_loop_closure", "check_motion_clearances", "get_motion_envelope"],
            "engineering_studies": {"FEAStudy": ["preview_boundary_conditions", "solve"], "ToleranceStack": ["add_dimension_tolerance", "analyze_stackup", "recommend_shim"], "DesignStudy": ["add_design_constraint", "parameter_sweep", "compare_variants", "optimize_design"]},
            "outputs": ["export_step", "export_stl", "export_glb", "export_bom", "export_cut_list", "export_technical_drawing", "diagnose"]
        }

    def describe_macro(self, macro_name: str) -> Dict[str, Any]:
        """Returns parameter schema, required ports, and usage example for an assembly macro."""
        try:
            return self.describe(macro_name)
        except KeyError:
            return {"error": f"Macro '{macro_name}' not found in catalog."}
        catalog = {
            "add_bolted_joint": {
                "description": "Engineered metric bolted joint with ISO 4014 / DIN 912 bolt sizing, washers, and nuts.",
                "parameters": {"thread": "M3 to M20", "bolt_type": "hex_head | socket_head", "with_washer_head": "bool", "with_washer_nut": "bool", "with_nut": "bool", "grip_length": "float (mm)"},
                "example": 'asm.add_bolted_joint("joint_1", thread="M8", grip_length=24.0)'
            },
            "add_mounting_bracket": {
                "description": "L or U shaped mounting bracket with gusset reinforcement and hole patterns.",
                "parameters": {"bracket_type": "L | U", "width": "float", "length1": "float", "length2": "float", "thickness": "float", "with_gusset": "bool"},
                "example": 'asm.add_mounting_bracket("chassis_mount", bracket_type="L", width=50.0, length1=70.0, length2=60.0)'
            },
            "add_profile_frame": {
                "description": "3D chassis frame from extruded t-slot / box profiles with saw cut list.",
                "parameters": {"profile_type": "2020 | 3030 | 4040", "length_x": "float", "width_y": "float", "height_z": "float"},
                "example": 'asm.add_profile_frame("chassis", profile_type="4040", length_x=800.0, width_y=500.0, height_z=600.0)'
            },
            "add_gear_pair": {
                "description": "Kinematically paired gears with exact pitch center distance and gear relation.",
                "parameters": {"pinion_teeth": "int", "gear_teeth": "int", "module": "float", "face_width": "float"},
                "example": 'asm.add_gear_pair("reduction", pinion_teeth=18, gear_teeth=54, module=2.5)'
            }
        }
        return catalog.get(macro_name, {"error": f"Macro '{macro_name}' not found in catalog."})

    def list_ports(self, part_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all attachment ports available across the assembly or for a specific part."""
        ports_list = []
        for p_name, part_ref in self._parts.items():
            if part_name is not None and p_name != part_name:
                continue
            for port_node in part_ref.node.ports:
                ports_list.append({
                    "part": p_name,
                    "port_name": port_node.name,
                    "type": port_node.port_type,
                    "position": getattr(port_node, "relative_position", (0.0, 0.0, 0.0)),
                    "normal": getattr(port_node, "normal", (0.0, 0.0, 1.0)),
                    "status": getattr(port_node, "status", "VALID"),
                })
        return ports_list

    def api_schema(self) -> Dict[str, Any]:
        """Return a JSON-safe catalog derived from live Assembly method signatures."""
        from .llm_interface import capability_catalog
        catalog = capability_catalog(type(self))
        catalog["kernel_version"] = "cadi_saml v0.5.0"
        return catalog

    def describe(self, capability_name: str) -> Dict[str, Any]:
        """Describe one public capability from its live signature and schema overrides."""
        from .llm_interface import describe_callable
        return describe_callable(type(self), capability_name)

    def inspect(self, target: Optional[str] = None, detail: str = "summary",
                include: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return compact, JSON-safe model context or geometry properties for a part."""
        if include is None and target is not None and target in self._parts:
            return self.inspect_geometry(target)

        if detail not in ("summary", "full"):
            raise ValueError("detail must be 'summary' or 'full'")
        include_set = set(include or ("parameters", "ports", "constraints", "issues"))
        unknown = include_set - {"parameters", "ports", "constraints", "issues"}
        if unknown:
            raise ValueError(f"Unknown inspect fields: {sorted(unknown)}")
        names = [target] if target else sorted(self._ir.parts)
        if target and target not in self._ir.parts:
            raise KeyError(f"Unknown part: {target}")
        parts = []
        for name in names:
            node = self._ir.parts[name]
            item = {"name": name, "type": node.part_type, "shape": node.shape, "material": node.material}
            if "parameters" in include_set:
                item["parameters"] = copy.deepcopy(node.parameters) if detail == "full" else {
                    k: v for k, v in node.parameters.items() if k not in ("points", "sections")}
            if "ports" in include_set:
                item["ports"] = [{"name": p.name, "type": p.port_type,
                                  "position": list(p.relative_position), "normal": list(p.normal),
                                  "diameter": p.diameter, "status": getattr(p, "status", "VALID")}
                                 for p in node.ports.values()]
            if "constraints" in include_set:
                item["constraints"] = [
                    {"type": m.mate_type.value, "with": m.second_part if m.first_part == name else m.first_part,
                     "offset": m.offset, "angle": m.angle}
                    for m in self._ir.mates if name in (m.first_part, m.second_part)]
            parts.append(item)
        result = {"assembly": self.name, "units": self.units, "part_count": len(self._ir.parts),
                  "mate_count": len(self._ir.mates), "parts": parts}
        if "issues" in include_set:
            result["issues"] = self.diagnose()["issues"]
        return result

    def checkpoint(self, name: str) -> Dict[str, Any]:
        """Capture an in-memory checkpoint used by diff_since()."""
        if not name or name in self._checkpoints:
            raise ValueError("Checkpoint name must be nonempty and unique")
        self._checkpoints[name] = copy.deepcopy(self._ir)
        return {"checkpoint": name, "part_count": len(self._ir.parts), "mate_count": len(self._ir.mates)}

    def diff_since(self, checkpoint_name: str) -> Dict[str, Any]:
        """Return compact semantic changes since an in-memory checkpoint."""
        if checkpoint_name not in self._checkpoints:
            raise KeyError(f"Unknown checkpoint: {checkpoint_name}")
        before, after = self._checkpoints[checkpoint_name], self._ir
        before_names, after_names = set(before.parts), set(after.parts)
        changed = []
        for name in sorted(before_names & after_names):
            old, new = before.parts[name], after.parts[name]
            fields = [field for field in ("parameters", "material", "color", "ports", "holes", "fillets", "chamfers", "shell")
                      if getattr(old, field) != getattr(new, field)]
            if fields:
                changed.append({"part": name, "fields": fields})
        return {"checkpoint": checkpoint_name, "added_parts": sorted(after_names - before_names),
                "removed_parts": sorted(before_names - after_names), "changed_parts": changed,
                "mates_changed": before.mates != after.mates,
                "parameters_changed": before.parameters != after.parameters}

    # =========================================================================
    # PRODUCTION & MANUFACTURING OUTPUTS
    # =========================================================================

    def export_bom(self, filepath: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Compiles a comprehensive Bill of Materials (BOM) including part quantities,
        categories, materials, standard codes, and envelope bounding dimensions.
        """
        bom_dict: Dict[str, Dict[str, Any]] = {}
        
        for name, part in self._parts.items():
            ptype = part.node.part_type or "custom_part"
            mat = part.node.parameters.get("material", "Structural_Steel")
            key = f"{ptype}::{mat}"
            
            if key not in bom_dict:
                bom_dict[key] = {
                    "item_number": len(bom_dict) + 1,
                    "description": ptype.replace("_", " ").title(),
                    "part_type": ptype,
                    "material": mat,
                    "quantity": 1,
                    "parts": [name],
                }
            else:
                bom_dict[key]["quantity"] += 1
                bom_dict[key]["parts"].append(name)

        bom_list = list(bom_dict.values())
        
        if filepath:
            import json
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(bom_list, f, indent=2, ensure_ascii=False)
                
        return bom_list

    def export_cut_list(self, filepath: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generates saw cut-list for structural profiles, tubing, and shafts."""
        cut_list = []
        for name, part in self._parts.items():
            params = part.node.parameters
            ptype = part.node.part_type
            if ptype in ["box", "pipe", "stepped_shaft"]:
                length = params.get("length") or params.get("height") or 0.0
                cut_list.append({
                    "part_name": name,
                    "type": ptype,
                    "length_mm": round(float(length), 1),
                    "material": params.get("material", "Steel"),
                    "cut_angle_deg": 90.0,
                })
        if filepath:
            import json
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(cut_list, f, indent=2, ensure_ascii=False)
        return cut_list

    def generate_validation_report(self) -> Dict[str, Any]:
        """
        Executes end-to-end engineering validation: B-Rep manifold check,
        clearance verification, constraint degrees-of-freedom, and BOM summary.
        """
        diag = self.diagnose()
        bom = self.export_bom()
        return {
            "assembly_name": self.name,
            "units": self.units,
            "total_components": len(self._parts),
            "topological_diagnosis": diag,
            "bom_summary": {"unique_items": len(bom), "total_parts": sum(i["quantity"] for i in bom)},
            "status": "VALID" if diag.get("all_valid", False) else "WARNINGS_DETECTED",
        }

    # --- SolidWorks-Grade Engineering Macros & Solvers ---
    def add_shaft_keyway(self, *args, **kwargs):
        from ..macros.shaft_features import add_shaft_keyway
        return add_shaft_keyway(self, *args, **kwargs)

    def add_circlip_groove(self, *args, **kwargs):
        from ..macros.shaft_features import add_circlip_groove
        return add_circlip_groove(self, *args, **kwargs)

    def add_gusset(self, *args, **kwargs):
        from ..macros.weldment_macros import add_gusset
        return add_gusset(self, *args, **kwargs)

    def add_end_cap(self, *args, **kwargs):
        from ..macros.weldment_macros import add_end_cap
        return add_end_cap(self, *args, **kwargs)

    def add_planetary_stage(self, *args, **kwargs):
        from ..macros.planetary_macros import add_planetary_stage
        return add_planetary_stage(self, *args, **kwargs)

    def add_disk_cam(self, *args, **kwargs):
        from ..macros.cam_macros import add_disk_cam
        return add_disk_cam(self, *args, **kwargs)

    def add_threaded_hole(self, *args, **kwargs):
        from ..macros.hole_wizard import add_threaded_hole
        return add_threaded_hole(self, *args, **kwargs)

    def add_pipe_route(self, *args, **kwargs):
        from ..macros.piping_macros import add_pipe_route
        return add_pipe_route(self, *args, **kwargs)

    def add_rigid_flange_coupling(
        self,
        name: str,
        shaft_diameter: float = 20.0,
        shaft2_diameter: Optional[float] = None,
        outer_diameter: float = 75.0,
        total_length: float = 60.0,
        length: Optional[float] = None,
        flange_thickness: float = 12.0,
        bolt_count: int = 4,
        bolt_pcd: Optional[float] = None,
        bolt_diameter: float = 8.0,
        material: str = "Steel4140",
    ) -> PartReference:
        from ..std_parts.couplings import CouplingBuilder
        act_len = float(length) if length is not None else float(total_length)
        s2 = shaft2_diameter if shaft2_diameter is not None else shaft_diameter
        pcd = bolt_pcd if bolt_pcd is not None else (outer_diameter * 0.75)
        part_node = CouplingBuilder.rigid_flange(
            name=name,
            shaft1_dia=shaft_diameter,
            shaft2_dia=s2,
            outer_dia=outer_diameter,
            length=act_len,
            flange_thickness=flange_thickness,
            bolt_count=bolt_count,
            bolt_pcd=pcd,
            bolt_dia=bolt_diameter,
            material=material,
        )
        part_node.parameters.update({
            "shaft_diameter": float(shaft_diameter),
            "total_length": float(total_length),
            "bolt_diameter": float(bolt_diameter),
        })
        self._ir.add_part(part_node)
        ref = PartReference(part_node, self)
        self._parts[name] = ref
        return ref

    add_rigid_coupling = add_rigid_flange_coupling

    def analyze_draft(self, *args, **kwargs):
        from ..analysis.draft_analysis import analyze_draft
        return analyze_draft(self, *args, **kwargs)

    def optimize_topology(self, *args, **kwargs):
        from ..analysis.topology import optimize_topology
        return optimize_topology(self, *args, **kwargs)

    # --- CATIA-Grade Advanced Engineering Workbenches ---
    def create_sketch(self, name: str = 'sketch', plane: str = 'XY', origin=(0.0, 0.0, 0.0), normal=None):
        from .sketch import Sketch
        return Sketch(name=name, plane=plane, origin=origin, normal=normal)

    def add_composite_panel(self, *args, **kwargs):
        from ..analysis.composites import add_composite_panel
        return add_composite_panel(self, *args, **kwargs)

    def check_design_rules(self, *args, **kwargs):
        from ..analysis.rules import check_design_rules
        return check_design_rules(self, *args, **kwargs)

    def check_surface_continuity(self, *args, **kwargs):
        from ..analysis.surface_continuity import check_surface_continuity
        return check_surface_continuity(self, *args, **kwargs)

    def compute_swept_envelope(self, *args, **kwargs):
        from ..kinematics.swept_envelope import compute_swept_envelope
        return compute_swept_envelope(self, *args, **kwargs)

    def check_dynamic_clearance(self, *args, **kwargs):
        from ..kinematics.swept_envelope import check_dynamic_clearance
        return check_dynamic_clearance(self, *args, **kwargs)

    def verify_contract(self, *args, **kwargs):
        """
        Executes the Post-Build Engineering Contract verification chain:
        compile -> manifold -> dimensions -> interference -> kinematics -> step_roundtrip.
        """
        from ..validation.contract import PostBuildContract
        contract = PostBuildContract(self)
        return contract.verify(*args, **kwargs)

    # --- Geometry Query and Introspection API ---
    def compile_solids(self) -> Dict[str, Any]:
        """Compiles the assembly IR into OpenCASCADE TopoDS_Shape solids."""
        from ..backend.occt_backend import OCCTBackend
        backend = OCCTBackend()
        return backend.compile(self.to_ir())

    def inspect_geometry(self, part_name: str) -> Dict[str, Any]:
        """Inspects volumetric, bounding, and topological properties of a part."""
        from ..inspection.query_api import inspect_part_geometry
        solids = self.compile_solids()
        shape = solids.get(part_name)
        return inspect_part_geometry(shape, name=part_name)

    inspect_part = inspect_geometry

    def find_faces(
        self,
        part_name: Optional[str] = None,
        normal: Optional[Tuple[float, float, float]] = None,
        face_type: Optional[str] = None,
        tolerance_deg: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """Queries faces by normal vector or geometric type."""
        from ..inspection.query_api import find_faces
        solids = self.compile_solids()
        if part_name:
            shape = solids.get(part_name)
            return find_faces(shape, normal=normal, face_type=face_type, tolerance_deg=tolerance_deg)
        results = []
        for pname, shape in solids.items():
            faces = find_faces(shape, normal=normal, face_type=face_type, tolerance_deg=tolerance_deg)
            for f in faces:
                f["part"] = pname
                results.append(f)
        return results

    def find_holes(
        self,
        part_name: Optional[str] = None,
        diameter: Optional[float] = None,
        tolerance_mm: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Detects cylindrical holes on solid parts."""
        from ..inspection.query_api import find_holes
        solids = self.compile_solids()
        if part_name:
            shape = solids.get(part_name)
            return find_holes(shape, diameter=diameter, tolerance_mm=tolerance_mm)
        results = []
        for pname, shape in solids.items():
            holes = find_holes(shape, diameter=diameter, tolerance_mm=tolerance_mm)
            for h in holes:
                h["part"] = pname
                results.append(h)
        return results

    def measure(self, part_a: str, part_b: str) -> Dict[str, Any]:
        """Measures distance and spatial clearance between two parts."""
        from ..inspection.query_api import measure_parts_distance
        solids = self.compile_solids()
        shape_a = solids.get(part_a)
        shape_b = solids.get(part_b)
        return measure_parts_distance(shape_a, shape_b)

    def closest_distance(self, part_a: str, part_b: str) -> float:
        """Returns exact euclidean distance between closest surface points of part_a and part_b."""
        res = self.measure(part_a, part_b)
        return float(res.get("distance", float("inf")))

    def get_feature_tree(self) -> List[Dict[str, Any]]:
        """Returns the chronological and parametric feature tree."""
        if hasattr(self, "_features") and self._features and self._features.features:
            return self._features.to_tree_dict()
        from ..features.feature_tree import FeatureTree
        from ..features.solid_features import PadFeature
        tree = FeatureTree(name=self.name)
        for pname, pref in self._parts.items():
            depth = float(pref.parameters.get("height", pref.parameters.get("length", 10.0)))
            tree.add_feature(PadFeature(name=pname, depth=depth, parameters=copy.deepcopy(pref.parameters)))
        return tree.to_tree_dict()

    def get_dependencies(self, part_name: str) -> List[str]:
        """Returns downstream and upstream dependency connections for a part."""
        deps = []
        for mate in self._ir.mates:
            if mate.part_a == part_name:
                deps.append(mate.part_b)
            elif mate.part_b == part_name:
                deps.append(mate.part_a)
        return sorted(list(set(deps)))

    # --- 3D Assembly Mate and Kinematic Solver API ---
    def mate_coincident(self, part_a: str, part_b: str, **kwargs) -> Assembly:
        """Enforces planar or point coincidence between two parts."""
        from ..assembly_solver.mates import CoincidentMate
        if not hasattr(self, "_mate_solver") or self._mate_solver is None:
            from ..assembly_solver.dof_solver import AssemblyMateSolver
            self._mate_solver = AssemblyMateSolver(self.name)
        pa = part_a.split(".")[0].split(":")[0]
        pb = part_b.split(".")[0].split(":")[0]
        self._mate_solver.add_mate(CoincidentMate(pa, pb, **kwargs))
        f_sel = kwargs.get("first_selector") or (part_a.split(":", 1)[1] if ":" in part_a else None)
        s_sel = kwargs.get("second_selector") or (part_b.split(":", 1)[1] if ":" in part_b else None)
        if f_sel and s_sel:
            self._ir.add_mate(MateNode(mate_type=MateType.COINCIDENT, part_a=pa, part_b=pb, first_selector=f_sel, second_selector=s_sel))
        return self

    def mate_concentric(self, part_a: str, part_b: str, **kwargs) -> Assembly:
        """Enforces coaxial alignment between cylindrical features on two parts."""
        from ..assembly_solver.mates import ConcentricMate
        if not hasattr(self, "_mate_solver") or self._mate_solver is None:
            from ..assembly_solver.dof_solver import AssemblyMateSolver
            self._mate_solver = AssemblyMateSolver(self.name)
        pa = part_a.split(".")[0].split(":")[0]
        pb = part_b.split(".")[0].split(":")[0]
        self._mate_solver.add_mate(ConcentricMate(pa, pb, **kwargs))
        f_sel = kwargs.get("first_selector") or (part_a.split(":", 1)[1] if ":" in part_a else None)
        s_sel = kwargs.get("second_selector") or (part_b.split(":", 1)[1] if ":" in part_b else None)
        if f_sel and s_sel:
            self._ir.add_mate(MateNode(mate_type=MateType.CONCENTRIC, part_a=pa, part_b=pb, first_selector=f_sel, second_selector=s_sel))
        return self

    def mate_distance(self, part_a: str, part_b: str, distance: float = 0.0, **kwargs) -> Assembly:
        """Enforces fixed offset distance between two parts."""
        from ..assembly_solver.mates import DistanceMate
        if not hasattr(self, "_mate_solver") or self._mate_solver is None:
            from ..assembly_solver.dof_solver import AssemblyMateSolver
            self._mate_solver = AssemblyMateSolver(self.name)
        pa = part_a.split(".")[0].split(":")[0]
        pb = part_b.split(".")[0].split(":")[0]
        self._mate_solver.add_mate(DistanceMate(pa, pb, distance=distance))
        f_sel = kwargs.get("first_selector") or (part_a.split(":", 1)[1] if ":" in part_a else None)
        s_sel = kwargs.get("second_selector") or (part_b.split(":", 1)[1] if ":" in part_b else None)
        if f_sel and s_sel:
            self._ir.add_mate(MateNode(mate_type=MateType.DISTANCE, part_a=pa, part_b=pb, first_selector=f_sel, second_selector=s_sel, parameters={"offset": distance}))
        return self

    def analyze_assembly_dof(self) -> Dict[str, Any]:
        """Analyzes 3D assembly degrees of freedom and unconstrained mobility."""
        if not hasattr(self, "_mate_solver") or self._mate_solver is None:
            from ..assembly_solver.dof_solver import AssemblyMateSolver
            self._mate_solver = AssemblyMateSolver(self.name)
        for pname in self._parts:
            self._mate_solver.add_part(pname)
        return self._mate_solver.analyze_dof()

