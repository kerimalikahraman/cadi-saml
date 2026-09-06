"""
tests.test_token_reduction
==========================
Unit and Integration Tests for SAML Token Reduction & Macro Enhancements:
1. Compact Coordinate String Parsing (parse_points)
2. 1-Line PCD Circular Bolt Pattern (add_pcd_holes)
3. High-Level Semantic Engineering Macros (add_flange, add_stepped_shaft, add_ibeam)
4. In-Place Delta Patching / Diff Revision (patch)
5. Token Savings Benchmarks
"""

import math
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
)


def test_compact_coordinate_string():
    """Verify revolve and polygon section accept space/comma-separated strings instead of verbose lists."""
    print("--- Testing Compact Coordinate String Parsing ---")
    asm = Assembly("CompactCoordTest")

    # Compact string for revolve profile
    compact_rim_pts = "100,0 120,0 120,20 100,20 100,0"
    rim = asm.add_revolve("compact_rim", profile_points=compact_rim_pts, angle=360.0)
    rim.set_appearance(color=(0.2, 0.2, 0.2), material="ForgedAlloy")

    # Compact string for 3D polygon cross section
    compact_poly_pts = "-10,-10,0  10,-10,0  10,10,0  -10,10,0"
    sec = asm.section_polygon(compact_poly_pts)
    asm.add_extrude("compact_extrude", section=sec, distance=30.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "compact_rim" in solids and not solids["compact_rim"].IsNull()
    assert "compact_extrude" in solids and not solids["compact_extrude"].IsNull()

    val = ValidationEngineer()
    assert val.check_manifold(solids["compact_rim"])
    assert val.check_manifold(solids["compact_extrude"])
    print("  -> Compact coordinate strings parsed and compiled into valid solids successfully!")


def test_pcd_bolt_pattern():
    """Verify 1-line circular PCD bolt pattern replaces manual hole loops."""
    print("--- Testing 1-Line PCD Bolt Pattern ---")
    asm = Assembly("PCDTest")
    plate = asm.add_cylinder("flange_disc", radius=80.0, height=15.0)

    # 1 line adds 6 evenly spaced M10 holes along 120mm PCD
    plate.add_pcd_holes(count=6, diameter=10.0, pcd=120.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    disc_solid = solids["flange_disc"]

    # Verify hole cutouts exist by checking volume reduction
    raw_vol = math.pi * (80.0 ** 2) * 15.0
    hole_vol = 6 * (math.pi * (5.0 ** 2) * 15.0)
    expected_vol = raw_vol - hole_vol

    mass_props = backend.calculate_mass_properties(asm.to_ir())
    actual_vol = mass_props["total_volume_mm3"]

    assert abs(actual_vol - expected_vol) < 200.0, f"Expected volume ~{expected_vol}, got {actual_vol}"
    print(f"  -> PCD Holes verified! All 6 bolt holes drilled (Volume: {actual_vol:,.1f} mm³)")


def test_semantic_engineering_macros():
    """Verify add_flange, add_stepped_shaft, and add_ibeam macros compile in 1 line."""
    print("--- Testing High-Level Semantic Engineering Macros ---")
    asm = Assembly("MacroSuite")

    # 1. Industrial mounting flange in 1 line
    asm.add_flange(
        name="drive_flange",
        outer_diameter=140.0,
        thickness=18.0,
        inner_bore=45.0,
        bolt_pcd=110.0,
        bolt_count=6,
        bolt_diameter=9.0,
        color=(0.3, 0.3, 0.35),
    )

    # 2. Multi-diameter stepped shaft in 1 line
    asm.add_stepped_shaft(
        name="transmission_shaft",
        steps=[(25.0, 40.0), (32.0, 20.0), (45.0, 70.0), (30.0, 30.0)],
        color=(0.7, 0.7, 0.75),
    )

    # 3. Standard I-Beam structural member in 1 line
    asm.add_ibeam(
        name="chassis_beam",
        length=250.0,
        height=80.0,
        flange_width=46.0,
        web_thickness=4.0,
        flange_thickness=6.0,
        color=(0.8, 0.2, 0.2),
    )

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    for expected in ["drive_flange", "transmission_shaft", "chassis_beam"]:
        assert expected in solids, f"Macro '{expected}' failed to compile"
        assert not solids[expected].IsNull()

    val = ValidationEngineer()
    for name, s in solids.items():
        assert val.check_manifold(s), f"Solid '{name}' is not manifold"

    print("  -> All 3 Engineering Macros (Flange, SteppedShaft, IBeam) compiled successfully!")


def test_delta_patch_revision():
    """Verify in-place patch modifies parameters without re-declaring the assembly."""
    print("--- Testing In-Place Delta Patching ---")
    asm = Assembly("PatchTest")
    c = asm.add_cylinder("piston", radius=20.0, height=50.0)
    c.set_appearance(color=(0.5, 0.5, 0.5), material="CastIron")

    # Before patch
    assert asm._ir.parts["piston"].parameters["radius"] == 20.0

    # User revision: "Piston çapını 25mm yap ve malzemeyi Al7075 yap"
    # LLM emits only 1 compact patch dictionary!
    asm.patch({
        "piston.radius": 25.0,
        "piston.material": "Al7075-T6",
        "piston.color": (0.9, 0.1, 0.1),
    })

    # After patch verification
    assert asm._ir.parts["piston"].parameters["radius"] == 25.0
    assert asm._ir.parts["piston"].material == "Al7075-T6"
    assert asm._ir.parts["piston"].color == (0.9, 0.1, 0.1)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    mass = backend.calculate_mass_properties(asm.to_ir())

    # New volume should reflect r=25.0: pi * 25^2 * 50 = ~98,174 mm³
    expected_vol = math.pi * (25.0 ** 2) * 50.0
    assert abs(mass["total_volume_mm3"] - expected_vol) < 100.0
    print(f"  -> Delta patch applied in-place successfully! New Volume: {mass['total_volume_mm3']:,.1f} mm³")


def test_token_reduction_benchmark():
    """Demonstrate token savings ratio."""
    print("--- Token Reduction Benchmark ---")
    # Comparing verbose manual flange vs semantic macro flange
    verbose_code = """
flange = asm.add_cylinder("flange", radius=70.0, height=18.0)
flange.add_hole("center_bore", diameter=45.0, position=(0.0, 0.0))
# 6 holes with manual trigonometry
for i in range(6):
    ang = i * 60.0 * 3.14159 / 180.0
    hx = 55.0 * math.cos(ang)
    hy = 55.0 * math.sin(ang)
    flange.add_hole(f"hole_{i}", diameter=9.0, position=(hx, hy))
flange.set_appearance(color=(0.3, 0.3, 0.35), material="Steel")
"""
    macro_code = 'asm.add_flange("flange", outer_diameter=140.0, thickness=18.0, inner_bore=45.0, bolt_pcd=110.0, bolt_count=6, bolt_diameter=9.0)'

    print(f"  -> Verbose code chars : {len(verbose_code.strip())} (~{len(verbose_code)//4} tokens)")
    print(f"  -> SAML Macro chars   : {len(macro_code.strip())} (~{len(macro_code)//4} tokens)")
    savings = (1.0 - len(macro_code) / len(verbose_code)) * 100.0
    print(f"  -> Token Savings      : {savings:.1f}% reduction!")


if __name__ == "__main__":
    print("=======================================================================")
    print("   Running SAML Token Reduction & Macro Enhancements Test Suite")
    print("=======================================================================")
    test_compact_coordinate_string()
    test_pcd_bolt_pattern()
    test_semantic_engineering_macros()
    test_delta_patch_revision()
    test_token_reduction_benchmark()
    print("\n>>> ALL SAML TOKEN REDUCTION TESTS PASSED (100% SUCCESS)! <<<")
