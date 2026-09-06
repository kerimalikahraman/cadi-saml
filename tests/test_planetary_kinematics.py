"""
tests.test_planetary_kinematics
===============================
Unit tests for epicyclic / planetary gear kinematics:
- Willis equation solver
- PlanetaryRelation transmission ratio calculations
- Assembly.add_planetary_relation
- Assembly.add_internal_gear and OCCT B-Rep compilation
"""

import math
import pytest
from cadi_saml.core.assembly import Assembly
from cadi_saml.backend.occt_backend import OCCTBackend
from cadi_saml.kinematics.relations import PlanetaryRelation, RelationType
from cadi_saml.macros.planetary_macros import add_planetary_stage


def test_planetary_relation_willis_equation():
    """Willis equation test for simple epicyclic planetary train."""
    # Example: Sun z_s = 18, Ring z_r = 54, Planet z_p = 18
    # Module m = 2.0. Check mesh: z_r = z_s + 2*z_p = 18 + 36 = 54
    rel = PlanetaryRelation(
        sun_part="sun",
        carrier_part="carrier",
        ring_part="ring",
        planet_parts=["p1", "p2", "p3"],
        z_sun=18,
        z_ring=54,
        z_planet=18,
        fixed_component="ring",
    )

    assert rel.relation_type == RelationType.PLANETARY
    # Ring fixed: ratio = 1 + z_r/z_s = 1 + 54/18 = 4.0
    assert abs(rel.stage_ratio - 4.0) < 1e-6

    # When sun rotates at 360 deg: carrier should rotate at 360 / 4.0 = 90 deg
    speeds = rel.solve_speeds(omega_sun=360.0)
    assert abs(speeds["sun"] - 360.0) < 1e-6
    assert abs(speeds["ring"] - 0.0) < 1e-6
    assert abs(speeds["carrier"] - 90.0) < 1e-6

    # Willis invariant: z_s*w_s + z_r*w_r - (z_s+z_r)*w_c == 0
    zs, zr = 18.0, 54.0
    ws, wr, wc = speeds["sun"], speeds["ring"], speeds["carrier"]
    residual = zs * ws + zr * wr - (zs + zr) * wc
    assert abs(residual) < 1e-5

    # Planet rotation on its pin: w_p = w_c - (z_s/z_p)*(w_s - w_c)
    # w_p = 90 - (18/18)*(360 - 90) = 90 - 270 = -180 deg
    assert abs(speeds["p1"] - (-180.0)) < 1e-6


def test_planetary_carrier_fixed_mode():
    """Carrier fixed (solar mode): w_c = 0, ring rotates reverse."""
    rel = PlanetaryRelation(
        sun_part="sun",
        carrier_part="carrier",
        ring_part="ring",
        planet_parts=["p1"],
        z_sun=20,
        z_ring=60,
        z_planet=20,
        fixed_component="carrier",
    )
    # Solar ratio = -z_r/z_s = -3.0
    assert abs(rel.stage_ratio - (-3.0)) < 1e-6
    speeds = rel.solve_speeds(omega_sun=300.0)
    assert abs(speeds["carrier"] - 0.0) < 1e-6
    assert abs(speeds["ring"] - (-100.0)) < 1e-6


def test_add_internal_gear_geometry():
    """Verify analytical internal involute ring gear compiles to valid OCCT solid."""
    asm = Assembly("InternalGearTest")
    gear_ref = asm.add_internal_gear(
        name="annular_ring",
        module=2.5,
        teeth=40,
        face_width=20.0,
        rim_thickness=12.0,
        bolt_count=6,
        bolt_diameter=6.0,
        bolt_pcd=115.0,
    )

    assert "annular_ring" in asm._parts
    assert "bore_axis" in gear_ref.ports
    assert "front_face" in gear_ref.ports

    # Analytical Involute Geometry Verification
    params = gear_ref.node.parameters
    assert params["args"]["teeth"] == 40
    assert params["args"]["module"] == 2.5
    assert abs(params["pitch_diameter"] - 100.0) < 1e-4   # d = m * z = 2.5 * 40 = 100.0 mm
    assert abs(params["tip_diameter"] - 95.0) < 1e-4      # d_a = d - 2*m = 95.0 mm (inward tooth tip)
    assert abs(params["root_diameter"] - 106.25) < 1e-4   # d_f = d + 2.5*m = 106.25 mm

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "annular_ring" in solids
    solid = solids["annular_ring"]
    assert solid is not None and not solid.IsNull()

    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    assert g.Mass() > 1000.0  # Positive volume in mm3


def test_planetary_macro_assembly_integration():
    """Verify add_planetary_stage creates full stage with internal ring gear and Willis relation."""
    asm = Assembly("PlanetaryFullStage")
    res = add_planetary_stage(
        asm,
        name="epicyclic_box",
        module=2.0,
        ratio=4.0,
        num_planets=3,
        face_width=15.0,
    )

    assert res["ratio"] == 4.0
    assert res["sun_teeth"] == 15
    assert res["planet_teeth"] == 15
    assert res["ring_teeth"] == 45

    # Check that parts exist
    assert f"epicyclic_box_sun_z{res['sun_teeth']}" in asm._parts
    assert f"epicyclic_box_ring_z{res['ring_teeth']}" in asm._parts
    assert "epicyclic_box_carrier" in asm._parts

    # Check relation
    mech = asm._get_mechanism()
    has_planetary_rel = any(isinstance(r, PlanetaryRelation) for r in mech.relations)
    assert has_planetary_rel is True
