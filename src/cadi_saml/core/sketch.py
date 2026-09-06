"""
cadi_saml.core.sketch
=====================
Declarative, AI-friendly 2D Sketching Engine.
Allows fluent composition of 2D profile geometries (circles, rectangles, slots,
regular polygons, arbitrary splines/polygons) and seamlessly converts them into
CrossSections, OpenCASCADE TopoDS_Wires, and TopoDS_Faces for extrusion or lofting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..ir.nodes import CrossSection


@dataclass
class SketchItem:
    """An individual 2D geometry element in a sketch."""
    item_type: str  # 'circle', 'rectangle', 'slot', 'polygon', 'regular_polygon'
    parameters: Dict[str, Any] = field(default_factory=dict)
    center: Tuple[float, float] = (0.0, 0.0)


class Sketch:
    """
    2D Planar Sketch builder.
    Can be used standalone or as a context manager with an Assembly.
    """

    def __init__(
        self,
        name: str = "sketch",
        plane: str = "XY",
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Optional[Tuple[float, float, float]] = None,
    ):
        self.name = name
        self.plane = plane.upper()
        self.origin = origin

        # Determine default normal from plane
        if normal:
            self.normal = normal
        elif self.plane == "XY":
            self.normal = (0.0, 0.0, 1.0)
        elif self.plane == "XZ":
            self.normal = (0.0, 1.0, 0.0)
        elif self.plane == "YZ":
            self.normal = (1.0, 0.0, 0.0)
        else:
            self.normal = (0.0, 0.0, 1.0)

        self._items: List[SketchItem] = []
        self._wires: List[List[Tuple[float, float, float]]] = []

    def add_circle(self, radius: float, center: Tuple[float, float] = (0.0, 0.0)) -> Sketch:
        """Add a 2D circular boundary."""
        self._items.append(
            SketchItem(item_type="circle", parameters={"radius": float(radius)}, center=center)
        )
        return self

    def add_rectangle(
        self, width: float, height: float, center: Tuple[float, float] = (0.0, 0.0)
    ) -> Sketch:
        """Add a 2D rectangular boundary."""
        self._items.append(
            SketchItem(
                item_type="rectangle",
                parameters={"width": float(width), "height": float(height)},
                center=center,
            )
        )
        return self

    def add_slot(
        self,
        length: float,
        width: Optional[float] = None,
        radius: Optional[float] = None,
        center: Tuple[float, float] = (0.0, 0.0),
        angle_deg: float = 0.0,
        points_per_arc: int = 12,
    ) -> Sketch:
        """
        Add a stadium/slot shape (two straight sides connected by two semicircular arcs).
        Accepts either width (diameter of ends) or radius.
        """
        if width is None and radius is not None:
            width = radius * 2.0
        elif width is None:
            width = 10.0

        r = width / 2.0
        half_l = max(0.0, (length - width) / 2.0)
        ang_rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(ang_rad), math.sin(ang_rad)


        pts_2d: List[Tuple[float, float]] = []

        # Right semicircular arc (from -pi/2 to +pi/2)
        for i in range(points_per_arc + 1):
            theta = -math.pi / 2.0 + (math.pi * i / points_per_arc)
            lx = half_l + r * math.cos(theta)
            ly = r * math.sin(theta)
            pts_2d.append((lx, ly))

        # Left semicircular arc (from +pi/2 to +3pi/2)
        for i in range(points_per_arc + 1):
            theta = math.pi / 2.0 + (math.pi * i / points_per_arc)
            lx = -half_l + r * math.cos(theta)
            ly = r * math.sin(theta)
            pts_2d.append((lx, ly))

        # Rotate and translate to center
        cx, cy = center
        transformed_pts: List[Tuple[float, float]] = []
        for x, y in pts_2d:
            rx = x * cos_a - y * sin_a + cx
            ry = x * sin_a + y * cos_a + cy
            transformed_pts.append((rx, ry))

        self._items.append(
            SketchItem(
                item_type="polygon",
                parameters={"points": transformed_pts},
                center=center,
            )
        )
        return self

    def add_polygon(self, points: List[Tuple[float, float]]) -> Sketch:
        """Add a 2D closed polygon from (X, Y) coordinate points."""
        self._items.append(
            SketchItem(item_type="polygon", parameters={"points": points}, center=(0.0, 0.0))
        )
        return self

    def add_regular_polygon(
        self,
        sides: int,
        radius: float,
        center: Tuple[float, float] = (0.0, 0.0),
        angle_deg: float = 0.0,
    ) -> Sketch:
        """Add a regular N-gon (hexagon, octagon, triangle, etc.)."""
        cx, cy = center
        pts: List[Tuple[float, float]] = []
        start_rad = math.radians(angle_deg)
        for i in range(sides):
            ang = start_rad + i * (2.0 * math.pi / sides)
            pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
        return self.add_polygon(pts)

    def to_cross_section(self) -> CrossSection:
        """
        Convert the primary sketch item into a CrossSection ready for
        add_extrude, add_loft, or add_sweep.
        """
        if not self._items:
            raise ValueError(f"Sketch '{self.name}' has no geometric items.")

        item = self._items[-1]
        cx, cy, cz = self.origin
        # Apply 2D center offset to 3D origin based on plane
        if self.plane == "XY":
            pt3d = (cx + item.center[0], cy + item.center[1], cz)
        elif self.plane == "XZ":
            pt3d = (cx + item.center[0], cy, cz + item.center[1])
        elif self.plane == "YZ":
            pt3d = (cx, cy + item.center[0], cz + item.center[1])
        else:
            pt3d = (cx + item.center[0], cy + item.center[1], cz)

        if item.item_type == "circle":
            return CrossSection(
                shape="circle",
                parameters=item.parameters,
                center=pt3d,
                normal=self.normal,
            )
        elif item.item_type == "rectangle":
            return CrossSection(
                shape="rectangle",
                parameters=item.parameters,
                center=pt3d,
                normal=self.normal,
            )
        elif item.item_type == "polygon":
            pts_2d = item.parameters["points"]
            pts_3d: List[Tuple[float, float, float]] = []
            for p in pts_2d:
                if self.plane == "XY":
                    pts_3d.append((cx + p[0], cy + p[1], cz))
                elif self.plane == "XZ":
                    pts_3d.append((cx + p[0], cy, cz + p[1]))
                elif self.plane == "YZ":
                    pts_3d.append((cx, cy + p[0], cz + p[1]))
                else:
                    pts_3d.append((cx + p[0], cy + p[1], cz))

            return CrossSection(
                shape="polygon",
                parameters={"points": pts_3d},
                center=pt3d,
                normal=self.normal,
            )

        raise NotImplementedError(f"Unsupported sketch item type: {item.item_type}")
