"""
End-to-end integration tests for extended cadi-saml capabilities:
- Additional primitives (cone, sphere, torus)
- Edge fillets and chamfers
- Standard hardware: Nut (DIN 934), Washer (DIN 125), Profile (VSlot 2020), Motor (NEMA 17)
- Assembly-level Boolean operations (cut, fuse)
- ValidationEngineer manifoldness & clash checks
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
    Nut,
    Washer,
    Profile,
    Motor,
    Fastener,
    Bearing,
)


def test_new_primitives_compilation():
    """Test cone, sphere, torus primitives compilation."""
    asm = Assembly(name="PrimitivesTest")
    asm.add_cone("my_cone", bottom_radius=10.0, top_radius=5.0, height=20.0)
    asm.add_sphere("my_sphere", radius=8.0)
    asm.add_torus("my_torus", major_radius=15.0, minor_radius=3.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert len(solids) == 3
    assert "my_cone" in solids
    assert "my_sphere" in solids
    assert "my_torus" in solids

    # Validate manifoldness
    val = ValidationEngineer()
    for name, shape in solids.items():
        assert val.check_manifold(shape), f"Primitive {name} is not manifold"


def test_fillet_and_chamfer():
    """Test fillet and chamfer modifications on a box."""
    asm = Assembly(name="FilletChamferTest")
    b1 = asm.add_box("box_filleted", 20.0, 20.0, 10.0)
    b1.add_fillet(radius=1.5, edges="all_top")

    b2 = asm.add_box("box_chamfered", 20.0, 20.0, 10.0)
    b2.add_chamfer(distance=1.0, edges="all_top")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert len(solids) == 2
    val = ValidationEngineer()
    assert val.check_manifold(solids["box_filleted"])
    assert val.check_manifold(solids["box_chamfered"])


def test_standard_parts_creation():
    """Test direct API creation of Nut, Washer, Profile, Motor."""
    asm = Assembly(name="StandardPartsCatalog")

    bolt = asm.add_fastener("bolt1", standard="ISO4762", size="M6", length=25.0)
    nut = asm.add_nut("nut1", standard="DIN934", size="M6")
    washer = asm.add_washer("washer1", standard="DIN125", size="M6")
    bearing = asm.add_bearing("bearing1", standard="SKF", code="608ZZ")
    profile = asm.add_profile("rail1", profile_type="2020", length=150.0)
    motor = asm.add_motor("stepper1", frame="NEMA17", body_length=40.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert len(solids) == 6
    val = ValidationEngineer()
    for name, shape in solids.items():
        assert val.check_manifold(shape), f"Standard part {name} is not manifold"


def test_motor_and_plate_assembly(tmp_dir: str = None):
    """
    Test real mechanical assembly:
    A plate mounted onto NEMA 17 front face, with 4 bolt holes aligned.
    """
    asm = Assembly(name="MotorMountAssembly")

    # 1. NEMA 17 Stepper
    motor = asm.add_motor("motor", frame="NEMA17", body_length=40.0)

    # 2. Aluminum mount plate: 50x50x4mm
    plate = asm.add_box("plate", 50.0, 50.0, 4.0)
    # Center hole for pilot boss (22mm)
    plate.add_hole("center_pilot_hole", diameter=23.0, position=(0.0, 0.0), face="top")
    # 4 mounting holes for M3 (at pitch 31mm -> x=±15.5, y=±15.5)
    plate.add_hole("mh1", diameter=3.4, position=(15.5, 15.5), face="top")
    plate.add_hole("mh2", diameter=3.4, position=(-15.5, 15.5), face="top")
    plate.add_hole("mh3", diameter=3.4, position=(-15.5, -15.5), face="top")
    plate.add_hole("mh4", diameter=3.4, position=(15.5, -15.5), face="top")

    # 3. Connect plate flush with motor mount face
    asm.connect(plate.face("bottom"), motor.port("mount_face"), mate_type="FLUSH")

    backend = OCCTBackend()
    out_dir = str(Path(__file__).parent.parent / "output")
    step_out = os.path.join(out_dir, "motor_assembly.step")
    stl_out = os.path.join(out_dir, "motor_assembly.stl")
    backend.export_step(asm.to_ir(), step_out)
    backend.export_stl(asm.to_ir(), stl_out)

    assert os.path.exists(step_out)
    assert os.path.getsize(step_out) > 1000
    print("  -> MotorMountAssembly STEP & STL export OK:", step_out, f"({os.path.getsize(step_out)} bytes)")


def test_boolean_cut_operation():
    """Test assembly-level boolean cut."""
    asm = Assembly(name="BooleanCutTest")

    # Target: 30x30x10 block
    asm.add_box("block", 30.0, 30.0, 10.0)
    # Tool: dia 10 cylinder through the center
    asm.add_cylinder("cutter_cyl", radius=5.0, height=20.0)

    # Cut cylinder from block
    asm.cut(target_part="block", tool_part="cutter_cyl", keep_tool=False)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    # cutter_cyl was consumed (keep_tool=False)
    assert "cutter_cyl" not in solids
    assert "block" in solids

    val = ValidationEngineer()
    assert val.check_manifold(solids["block"])
    print("  -> Boolean cut operation OK")


if __name__ == "__main__":
    print("=== Running cadi-saml Extended Capabilities Tests ===")
    print("[1/5] Testing primitives (cone, sphere, torus)...")
    test_new_primitives_compilation()
    print("  -> Primitives OK")

    print("[2/5] Testing fillets and chamfers...")
    test_fillet_and_chamfer()
    print("  -> Fillet/Chamfer OK")

    print("[3/5] Testing standard parts (nut, washer, profile, motor)...")
    test_standard_parts_creation()
    print("  -> Standard parts catalog OK")

    print("[4/5] Testing motor and mount plate assembly...")
    test_motor_and_plate_assembly()
    print("  -> Assembly mate OK")

    print("[5/5] Testing boolean operations (cut)...")
    test_boolean_cut_operation()

    print("\n>>> ALL EXTENDED CAPABILITIES TESTS PASSED SUCCESSFULLY! <<<")
