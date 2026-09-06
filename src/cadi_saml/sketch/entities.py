"""
2D Parametric Sketch Entities for CADI-SAML.
Defines Point, Line, Arc, Circle, and Spline primitives in local sketch coordinate space.
"""

from typing import Any, Dict, List, Optional, Tuple
import math
import uuid


class SketchPoint:
    """A 2D point with solvable coordinates (x, y)."""

    def __init__(self, x: float, y: float, fixed: bool = False, name: Optional[str] = None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"P_{self.id}"
        self.x: float = float(x)
        self.y: float = float(y)
        self.fixed: bool = fixed

    def get_vars(self) -> List[float]:
        return [] if self.fixed else [self.x, self.y]

    def set_vars(self, vals: List[float], offset: int) -> int:
        if not self.fixed:
            self.x = float(vals[offset])
            self.y = float(vals[offset + 1])
            return 2
        return 0

    def distance_to(self, other: "SketchPoint") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "type": "point", "x": round(self.x, 4), "y": round(self.y, 4), "fixed": self.fixed}


class SketchLine:
    """A 2D line segment defined by start and end points."""

    def __init__(self, start: SketchPoint, end: SketchPoint, name: Optional[str] = None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"Line_{self.id}"
        self.start: SketchPoint = start
        self.end: SketchPoint = end

    @property
    def dx(self) -> float:
        return self.end.x - self.start.x

    @property
    def dy(self) -> float:
        return self.end.y - self.start.y

    @property
    def length(self) -> float:
        return math.hypot(self.dx, self.dy)

    @property
    def angle_rad(self) -> float:
        return math.atan2(self.dy, self.dx)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": "line",
            "start": (round(self.start.x, 4), round(self.start.y, 4)),
            "end": (round(self.end.x, 4), round(self.end.y, 4)),
            "length": round(self.length, 4),
        }


class SketchCircle:
    """A 2D circle defined by center point and radius."""

    def __init__(self, center: SketchPoint, radius: float, name: Optional[str] = None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"Circle_{self.id}"
        self.center: SketchPoint = center
        self.radius: float = float(radius)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": "circle",
            "center": (round(self.center.x, 4), round(self.center.y, 4)),
            "radius": round(self.radius, 4),
            "diameter": round(self.radius * 2.0, 4),
        }


class SketchArc:
    """A 2D circular arc defined by center, radius, start angle, and end angle."""

    def __init__(
        self,
        center: SketchPoint,
        radius: float,
        start_angle_deg: float = 0.0,
        end_angle_deg: float = 90.0,
        name: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"Arc_{self.id}"
        self.center: SketchPoint = center
        self.radius: float = float(radius)
        self.start_angle_rad: float = math.radians(start_angle_deg)
        self.end_angle_rad: float = math.radians(end_angle_deg)

    @property
    def start_point(self) -> Tuple[float, float]:
        return (
            self.center.x + self.radius * math.cos(self.start_angle_rad),
            self.center.y + self.radius * math.sin(self.start_angle_rad),
        )

    @property
    def end_point(self) -> Tuple[float, float]:
        return (
            self.center.x + self.radius * math.cos(self.end_angle_rad),
            self.center.y + self.radius * math.sin(self.end_angle_rad),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": "arc",
            "center": (round(self.center.x, 4), round(self.center.y, 4)),
            "radius": round(self.radius, 4),
            "start_deg": round(math.degrees(self.start_angle_rad), 2),
            "end_deg": round(math.degrees(self.end_angle_rad), 2),
        }
