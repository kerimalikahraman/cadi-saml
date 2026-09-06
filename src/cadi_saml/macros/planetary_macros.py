"""
cadi_saml.macros.planetary_macros
=================================
SolidWorks-grade Planetary Gearbox Wizard.
Computes kinematically valid tooth counts, checks assembleability conditions,
generates sun gear, planet gears arrayed around the carrier, carrier plate,
and ring gear housing, and establishes kinematic gear coupling relations.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


def solve_planetary_teeth(
    desired_ratio: float = 4.0,
    num_planets: int = 3,
    min_sun_teeth: int = 15,
) -> Tuple[int, int, int, float]:
    """
    Solves for integer tooth counts (z_sun, z_planet, z_ring) satisfying:
    1. Concentricity: z_ring = z_sun + 2 * z_planet
    2. Assembleability: (z_sun + z_ring) % num_planets == 0
    3. Ratio: ratio = 1 + z_ring / z_sun (with fixed ring)
    Returns: (z_sun, z_planet, z_ring, actual_ratio)
    """
    best_match = None
    best_error = float("inf")

    # Search a practical tooth range
    for z_s in range(min_sun_teeth, 45):
        ideal_zr = z_s * (desired_ratio - 1.0)
        # Try nearby integers for z_r
        for z_r in range(max(z_s + 4, int(ideal_zr) - 2), int(ideal_zr) + 4):
            # Check if z_r - z_s is even so z_p is an integer
            if (z_r - z_s) % 2 != 0:
                continue
            z_p = (z_r - z_s) // 2
            if z_p < 10:
                continue

            # Check assembleability condition for equally spaced planets
            if (z_s + z_r) % num_planets != 0:
                continue

            # Check planet-to-planet tip clearance
            # Adjacent planet center distance = 2 * R_orbit * sin(pi / num_planets)
            # Must be > tip diameter of planet (m * (z_p + 2))
            # R_orbit = m * (z_s + z_p) / 2
            # Clearance check in tooth units: (z_s + z_p) * sin(pi / num_planets) > (z_p + 2)
            if (z_s + z_p) * math.sin(math.pi / num_planets) <= (z_p + 2):
                continue

            actual_ratio = 1.0 + float(z_r) / float(z_s)
            error = abs(actual_ratio - desired_ratio)
            if error < best_error:
                best_error = error
                best_match = (z_s, z_p, z_r, actual_ratio)
                if error < 1e-4:
                    return best_match

    from ..core.exceptions import CADISpecificationError

    if best_match is not None and best_error < 0.35:
        return best_match

    raise CADISpecificationError(
        message=f"İstenen oran ({desired_ratio}) ve {num_planets} planet dişli için eşmerkezlilik ve montajlanabilirlik şartını (Z_r = Z_s + 2*Z_p, (Z_s+Z_r)%k=0) sağlayan tam sayı dişli kombinasyonu bulunamadı.",
        parameter_name="ratio",
        provided_value=desired_ratio,
        suggested_fix="Standart planet dişli oranlarından birini hedefleyin (örn. 3.0 ile 9.0 arasında) veya planet sayısını (num_planets) değiştirin.",
    )


def add_planetary_stage(
    assembly: "Assembly",
    name: str,
    module: float = 1.5,
    ratio: float = 4.0,
    num_planets: int = 3,
    face_width: float = 12.0,
    sun_teeth: Optional[int] = None,
    planet_teeth: Optional[int] = None,
    ring_teeth: Optional[int] = None,
    carrier_thickness: float = 6.0,
    pin_diameter: Optional[float] = None,
    material: str = "Steel4140",
    fixed_component: Optional[str] = "ring",
) -> Dict[str, Any]:
    """
    Creates a full planetary gear reduction stage.
    Generates:
      - Sun gear centered at (0, 0, 0)
      - num_planets symmetrically distributed at R_orbit
      - Planet carrier spider plate with mounting pins
      - Ring gear outer housing
      - Kinematic gear and revolute relations
    """
    if num_planets < 2:
        raise ValueError("Planetary stage requires at least 2 planets.")

    # Automatically derive planet_teeth if sun_teeth and ring_teeth are supplied
    if sun_teeth and ring_teeth and not planet_teeth:
        planet_teeth = (int(ring_teeth) - int(sun_teeth)) // 2

    # Determine tooth counts
    if sun_teeth and planet_teeth and ring_teeth:
        z_s = int(sun_teeth)
        z_p = int(planet_teeth)
        z_r = int(ring_teeth)
        if z_r != z_s + 2 * z_p:
            raise ValueError(
                f"Concentricity violated: z_ring ({z_r}) must equal z_sun ({z_s}) + 2*z_planet ({2*z_p})"
            )
        if (z_s + z_r) % num_planets != 0:
            raise ValueError(
                f"Assembleability condition violated: ({z_s} + {z_r}) % {num_planets} != 0"
            )
        actual_ratio = 1.0 + float(z_r) / float(z_s)
    else:
        z_s, z_p, z_r, actual_ratio = solve_planetary_teeth(
            desired_ratio=ratio,
            num_planets=num_planets,
        )

    # Pitch diameters and orbit radius
    d_sun = module * z_s
    d_planet = module * z_p
    d_ring = module * z_r
    r_orbit = module * (z_s + z_p) / 2.0

    pin_dia = float(pin_diameter or max(4.0, d_planet * 0.35))
    parts_created = []

    # 1. Sun Gear
    sun_name = f"{name}_sun_z{z_s}"
    assembly.add_spur_gear(
        name=sun_name,
        module=module,
        teeth=z_s,
        face_width=face_width,
        bore_dia=max(6.0, d_sun * 0.35),
        material=material,
        color=(0.82, 0.71, 0.45),
    )
    parts_created.append(sun_name)

    # 2. Planet Gears
    planet_names = []
    angle_step = 2.0 * math.pi / num_planets
    for i in range(num_planets):
        theta = i * angle_step
        px = r_orbit * math.cos(theta)
        py = r_orbit * math.sin(theta)
        p_name = f"{name}_planet_{i+1}_z{z_p}"

        assembly.add_spur_gear(
            name=p_name,
            module=module,
            teeth=z_p,
            face_width=face_width,
            origin=(px, py, 0.0),
            bore_dia=pin_dia + 0.5,
            material=material,
            color=(0.60, 0.70, 0.85),
        )
        parts_created.append(p_name)
        planet_names.append(p_name)

    # 3. Carrier Plate
    carrier_name = f"{name}_carrier"
    carrier_radius = r_orbit + pin_dia * 1.8
    assembly.add_cylinder(
        name=carrier_name,
        radius=carrier_radius,
        height=carrier_thickness,
        origin=(0.0, 0.0, -carrier_thickness),
    )
    parts_created.append(carrier_name)

    # Carrier Pins
    for i, p_name in enumerate(planet_names):
        theta = i * angle_step
        px = r_orbit * math.cos(theta)
        py = r_orbit * math.sin(theta)
        pin_name = f"{name}_pin_{i+1}"
        assembly.add_cylinder(
            name=pin_name,
            radius=pin_dia / 2.0,
            height=face_width + carrier_thickness,
            origin=(px, py, -carrier_thickness),
        )
        parts_created.append(pin_name)

    # 4. Ring Gear Outer Housing with Analytical Involute Teeth
    ring_name = f"{name}_ring_z{z_r}"
    ring_outer_radius = (d_ring / 2.0) + (module * 4.0)
    if hasattr(assembly, "add_internal_gear"):
        assembly.add_internal_gear(
            name=ring_name,
            module=module,
            teeth=z_r,
            face_width=face_width,
            outer_dia=ring_outer_radius * 2.0,
            origin=(0.0, 0.0, 0.0),
            bolt_count=4,
            bolt_diameter=max(5.0, module * 3.0),
            bolt_pcd=(ring_outer_radius + d_ring / 2.0),
            color=(0.55, 0.55, 0.60),
            material=material,
        )
    else:
        assembly.add_flange(
            name=ring_name,
            outer_diameter=ring_outer_radius * 2.0,
            thickness=face_width,
            inner_bore=d_ring,
            bolt_count=4,
            bolt_diameter=max(5.0, module * 3.0),
            bolt_pcd=(ring_outer_radius + d_ring / 2.0),
        )
    parts_created.append(ring_name)

    # 5. Planetary Willis Kinematic Relation & Revolute Joints
    assembly.add_revolute_joint(sun_name, axis=(0, 0, 1), origin=(0, 0, 0))
    assembly.add_revolute_joint(carrier_name, axis=(0, 0, 1), origin=(0, 0, 0))
    assembly.add_revolute_joint(ring_name, axis=(0, 0, 1), origin=(0, 0, 0))
    for i, p_name in enumerate(planet_names):
        theta = i * angle_step
        px = r_orbit * math.cos(theta)
        py = r_orbit * math.sin(theta)
        assembly.add_revolute_joint(p_name, axis=(0, 0, 1), origin=(px, py, 0))

    if hasattr(assembly, "add_planetary_relation"):
        assembly.add_planetary_relation(
            sun_part=sun_name,
            carrier_part=carrier_name,
            ring_part=ring_name,
            planet_parts=planet_names,
            z_sun=z_s,
            z_ring=z_r,
            z_planet=z_p,
            fixed_component=fixed_component or "ring",
        )

    return {
        "planetary_stage": name,
        "module": module,
        "ratio": actual_ratio,
        "target_ratio": ratio,
        "num_planets": num_planets,
        "sun_teeth": z_s,
        "planet_teeth": z_p,
        "ring_teeth": z_r,
        "pitch_diameters": {
            "sun_mm": d_sun,
            "planet_mm": d_planet,
            "ring_mm": d_ring,
        },
        "orbit_radius_mm": r_orbit,
        "face_width_mm": face_width,
        "parts_created": parts_created,
    }
