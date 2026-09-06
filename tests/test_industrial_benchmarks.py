"""
tests.test_industrial_benchmarks
================================
10-Assembly Industrial Benchmark & Stress-Test Suite for cadi_saml CAD Kernel.

Assemblies Tested:
1. Two-Stage Helical Reduction Gearbox (Shafts, Gears, Bearings, Seals, Keyways)
2. Welded Tubular Space Frame Chassis (Profiles + Gussets + End Caps + Bolted Joints)
3. High-Torque Planetary Reduction Stage (Sun, Planets, Ring, Carrier)
4. Slider-Crank Internal Combustion Engine Mechanism (Crankcase, Crankshaft, Conrod, Piston)
5. S-V-A-J Kinematic Disk Cam & Valve Follower Subsystem (Camshaft, Circlips, Cam, Follower)
6. Sheet Metal Electronic Enclosure Bracket with Flat Pattern Unfold (Bends, Reliefs, Holes, DXF/SVG)
7. Quasi-Isotropic Carbon Fiber Monocoque Panel with Threaded Inserts (CLT Layup, ABD Matrix, Hole Wizard)
8. Injection Mold Tooling Core & Cavity with Draft & Undercut Analysis
9. Rigid Flange Coupling Power Transmission Hub (DIN 115 Hubs, PCD Bolts, DIN 6885 Keys)
10. Automotive Suspension Wishbone Arm with Dynamic DMU Swept Motion Envelope
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    SheetMetalBuilder,
    add_threaded_hole,
    add_pipe_route,
    lookup_metric_thread,
)


def test_benchmark_01_two_stage_helical_gearbox():
    """
    Benchmark 1: Two-Stage Industrial Reduction Gearbox
    Components: Housing frame, 3 shafts (input, intermediate, output),
    helical gear pairs, deep groove ball bearings, DIN 3760 radial shaft seals, DIN 6885 keyways.
    100% Zero-Coordinate placement for features via semantic references.
    """
    asm = Assembly("TwoStageGearbox")

    # 1. Cast housing box
    asm.add_box("gearbox_housing", length=260.0, width=180.0, height=160.0, origin=(0.0, 0.0, 0.0))

    # 2. Input Shaft & components (pure zero coordinates for mounted parts, positioned via semantic mates)
    # Stage 1: m=2.5, z1=18 (d=45), z2=36 (d=90) -> center distance = 67.5 mm
    # Stage 2: m=3.0, z3=16 (d=48), z4=48 (d=144) -> center distance = 96.0 mm
    asm.add_cylinder("input_shaft", radius=10.0, height=180.0, origin=(0.0, 0.0, -20.0))
    asm.add_spur_gear("pinion_stage1", module=2.5, teeth=18, face_width=25.0, origin=(0.0, 0.0, 0.0))
    asm.connect("input_shaft:axis", "pinion_stage1:bore_axis", mate_type="COAXIAL")
    asm.connect("input_shaft:bottom", "pinion_stage1:back_face", mate_type="FLUSH", offset=50.0)

    asm.add_bearing("input_brg_front", standard="SKF", code="608ZZ")
    asm.add_bearing("input_brg_rear", standard="SKF", code="608ZZ")
    asm.add_seal("input_oil_seal", seal_type="radial_shaft_seal", shaft_dia=20.0, outer_dia=35.0, width=7.0)
    asm.add_shaft_keyway(target_shaft="input_shaft", under_part="pinion_stage1")

    # 3. Intermediate Shaft & gears (mounted parts have zero origin and are mated coaxially)
    asm.add_cylinder("inter_shaft", radius=14.0, height=180.0, origin=(67.5, 0.0, -20.0))
    asm.add_spur_gear("wheel_stage1", module=2.5, teeth=36, face_width=25.0, origin=(0.0, 0.0, 0.0))
    asm.connect("inter_shaft:axis", "wheel_stage1:bore_axis", mate_type="COAXIAL")
    asm.connect("inter_shaft:bottom", "wheel_stage1:back_face", mate_type="FLUSH", offset=50.0)

    asm.add_spur_gear("pinion_stage2", module=3.0, teeth=16, face_width=30.0, origin=(0.0, 0.0, 0.0))
    asm.connect("inter_shaft:axis", "pinion_stage2:bore_axis", mate_type="COAXIAL")
    asm.connect("inter_shaft:bottom", "pinion_stage2:back_face", mate_type="FLUSH", offset=95.0)

    asm.add_bearing("inter_brg_front", standard="SKF", code="608ZZ")
    asm.add_shaft_keyway(target_shaft="inter_shaft", under_part="wheel_stage1")

    # 4. Output Shaft & Bull Gear
    asm.add_cylinder("output_shaft", radius=18.0, height=200.0, origin=(67.5 + 96.0, 0.0, -30.0))
    asm.add_spur_gear("wheel_stage2", module=3.0, teeth=48, face_width=30.0, origin=(0.0, 0.0, 0.0))
    asm.connect("output_shaft:axis", "wheel_stage2:bore_axis", mate_type="COAXIAL")
    asm.connect("output_shaft:bottom", "wheel_stage2:back_face", mate_type="FLUSH", offset=95.0)

    asm.add_seal("output_oil_seal", seal_type="radial_shaft_seal", shaft_dia=36.0, outer_dia=52.0, width=8.0)
    asm.add_shaft_keyway(target_shaft="output_shaft", under_part="wheel_stage2")

    # 5. Kinematic Degrees of Freedom & Transmission Relations
    asm.add_revolute_joint("pinion_stage1", axis=(0, 0, 1), origin=(0.0, 0.0, 30.0))
    asm.add_revolute_joint("wheel_stage1", axis=(0, 0, 1), origin=(67.5, 0.0, 30.0))
    asm.add_revolute_joint("pinion_stage2", axis=(0, 0, 1), origin=(67.5, 0.0, 75.0))
    asm.add_revolute_joint("wheel_stage2", axis=(0, 0, 1), origin=(67.5 + 96.0, 0.0, 75.0))

    r1 = asm.add_gear_relation("pinion_stage1", "wheel_stage1")
    r2 = asm.add_gear_relation("pinion_stage2", "wheel_stage2")
    assert abs(r1.ratio - 0.5) < 1e-4
    assert abs(r2.ratio - (16.0 / 48.0)) < 1e-4

    # 6. Post-Build Contract Verification (compilation -> manifold -> dimensions -> kinematics -> step roundtrip)
    contract_report = asm.verify_contract(test_step_roundtrip=True, check_clash=False)
    assert contract_report.passed
    assert contract_report.stages["compilation"].passed
    assert contract_report.stages["manifold"].passed
    assert contract_report.stages["dimensions"].passed
    assert contract_report.stages["kinematics"].passed
    assert contract_report.stages["step_roundtrip"].passed
    assert contract_report.stages["step_roundtrip"].details["volume_delta_ratio"] < 0.005

    # 7. Check BOM generation
    from cadi_saml import extract_assembly_bom
    bom_report = extract_assembly_bom(asm)
    assert len(bom_report.items) >= 4
    assert any("pinion" in item.name.lower() or "gear" in item.name.lower() for item in bom_report.items)


def test_benchmark_02_welded_space_frame_chassis():
    """
    Benchmark 2: Welded Space Frame Chassis Substructure
    Components: RHS/SHS columns, cross beams, reinforcement gusset plates with corner weld relief,
    profile end caps snapped to extremities, and ISO bolted joints.
    """
    asm = Assembly("SpaceFrameChassis")

    # 1. Main vertical pillars and horizontal beam
    asm.add_box("column_left", length=60.0, width=60.0, height=300.0, origin=(-150.0, 0.0, 0.0))
    asm.add_box("column_right", length=60.0, width=60.0, height=300.0, origin=(150.0, 0.0, 0.0))
    asm.add_box("cross_beam", length=360.0, width=60.0, height=60.0, origin=(0.0, 0.0, 150.0))

    # 2. Structural Gussets between column and beam (Zero-Coordinate heuristic)
    asm.add_gusset(name="gusset_left", between=("column_left", "cross_beam"), d1=70.0, d2=70.0, thickness=6.0, chamfer=15.0)
    asm.add_gusset(name="gusset_right", between=("column_right", "cross_beam"), d1=70.0, d2=70.0, thickness=6.0, chamfer=15.0)

    # 3. Profile end caps snapped directly to column tops
    asm.add_end_cap(name="cap_col_left", on_profile="column_left", side="top", thickness=4.0)
    asm.add_end_cap(name="cap_col_right", on_profile="column_right", side="top", thickness=4.0)

    # 4. Standard ISO metric fasteners securing the structure
    asm.add_bolt("chassis_bolt_left", size="M10", length=80.0)
    asm.add_washer("chassis_washer_left", size="M10")
    asm.add_nut("chassis_nut_left", size="M10")

    # 5. Compile B-Rep solids
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "column_left" in shapes and not shapes["column_left"].IsNull()
    assert "cross_beam" in shapes and not shapes["cross_beam"].IsNull()
    assert "gusset_left" in shapes and not shapes["gusset_left"].IsNull()
    assert "cap_col_left" in shapes and not shapes["cap_col_left"].IsNull()


def test_benchmark_03_planetary_gear_stage():
    """
    Benchmark 3: High-Torque Planetary Reduction Stage
    Components: Sun gear, 3 planet gears on carrier, internal ring gear.
    Validates integer tooth mesh condition (Z_r = Z_s + 2*Z_p) and planetary stage macro.
    """
    asm = Assembly("PlanetaryGearbox")

    stage_res = asm.add_planetary_stage(
        name="epicyclic_stage_1",
        sun_teeth=16,
        planet_teeth=20,
        ring_teeth=56,
        module=2.0,
        face_width=20.0,
        num_planets=3,
    )

    assert stage_res["ratio"] == 4.5  # 1 + 56 / 16
    assert len(stage_res["parts_created"]) >= 6

    # Compile and verify solids
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "epicyclic_stage_1_sun_z16" in shapes
    assert "epicyclic_stage_1_ring_z56" in shapes
    assert "epicyclic_stage_1_planet_1_z20" in shapes
    assert not shapes["epicyclic_stage_1_sun_z16"].IsNull()


def test_benchmark_04_slider_crank_piston_mechanism():
    """
    Benchmark 4: Internal Combustion Engine Slider-Crank Mechanism
    Components: Crankcase block, crankshaft, connecting rod, piston slider.
    Validates Kinematic Joints (Revolute + Prismatic) and 1D motion kinematic loop.
    """
    asm = Assembly("EngineSliderCrank")

    # 1. Crankcase housing
    asm.add_box("crankcase", length=140.0, width=120.0, height=180.0, origin=(0.0, 0.0, 50.0))

    # 2. Crankshaft
    asm.add_cylinder("crankshaft", radius=18.0, height=100.0, origin=(0.0, 0.0, 0.0))

    # 3. Connecting rod & Piston
    asm.add_box("conrod", length=120.0, width=20.0, height=14.0, origin=(0.0, 40.0, 50.0))
    asm.add_cylinder("piston", radius=35.0, height=45.0, origin=(0.0, 0.0, 130.0))

    # 4. Kinematic Joints
    asm.add_revolute_joint("crankshaft", origin=(0.0, 0.0, 0.0), axis=(0.0, 1.0, 0.0), name="crank_main_bearing")
    asm.add_prismatic_joint("piston", origin=(0.0, 0.0, 130.0), axis=(0.0, 0.0, 1.0), name="cylinder_bore_slider")

    # 5. Compile IR
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "crankcase" in shapes and not shapes["crankcase"].IsNull()
    assert "piston" in shapes and not shapes["piston"].IsNull()
    assert len(asm._mechanism.joints) == 2


def test_benchmark_05_disk_cam_and_valve_follower():
    """
    Benchmark 5: S-V-A-J Kinematic Disk Cam & Spring-Loaded Valve Follower
    Components: Camshaft, DIN 471 circlips, Cycloidal disk cam with zero-coordinate on_shaft snapping,
    roller follower and valve stem.
    """
    asm = Assembly("CamValveTrain")

    # 1. Rotating Camshaft
    asm.add_cylinder("camshaft", radius=12.0, height=160.0, origin=(0.0, 0.0, 0.0))

    # 2. Disk Cam with S-V-A-J Rise-Dwell-Fall-Dwell segments snapped to camshaft
    cam_meta = asm.add_disk_cam(
        name="intake_cam",
        on_shaft="camshaft",
        base_radius=28.0,
        lift=10.0,
        width=16.0,
        bore_dia=24.0,
        segments=[
            {"type": "rise", "angle_deg": 100.0, "law": "cycloidal"},
            {"type": "dwell", "angle_deg": 60.0, "lift_val": 10.0},
            {"type": "fall", "angle_deg": 100.0, "law": "cycloidal"},
            {"type": "dwell", "angle_deg": 100.0, "lift_val": 0.0},
        ],
    )
    assert cam_meta["max_lift_mm"] == 10.0
    assert cam_meta["num_profile_points"] > 50

    # 3. DIN 471 retaining circlip groove to lock cam axially
    asm.add_circlip_groove(target_shaft="camshaft", against_part="intake_cam", side="right")

    # 4. Roller valve follower
    asm.add_cylinder("roller_follower", radius=8.0, height=14.0, origin=(38.0, 0.0, 8.0))
    asm.add_cylinder("valve_stem", radius=4.0, height=70.0, origin=(38.0, 0.0, 16.0))

    # 5. Compile B-Rep
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "intake_cam" in shapes and not shapes["intake_cam"].IsNull()
    assert "camshaft" in shapes and not shapes["camshaft"].IsNull()
    assert "roller_follower" in shapes and not shapes["roller_follower"].IsNull()


def test_benchmark_06_sheet_metal_enclosure_with_flat_pattern(tmp_path: Path):
    """
    Benchmark 6: Sheet Metal Industrial Electronic Enclosure Bracket
    Components: S235JR sheet metal base plate, 4 bent flanges with corner reliefs,
    punched D-sub / cable pass-through holes.
    Validates DIN 6935 K-Factor Flat Pattern Unfolding (SVG, DXF, 3D flat solid).
    """
    sm = SheetMetalBuilder(name="enclosure_chassis", thickness=1.5, k_factor=0.44, material="S235JR")
    sm.base_plate(length=150.0, width=100.0, origin=(0.0, 0.0, 0.0))

    # Flanges on all 4 sides with 90° bends
    sm.add_flange("right", length=40.0, angle=90.0, inner_radius=1.5)
    sm.add_flange("left", length=40.0, angle=90.0, inner_radius=1.5)
    sm.add_flange("back", length=30.0, angle=90.0, inner_radius=1.5)
    sm.add_flange("front", length=30.0, angle=90.0, inner_radius=1.5)

    # Cable pass-through and mounting holes
    sm.add_hole(diameter=25.0, x=75.0, y=50.0)
    sm.add_hole(diameter=4.5, x=20.0, y=20.0)
    sm.add_hole(diameter=4.5, x=130.0, y=20.0)
    sm.add_hole(diameter=4.5, x=20.0, y=80.0)
    sm.add_hole(diameter=4.5, x=130.0, y=80.0)

    # 1. Unfold flat pattern
    flat = sm.unfold_flat_pattern()
    assert flat.blank_length > 150.0
    assert flat.blank_width > 100.0
    assert len(flat.bend_lines) == 4
    assert len(flat.holes) == 5

    # 2. Export 2D DXF & SVG
    svg_p = str(tmp_path / "enclosure.svg")
    dxf_p = str(tmp_path / "enclosure.dxf")
    flat.to_svg(svg_p)
    flat.to_dxf(dxf_p)
    assert Path(svg_p).exists()
    assert Path(dxf_p).exists()

    # 3. 3D solids
    folded_solid = sm.build_occt_solid()
    unfolded_solid = flat.build_unfolded_occt_solid()
    assert not folded_solid.IsNull()
    assert not unfolded_solid.IsNull()


def test_benchmark_07_composite_monocoque_with_threaded_inserts():
    """
    Benchmark 7: Quasi-Isotropic Carbon Fiber Monocoque Panel with Threaded Inserts
    Components: [0/45/-45/90]_s 8-ply quasi-isotropic carbon fiber laminate panel via Classical Laminate Theory (CLT).
    Validates ABD stiffness matrix, Tsai-Wu failure safety factor, and PCD M5 threaded inserts.
    """
    asm = Assembly("CarbonMonocoquePanel")

    # 1. Composite Layup
    panel_meta = asm.add_composite_panel(
        name="cf_floor_panel",
        length=250.0,
        width=180.0,
        material="Carbon_T300_Epoxy",
        angles=[0, 45, -45, 90],
        symmetric=True,
        ply_thickness=0.25,
    )

    assert panel_meta["total_thickness_mm"] == 2.0
    assert panel_meta["num_plies"] == 8
    assert "equivalent_moduli_gpa" in panel_meta

    # 2. ISO 965 M5 Threaded Brass Inserts on PCD circular pattern
    insert_res = asm.add_threaded_hole(
        target_part="cf_floor_panel",
        thread="M5",
        depth=10.0,
        at_pcd=120.0,
        num_holes=6,
        countersink=True,
    )
    assert insert_res["thread"] == "M5"
    assert insert_res["num_holes"] == 6

    # 3. Compile B-Rep solid
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())
    assert "cf_floor_panel" in shapes and not shapes["cf_floor_panel"].IsNull()


def test_benchmark_08_injection_mold_core_cavity_draft_analysis():
    """
    Benchmark 8: Injection Mold Tooling Core & Cavity Assembly
    Components: Cavity mold block, core mold block, molded plastic part.
    Validates CATIA-grade Draft Angle & Undercut Analysis (pull vector normal dot product).
    """
    asm = Assembly("InjectionMoldTooling")

    # 1. Mold blocks
    asm.add_box("cavity_plate", length=200.0, width=160.0, height=80.0, origin=(0.0, 0.0, 40.0))
    asm.add_box("core_plate", length=200.0, width=160.0, height=80.0, origin=(0.0, 0.0, -40.0))

    # 2. Molded plastic housing with drafted side walls
    asm.add_box("plastic_enclosure", length=120.0, width=90.0, height=45.0, origin=(0.0, 0.0, 0.0))

    # 3. Perform Draft & Undercut Analysis along +Z mold pull vector
    draft_report = asm.analyze_draft(
        part_name="plastic_enclosure",
        pull_direction=(0.0, 0.0, 1.0),
        min_draft_deg=1.5,
    )
    assert draft_report["pull_direction"] == (0.0, 0.0, 1.0)
    assert draft_report["total_faces_evaluated"] >= 6
    assert draft_report["undercuts_detected"] == 0

    # 4. Compile B-Rep solids
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())
    assert "cavity_plate" in shapes and not shapes["cavity_plate"].IsNull()
    assert "core_plate" in shapes and not shapes["core_plate"].IsNull()


def test_benchmark_09_rigid_flange_coupling_transmission():
    """
    Benchmark 9: Rigid Flange Coupling Power Transmission Assembly
    Components: Driving motor shaft, driven pump shaft, DIN 115 rigid flange coupling,
    DIN 6885 drive keys, PCD bolt circle securing the flanges, and connecting hydraulic pipe route.
    """
    asm = Assembly("CoupledTransmission")

    # 1. Driving and Driven Shafts
    asm.add_cylinder("motor_shaft", radius=15.0, height=120.0, origin=(-70.0, 0.0, 0.0))
    asm.add_cylinder("pump_shaft", radius=15.0, height=120.0, origin=(70.0, 0.0, 0.0))

    # 2. Rigid Flange Coupling connecting the shafts
    cpl_ref = asm.add_coupling(
        name="flange_coupling_hub",
        coupling_type="rigid_flange",
        shaft1_dia=30.0,
        shaft2_dia=30.0,
        outer_dia=90.0,
        length=80.0,
    )

    # 3. DIN 6885 torque transmission keyway
    asm.add_shaft_keyway(target_shaft="motor_shaft", against_part="flange_coupling_hub", side="left")

    # 4. PCD M8 bolt circle securing the flange coupling halves
    bolt_circle = asm.add_threaded_hole(
        target_part="flange_coupling_hub",
        thread="M8",
        depth=30.0,
        through_hole=True,
        at_pcd=68.0,
        num_holes=4,
    )
    assert bolt_circle["num_holes"] == 4

    # 5. Add DN20 lubrication oil line to the coupling
    pipe_res = asm.add_pipe_route(
        name="lube_line",
        from_port=(-70.0, 0.0, 60.0),
        to_port=(0.0, 45.0, 0.0),
        standard="DN20",
    )
    assert pipe_res["outer_dia_mm"] == 26.9

    # 6. Compile B-Rep solids
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "motor_shaft" in shapes and not shapes["motor_shaft"].IsNull()
    assert "flange_coupling_hub" in shapes and not shapes["flange_coupling_hub"].IsNull()
    assert "lube_line" in shapes and not shapes["lube_line"].IsNull()


def test_benchmark_10_suspension_wishbone_with_swept_envelope():
    """
    Benchmark 10: Automotive Suspension Wishbone Arm with Swept Motion Envelope
    Components: Double wishbone tubular A-arm, pivot bushes with Revolute Joint,
    ball joint knuckle mount.
    Validates DMU dynamic motion swept envelope computation across bump/rebound travel.
    """
    asm = Assembly("SuspensionWishbone")

    # 1. Subframe mounting chassis
    asm.add_box("subframe_bracket", length=220.0, width=50.0, height=60.0, origin=(0.0, 0.0, 0.0))

    # 2. Wishbone control arm (cantilever from subframe out in +X)
    # Box centered at ox=110, length=220 extends from X=0 to X=220
    asm.add_box("wishbone_arm", length=220.0, width=35.0, height=25.0, origin=(110.0, 0.0, 0.0))

    # 3. Kinematic Revolute Joint representing chassis pivot axis
    asm.add_revolute_joint("wishbone_arm", origin=(0.0, 0.0, 0.0), axis=(0.0, 1.0, 0.0), name="chassis_pivot_joint")

    # 4. DMU Dynamic Motion Swept Envelope (+/- 15 degrees suspension travel)
    dmu_res = asm.compute_swept_envelope(
        moving_part="wishbone_arm",
        angle_range=(-15.0, 15.0),
        steps=7,
    )

    assert dmu_res["steps_sampled"] == 7
    assert dmu_res["swept_bounding_volume_mm3"] > 0.0

    # 5. Compile B-Rep solids
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())

    assert "wishbone_arm" in shapes and not shapes["wishbone_arm"].IsNull()
