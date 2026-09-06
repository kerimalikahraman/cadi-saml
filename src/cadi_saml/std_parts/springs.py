"""
cadi_saml.std_parts.springs
===========================
Parametric mechanical springs and motorsport suspension components:
- CoilSpring: Helical compression spring with ground flat ends and 3D B-Spline sweep
- Coilover: High-performance racing damper + spring assembly
"""

from __future__ import annotations

import math
from typing import Optional, Tuple, List, Dict, Any

import OCP.gp as gp
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepPrimAPI as BRepPrim
import OCP.BRepAlgoAPI as BRepAlgo
import OCP.BRepOffsetAPI as BRepOffsetAPI
import OCP.TopoDS as TopoDS
import OCP.GeomAPI as GeomAPI
import OCP.TColgp as TColgp

from ..core.ports import Port, PortType

class CoilSpring:
    """Parametric Helical Compression Spring with Ground Flat Ends."""

    @staticmethod
    def create_solid(
        wire_dia: float = 8.0,
        outer_dia: float = 65.0,
        free_length: float = 140.0,
        active_coils: float = 6.0,
        ground_ends: bool = True,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        """
        Creates a watertight 3D solid helical spring swept along an analytical helix.
        Returns (TopoDS_Shape, ports_dict).
        """
        d = float(wire_dia)
        D_out = float(outer_dia)
        L0 = float(free_length)
        n = float(active_coils)

        # Mean coil radius
        R_mean = (D_out - d) / 2.0
        total_coils = n + (1.5 if ground_ends else 0.0)
        total_angle = total_coils * 2.0 * math.pi
        pitch = L0 / total_coils

        # Sample points along the 3D helix
        samples_per_coil = 24
        total_samples = int(total_coils * samples_per_coil) + 1
        
        h_array = TColgp.TColgp_HArray1OfPnt(1, total_samples)

        pts: List[gp.gp_Pnt] = []
        for i in range(1, total_samples + 1):
            t = (i - 1) / (total_samples - 1)
            theta = t * total_angle
            z = t * L0
            x = R_mean * math.cos(theta)
            y = R_mean * math.sin(theta)
            p = gp.gp_Pnt(x, y, z)
            h_array.SetValue(i, p)
            pts.append(p)

        # Interpolate into smooth B-Spline curve
        interp = GeomAPI.GeomAPI_Interpolate(h_array, False, 1e-4)
        interp.Perform()
        if not interp.IsDone():
            raise RuntimeError("Failed to interpolate 3D spring helix curve")
        
        helix_curve = interp.Curve()
        helix_edge = BRepBuilder.BRepBuilderAPI_MakeEdge(helix_curve).Edge()
        spine_wire = BRepBuilder.BRepBuilderAPI_MakeWire(helix_edge).Wire()

        # Create circle profile at starting point normal to tangent
        p_start = pts[0]
        p_next = pts[1]
        tangent = gp.gp_Vec(p_start, p_next)
        t_dir = gp.gp_Dir(tangent)

        circle_ax2 = gp.gp_Ax2(p_start, t_dir)
        circle_edge = BRepBuilder.BRepBuilderAPI_MakeEdge(gp.gp_Circ(circle_ax2, d / 2.0)).Edge()
        profile_wire = BRepBuilder.BRepBuilderAPI_MakeWire(circle_edge).Wire()
        profile_face = BRepBuilder.BRepBuilderAPI_MakeFace(profile_wire).Face()

        # Sweep wire along spine
        pipe = BRepOffsetAPI.BRepOffsetAPI_MakePipe(spine_wire, profile_face)
        spring_solid = pipe.Shape()

        # Cut ends flat if ground_ends is True
        if ground_ends:
            cutter_size = D_out * 3.0
            # Bottom cut plane at z = d/4
            cut_bottom_z = d * 0.35
            box_bottom = BRepPrim.BRepPrimAPI_MakeBox(
                gp.gp_Pnt(-cutter_size / 2.0, -cutter_size / 2.0, -cutter_size + cut_bottom_z),
                cutter_size,
                cutter_size,
                cutter_size
            ).Shape()
            spring_solid = BRepAlgo.BRepAlgoAPI_Cut(spring_solid, box_bottom).Shape()

            # Top cut plane at z = L0 - d*0.35
            cut_top_z = L0 - d * 0.35
            box_top = BRepPrim.BRepPrimAPI_MakeBox(
                gp.gp_Pnt(-cutter_size / 2.0, -cutter_size / 2.0, cut_top_z),
                cutter_size,
                cutter_size,
                cutter_size
            ).Shape()
            spring_solid = BRepAlgo.BRepAlgoAPI_Cut(spring_solid, box_top).Shape()

        ports = {
            "bottom_seat": Port(
                name="bottom_seat",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, -1.0),
                port_type=PortType.FLANGE,
                metadata={"outer_dia": D_out, "inner_dia": D_out - 2 * d}
            ),
            "top_seat": Port(
                name="top_seat",
                origin=(0.0, 0.0, L0),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.FLANGE,
                metadata={"outer_dia": D_out, "inner_dia": D_out - 2 * d}
            ),
            "axis": Port(
                name="axis",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.AXIS,
                metadata={"free_length": L0}
            ),
        }

        return spring_solid, ports

class Coilover:
    """Formula Student / Racing Coilover Damper and Spring Assembly."""

    @staticmethod
    def create_solid(
        damper_body_dia: float = 46.0,
        damper_body_length: float = 160.0,
        rod_dia: float = 16.0,
        eye_to_eye_length: float = 280.0,
        spring_outer_dia: float = 68.0,
        spring_wire_dia: float = 9.0,
        extended_length: Optional[float] = None,
        stroke: Optional[float] = None,
        wire_dia: Optional[float] = None,
        **kwargs,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        """Creates an integrated racing coilover assembly (damper + spring + perches)."""
        if extended_length is not None:
            eye_to_eye_length = float(extended_length)
        if wire_dia is not None:
            spring_wire_dia = float(wire_dia)

        # Damper body cylinder
        body = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, 0, 20), gp.gp_Dir(0, 0, 1)),
            damper_body_dia / 2.0,
            damper_body_length
        ).Shape()

        # Lower mounting eyelet (ring at z=10, axis along Y)
        lower_eye = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, -15, 10), gp.gp_Dir(0, 1, 0)),
            18.0,
            30.0
        ).Shape()
        lower_hole = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, -16, 10), gp.gp_Dir(0, 1, 0)),
            6.0,
            32.0
        ).Shape()
        lower_eye = BRepAlgo.BRepAlgoAPI_Cut(lower_eye, lower_hole).Shape()
        damper_asm = BRepAlgo.BRepAlgoAPI_Fuse(body, lower_eye).Shape()

        # Chrome piston rod
        rod_length = eye_to_eye_length - damper_body_length - 30.0
        rod = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, 0, 20 + damper_body_length), gp.gp_Dir(0, 0, 1)),
            rod_dia / 2.0,
            rod_length
        ).Shape()
        damper_asm = BRepAlgo.BRepAlgoAPI_Fuse(damper_asm, rod).Shape()

        # Upper eyelet
        upper_eye = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, -15, eye_to_eye_length - 10), gp.gp_Dir(0, 1, 0)),
            18.0,
            30.0
        ).Shape()
        upper_hole = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, -16, eye_to_eye_length - 10), gp.gp_Dir(0, 1, 0)),
            6.0,
            32.0
        ).Shape()
        upper_eye = BRepAlgo.BRepAlgoAPI_Cut(upper_eye, upper_hole).Shape()
        damper_asm = BRepAlgo.BRepAlgoAPI_Fuse(damper_asm, upper_eye).Shape()

        # Spring
        spring_length = damper_body_length * 0.95
        spring_solid, _ = CoilSpring.create_solid(
            wire_dia=spring_wire_dia,
            outer_dia=spring_outer_dia,
            free_length=spring_length,
            active_coils=5.5,
            ground_ends=True
        )

        # Move spring to sit over damper body
        tr = gp.gp_Trsf()
        tr.SetTranslation(gp.gp_Vec(0, 0, 35.0))
        tr_spring = BRepBuilder.BRepBuilderAPI_Transform(spring_solid, tr, True).Shape()

        final_assembly = BRepAlgo.BRepAlgoAPI_Fuse(damper_asm, tr_spring).Shape()

        ports = {
            "lower_eyelet": Port(
                name="lower_eyelet",
                origin=(0.0, 0.0, 10.0),
                direction=(0.0, 1.0, 0.0),
                port_type=PortType.HOLE,
                metadata={"bore_dia": 12.0}
            ),
            "upper_eyelet": Port(
                name="upper_eyelet",
                origin=(0.0, 0.0, eye_to_eye_length - 10.0),
                direction=(0.0, 1.0, 0.0),
                port_type=PortType.HOLE,
                metadata={"bore_dia": 12.0}
            ),
            "centerline": Port(
                name="centerline",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.AXIS,
                metadata={"eye_to_eye": eye_to_eye_length}
            )
        }

        return final_assembly, ports
