"""
tests/test_sheet_metal_and_smart_fillets.py
===========================================
Tests for Sheet Metal design, DIN 6935 K-factor unfolding,
and smart spatial Fillet/Chamfer operations.
"""

import sys
import os
import pytest
from pathlib import Path

# Ensure library/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml import Assembly, OCCTBackend, ValidationEngineer, SheetMetalBuilder
import OCP.BRepCheck as BRepCheck


def test_smart_fillet_and_chamfer_on_assembly():
    """Verify Assembly.fillet and Assembly.chamfer with spatial selectors."""
    with Assembly("Smart_Fillet_Test", units="mm") as asm:
        box = asm.add_box("main_block", length=60.0, width=40.0, height=25.0)
        # Use new Assembly.fillet and Assembly.chamfer methods
        asm.fillet("main_block", radius=3.0, edges="vertical")
        asm.chamfer("main_block", distance=1.5, edges="all_top")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "main_block" in solids
    solid = solids["main_block"]

    analyzer = BRepCheck.BRepCheck_Analyzer(solid)
    assert analyzer.IsValid(), "Filleted & chamfered block must be a valid B-Rep solid."

    ve = ValidationEngineer()
    for name, s in solids.items():
        assert ve.check_manifold(s), f"{name} must be watertight manifold"


def test_part_reference_fillet_chamfer_aliases():
    """Verify chained .fillet() and .chamfer() on PartReference."""
    with Assembly("PartRef_Fillet_Test", units="mm") as asm:
        cyl = asm.add_cylinder("boss", radius=20.0, height=30.0)
        cyl.fillet(radius=2.0, edges="all_top")
        cyl.chamfer(distance=1.0, edges="all_bottom")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "boss" in solids
    analyzer = BRepCheck.BRepCheck_Analyzer(solids["boss"])
    assert analyzer.IsValid()


def test_sheet_metal_builder_din6935_unfolding():
    """Verify DIN 6935 K-Factor, Bend Allowance (BA), and Bend Deduction (BD)."""
    sm = SheetMetalBuilder("enclosure_bracket", thickness=2.0, k_factor=0.44)
    sm.base_plate(length=100.0, width=60.0)
    sm.add_flange("right", length=40.0, angle=90.0, inner_radius=2.0)
    sm.add_flange("left", length=40.0, angle=90.0, inner_radius=2.0)
    sm.add_hole(diameter=6.5, x=50.0, y=30.0)

    # 1. Check flat pattern calculation
    flat = sm.get_flat_pattern()
    assert flat.thickness == 2.0
    assert flat.k_factor == 0.44
    assert flat.blank_width == 60.0
    # Expected blank length: 100 + 2 * (40 - setback + BA/2)
    # BA = (pi * 90 / 180) * (2.0 + 0.44 * 2.0) = 1.5708 * 2.88 = 4.524 mm
    # Setback = (2.0 + 2.0) * tan(45) = 4.0 mm
    # Added leg = 40 - 4.0 + 2.262 = 38.262 mm -> Total = 100 + 2 * 38.262 = 176.524 mm
    assert abs(flat.blank_length - 176.524) < 0.1
    assert len(flat.bend_lines) == 2

    # 2. Check 3D solid construction
    solid = sm.build_occt_solid()
    analyzer = BRepCheck.BRepCheck_Analyzer(solid)
    assert analyzer.IsValid()


def test_assembly_sheet_metal_bracket_macro():
    """Verify asm.add_sheet_metal_bracket macro for L, U, Z brackets."""
    with Assembly("Bracket_Assembly", units="mm") as asm:
        l_bracket = asm.add_sheet_metal_bracket(
            "l_bracket",
            bracket_type="L",
            width=45.0,
            length1=50.0,
            length2=35.0,
            thickness=1.5,
            k_factor=0.44,
            hole_diameter=5.2
        )
        u_bracket = asm.add_sheet_metal_bracket(
            "u_channel",
            bracket_type="U",
            width=40.0,
            length1=80.0,
            length2=25.0,
            thickness=2.0,
            hole_diameter=8.5
        )

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "l_bracket" in solids
    assert "u_channel" in solids

    for name, s in solids.items():
        analyzer = BRepCheck.BRepCheck_Analyzer(s)
        assert analyzer.IsValid(), f"{name} must be a valid B-Rep solid"

    ve = ValidationEngineer()
    for name, s in solids.items():
        assert ve.check_manifold(s), f"{name} must be watertight manifold"
