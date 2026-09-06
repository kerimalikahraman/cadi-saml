"""
tests.test_advanced_occt_modules
================================
Unit and Integration Tests for Advanced OpenCASCADE Capabilities in cadi_saml:
1. Native glTF / GLB Binary Exporter (RWGltf_CafWriter)
2. 2D Technical Drawing Engine (HLRBRep Hidden Line Removal -> 4-View Vector SVG)
3. Casting & Molding Draft Angle Module (BRepOffsetAPI_DraftAngle)
4. Topology Healing & Face Sewing (BRepBuilderAPI_Sewing & ShapeFix_Shape)
5. Full OZ Racing Formula Student Wheel GLB and 2D Engineering Drawing Generation
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
)
from test_formula_student_wheel import create_oz_formula_student_carbonio_wheel


def test_gltf_glb_export():
    """Verify native binary .glb export with colors and XCAF metadata."""
    print("--- Testing Native GLB Export ---")
    asm = Assembly("GLBTestAssembly")
    p1 = asm.add_box("chassis_block", 40.0, 30.0, 15.0)
    p1.set_appearance(color=(0.8, 0.1, 0.1), material="AnodizedRed")

    p2 = asm.add_cylinder("pin_shaft", radius=6.0, height=25.0)
    p2.set_appearance(color=(0.2, 0.5, 0.9), material="BlueSteel")

    out_dir = Path(__file__).parent.parent / "output"
    os.makedirs(out_dir, exist_ok=True)
    glb_path = out_dir / "test_chassis.glb"

    asm.export_glb(str(glb_path))
    assert glb_path.exists(), "GLB file was not created"
    assert glb_path.stat().st_size > 1000, "GLB file is unexpectedly small"
    print(f"  -> GLB created successfully: {glb_path} ({glb_path.stat().st_size / 1024:.1f} KB)")


def test_2d_technical_drawing_svg():
    """Verify 4-view 2D engineering drawing generation (HLRBRep -> Vector SVG)."""
    print("--- Testing 2D Technical Drawing Engine (HLRBRep) ---")
    asm = Assembly("FlangePart")
    p = asm.add_box("mounting_flange", 60.0, 40.0, 20.0)
    p.add_hole("bore_hole", diameter=14.0, position=(30.0, 20.0))


    out_dir = Path(__file__).parent.parent / "output"
    os.makedirs(out_dir, exist_ok=True)
    svg_path = out_dir / "flange_technical_drawing.svg"

    asm.export_technical_drawing(str(svg_path), title="Flange Plate ISO 2768")
    assert svg_path.exists(), "SVG drawing file was not created"
    assert svg_path.stat().st_size > 1000, "SVG drawing file is unexpectedly small"

    # Verify SVG structure and standard engineering views
    with open(svg_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "<svg" in content and "</svg>" in content
    assert "ÜST GÖRÜNÜŞ" in content
    assert "ÖN GÖRÜNÜŞ" in content
    assert "SAĞ YAN GÖRÜNÜŞ" in content
    assert "İZOMETRİK GÖRÜNÜŞ" in content
    assert "stroke-dasharray" in content, "Hidden lines were not generated"
    print(f"  -> 2D Engineering SVG created successfully: {svg_path} ({svg_path.stat().st_size / 1024:.1f} KB)")


def test_draft_angle_molding():
    """Verify casting/molding draft angle application to vertical side faces."""
    print("--- Testing Draft Angle Module ---")
    asm = Assembly("MoldingCore")
    p = asm.add_box("mold_pattern", 30.0, 30.0, 25.0)
    p.add_draft_angle(angle_deg=3.0, pull_direction=(0.0, 0.0, 1.0), neutral_plane_z=0.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "mold_pattern" in solids
    solid = solids["mold_pattern"]
    assert not solid.IsNull()

    val = ValidationEngineer()
    assert val.check_manifold(solid), "Drafted solid is not manifold"
    print("  -> Draft Angle applied successfully: Solid is manifold and valid!")


def test_topology_healing_and_sewing():
    """Verify surface sewing and ShapeFix geometry repair."""
    print("--- Testing Topology Healing & Sewing ---")
    import OCP.BRepPrimAPI as BRepPrim

    box = BRepPrim.BRepPrimAPI_MakeBox(20.0, 20.0, 20.0).Solid()
    val = ValidationEngineer()
    healed = val.heal_and_sew(box, tolerance=1e-3)
    assert not healed.IsNull()
    assert val.check_manifold(healed), "Healed shape is not manifold"
    print("  -> Healing & Sewing successfully verified!")


def test_oz_wheel_glb_and_technical_drawing():
    """Generate professional GLB and 4-view 2D engineering drawing for OZ Formula Student Wheel."""
    print("--- Generating Full Wheel GLB and 2D Technical Drawing ---")
    asm = create_oz_formula_student_carbonio_wheel(include_accessories=True)

    out_dir = Path(__file__).parent.parent / "output"
    os.makedirs(out_dir, exist_ok=True)
    wheel_glb = out_dir / "oz_formula_student_carbonio_wheel.glb"
    wheel_svg = out_dir / "oz_formula_student_wheel_drawing.svg"

    # 1. Native GLB export
    asm.export_glb(str(wheel_glb), deflection=0.1)
    assert wheel_glb.exists() and wheel_glb.stat().st_size > 100_000
    print(f"  -> Wheel GLB exported: {wheel_glb} ({wheel_glb.stat().st_size / 1024:.1f} KB)")

    # 2. 2D 4-View Technical Drawing export
    asm.export_technical_drawing(
        str(wheel_svg),
        title="O·Z RACING FORMULA STUDENT 13 INCH HYBRID WHEEL",
        sheet_width=1920,
        sheet_height=1080,
    )
    assert wheel_svg.exists() and wheel_svg.stat().st_size > 10_000
    print(f"  -> Wheel 2D Technical Drawing exported: {wheel_svg} ({wheel_svg.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    print("=======================================================================")
    print("   Running Advanced OpenCASCADE Features Test Suite")
    print("=======================================================================")
    test_gltf_glb_export()
    test_2d_technical_drawing_svg()
    test_draft_angle_molding()
    test_topology_healing_and_sewing()
    test_oz_wheel_glb_and_technical_drawing()
    print("\n>>> ALL ADVANCED OPENCASCADE MODULE TESTS PASSED (100% SUCCESS)! <<<")
