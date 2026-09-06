"""
2D Geometric Constraints for CADI-SAML Sketch Solver.
Implements analytical error residuals for non-linear constraint minimization.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple
import math

from cadi_saml.sketch.entities import SketchPoint, SketchLine, SketchCircle, SketchArc


class SketchConstraint(ABC):
    """Abstract base class for all 2D sketch constraints."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def residuals(self) -> List[float]:
        """Calculates constraint error residuals. Target is 0.0 for satisfied state."""
        pass

    @abstractmethod
    def equation_count(self) -> int:
        """Returns number of scalar constraint equations imposed."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class CoincidentConstraint(SketchConstraint):
    """Enforces two points occupy the exact same coordinate (dx=0, dy=0)."""

    def __init__(self, p1: SketchPoint, p2: SketchPoint):
        super().__init__(f"Coincident({p1.name}, {p2.name})")
        self.p1 = p1
        self.p2 = p2

    def residuals(self) -> List[float]:
        return [self.p1.x - self.p2.x, self.p1.y - self.p2.y]

    def equation_count(self) -> int:
        return 2

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "coincident", "p1": self.p1.name, "p2": self.p2.name}


class HorizontalConstraint(SketchConstraint):
    """Enforces line segment is horizontal (dy = 0)."""

    def __init__(self, line: SketchLine):
        super().__init__(f"Horizontal({line.name})")
        self.line = line

    def residuals(self) -> List[float]:
        return [self.line.end.y - self.line.start.y]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "horizontal", "line": self.line.name}


class VerticalConstraint(SketchConstraint):
    """Enforces line segment is vertical (dx = 0)."""

    def __init__(self, line: SketchLine):
        super().__init__(f"Vertical({line.name})")
        self.line = line

    def residuals(self) -> List[float]:
        return [self.line.end.x - self.line.start.x]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "vertical", "line": self.line.name}


class DistanceConstraint(SketchConstraint):
    """Enforces precise Euclidean distance between two points."""

    def __init__(self, p1: SketchPoint, p2: SketchPoint, distance: float):
        super().__init__(f"Distance({p1.name}, {p2.name}) = {distance}")
        self.p1 = p1
        self.p2 = p2
        self.target_distance = float(distance)

    def residuals(self) -> List[float]:
        dist = math.hypot(self.p1.x - self.p2.x, self.p1.y - self.p2.y)
        return [dist - self.target_distance]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "distance", "p1": self.p1.name, "p2": self.p2.name, "distance": self.target_distance}


class ParallelConstraint(SketchConstraint):
    """Enforces two lines are parallel: cross_product(v1, v2) = 0."""

    def __init__(self, line1: SketchLine, line2: SketchLine):
        super().__init__(f"Parallel({line1.name}, {line2.name})")
        self.l1 = line1
        self.l2 = line2

    def residuals(self) -> List[float]:
        cross = self.l1.dx * self.l2.dy - self.l1.dy * self.l2.dx
        return [cross]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "parallel", "l1": self.l1.name, "l2": self.l2.name}


class PerpendicularConstraint(SketchConstraint):
    """Enforces two lines are orthogonal: dot_product(v1, v2) = 0."""

    def __init__(self, line1: SketchLine, line2: SketchLine):
        super().__init__(f"Perpendicular({line1.name}, {line2.name})")
        self.l1 = line1
        self.l2 = line2

    def residuals(self) -> List[float]:
        dot = self.l1.dx * self.l2.dx + self.l1.dy * self.l2.dy
        return [dot]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "perpendicular", "l1": self.l1.name, "l2": self.l2.name}


class ConcentricConstraint(SketchConstraint):
    """Enforces two circular entities share the identical center point."""

    def __init__(self, c1: SketchCircle, c2: SketchCircle):
        super().__init__(f"Concentric({c1.name}, {c2.name})")
        self.c1 = c1
        self.c2 = c2

    def residuals(self) -> List[float]:
        return [self.c1.center.x - self.c2.center.x, self.c1.center.y - self.c2.center.y]

    def equation_count(self) -> int:
        return 2

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "concentric", "c1": self.c1.name, "c2": self.c2.name}


class EqualConstraint(SketchConstraint):
    """Enforces equal length between two lines or equal radius between two circles."""

    def __init__(self, e1: Any, e2: Any):
        super().__init__(f"Equal({e1.name}, {e2.name})")
        self.e1 = e1
        self.e2 = e2

    def residuals(self) -> List[float]:
        if hasattr(self.e1, "length") and hasattr(self.e2, "length"):
            return [self.e1.length - self.e2.length]
        if hasattr(self.e1, "radius") and hasattr(self.e2, "radius"):
            return [self.e1.radius - self.e2.radius]
        return [0.0]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "equal", "e1": self.e1.name, "e2": self.e2.name}


class TangentConstraint(SketchConstraint):
    """Enforces tangency between a line and a circle."""

    def __init__(self, line: SketchLine, circle: SketchCircle):
        super().__init__(f"Tangent({line.name}, {circle.name})")
        self.line = line
        self.circle = circle

    def residuals(self) -> List[float]:
        # Perpendicular distance from circle center to infinite line must equal circle radius
        # Line equation: A*x + B*y + C = 0
        # A = dy, B = -dx, C = dx*y1 - dy*x1
        dx = self.line.dx
        dy = self.line.dy
        line_len = math.hypot(dx, dy)
        if line_len < 1e-9:
            return [0.0]

        # Normal distance
        num = abs(dy * self.circle.center.x - dx * self.circle.center.y + (self.line.start.x * self.line.end.y - self.line.end.x * self.line.start.y))
        dist = num / line_len
        return [dist - self.circle.radius]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "tangent", "line": self.line.name, "circle": self.circle.name}


class AngleConstraint(SketchConstraint):
    """Enforces angle in degrees between two lines."""

    def __init__(self, line1: SketchLine, line2: SketchLine, angle_deg: float):
        super().__init__(f"Angle({line1.name}, {line2.name}) = {angle_deg}")
        self.l1 = line1
        self.l2 = line2
        self.target_rad = math.radians(angle_deg)

    def residuals(self) -> List[float]:
        l1_len = self.l1.length
        l2_len = self.l2.length
        if l1_len < 1e-9 or l2_len < 1e-9:
            return [0.0]
        dot = (self.l1.dx * self.l2.dx + self.l1.dy * self.l2.dy) / (l1_len * l2_len)
        dot = max(-1.0, min(1.0, dot))
        curr_rad = math.acos(dot)
        return [curr_rad - self.target_rad]

    def equation_count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "angle", "l1": self.l1.name, "l2": self.l2.name, "angle_deg": math.degrees(self.target_rad)}
