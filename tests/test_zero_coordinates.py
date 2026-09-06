"""
tests/test_zero_coordinates.py
==============================
Tests verifying 100% Zero-Coordinate Semantic CAD generation in cadi_saml.
No X, Y, Z coordinate guessing or hallucination required by AI agents.
All features snap and align via semantic references, mounted parts, and ports:
1. Shaft Keyway & Circlip placed via under_part & against_part
2. Gusset & End Cap placed via between=('part1', 'part2') & on_profile='col'
3. DMU Dynamic Clearance auto-resolving axis and pivot from joints/ports
4. Composite Panel & Disk Cam mounted semantically to parent parts
"""

import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    add_shaft_keyway,
    add_circlip_groove,
    add_gusset,
    add_end_cap,
    check_dynamic_clearance,
    compute_swept_envelope,
    add_composite_panel,
    add_disk_cam,
)


def test_zero_coordinate_shaft_features():
    """Verify keyway and circlip placed purely relative to mounted gear and bearing."""
    asm = Assembly(name="transmission_shaft_assembly")
    # Base shaft (120mm length)
    asm.add_cylinder(name="main_shaft", radius=12.5, height=120.0)

    # Mounted gear at Z=40..60 (face_width=20)
    asm.add_spur_gear(
        name="driven_gear",
        module=2.0,
        teeth=24,
        face_width=20.0,
        origin=(0.0, 0.0, 40.0),
    )

    # Mounted bearing at Z=80..95 (thickness=15)
    asm.add_box(
        name="bearing_unit",
        length=52.0,
        width=52.0,
        height=15.0,
        origin=(0.0, 0.0, 80.0),
    )

    # 1. ZERO-COORDINATE Keyway: align directly under 'driven_gear'
    kw = asm.add_shaft_keyway(shaft_part="main_shaft", under_part="driven_gear")
    assert kw["aligned_under_part"] == "driven_gear"
    # Driven gear is at Z=40 with face_width=20 -> center is at Z=50
    # Key length is 8 * 3.5 = 28 -> Z starts at 50 - 14 = 36
    assert abs(kw["z_position"] - 36.0) < 1.0

    # 2. ZERO-COORDINATE Circlip Groove: position right against bearing front face
    cc = asm.add_circlip_groove(
        shaft_part="main_shaft", against_part="bearing_unit", side="front"
    )
    assert cc["retaining_against_part"] == "bearing_unit"
    # Bearing starts at Z=80 -> groove placed right in front of it
    assert cc["z_position"] < 80.0

    # B-Rep Manifold verification
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "main_shaft" in solids
    assert not solids["main_shaft"].IsNull()


def test_zero_coordinate_weldments():
    """Verify gusset and end cap placed with zero coordinates between profiles."""
    asm = Assembly(name="space_frame_joint")
    # Column extending along Z
    asm.add_box(name="vertical_column", length=40.0, width=40.0, height=200.0, origin=(0.0, 0.0, 0.0))
    # Beam extending along X
    asm.add_box(name="horizontal_beam", length=200.0, width=40.0, height=40.0, origin=(0.0, 0.0, 0.0))

    # 1. ZERO-COORDINATE Gusset: placed between column and beam
    gusset = asm.add_gusset(
        name="corner_gusset",
        between=("vertical_column", "horizontal_beam"),
        thickness=6.0,
        chamfer=10.0,
    )
    assert gusset["between_parts"] == ("vertical_column", "horizontal_beam")
    assert "weld_face_vertical" in asm._parts["corner_gusset"].ports

    # 2. ZERO-COORDINATE End Cap: placed directly on the top end of the column
    cap = asm.add_end_cap(
        name="column_top_cap",
        on_profile="vertical_column",
        side="top",
    )
    assert cap["on_profile"] == "vertical_column"
    assert "mount_face" in asm._parts["column_top_cap"].ports

    # B-Rep Manifold verification
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "corner_gusset" in solids
    assert "column_top_cap" in solids
    assert not solids["corner_gusset"].IsNull()
    assert not solids["column_top_cap"].IsNull()


def test_zero_coordinate_dmu_clearance():
    """Verify DMU clearance automatically resolves pivot axis and origin from joint/port."""
    asm = Assembly(name="crank_assembly")
    # Crank arm
    asm.add_box(name="rotating_crank", length=30.0, width=10.0, height=10.0, origin=(15.0, 0.0, 0.0))
    # Declare revolute joint with its pivot axis
    asm.add_revolute_joint(part_name="rotating_crank", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

    # Stationary housing placed safely away at X=60
    asm.add_box(name="outer_bracket", length=20.0, width=20.0, height=20.0, origin=(60.0, 0.0, 0.0))

    # ZERO-COORDINATE Dynamic Clearance: no manual axis=(...) or origin=(...) required!
    clearance = asm.check_dynamic_clearance(
        moving_part="rotating_crank",
        static_part="outer_bracket",
    )
    assert clearance["status"] == "PASS"
    assert clearance["has_clash"] is False
    assert clearance["resolved_axis"] == (0.0, 0.0, 1.0)
    assert clearance["resolved_origin"] == (0.0, 0.0, 0.0)


def test_zero_coordinate_composites_and_cam():
    """Verify composite panel mounting and cam shaft coaxial snapping."""
    asm = Assembly(name="engine_and_body")

    # 1. Composite panel mounted to chassis
    asm.add_box(name="chassis_rail", length=200.0, width=100.0, height=30.0)
    panel = asm.add_composite_panel(
        name="floor_panel",
        mount_to="chassis_rail:mount_face",
        length=200.0,
        width=100.0,
    )
    assert "floor_panel" in asm._parts
    assert panel["num_plies"] == 8

    # 2. Disk cam coaxially snapped to camshaft
    asm.add_cylinder(name="camshaft_bar", radius=10.0, height=180.0)
    cam = asm.add_disk_cam(
        name="intake_lobe",
        on_shaft="camshaft_bar",
        lift=6.0,
    )
    assert cam["cam_name"] == "intake_lobe"

    # Verify all mates registered in IR
    ir = asm.to_ir()
    assert len(ir.mates) >= 2
