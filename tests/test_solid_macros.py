"""
tests/test_solid_macros.py
==========================
Comprehensive test suite for SolidWorks-grade engineering macros and solvers:
1. DIN 6885 Parallel Keyways & DIN 471 Circlip Grooves
2. Weldment Gusset Plates & Profile End Caps
3. Planetary Gearset Stage Wizard & Kinematics
4. Mathematical Motion Cam Generator (S-V-A-J curves)
5. Mold Draft Angle & Undercut Analysis
6. SIMP Topology Optimization Engine
"""

import math
import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    lookup_din_6885,
    lookup_din_471,
    solve_planetary_teeth,
    evaluate_motion_law,
    analyze_draft,
    TopologyOptimizer,
    optimize_topology,
)


def test_lookup_din_standards():
    """Verify DIN 6885 and DIN 471 standard lookup tables."""
    # DIN 6885 for 25mm shaft: b=8, h=7, t1=4.0
    b, h, t1, t2 = lookup_din_6885(25.0)
    assert b == 8.0
    assert h == 7.0
    assert t1 == 4.0
    assert t2 == 3.3

    # DIN 471 for 25mm shaft: m=1.30, t=0.65
    m, t, s = lookup_din_471(25.0)
    assert m == 1.30
    assert t == 0.65
    assert s == 1.2


def test_shaft_keyway_and_circlip():
    """Test cutting engineered keyway and retaining ring groove into a shaft."""
    asm = Assembly(name="shaft_features_assembly")
    shaft = asm.add_cylinder(name="drive_shaft", radius=12.5, height=100.0)  # dia 25mm

    # Cut keyway at z = 30mm
    kw_report = asm.add_shaft_keyway(shaft_part="drive_shaft", z_position=30.0, length=28.0)
    assert kw_report["width_mm"] == 8.0
    assert kw_report["depth_mm"] == 4.0
    assert kw_report["length_mm"] == 28.0

    # Cut circlip groove at z = 15mm
    cc_report = asm.add_circlip_groove(shaft_part="drive_shaft", z_position=15.0)
    assert cc_report["groove_width_mm"] == 1.30
    assert cc_report["groove_depth_mm"] == 0.65

    # Compile and verify B-Rep validity
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "drive_shaft" in solids
    solid = solids["drive_shaft"]
    assert solid is not None and not solid.IsNull()

    diag = asm.diagnose()
    assert diag["passed"] is True


def test_weldment_gusset_and_end_cap():
    """Test gusset stiffener plates and profile end-caps."""
    asm = Assembly(name="weldment_assembly")
    
    # 1. Add Gusset Plate
    gusset_report = asm.add_gusset(
        name="frame_gusset",
        width=50.0,
        height=50.0,
        thickness=6.0,
        chamfer_size=10.0,
    )
    assert "frame_gusset" in asm._parts
    assert "weld_face_vertical" in asm._parts["frame_gusset"].ports
    assert "weld_face_horizontal" in asm._parts["frame_gusset"].ports

    # 2. Add Profile End Cap
    cap_report = asm.add_end_cap(
        name="profile_cap_4040",
        width=40.0,
        height=40.0,
        thickness=4.0,
        corner_radius=4.0,
    )
    assert "profile_cap_4040" in asm._parts
    assert "mount_face" in asm._parts["profile_cap_4040"].ports

    # Verify solids
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "frame_gusset" in solids
    assert "profile_cap_4040" in solids
    assert not solids["frame_gusset"].IsNull()
    assert not solids["profile_cap_4040"].IsNull()


def test_planetary_gear_stage_wizard():
    """Test tooth count solver and planetary stage assembly generation."""
    # 1. Test mathematical tooth solver
    z_s, z_p, z_r, ratio = solve_planetary_teeth(desired_ratio=4.0, num_planets=3)
    assert z_r == z_s + 2 * z_p
    assert (z_s + z_r) % 3 == 0
    assert abs(ratio - 4.0) < 0.1

    # 2. Test full macro assembly creation
    asm = Assembly(name="planetary_drive")
    report = asm.add_planetary_stage(
        name="stage1",
        module=1.5,
        ratio=4.0,
        num_planets=3,
        face_width=12.0,
    )

    assert report["num_planets"] == 3
    assert len(report["parts_created"]) >= 5  # sun, 3 planets, carrier, pins, ring
    assert report["sun_teeth"] == z_s
    assert report["planet_teeth"] == z_p
    assert report["ring_teeth"] == z_r

    # Check kinematic relations recorded in mechanism (Willis planetary epicyclic relation)
    from cadi_saml.kinematics.relations import PlanetaryRelation
    assert any(isinstance(r, PlanetaryRelation) for r in asm._mechanism.relations)


def test_mathematical_motion_cam():
    """Test S-V-A-J kinematic motion laws and 3D disk cam generation."""
    # 1. Test Cycloidal motion law
    s0, _, _ = evaluate_motion_law("cycloidal", 0.0, lift=10.0, is_rise=True)
    assert abs(s0 - 0.0) < 1e-6
    s_mid, _, _ = evaluate_motion_law("cycloidal", 0.5, lift=10.0, is_rise=True)
    assert abs(s_mid - 5.0) < 1e-6
    s1, _, _ = evaluate_motion_law("cycloidal", 1.0, lift=10.0, is_rise=True)
    assert abs(s1 - 10.0) < 1e-6

    # 2. Test Harmonic motion law
    sh_mid, _, _ = evaluate_motion_law("harmonic", 0.5, lift=10.0, is_rise=True)
    assert abs(sh_mid - 5.0) < 1e-6

    # 3. Create full 3D disk cam
    asm = Assembly(name="cam_assembly")
    report = asm.add_disk_cam(
        name="intake_cam",
        base_radius=25.0,
        lift=8.0,
        width=10.0,
        bore_dia=12.0,
        num_samples=90,
    )
    assert report["cam_name"] == "intake_cam"
    assert report["base_radius_mm"] == 25.0
    assert report["max_lift_mm"] == 8.0

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "intake_cam" in solids
    assert not solids["intake_cam"].IsNull()


def test_mold_draft_analysis():
    """Test mold draft angle and undercut detection engine."""
    asm = Assembly(name="mold_test_assembly")
    # Vertical prism box: all 4 side walls have 0° draft, top has 90°
    asm.add_box(name="cavity_insert", length=30.0, width=30.0, height=20.0)

    report = asm.analyze_draft(
        part_name="cavity_insert",
        pull_direction=(0.0, 0.0, 1.0),
        min_draft_deg=1.5,
    )

    assert report["total_faces_evaluated"] == 6
    assert report["undercuts_detected"] is False
    # Top face is parting, bottom face is parting, 4 vertical faces have draft < 1.5°
    assert report["summary"]["insufficient_draft_count"] == 4
    assert report["summary"]["parting_top_count"] == 1
    assert report["summary"]["parting_bottom_count"] == 1
    assert report["status"] == "WARNING_DRAFT"


def test_simp_topology_optimization():
    """Test SIMP compliance minimization and CAD lightweight feature generation."""
    # 1. Direct optimizer solve on small cantilever grid
    opt = TopologyOptimizer(
        nelx=16,
        nely=8,
        volfrac=0.5,
        length_mm=40.0,
        height_mm=20.0,
        thickness_mm=5.0,
        problem_type="cantilever",
    )
    result = opt.solve(max_iter=10)
    assert result.iterations > 0
    assert result.final_compliance > 0.0
    assert abs(result.volume_achieved - 0.5) < 0.08

    # 2. Assembly integration
    asm = Assembly(name="topology_assembly")
    cad_report = asm.optimize_topology(
        part_name="lightweight_arm",
        length_mm=50.0,
        height_mm=25.0,
        thickness_mm=6.0,
        target_volume_fraction=0.45,
        nelx=14,
        nely=7,
    )
    assert "lightweight_arm" in asm._parts
    assert cad_report["achieved_volume_fraction"] < 0.60
    assert cad_report["mass_reduction_percent"] > 35.0

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "lightweight_arm" in solids
    assert not solids["lightweight_arm"].IsNull()
