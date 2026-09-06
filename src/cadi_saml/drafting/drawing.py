"""
cadi_saml.drafting.drawing
==========================
Generates production-grade 2D engineering drawings (ISO / DIN drawing sheets)
with multi-view orthographic projections, hidden line rendering, drawing frames,
and engineering title blocks (antet) in vector SVG format.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from OCP.TopoDS import TopoDS_Shape
from .projection import HLRProjectionResult, HLRViewExtractor


@dataclass
class SheetDimensions:
    width: float   # mm
    height: float  # mm
    margin_left: float = 20.0
    margin_top: float = 10.0
    margin_right: float = 10.0
    margin_bottom: float = 10.0


SHEET_SIZES: Dict[str, SheetDimensions] = {
    "A4": SheetDimensions(width=297.0, height=210.0),
    "A4_PORTRAIT": SheetDimensions(width=210.0, height=297.0),
    "A3": SheetDimensions(width=420.0, height=297.0),
}


class DrawingSheet:
    """
    ISO-standard engineering drawing sheet layout engine.
    Arranges 2D HLR projection views, border frames, and title blocks.
    """

    def __init__(
        self,
        title: str = "ENGINEERING DRAWING",
        part_name: str = "PART_01",
        material: str = "S235JR",
        units: str = "mm",
        sheet_size: str = "A4",
        author: str = "CADi SAML Engine",
    ):
        self.title = title
        self.part_name = part_name
        self.material = material
        self.units = units
        self.author = author
        self.date_str = datetime.date.today().strftime("%Y-%m-%d")

        key = sheet_size.upper().strip()
        self.dim = SHEET_SIZES.get(key, SHEET_SIZES["A4"])
        self.views: Dict[str, HLRProjectionResult] = {}

    def add_view(self, view_name: str, projection: HLRProjectionResult) -> None:
        """Adds an HLR projection result for a specific view."""
        self.views[view_name] = projection

    def generate_views_from_shape(
        self,
        shape: TopoDS_Shape,
        views: Optional[List[str]] = None,
    ) -> None:
        """Extracts and adds HLR projections for the given shape."""
        if views is None:
            views = ["top", "front", "right", "iso"]

        for v in views:
            proj = HLRViewExtractor.extract_view(shape, view_name=v)
            self.add_view(v, proj)

    def render_svg(self) -> str:
        """Compiles the entire drawing sheet into clean, scalable SVG text."""
        w = self.dim.width
        h = self.dim.height

        svg_parts: List[str] = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}mm" height="{h}mm">',
            f'  <defs>',
            f'    <style>',
            f'      .border-line {{ stroke: #000000; stroke-width: 0.5; fill: none; }}',
            f'      .inner-border {{ stroke: #000000; stroke-width: 0.35; fill: none; }}',
            f'      .title-block {{ stroke: #000000; stroke-width: 0.3; fill: none; }}',
            f'      .text-title {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 3.5px; font-weight: bold; fill: #111111; }}',
            f'      .text-label {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 2.0px; fill: #555555; }}',
            f'      .text-value {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 2.5px; font-weight: 600; fill: #000000; }}',
            f'      .view-label {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 3.0px; font-weight: bold; fill: #222222; text-anchor: middle; }}',
            f'      .visible-edge {{ stroke: #0b0f19; stroke-width: 0.35; stroke-linecap: round; stroke-linejoin: round; fill: none; }}',
            f'      .hidden-edge {{ stroke: #6b7280; stroke-width: 0.20; stroke-dasharray: 1.5, 1.2; stroke-linecap: round; fill: none; }}',
            f'    </style>',
            f'  </defs>',
            f'  <!-- Background -->',
            f'  <rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>',
        ]

        # 1. Outer Border and Drawing Frame
        svg_parts.append(self._render_border())

        # 2. Title Block (Antet) in bottom right corner
        svg_parts.append(self._render_title_block())

        # 3. View Projections Placement
        svg_parts.append(self._render_views())

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def export_svg(self, filepath: str) -> None:
        """Writes drawing to an SVG file."""
        out_path = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        content = self.render_svg()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _render_border(self) -> str:
        """Renders standard ISO drawing boundary frames."""
        w = self.dim.width
        h = self.dim.height
        ml = self.dim.margin_left
        mt = self.dim.margin_top
        mr = self.dim.margin_right
        mb = self.dim.margin_bottom

        lines = [
            f'  <!-- Drawing Borders -->',
            f'  <rect x="5" y="5" width="{w - 10}" height="{h - 10}" class="border-line"/>',
            f'  <rect x="{ml}" y="{mt}" width="{w - ml - mr}" height="{h - mt - mb}" class="inner-border"/>',
        ]
        return "\n".join(lines)

    def _render_title_block(self) -> str:
        """Renders standard engineering title block (Antet)."""
        w = self.dim.width
        h = self.dim.height
        mr = self.dim.margin_right
        mb = self.dim.margin_bottom

        tb_w = 110.0
        tb_h = 32.0
        x0 = w - mr - tb_w
        y0 = h - mb - tb_h

        lines = [
            f'  <!-- Title Block (Antet) -->',
            f'  <g id="title_block">',
            f'    <rect x="{x0}" y="{y0}" width="{tb_w}" height="{tb_h}" fill="#fcfcfd" class="title-block"/>',
            # Horizontal dividers
            f'    <line x1="{x0}" y1="{y0 + 12}" x2="{x0 + tb_w}" y2="{y0 + 12}" class="title-block"/>',
            f'    <line x1="{x0}" y1="{y0 + 22}" x2="{x0 + tb_w}" y2="{y0 + 22}" class="title-block"/>',
            # Vertical dividers
            f'    <line x1="{x0 + 60}" y1="{y0}" x2="{x0 + 60}" y2="{y0 + tb_h}" class="title-block"/>',
            f'    <line x1="{x0 + 85}" y1="{y0 + 12}" x2="{x0 + 85}" y2="{y0 + tb_h}" class="title-block"/>',
            # Text Elements
            f'    <text x="{x0 + 3}" y="{y0 + 5}" class="text-label">DRAWING TITLE / PROJE ADI</text>',
            f'    <text x="{x0 + 3}" y="{y0 + 10}" class="text-title">{self.title}</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 5}" class="text-label">PART / PARCA</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 10}" class="text-value">{self.part_name}</text>',
            f'    <text x="{x0 + 3}" y="{y0 + 16}" class="text-label">MATERIAL / MALZEME</text>',
            f'    <text x="{x0 + 3}" y="{y0 + 20}" class="text-value">{self.material}</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 16}" class="text-label">DATE / TARIH</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 20}" class="text-value">{self.date_str}</text>',
            f'    <text x="{x0 + 88}" y="{y0 + 16}" class="text-label">UNITS</text>',
            f'    <text x="{x0 + 88}" y="{y0 + 20}" class="text-value">{self.units}</text>',
            f'    <text x="{x0 + 3}" y="{y0 + 26}" class="text-label">AUTHOR / TASARIMCI</text>',
            f'    <text x="{x0 + 3}" y="{y0 + 30}" class="text-value">{self.author}</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 26}" class="text-label">SHEET</text>',
            f'    <text x="{x0 + 63}" y="{y0 + 30}" class="text-value">1 / 1</text>',
            f'    <text x="{x0 + 88}" y="{y0 + 26}" class="text-label">STATUS</text>',
            f'    <text x="{x0 + 88}" y="{y0 + 30}" class="text-value">RELEASED</text>',
            f'  </g>',
        ]
        return "\n".join(lines)

    def _render_views(self) -> str:
        """Arranges 2D projection views into designated quadrants."""
        ml = self.dim.margin_left + 5.0
        mt = self.dim.margin_top + 5.0
        w_avail = self.dim.width - self.dim.margin_left - self.dim.margin_right - 10.0
        h_avail = self.dim.height - self.dim.margin_top - self.dim.margin_bottom - 10.0

        quad_w = w_avail / 2.0
        quad_h = h_avail / 2.0

        # Standard layout:
        # Top-Left:     Top View
        # Bottom-Left:  Front View
        # Top-Right:    Isometric View
        # Bottom-Right: Right View (above title block)
        view_slots = {
            "top": (ml, mt, quad_w, quad_h, "TOP VIEW / UST GORUNUS"),
            "front": (ml, mt + quad_h, quad_w, quad_h, "FRONT VIEW / ON GORUNUS"),
            "iso": (ml + quad_w, mt, quad_w, quad_h, "ISOMETRIC VIEW / IZOMETRIK"),
            "right": (ml + quad_w, mt + quad_h, quad_w, quad_h - 18.0, "RIGHT VIEW / SAG GORUNUS"),
        }

        rendered = []
        for v_name, (vx, vy, vw, vh, label) in view_slots.items():
            if v_name in self.views:
                proj = self.views[v_name]
                rendered.append(self._render_single_view(proj, vx, vy, vw, vh, label))

        return "\n".join(rendered)

    def _render_single_view(
        self,
        proj: HLRProjectionResult,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        label: str,
    ) -> str:
        """Transforms and scales a single 2D projection into the specified box."""
        margin_pad = 8.0
        target_w = max(10.0, box_w - 2 * margin_pad)
        target_h = max(10.0, box_h - 2 * margin_pad - 6.0)

        # Scale factor
        pw = proj.width
        ph = proj.height
        scale = min(target_w / pw, target_h / ph) if (pw > 0 and ph > 0) else 1.0

        # Center in box
        center_x = box_x + box_w / 2.0
        center_y = box_y + (box_h - 6.0) / 2.0

        mid_px = (proj.min_x + proj.max_x) / 2.0
        mid_py = (proj.min_y + proj.max_y) / 2.0

        def tf(x: float, y: float) -> Tuple[float, float]:
            # OpenCASCADE 2D Y is up; SVG Y is down, so invert Y
            sx = center_x + (x - mid_px) * scale
            sy = center_y - (y - mid_py) * scale
            return (sx, sy)

        paths = [
            f'  <!-- View: {proj.view_name} -->',
            f'  <g id="view_{proj.view_name}">',
            f'    <text x="{center_x}" y="{box_y + box_h - 1.0}" class="view-label">{label}</text>',
        ]

        # 1. Hidden Lines (Rendered first so visible lines stay on top)
        for seg in proj.hidden_segments:
            if len(seg) >= 2:
                d_str = " ".join(
                    f"{'M' if i == 0 else 'L'} {tf(p[0], p[1])[0]:.2f} {tf(p[0], p[1])[1]:.2f}"
                    for i, p in enumerate(seg)
                )
                paths.append(f'    <path d="{d_str}" class="hidden-edge"/>')

        # 2. Visible Lines
        for seg in proj.visible_segments:
            if len(seg) >= 2:
                d_str = " ".join(
                    f"{'M' if i == 0 else 'L'} {tf(p[0], p[1])[0]:.2f} {tf(p[0], p[1])[1]:.2f}"
                    for i, p in enumerate(seg)
                )
                paths.append(f'    <path d="{d_str}" class="visible-edge"/>')

        paths.append('  </g>')
        return "\n".join(paths)
