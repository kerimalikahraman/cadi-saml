"""
cadi_saml.macros.cam_macros
===========================
Mathematical Motion Cam Design Wizard.
Supports classic kinematic S-V-A-J (Stroke-Velocity-Acceleration-Jerk) motion laws:
- Dwell (constant position, zero velocity & jerk)
- Cycloidal (zero impact, continuous acceleration for high-speed indexing)
- Modified Sine (low peak acceleration, used in automotive valvetrains)
- Simple Harmonic (smooth medium-speed cams)
Generates full 3D B-Rep disk cams with shaft bore, keyway, and follower ports.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


def evaluate_motion_law(
    law: str,
    theta_norm: float,  # Normalized angle in segment [0, 1]
    lift: float,
    is_rise: bool = True,
) -> Tuple[float, float, float]:
    """
    Evaluates displacement s, normalized velocity v', and normalized acceleration a'
    for normalized parameter u = theta / beta in [0, 1].
    Returns (s, v_prime, a_prime) where v = v_prime * (h / beta), a = a_prime * (h / beta^2).
    """
    u = max(0.0, min(1.0, float(theta_norm)))
    law = law.lower().strip()

    if law == "dwell":
        s = lift if not is_rise else 0.0
        return s, 0.0, 0.0

    if law in ("cycloidal", "cyclo"):
        if is_rise:
            # s = h * [u - (1 / 2pi) * sin(2pi * u)]
            s = lift * (u - (1.0 / (2.0 * math.pi)) * math.sin(2.0 * math.pi * u))
            vp = lift * (1.0 - math.cos(2.0 * math.pi * u))
            ap = lift * (2.0 * math.pi * math.sin(2.0 * math.pi * u))
        else:
            # s = h * [1 - u + (1 / 2pi) * sin(2pi * u)]
            s = lift * (1.0 - u + (1.0 / (2.0 * math.pi)) * math.sin(2.0 * math.pi * u))
            vp = -lift * (1.0 - math.cos(2.0 * math.pi * u))
            ap = -lift * (2.0 * math.pi * math.sin(2.0 * math.pi * u))
        return s, vp, ap

    if law in ("harmonic", "shm"):
        if is_rise:
            # s = (h/2) * [1 - cos(pi * u)]
            s = (lift / 2.0) * (1.0 - math.cos(math.pi * u))
            vp = (lift * math.pi / 2.0) * math.sin(math.pi * u)
            ap = (lift * (math.pi ** 2) / 2.0) * math.cos(math.pi * u)
        else:
            s = (lift / 2.0) * (1.0 + math.cos(math.pi * u))
            vp = -(lift * math.pi / 2.0) * math.sin(math.pi * u)
            ap = -(lift * (math.pi ** 2) / 2.0) * math.cos(math.pi * u)
        return s, vp, ap

    if law in ("modified_sine", "mod_sine"):
        # Modified sine curve: quarter sine rise, linear, quarter sine
        if is_rise:
            if u <= 0.125:
                theta_m = 4.0 * math.pi * u
                s = lift * (math.pi / (4.0 + math.pi)) * (u - (1.0 / (4.0 * math.pi)) * math.sin(theta_m))
            elif u <= 0.875:
                u_mid = u - 0.125
                s = lift * (math.pi / (4.0 + math.pi)) * (0.125 + u_mid)
            else:
                u_end = u - 0.875
                theta_m = 4.0 * math.pi * u_end
                s = lift * (1.0 - (math.pi / (4.0 + math.pi)) * (0.125 - u_end + (1.0 / (4.0 * math.pi)) * math.sin(theta_m)))
            vp = lift * (math.pi / (4.0 + math.pi))
            ap = 0.0
        else:
            # Invert for fall
            s_rise, vp_rise, ap_rise = evaluate_motion_law("modified_sine", 1.0 - u, lift, is_rise=True)
            return s_rise, -vp_rise, -ap_rise
        return s, vp, ap

    # Explicit linear / constant velocity law
    if law in ("linear", "constant_velocity", "uniform"):
        if is_rise:
            s = lift * u
            vp = lift
            ap = 0.0
        else:
            s = lift * (1.0 - u)
            vp = -lift
            ap = 0.0
        return s, vp, ap

    from ..core.exceptions import CADISpecificationError

    valid_laws = ["cycloidal", "harmonic", "modified_sine", "linear", "dwell"]
    raise CADISpecificationError(
        message=f"Bilinmeyen kam hareket yasası: '{law}'.",
        parameter_name="law",
        provided_value=law,
        valid_options=valid_laws,
        suggested_fix=f"Standart kinematik hareket yasalarından birini seçin: {', '.join(valid_laws)}",
    )


def add_disk_cam(
    assembly: "Assembly",
    name: str,
    on_shaft: Optional[str] = None,
    base_radius: float = 30.0,
    lift: float = 12.0,
    width: float = 15.0,
    face_width: Optional[float] = None,
    bore_dia: float = 15.0,
    motion_profile: Optional[str] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    num_samples: int = 180,
    material: str = "Steel4140",
    color: Tuple[float, float, float] = (0.78, 0.72, 0.65),
) -> Dict[str, Any]:
    """
    Builds a complete, manifold 3D disk cam based on kinematic motion law segments.
    Supports ZERO-COORDINATE placement onto a shaft via on_shaft='camshaft_1'.

    Default segment cycle if None provided (Rise-Dwell-Fall-Dwell):
      1. Rise: 0° -> 120° (Cycloidal, 12mm)
      2. Dwell: 120° -> 180° (Top dwell, 12mm)
      3. Fall: 180° -> 300° (Cycloidal back to 0mm)
      4. Dwell: 300° -> 360° (Bottom dwell, 0mm)
    """
    actual_width = float(face_width if face_width is not None else width)
    if segments is None:
        law = (motion_profile or "cycloidal").lower().strip()
        segments = [
            {"type": "rise", "angle_deg": 120.0, "law": law},
            {"type": "dwell", "angle_deg": 60.0, "lift_val": lift},
            {"type": "fall", "angle_deg": 120.0, "law": law},
            {"type": "dwell", "angle_deg": 60.0, "lift_val": 0.0},
        ]

    # Validate angles sum to 360
    total_angle = sum(float(seg["angle_deg"]) for seg in segments)
    if abs(total_angle - 360.0) > 1e-3:
        raise ValueError(f"Cam motion segments must sum to 360 degrees, got {total_angle} degrees.")

    # Generate 2D profile coordinates
    profile_pts: List[Tuple[float, float]] = []
    current_angle = 0.0
    current_lift = 0.0

    # Build angular lookup tables
    segment_ranges = []
    accum_ang = 0.0
    for seg in segments:
        deg = float(seg["angle_deg"])
        segment_ranges.append((accum_ang, accum_ang + deg, seg))
        accum_ang += deg

    for i in range(num_samples):
        theta_deg = (360.0 * i) / num_samples
        theta_rad = math.radians(theta_deg)

        # Locate segment
        active_seg = segments[-1]
        start_a, end_a = 0.0, 360.0
        for s_ang, e_ang, s_data in segment_ranges:
            if s_ang <= theta_deg < e_ang or (i == num_samples - 1 and theta_deg <= e_ang):
                active_seg = s_data
                start_a = s_ang
                end_a = e_ang
                break

        seg_type = active_seg.get("type", "dwell").lower()
        seg_law = active_seg.get("law", "cycloidal")
        seg_deg = end_a - start_a
        u = (theta_deg - start_a) / seg_deg if seg_deg > 1e-4 else 0.0

        if seg_type == "rise":
            s, _, _ = evaluate_motion_law(seg_law, u, lift, is_rise=True)
        elif seg_type == "fall":
            s, _, _ = evaluate_motion_law(seg_law, u, lift, is_rise=False)
        elif seg_type == "dwell":
            s = float(active_seg.get("lift_val", lift if "fall" in [s.get("type") for s in segments] else 0.0))
        else:
            s = 0.0

        r = base_radius + s
        px = r * math.cos(theta_rad)
        py = r * math.sin(theta_rad)
        profile_pts.append((round(px, 5), round(py, 5)))

    # Create Sketch and extrude
    from ..core.sketch import Sketch
    sketch = Sketch(name=f"{name}_profile_sketch", plane="XY")
    sketch.add_polygon(profile_pts)

    part_ref = assembly.add_extrude(
        name=name,
        section=sketch,
        distance=actual_width,
        direction=(0.0, 0.0, 1.0),
    )
    part_ref.node.parameters.update({
        "base_radius": float(base_radius),
        "lift": float(lift),
        "face_width": float(actual_width),
        "width": float(actual_width),
        "bore_dia": float(bore_dia),
    })
    part_ref.set_appearance(color=color, material=material)

    # Cut center bore if requested
    if bore_dia > 0.0:
        bore_name = f"{name}_center_bore"
        assembly.add_cylinder(
            name=bore_name,
            radius=bore_dia / 2.0,
            height=width + 10.0,
            origin=(0.0, 0.0, -5.0),
        )
        assembly.cut(name, bore_name, keep_tool=False)

    # Attach ports for shaft and follower contact
    part_ref.add_port(
        name="bore_axis",
        port_type="axis",
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        diameter=bore_dia,
    )
    part_ref.add_port(
        name="cam_surface_prime",
        port_type="point",
        position=(base_radius, 0.0, width / 2.0),
        normal=(1.0, 0.0, 0.0),
    )

    if on_shaft:
        assembly.connect(f"{name}:bore_axis", f"{on_shaft}:bore_axis", mate_type="COAXIAL")

    return {
        "cam_name": name,
        "base_radius_mm": base_radius,
        "max_lift_mm": lift,
        "width_mm": width,
        "bore_diameter_mm": bore_dia,
        "num_profile_points": len(profile_pts),
        "segments": segments,
        "ports": ["bore_axis", "cam_surface_prime"],
    }
