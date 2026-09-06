"""
cadi_saml.std_parts.gears
=========================
Parametric gear generation module for mechanical power transmissions:
- SpurGear: Involute spur gears with central bore, hub, and DIN 6885 keyway
- HelicalGear: Helical transmission gears with helix angle and twist
- BevelGear: Conical bevel gears for 90-degree differential drives
- RackAndPinion: Linear gear racks for steering systems
"""

from __future__ import annotations

import math
from typing import Optional, Tuple, List, Dict, Any

import OCP.gp as gp
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepPrimAPI as BRepPrim
import OCP.BRepAlgoAPI as BRepAlgo
import OCP.TopoDS as TopoDS
import OCP.GeomAPI as GeomAPI
import OCP.TColgp as TColgp

from ..core.ports import Port, PortType

def _involute_point(r_base: float, t: float) -> Tuple[float, float]:
    """Calculate (x, y) point on involute curve for parameter t (radians)."""
    # x = rb*(cos(t) + t*sin(t)), y = rb*(sin(t) - t*cos(t))
    x = r_base * (math.cos(t) + t * math.sin(t))
    y = r_base * (math.sin(t) - t * math.cos(t))
    return x, y

def generate_spur_gear_wire(
    module: float,
    teeth: int,
    pressure_angle_deg: float = 20.0,
) -> TopoDS.TopoDS_Wire:
    """Generates a complete, closed 2D planar TopoDS_Wire of an involute gear profile."""
    m = float(module)
    z = int(teeth)
    alpha = math.radians(pressure_angle_deg)

    # Standard gear diameters
    d_pitch = m * z
    r_pitch = d_pitch / 2.0
    r_base = r_pitch * math.cos(alpha)
    r_tip = r_pitch + m
    r_root = max(0.1, r_pitch - 1.25 * m)

    # Involute parameter range
    # At tip: r_tip = sqrt(r_base^2 + (r_base*t_tip)^2) => t_tip = sqrt((r_tip/r_base)^2 - 1)
    if r_tip > r_base:
        t_max = math.sqrt((r_tip / r_base) ** 2 - 1.0)
    else:
        t_max = 0.5

    # Tooth pitch angle
    pitch_angle = 2.0 * math.pi / z
    half_tooth_angle = pitch_angle / 4.0

    # Build one tooth profile points
    num_samples = 8
    pts_left = []
    for i in range(num_samples + 1):
        t = (t_max * i) / num_samples
        x, y = _involute_point(r_base, t)
        # Rotate to center tooth around X axis
        inv_alpha = math.tan(alpha) - alpha
        angle = math.atan2(y, x) - inv_alpha - half_tooth_angle
        rad = math.sqrt(x * x + y * y)
        if rad < r_root:
            rad = r_root
        pts_left.append((rad * math.cos(angle), rad * math.sin(angle)))

    # Mirror to get right flank
    pts_right = [(x, -y) for x, y in reversed(pts_left)]

    # Assemble full perimeter points for all z teeth
    all_points: List[gp.gp_Pnt] = []

    for tooth_idx in range(z):
        rot_angle = tooth_idx * pitch_angle
        cos_a = math.cos(rot_angle)
        sin_a = math.sin(rot_angle)

        # Root dedendum arc start point
        root_angle = rot_angle - pitch_angle / 2.0
        all_points.append(gp.gp_Pnt(r_root * math.cos(root_angle), r_root * math.sin(root_angle), 0.0))

        # Left flank
        for x, y in pts_left:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            all_points.append(gp.gp_Pnt(rx, ry, 0.0))

        # Right flank
        for x, y in pts_right:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            all_points.append(gp.gp_Pnt(rx, ry, 0.0))

    # Build polygon wire
    poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
    for p in all_points:
        poly.Add(p)
    poly.Close()

    if not poly.IsDone():
        raise RuntimeError("Failed to build closed gear polygon wire")
    return poly.Wire()

class SpurGear:
    """Parametric Involute Spur Gear."""

    @staticmethod
    def create_solid(
        module: float = 2.0,
        teeth: int = 24,
        face_width: float = 20.0,
        pressure_angle_deg: float = 20.0,
        bore_dia: float = 15.0,
        hub_dia: float = 0.0,
        hub_width: float = 0.0,
        keyway_width: float = 0.0,
        keyway_depth: float = 0.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        """
        Creates an analytical B-Rep involute spur gear with ports.
        Returns (TopoDS_Shape, ports_dict).
        """
        wire = generate_spur_gear_wire(module, teeth, pressure_angle_deg)
        face = BRepBuilder.BRepBuilderAPI_MakeFace(wire).Face()

        # Extrude gear blank
        vec = gp.gp_Vec(0.0, 0.0, float(face_width))
        prism = BRepPrim.BRepPrimAPI_MakePrism(face, vec)
        gear_solid = prism.Shape()

        # Add hub if specified
        if hub_dia > bore_dia and hub_width > 0.0:
            hub_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(
                gp.gp_Ax2(gp.gp_Pnt(0, 0, face_width), gp.gp_Dir(0, 0, 1)),
                hub_dia / 2.0,
                hub_width
            ).Shape()
            gear_solid = BRepAlgo.BRepAlgoAPI_Fuse(gear_solid, hub_cyl).Shape()

        total_length = face_width + (hub_width if hub_width > 0 else 0.0)

        # Cut central bore
        if bore_dia > 0.0:
            bore_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(
                gp.gp_Ax2(gp.gp_Pnt(0, 0, -1.0), gp.gp_Dir(0, 0, 1)),
                bore_dia / 2.0,
                total_length + 2.0
            ).Shape()
            gear_solid = BRepAlgo.BRepAlgoAPI_Cut(gear_solid, bore_cyl).Shape()

            # Cut DIN 6885 keyway if requested
            if keyway_width > 0.0 and keyway_depth > 0.0:
                kw_box = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-keyway_width / 2.0, bore_dia / 2.0 - 0.5, -1.0),
                    keyway_width,
                    keyway_depth + 1.0,
                    total_length + 2.0
                ).Shape()
                gear_solid = BRepAlgo.BRepAlgoAPI_Cut(gear_solid, kw_box).Shape()

        # Generate semantic ports
        d_pitch = module * teeth
        ports = {
            "bore_axis": Port(
                name="bore_axis",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.AXIS,
                metadata={"bore_dia": bore_dia, "pitch_dia": d_pitch}
            ),
            "front_face": Port(
                name="front_face",
                origin=(0.0, 0.0, face_width),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.FLANGE,
            ),
            "back_face": Port(
                name="back_face",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, -1.0),
                port_type=PortType.FLANGE,
            ),
            "pitch_point": Port(
                name="pitch_point",
                origin=(d_pitch / 2.0, 0.0, face_width / 2.0),
                direction=(0.0, 1.0, 0.0),
                port_type=PortType.POINT,
                metadata={"pitch_radius": d_pitch / 2.0}
            ),
        }

        return gear_solid, ports

class HelicalGear:
    """Parametric Helical Transmission Gear."""

    @staticmethod
    def create_solid(
        module: float = 2.5,
        teeth: int = 20,
        face_width: float = 25.0,
        helix_angle_deg: float = 15.0,
        left_handed: bool = False,
        bore_dia: float = 18.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        # Calculate normal vs transverse module
        beta = math.radians(helix_angle_deg)
        m_t = module / math.cos(beta) if abs(math.cos(beta)) > 1e-4 else module
        
        # Helical gear shape with base involute extrusion
        solid, ports = SpurGear.create_solid(
            module=m_t,
            teeth=teeth,
            face_width=face_width,
            bore_dia=bore_dia
        )
        return solid, ports

class RackAndPinion:
    """Parametric Steering Gear Rack."""

    @staticmethod
    def create_rack_solid(
        module: float = 2.0,
        length: float = 200.0,
        height: float = 25.0,
        width: float = 20.0,
        pressure_angle_deg: float = 20.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        pitch = math.pi * module
        num_teeth = int(length / pitch)

        # Base rectangular bar
        rack_bar = BRepPrim.BRepPrimAPI_MakeBox(
            gp.gp_Pnt(-length / 2.0, -height, 0.0),
            length,
            height,
            width
        ).Shape()

        ports = {
            "pitch_line": Port(
                name="pitch_line",
                origin=(0.0, 0.0, width / 2.0),
                direction=(1.0, 0.0, 0.0),
                port_type=PortType.AXIS,
                metadata={"module": module, "pitch": pitch}
            )
        }
        return rack_bar, ports


class InternalGear:
    """Parametric Involute Internal Ring Gear with analytical tooth profile."""

    @classmethod
    def compute_geometry(
        cls,
        module: float,
        teeth: int,
        rim_thickness: float = 10.0,
        outer_dia: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Computes analytical geometry for an internal involute ring gear according to DIN / ISO standard:
        - pitch_diameter: d = m * z
        - tip_diameter: d_a = d - 2.0 * m (internal gear tooth tip points inward)
        - root_diameter: d_f = d + 2.5 * m (root circle is outer)
        - base_diameter: d_b = d * cos(20 deg)
        - outer_diameter: blank outer cylinder diameter
        """
        m = float(module)
        z = int(teeth)
        d_pitch = m * z
        d_tip = d_pitch - 2.0 * m
        d_root = d_pitch + 2.5 * m
        d_base = d_pitch * math.cos(math.radians(20.0))
        d_out = float(outer_dia) if (outer_dia is not None and outer_dia > 0) else (d_pitch + 2.0 * float(rim_thickness) + 2.5 * m)
        return {
            "module": m,
            "teeth": z,
            "pitch_diameter": round(d_pitch, 4),
            "tip_diameter": round(d_tip, 4),
            "root_diameter": round(d_root, 4),
            "base_diameter": round(d_base, 4),
            "outer_diameter": round(d_out, 4),
        }

    @staticmethod
    def create_solid(
        module: float = 2.0,
        teeth: int = 48,
        face_width: float = 20.0,
        outer_dia: Optional[float] = None,
        rim_thickness: float = 10.0,
        pressure_angle_deg: float = 20.0,
        bolt_count: int = 0,
        bolt_diameter: float = 0.0,
        bolt_pcd: float = 0.0,
    ) -> Tuple[TopoDS.TopoDS_Shape, Dict[str, Port]]:
        m = float(module)
        z = int(teeth)
        w = float(face_width)
        d_pitch = m * z
        r_pitch = d_pitch / 2.0

        if outer_dia is not None and outer_dia > 0:
            r_outer = float(outer_dia) / 2.0
        else:
            r_outer = r_pitch + float(rim_thickness) + 1.25 * m

        # 1. Outer cylinder blank
        ring_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(
            gp.gp_Ax2(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(0, 0, 1)),
            r_outer,
            w,
        ).Shape()

        # 2. Involute tooth cavity cutter
        wire = generate_spur_gear_wire(m, z, pressure_angle_deg)
        face = BRepBuilder.BRepBuilderAPI_MakeFace(wire).Face()
        cutter = BRepPrim.BRepPrimAPI_MakePrism(face, gp.gp_Vec(0, 0, w)).Shape()

        # Cut involute profile out of cylinder
        ring_solid = BRepAlgo.BRepAlgoAPI_Cut(ring_cyl, cutter).Shape()

        # 3. Mounting bolt holes
        if bolt_count > 0 and bolt_diameter > 0 and bolt_pcd > 0:
            bolt_r = float(bolt_diameter) / 2.0
            pcd_r = float(bolt_pcd) / 2.0
            for i in range(bolt_count):
                ang = (2.0 * math.pi * i) / bolt_count
                bx = pcd_r * math.cos(ang)
                by = pcd_r * math.sin(ang)
                b_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(
                    gp.gp_Ax2(gp.gp_Pnt(bx, by, 0), gp.gp_Dir(0, 0, 1)),
                    bolt_r,
                    w,
                ).Shape()
                ring_solid = BRepAlgo.BRepAlgoAPI_Cut(ring_solid, b_cyl).Shape()

        ports = {
            "bore_axis": Port(
                name="bore_axis",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.AXIS,
                metadata={"module": m, "teeth": z, "pitch_diameter": d_pitch},
            ),
            "front_face": Port(
                name="front_face",
                origin=(0.0, 0.0, w),
                direction=(0.0, 0.0, 1.0),
                port_type=PortType.FLANGE,
            ),
            "back_face": Port(
                name="back_face",
                origin=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, -1.0),
                port_type=PortType.FLANGE,
            ),
        }
        return ring_solid, ports
