"""
cadi_saml.std_parts.linkages
============================
Parametric CAD solid generation for planar linkage mechanisms and reciprocating engines:
- Crankshaft: Single-piece crankshaft with main journal, counterweight web, and offset crankpin.
- ConnectingRod: Analytical connecting rod with big-end eye, tapered shank, small-end eye, and pin bores.
- SliderPiston: Horizontal cylindrical piston slider with wristpin and conrod clearance pocket.
- EngineFrame: Engine bedplate with crankshaft bearing pedestal and hollow cylinder bore.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import OCP.BRepAlgoAPI as BRepAlgo
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepPrimAPI as BRepPrim
import OCP.gp as gp
import OCP.TopoDS as TopoDS

from ..core.ports import Port, PortType


class Crankshaft:
    """Parametric single-piece crankshaft with integrated crankpin and main journal."""

    @staticmethod
    def create_solid(
        crank_radius: float = 30.0,
        disc_radius: float = 44.0,
        disc_thickness: float = 10.0,
        pin_diameter: float = 14.0,
        pin_length: float = 16.0,
        shaft_diameter: float = 16.0,
        shaft_length: float = 24.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        # Flywheel disc at Z=0 to disc_thickness
        disc_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
        disc = BRepPrim.BRepPrimAPI_MakeCylinder(disc_ax, disc_radius, disc_thickness).Solid()

        # Counterweight crescent / relief hole opposite the pin for realistic crankshaft look
        cw_hole_ax = gp.gp_Ax2(gp.gp_Pnt(-crank_radius * 0.7, 0.0, -1.0), gp.gp_Dir(0.0, 0.0, 1.0))
        cw_hole = BRepPrim.BRepPrimAPI_MakeCylinder(cw_hole_ax, 14.0, disc_thickness + 2.0).Solid()
        disc = BRepAlgo.BRepAlgoAPI_Cut(disc, cw_hole).Shape()

        # Offset crankpin at X=crank_radius, projecting forward along +Z
        pin_ax = gp.gp_Ax2(gp.gp_Pnt(crank_radius, 0.0, disc_thickness), gp.gp_Dir(0.0, 0.0, 1.0))
        pin = BRepPrim.BRepPrimAPI_MakeCylinder(pin_ax, pin_diameter / 2.0, pin_length).Solid()

        # Main shaft journal projecting backward along -Z
        shaft_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, -1.0))
        shaft = BRepPrim.BRepPrimAPI_MakeCylinder(shaft_ax, shaft_diameter / 2.0, shaft_length).Solid()

        # Fuse into a single monolithic crankshaft solid
        body = BRepAlgo.BRepAlgoAPI_Fuse(disc, pin).Shape()
        body = BRepAlgo.BRepAlgoAPI_Fuse(body, shaft).Shape()

        return body, {}


class ConnectingRod:
    """Parametric authentic connecting rod (biyel kolu) with I-beam shank and pin bores."""

    @staticmethod
    def create_solid(
        length: float = 90.0,
        big_bore_dia: float = 14.0,
        big_head_dia: float = 28.0,
        small_bore_dia: float = 10.0,
        small_head_dia: float = 20.0,
        thickness: float = 10.0,
        shank_width: float = 12.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        # Big end boss at (0, 0, 0)
        big_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
        big_boss = BRepPrim.BRepPrimAPI_MakeCylinder(big_ax, big_head_dia / 2.0, thickness).Solid()

        # Small end boss at (length, 0, 0)
        small_ax = gp.gp_Ax2(gp.gp_Pnt(length, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
        small_boss = BRepPrim.BRepPrimAPI_MakeCylinder(small_ax, small_head_dia / 2.0, thickness).Solid()

        # Shank connecting the two bosses
        shank = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(0.0, -shank_width / 2.0, 0.0), length, shank_width, thickness
        ).Solid()

        # Fuse bosses and shank
        rod = BRepAlgo.BRepAlgoAPI_Fuse(big_boss, shank).Shape()
        rod = BRepAlgo.BRepAlgoAPI_Fuse(rod, small_boss).Shape()

        # Bore crankpin hole through big end
        big_hole_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -1.0), gp.gp_Dir(0.0, 0.0, 1.0))
        big_hole = BRepPrim.BRepPrimAPI_MakeCylinder(big_hole_ax, big_bore_dia / 2.0, thickness + 2.0).Solid()
        rod = BRepAlgo.BRepAlgoAPI_Cut(rod, big_hole).Shape()

        # Bore wristpin hole through small end
        small_hole_ax = gp.gp_Ax2(gp.gp_Pnt(length, 0.0, -1.0), gp.gp_Dir(0.0, 0.0, 1.0))
        small_hole = BRepPrim.BRepPrimAPI_MakeCylinder(small_hole_ax, small_bore_dia / 2.0, thickness + 2.0).Solid()
        rod = BRepAlgo.BRepAlgoAPI_Cut(rod, small_hole).Shape()

        return rod, {}


class SliderPiston:
    """Horizontal cylindrical piston with piston rings, wristpin, and wide swing pocket."""

    @staticmethod
    def create_solid(
        diameter: float = 34.0,
        length: float = 42.0,
        pin_diameter: float = 10.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        # Cylinder aligned along X axis, centered at (0, 0, 0)
        ax = gp.gp_Ax2(gp.gp_Pnt(-length / 2.0, 0.0, 0.0), gp.gp_Dir(1.0, 0.0, 0.0))
        body = BRepPrim.BRepPrimAPI_MakeCylinder(ax, diameter / 2.0, length).Solid()

        # Piston ring grooves near the crown (+X end)
        for ring_x in [length / 2.0 - 5.0, length / 2.0 - 9.0]:
            rg_ax = gp.gp_Ax2(gp.gp_Pnt(ring_x - 0.75, 0.0, 0.0), gp.gp_Dir(1.0, 0.0, 0.0))
            cutter_outer = BRepPrim.BRepPrimAPI_MakeCylinder(rg_ax, diameter / 2.0 + 1.0, 1.5).Solid()
            cutter_inner = BRepPrim.BRepPrimAPI_MakeCylinder(rg_ax, diameter / 2.0 - 1.2, 1.5).Solid()
            ring_groove = BRepAlgo.BRepAlgoAPI_Cut(cutter_outer, cutter_inner).Shape()
            body = BRepAlgo.BRepAlgoAPI_Cut(body, ring_groove).Shape()

        # Hollow skirt pocket for connecting rod swing (open towards -X crank direction)
        pocket = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(-length / 2.0 - 1.0, -12.0, -12.0), length / 2.0 + 3.0, 24.0, 24.0
        ).Solid()
        body = BRepAlgo.BRepAlgoAPI_Cut(body, pocket).Shape()

        # Solid internal wristpin through (0, 0, 0) along Z
        pin_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -diameter / 2.0 + 2.0), gp.gp_Dir(0.0, 0.0, 1.0))
        wrist_pin = BRepPrim.BRepPrimAPI_MakeCylinder(pin_ax, pin_diameter / 2.0, diameter - 4.0).Solid()
        body = BRepAlgo.BRepAlgoAPI_Fuse(body, wrist_pin).Shape()

        return body, {}


class EngineFrame:
    """Engine frame bedplate with crankshaft bearing stand, hollow cylinder bore, and top cutaway window."""

    @staticmethod
    def create_solid(
        base_length: float = 250.0,
        base_width: float = 90.0,
        base_thickness: float = 12.0,
        bearing_center_z: float = 32.0,
        cylinder_bore_dia: float = 36.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        # Bedplate: X in [-55, 195], Y in [-45, 45], Z in [0, 12]
        base = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(-55.0, -base_width / 2.0, 0.0), base_length, base_width, base_thickness
        ).Solid()

        # Bedplate 4 mounting holes at corners
        for hx in [-42.0, 180.0]:
            for hy in [-35.0, 35.0]:
                h_ax = gp.gp_Ax2(gp.gp_Pnt(hx, hy, -1.0), gp.gp_Dir(0.0, 0.0, 1.0))
                bolt_h = BRepPrim.BRepPrimAPI_MakeCylinder(h_ax, 4.5, base_thickness + 2.0).Solid()
                base = BRepAlgo.BRepAlgoAPI_Cut(base, bolt_h).Shape()

        # Crankshaft bearing pedestal boss at X in [-24, 24], Y in [-24, 24], Z in [12, 17]
        stand = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(-24.0, -24.0, base_thickness), 48.0, 48.0, 5.0
        ).Solid()
        # Bearing hole along Z through pedestal and base
        b_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -1.0), gp.gp_Dir(0.0, 0.0, 1.0))
        b_bore = BRepPrim.BRepPrimAPI_MakeCylinder(b_ax, 9.0, 20.0).Solid()
        stand = BRepAlgo.BRepAlgoAPI_Cut(stand, b_bore).Shape()

        # Cylinder block at X in [68, 188], Y in [-32, 32], Z in [12, 54]
        cyl_block = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(68.0, -32.0, base_thickness), 120.0, 64.0, 42.0
        ).Solid()

        # Cylinder through-bore along X at Y=0, Z=bearing_center_z
        cyl_ax = gp.gp_Ax2(gp.gp_Pnt(60.0, 0.0, bearing_center_z), gp.gp_Dir(1.0, 0.0, 0.0))
        cyl_bore = BRepPrim.BRepPrimAPI_MakeCylinder(cyl_ax, cylinder_bore_dia / 2.0, 140.0).Solid()
        cyl_block = BRepAlgo.BRepAlgoAPI_Cut(cyl_block, cyl_bore).Shape()

        # Cutaway inspection window on top so the piston is clearly visible inside
        cutaway = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(80.0, -15.0, 45.0), 95.0, 30.0, 15.0
        ).Solid()
        cyl_block = BRepAlgo.BRepAlgoAPI_Cut(cyl_block, cutaway).Shape()

        # Fuse into solid engine frame
        frame = BRepAlgo.BRepAlgoAPI_Fuse(base, stand).Shape()
        frame = BRepAlgo.BRepAlgoAPI_Fuse(frame, cyl_block).Shape()

        return frame, {}
