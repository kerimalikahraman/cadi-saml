"""
cadi_saml.core.text_engine
==========================
High-Performance 3D B-Rep Text, Decal, and Engraving Engine.
Uses OpenCASCADE StdPrs_BRepTextBuilder and StdPrs_BRepFont to generate
exact 3D parametric solids from typography for branding, part numbering,
and technical markings (e.g., 'O·Z RACING', 'CARBONIO', 'Formula Student').
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import OCP.BRep as BRep
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepPrimAPI as BRepPrim
import OCP.Font as Font
import OCP.NCollection as NCol
import OCP.StdPrs as StdPrs
import OCP.TopAbs as TopAbs
import OCP.TopExp as TopExp
import OCP.TopoDS as TopoDS
import OCP.gp as gp


class TextEngine:
    """Generates 3D solid B-Rep geometry for text strings."""

    @staticmethod
    def build_3d_text(
        text: str,
        font_size: float = 10.0,
        depth: float = 1.0,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        font_name: str = "Arial",
    ) -> TopoDS.TopoDS_Shape:
        """
        Build 3D extruded B-Rep solid text compound.
        """
        builder = StdPrs.StdPrs_BRepTextBuilder()
        try:
            brep_font = StdPrs.StdPrs_BRepFont(
                NCol.NCollection_Utf8String(font_name),
                Font.Font_FontAspect_Bold,
                float(font_size),
            )
        except Exception:
            brep_font = StdPrs.StdPrs_BRepFont(
                NCol.NCollection_Utf8String("Arial"),
                Font.Font_FontAspect_Regular,
                float(font_size),
            )

        # Coordinate system for text
        pos_pnt = gp.gp_Pnt(*position)
        norm_dir = gp.gp_Dir(*normal)

        # Determine reference X direction
        x_candidate = gp.gp_Dir(1.0, 0.0, 0.0)
        if abs(norm_dir.Dot(x_candidate)) > 0.95:
            x_candidate = gp.gp_Dir(0.0, 1.0, 0.0)
        y_dir = norm_dir.Crossed(x_candidate)
        x_dir = y_dir.Crossed(norm_dir)

        ax3 = gp.gp_Ax3(pos_pnt, norm_dir, x_dir)
        text_shape = builder.Perform(brep_font, NCol.NCollection_Utf8String(text), ax3)

        # Extrude all planar letter faces along normal vector by depth
        compound_builder = BRep.BRep_Builder()
        text_solid_compound = TopoDS.TopoDS_Compound()
        compound_builder.MakeCompound(text_solid_compound)

        extrude_vec = gp.gp_Vec(norm_dir.X() * depth, norm_dir.Y() * depth, norm_dir.Z() * depth)

        exp = TopExp.TopExp_Explorer(text_shape, TopAbs.TopAbs_FACE)
        has_faces = False
        while exp.More():
            face = TopoDS.TopoDS.Face_s(exp.Current())
            letter_prism = BRepPrim.BRepPrimAPI_MakePrism(face, extrude_vec).Shape()
            compound_builder.Add(text_solid_compound, letter_prism)
            has_faces = True
            exp.Next()

        if not has_faces:
            # If no faces were extracted, return the original wire/shape
            return text_shape

        return text_solid_compound

    @staticmethod
    def build_circular_text(
        text: str,
        radius: float,
        center_angle_deg: float = 90.0,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        font_size: float = 10.0,
        depth: float = 1.0,
        font_name: str = "Arial",
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        inward_facing: bool = False,
    ) -> TopoDS.TopoDS_Shape:
        """
        Build 3D B-Rep text curved along a circular arc of given radius.
        text: string to render
        radius: distance from circle center to text baseline in mm
        center_angle_deg: angle around circle where text is centered (0°=+X, 90°=+Y, 180°=-X, 270°=-Y)
        center: 3D origin of the circle (cx, cy, cz)
        normal: normal of the circle plane (default +Z)
        inward_facing: if True, text top faces toward center; if False, text top faces outwards
        """
        import OCP.Bnd as Bnd
        import OCP.BRepBndLib as BRepBndLib

        builder = StdPrs.StdPrs_BRepTextBuilder()
        try:
            brep_font = StdPrs.StdPrs_BRepFont(
                NCol.NCollection_Utf8String(font_name),
                Font.Font_FontAspect_Bold,
                float(font_size),
            )
        except Exception:
            brep_font = StdPrs.StdPrs_BRepFont(
                NCol.NCollection_Utf8String("Arial"),
                Font.Font_FontAspect_Regular,
                float(font_size),
            )

        # 1. Pre-measure character widths
        widths = []
        char_shapes = []
        for ch in text:
            if ch == " ":
                w = font_size * 0.45
                widths.append(w)
                char_shapes.append(None)
                continue
            sh = builder.Perform(brep_font, NCol.NCollection_Utf8String(ch), gp.gp_Ax3())
            bnd = Bnd.Bnd_Box()
            BRepBndLib.BRepBndLib.Add_s(sh, bnd)
            vals = bnd.Get()
            w = max(font_size * 0.2, vals[3] - vals[0])
            mid_x = (vals[0] + vals[3]) / 2.0
            mid_y = (vals[1] + vals[4]) / 2.0
            widths.append(w)
            char_shapes.append((sh, mid_x, mid_y))

        letter_spacing = font_size * 0.18
        total_arc_len = sum(widths) + max(0, len(text) - 1) * letter_spacing

        cx, cy, cz = center
        curr_arc = total_arc_len / 2.0

        compound_builder = BRep.BRep_Builder()
        text_solid_compound = TopoDS.TopoDS_Compound()
        compound_builder.MakeCompound(text_solid_compound)

        extrude_vec = gp.gp_Vec(normal[0] * depth, normal[1] * depth, normal[2] * depth)

        for ch, w, item in zip(text, widths, char_shapes):
            if item is None:
                curr_arc -= (w + letter_spacing)
                continue

            sh, mx, my = item
            ch_mid_arc = curr_arc - w / 2.0
            if not inward_facing:
                ang = math.radians(center_angle_deg) + (ch_mid_arc / radius)
                rot_ang = ang - math.pi / 2.0
            else:
                # When letters face inwards towards the center, reverse traversal so characters read left-to-right/naturally without mirroring
                ang = math.radians(center_angle_deg) - (ch_mid_arc / radius)
                rot_ang = ang + math.pi / 2.0

            px = cx + radius * math.cos(ang)
            py = cy + radius * math.sin(ang)



            t_center = gp.gp_Trsf()
            t_center.SetTranslation(gp.gp_Vec(-mx, -my, 0.0))

            t_rot = gp.gp_Trsf()
            t_rot.SetRotation(gp.gp_Ax1(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(0, 0, 1)), rot_ang)

            t_trans = gp.gp_Trsf()
            t_trans.SetTranslation(gp.gp_Vec(px, py, cz))

            final_t = t_trans.Multiplied(t_rot.Multiplied(t_center))
            sh_placed = BRepBuilder.BRepBuilderAPI_Transform(sh, final_t, True).Shape()

            exp = TopExp.TopExp_Explorer(sh_placed, TopAbs.TopAbs_FACE)
            while exp.More():
                face = TopoDS.TopoDS.Face_s(exp.Current())
                prism = BRepPrim.BRepPrimAPI_MakePrism(face, extrude_vec).Shape()
                compound_builder.Add(text_solid_compound, prism)
                exp.Next()

            curr_arc -= (w + letter_spacing)

        return text_solid_compound

