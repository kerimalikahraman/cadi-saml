"""
Unit and Integration Tests for Advanced cadi-saml Capabilities:
1. Motorsport Standard Parts (CenterlockNut, BrakeRotor, BrakeCaliper, DrivePin, HeimJoint)
2. Declarative 2D Sketch Engine (Circle, Rectangle, Slot, Regular Polygon)
3. 3D B-Rep Typography & Engraving (TextEngine)
4. Multi-Material Colored STEP (AP214 XCAF) Exporter
5. Full OZ Racing Formula Student Wheel Assembly
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src and tests to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
    Sketch,
    Motorsport,
)
from test_formula_student_wheel import create_oz_formula_student_carbonio_wheel



def test_motorsport_components():
    """Verify all motorsport components compile to valid 3D B-Rep solids."""
    asm = Assembly("MotorsportSuite")
    asm.add_centerlock_nut("nut", size="M30")
    asm.add_brake_rotor("rotor", outer_diameter=220.0)
    asm.add_brake_caliper("caliper")
    asm.add_drive_pin("pin")
    asm.add_heim_joint("heim")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert len(solids) == 5
    for expected in ["nut", "rotor", "caliper", "pin", "heim"]:
        assert expected in solids, f"Missing {expected} in compiled solids"

    # Validate manifoldness
    val = ValidationEngineer()
    for name, shape in solids.items():
        assert val.check_manifold(shape), f"Motorsport part '{name}' is not manifold"


def test_sketch_engine():
    """Verify 2D sketch composition with slot and regular polygon extrusion."""
    asm = Assembly("SketchSuite")

    # 1. Slot profile
    sk_slot = asm.sketch(name="slot_sk", plane="XY")
    sk_slot.add_slot(length=50.0, width=16.0, center=(0.0, 0.0), angle_deg=45.0)
    asm.add_extrude("slot_solid", section=sk_slot, distance=10.0)

    # 2. Hexagon profile
    sk_hex = asm.sketch(name="hex_sk", plane="XY", origin=(50.0, 0.0, 0.0))
    sk_hex.add_regular_polygon(sides=6, radius=15.0)
    asm.add_extrude("hex_solid", section=sk_hex, distance=12.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert len(solids) == 2
    assert "slot_solid" in solids
    assert "hex_solid" in solids

    val = ValidationEngineer()
    for name, shape in solids.items():
        assert val.check_manifold(shape), f"Sketch solid '{name}' is not manifold"


def test_3d_text_engine():
    """Verify 3D parametric text solid generation."""
    asm = Assembly("TextSuite")
    asm.add_text("brand", text="OZ RACING", font_size=14.0, depth=2.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "brand" in solids
    assert not solids["brand"].IsNull()


def test_colored_step_export():
    """Verify Multi-Material AP214 Colored STEP export with XCAF metadata."""
    asm = Assembly("ColoredStepSuite")
    b1 = asm.add_box("red_part", length=20.0, width=20.0, height=10.0)
    b1.set_appearance(color=(1.0, 0.0, 0.0), material="AnodizedRed")

    b2 = asm.add_cylinder("blue_part", radius=8.0, height=20.0)
    b2.set_appearance(color=(0.0, 0.0, 1.0), material="AnodizedBlue")

    backend = OCCTBackend()
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        backend.export_step_colored(asm.to_ir(), tmp_path)
        assert os.path.exists(tmp_path)
        assert os.path.getsize(tmp_path) > 1000
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_full_oz_wheel_assembly():
    """Verify full OZ Racing Formula Student Carbonio assembly with all parts."""
    asm = create_oz_formula_student_carbonio_wheel(include_accessories=True)
    backend = OCCTBackend()

    solids = backend.compile(asm.to_ir())
    assert len(solids) >= 14
    assert "carbon_barrel" in solids
    assert "center_hub" in solids
    assert "centerlock_nut" in solids
    assert "brake_rotor" in solids
    assert "spoke_body" in solids

    mass_props = backend.calculate_mass_properties(asm.to_ir())
    assert mass_props["total_mass_kg"] > 0.0


if __name__ == "__main__":
    print("Running advanced capabilities test suite...")
    test_motorsport_components()
    print("  -> Motorsport components: OK")
    test_sketch_engine()
    print("  -> Sketch engine: OK")
    test_3d_text_engine()
    print("  -> 3D text engine: OK")
    test_colored_step_export()
    print("  -> Colored STEP export: OK")
    test_full_oz_wheel_assembly()
    print("  -> Full OZ Wheel assembly: OK")
    print("\n>>> ALL ADVANCED CAPABILITIES TESTS PASSED! <<<")
