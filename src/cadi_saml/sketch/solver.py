"""
2D Geometric Sketch Constraint Solver and Degrees of Freedom (DOF) Engine for CADI-SAML.
Resolves under-constrained, fully-constrained, and over-constrained parametric profiles.
"""

from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np

from cadi_saml.sketch.entities import SketchPoint, SketchLine, SketchCircle, SketchArc
from cadi_saml.sketch.constraints import (
    SketchConstraint,
    CoincidentConstraint,
    HorizontalConstraint,
    VerticalConstraint,
    DistanceConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    ConcentricConstraint,
    EqualConstraint,
    TangentConstraint,
    AngleConstraint,
)

try:
    from scipy.optimize import least_squares
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class SketchSolver:
    """
    2D Parametric Sketch Manager and Constraint Solver.
    """

    def __init__(self, name: str = "Sketch"):
        self.name = name
        self.points: List[SketchPoint] = []
        self.lines: List[SketchLine] = []
        self.circles: List[SketchCircle] = []
        self.arcs: List[SketchArc] = []
        self.constraints: List[SketchConstraint] = []

    def add_point(self, x: float, y: float, fixed: bool = False, name: Optional[str] = None) -> SketchPoint:
        p = SketchPoint(x, y, fixed=fixed, name=name)
        self.points.append(p)
        return p

    def add_line(self, p1: SketchPoint, p2: SketchPoint, name: Optional[str] = None) -> SketchLine:
        line = SketchLine(p1, p2, name=name)
        self.lines.append(line)
        return line

    def add_circle(self, center: SketchPoint, radius: float, name: Optional[str] = None) -> SketchCircle:
        circle = SketchCircle(center, radius, name=name)
        self.circles.append(circle)
        return circle

    def add_arc(
        self,
        center: SketchPoint,
        radius: float,
        start_deg: float = 0.0,
        end_deg: float = 90.0,
        name: Optional[str] = None,
    ) -> SketchArc:
        arc = SketchArc(center, radius, start_deg, end_deg, name=name)
        self.arcs.append(arc)
        return arc

    def add_constraint(self, constraint: SketchConstraint) -> SketchConstraint:
        self.constraints.append(constraint)
        return constraint

    # Convenience constraint helpers
    def constrain_horizontal(self, line: SketchLine) -> HorizontalConstraint:
        return self.add_constraint(HorizontalConstraint(line))

    def constrain_vertical(self, line: SketchLine) -> VerticalConstraint:
        return self.add_constraint(VerticalConstraint(line))

    def constrain_distance(self, p1: SketchPoint, p2: SketchPoint, distance: float) -> DistanceConstraint:
        return self.add_constraint(DistanceConstraint(p1, p2, distance))

    def constrain_coincident(self, p1: SketchPoint, p2: SketchPoint) -> CoincidentConstraint:
        return self.add_constraint(CoincidentConstraint(p1, p2))

    def constrain_parallel(self, l1: SketchLine, l2: SketchLine) -> ParallelConstraint:
        return self.add_constraint(ParallelConstraint(l1, l2))

    def constrain_perpendicular(self, l1: SketchLine, l2: SketchLine) -> PerpendicularConstraint:
        return self.add_constraint(PerpendicularConstraint(l1, l2))

    def constrain_concentric(self, c1: SketchCircle, c2: SketchCircle) -> ConcentricConstraint:
        return self.add_constraint(ConcentricConstraint(c1, c2))

    def constrain_equal(self, e1: Any, e2: Any) -> EqualConstraint:
        return self.add_constraint(EqualConstraint(e1, e2))

    def constrain_tangent(self, line: SketchLine, circle: SketchCircle) -> TangentConstraint:
        return self.add_constraint(TangentConstraint(line, circle))

    def constrain_angle(self, l1: SketchLine, l2: SketchLine, angle_deg: float) -> AngleConstraint:
        return self.add_constraint(AngleConstraint(l1, l2, angle_deg))

    def _pack_variables(self) -> np.ndarray:
        vars_list = []
        for p in self.points:
            vars_list.extend(p.get_vars())
        return np.array(vars_list, dtype=float)

    def _unpack_variables(self, x: np.ndarray) -> None:
        idx = 0
        for p in self.points:
            if not p.fixed:
                p.x = float(x[idx])
                p.y = float(x[idx + 1])
                idx += 2

    def _objective(self, x: np.ndarray) -> np.ndarray:
        self._unpack_variables(x)
        residuals = []
        for c in self.constraints:
            residuals.extend(c.residuals())
        return np.array(residuals, dtype=float)

    def analyze_dof(self) -> Dict[str, Any]:
        """
        Evaluates system Degrees of Freedom (DOF).
        Reports under_constrained, fully_constrained, or over_constrained status.
        """
        free_pts = [p for p in self.points if not p.fixed]
        num_vars = len(free_pts) * 2
        num_eqs = sum(c.equation_count() for c in self.constraints)

        dof = max(0, num_vars - num_eqs)
        missing: List[str] = []

        if dof > 0:
            status = "under_constrained"
            # Suggest missing constraints
            for p in free_pts:
                p_constraints = [c for c in self.constraints if hasattr(c, "p1") and (c.p1 == p or c.p2 == p)]
                if not p_constraints:
                    missing.append(f"Position or distance constraint for point '{p.name}'")
            for l in self.lines:
                has_len = any(isinstance(c, DistanceConstraint) and ((c.p1 == l.start and c.p2 == l.end) or (c.p1 == l.end and c.p2 == l.start)) for c in self.constraints)
                has_orient = any(isinstance(c, (HorizontalConstraint, VerticalConstraint, AngleConstraint)) and getattr(c, "line", getattr(c, "l1", None)) == l for c in self.constraints)
                if not has_len:
                    missing.append(f"Length/distance constraint for line '{l.name}'")
                if not has_orient:
                    missing.append(f"Orientation (Horizontal/Vertical/Angle) for line '{l.name}'")
        elif num_eqs > num_vars:
            status = "over_constrained"
        else:
            status = "fully_constrained"

        return {
            "status": status,
            "free_dof": dof,
            "num_variables": num_vars,
            "num_equations": num_eqs,
            "missing_constraints": missing[:5],
        }

    def solve(self, max_iter: int = 100) -> Dict[str, Any]:
        """
        Numerically relaxes constraints to find valid geometry coordinates.
        Returns convergence status, final residual norm, and DOF report.
        """
        dof_info = self.analyze_dof()
        x0 = self._pack_variables()

        if len(x0) == 0 or len(self.constraints) == 0:
            return {
                "converged": True,
                "residual_norm": 0.0,
                **dof_info,
            }

        if HAS_SCIPY:
            res = least_squares(self._objective, x0, method="lm", max_nfev=max_iter * 10)
            self._unpack_variables(res.x)
            norm = float(np.linalg.norm(res.fun))
            converged = bool(norm < 1e-4)
        else:
            # Pure Python Gauss-Newton fallback
            x_curr = x0.copy()
            norm = 1.0
            converged = False
            for _ in range(max_iter):
                r0 = self._objective(x_curr)
                norm = float(np.linalg.norm(r0))
                if norm < 1e-4:
                    converged = True
                    break
                # Finite difference Jacobian
                eps = 1e-6
                J = np.zeros((len(r0), len(x_curr)))
                for j in range(len(x_curr)):
                    x_plus = x_curr.copy()
                    x_plus[j] += eps
                    r_plus = self._objective(x_plus)
                    J[:, j] = (r_plus - r0) / eps
                # Levenberg-Marquardt step
                damping = 1e-3 * np.eye(len(x_curr))
                try:
                    delta = np.linalg.solve(J.T @ J + damping, -J.T @ r0)
                    x_curr += delta
                except np.linalg.LinAlgError:
                    break
            self._unpack_variables(x_curr)

        return {
            "converged": converged,
            "residual_norm": round(norm, 6),
            **dof_info,
        }
