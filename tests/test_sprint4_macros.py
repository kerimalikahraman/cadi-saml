"""
tests.test_sprint4_macros
=========================
Comprehensive Test Suite for Sprint 4 Industrial Standard Macros:
1. ISO 965-1 / DIN 13 Hole Wizard (M3 - M20, blind cone 118°, countersink, PCD pattern)
2. DIN 6935 K-Factor Sheet Metal 2D Flat Pattern Unfolding Engine (SVG, DXF, 3D flat solid)
3. EN 10220 / DIN 2448 3D Piping & Tubing Route Sweep Wizard (zero-coordinate semantic ports)
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
    lookup_metric_thread,
    METRIC_THREADS,
    add_pipe_route,
    PIPE_SCHEDULES,
)


def test_hole_wizard_thread_lookup():
    """Verify ISO 965-1 / DIN 13 coarse metric thread table values."""
    m8 = lookup_metric_thread("M8")
    assert m8.nominal_dia == 8.0
    assert m8.pitch == 1.25
    assert m8.tap_drill_dia == 6.80
    assert m8.clearance_medium == 9.0

    m16 = lookup_metric_thread("M16x2.0")
    assert m16.nominal_dia == 16.0
    assert m16.pitch == 2.0
    assert m16.tap_drill_dia == 14.00


def test_hole_wizard_threaded_hole_blind_and_through():
    """Verify threaded hole cuts with 118° conical tip and countersink in an assembly."""
    asm = Assembly("HoleWizardTest")
    # Base manifold block
    asm.add_box("manifold_block", length=120.0, width=80.0, height=50.0, origin=(0.0, 0.0, 0.0))

    # Blind M10 hole with countersink
    hole_res = asm.add_threaded_hole(
        target_part="manifold_block",
        thread="M10",
        depth=25.0,
        through_hole=False,
        countersink=True,
        on_face="top",
        relative_pos=(-30.0, 0.0),
    )
    assert hole_res["thread"] == "M10"
    assert hole_res["tap_drill_dia_mm"] == 8.5
    assert hole_res["hole_depth_mm"] == 25.0
    assert hole_res["cone_depth_mm"] > 2.0  # tan(31°) * 4.25mm

    # Through M8 hole
    through_res = asm.add_threaded_hole(
        target_part="manifold_block",
        thread="M8",
        through_hole=True,
        countersink=False,
        on_face="top",
        relative_pos=(30.0, 0.0),
    )
    assert through_res["through_hole"] is True
    assert through_res["tap_drill_dia_mm"] == 6.80

    # Compile assembly IR to verify manifold B-Rep
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())
    assert "manifold_block" in shapes
    assert not shapes["manifold_block"].IsNull()


def test_hole_wizard_pcd_circular_pattern():
    """Verify PCD bolt hole circle creation with Hole Wizard."""
    asm = Assembly("PCDFlangeTest")
    asm.add_cylinder("flange_disc", radius=60.0, height=20.0, origin=(0.0, 0.0, 0.0))

    pcd_res = asm.add_threaded_hole(
        target_part="flange_disc",
        thread="M6",
        depth=15.0,
        pcd=80.0,
        num_holes=6,
        on_face="top",
    )
    assert pcd_res["is_pcd"] is True
    assert pcd_res["num_holes"] == 6
    assert pcd_res["pcd_mm"] == 80.0
    assert len(pcd_res["holes"]) == 6

    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())
    assert "flange_disc" in shapes
    assert not shapes["flange_disc"].IsNull()


def test_sheet_metal_flat_pattern_unfolding(tmp_path: Path):
    """Verify DIN 6935 K-factor bend allowance, flat pattern blank, SVG, DXF, and 3D solid."""
    sm = SheetMetalBuilder("chassis_bracket", thickness=2.5, k_factor=0.44, material="AlMg3")
    sm.base_plate(length=120.0, width=80.0, origin=(0.0, 0.0, 0.0))
    sm.add_flange("right", length=35.0, angle=90.0, inner_radius=2.5)
    sm.add_flange("left", length=35.0, angle=90.0, inner_radius=2.5)
    sm.add_hole(diameter=9.0, x=60.0, y=40.0)

    # 1. Calculate flat pattern
    flat = sm.unfold_flat_pattern()
    assert flat.blank_width == 80.0
    # Blank length should equal base (120) + 2 * flange developed addition
    assert flat.blank_length > 120.0
    assert flat.total_bend_allowance > 0.0
    assert flat.total_bend_deduction > 0.0
    assert len(flat.bend_lines) == 2
    assert len(flat.holes) == 1

    # 2. Test SVG generation and write
    svg_file = str(tmp_path / "bracket_flat.svg")
    svg_str = flat.to_svg(filepath=svg_file)
    assert "<svg" in svg_str
    assert "BEND 90°" in svg_str
    assert Path(svg_file).exists()

    # 3. Test DXF generation and write
    dxf_file = str(tmp_path / "bracket_flat.dxf")
    dxf_str = flat.to_dxf(filepath=dxf_file)
    assert "SECTION" in dxf_str
    assert "CUT" in dxf_str
    assert "BEND" in dxf_str
    assert Path(dxf_file).exists()

    # 4. Test 3D flat blank solid construction
    flat_solid = flat.build_unfolded_occt_solid()
    assert not flat_solid.IsNull()

    # 5. Test 3D folded solid construction
    folded_solid = sm.build_occt_solid()
    assert not folded_solid.IsNull()


def test_piping_route_macro_semantic_ports():
    """Verify EN 10220 standard pipe route with zero-coordinate semantic connection."""
    asm = Assembly("HydraulicSubsystem")
    asm.add_box("hydraulic_pump", length=80.0, width=80.0, height=50.0, origin=(0.0, 0.0, 0.0))
    asm.add_box("reservoir_tank", length=120.0, width=100.0, height=80.0, origin=(200.0, 150.0, 40.0))

    # Route DN25 pipe from pump top to tank left face
    pipe_res = asm.add_pipe_route(
        name="pressure_line",
        from_port="hydraulic_pump:top",
        to_port="reservoir_tank:left",
        standard="DN25",
    )
    assert pipe_res["standard"] == "DN25"
    assert pipe_res["outer_dia_mm"] == 33.7
    assert pipe_res["wall_thickness_mm"] == 2.6
    assert pipe_res["cut_length_mm"] > 200.0
    assert pipe_res["num_waypoints"] >= 4

    # Verify B-Rep geometry compiled in OCCTBackend
    backend = OCCTBackend()
    shapes = backend.compile(asm.to_ir())
    assert "pressure_line" in shapes
    assert not shapes["pressure_line"].IsNull()
