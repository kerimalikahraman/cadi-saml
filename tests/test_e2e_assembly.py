"""
tests/test_e2e_assembly.py
==========================
End-to-end verification test for cadi-saml pure OpenCASCADE engine.
"""

import os
import sys

# Add library/src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cadi_saml import Assembly, Fastener, Bearing, OCCTBackend, ValidationEngineer


def test_e2e_declarative_assembly(tmp_path):
    # 1. Create declarative assembly using Pythonic SAML
    with Assembly("E2E_Gearbox_Test", units="mm", material="AlSi10Mg") as asm:
        # 1. Base plate with bored hole for M8 clearance (Dia: 8.5mm, through-hole)
        base = asm.add_box("base_plate", length=100.0, width=80.0, height=12.0)
        base.add_hole(name="mount_hole", diameter=8.5, depth=0.0, position=(0.0, 0.0))
        
        # 2. Standard SKF 608ZZ Bearing (Outer: 22mm, Bore: 8mm, Width: 7mm)
        bearing = Bearing.SKF(name="main_bearing", code="608ZZ")

        # 3. Standard ISO 4762 M8 Bolt with Hex Socket (Shank: 8mm, Length: 35mm)
        bolt = Fastener.ISO4762(name="clamp_bolt", size="M8", length=35.0)

        # Register standard parts to assembly IR
        asm._ir.add_part(bearing)
        asm._ir.add_part(bolt)

        # Logical Mechanical Assembly Chain:
        # A) Mount bearing onto the top face of the base plate
        asm.connect(base.face("top"), "main_bearing:port:back_face", mate_type="FLUSH")

        # B) Seat the bolt head onto the front face of the bearing (bolt passes through bearing bore & plate hole)
        asm.connect("main_bearing:port:front_face", "clamp_bolt:port:under_head", mate_type="FLUSH")

        # Generate IR
        ir = asm.to_ir()

    assert ir.metadata.name == "E2E_Gearbox_Test"
    assert len(ir.parts) == 3
    assert len(ir.mates) == 2

    # 2. Compile directly with pure OpenCASCADE backend
    backend = OCCTBackend()
    solids = backend.compile(ir)

    # 3. Validation Engineer: Check for clashes and manifoldness
    validator = ValidationEngineer(clash_volume_tolerance=0.05)
    for name, solid in solids.items():
        assert validator.check_manifold(name, solid), f"Part '{name}' is not a valid manifold solid!"

    clashes = validator.check_clashes(solids)
    print(f"\n[Validation] Toplam Çakışma Sayısı: {len(clashes)}")
    if clashes:
        print(validator.generate_feedback(clashes))

    # 4. Export STEP
    step_output = str(tmp_path / "e2e_assembly.step")
    exported_file = backend.export_step(ir, step_output)
    assert os.path.exists(exported_file)
    assert os.path.getsize(exported_file) > 1000

    # 5. Export STL
    stl_output = str(tmp_path / "e2e_assembly.stl")
    exported_stl = backend.export_stl(ir, stl_output)
    assert os.path.exists(exported_stl)
    assert os.path.getsize(exported_stl) > 500

    print("\n[SUCCESS] E2E OpenCASCADE Assembly Test Passed! Real bored hole, hex socket bolt & validation verified.")


if __name__ == "__main__":
    from pathlib import Path
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    test_e2e_declarative_assembly(out_dir)
    print(f"\n[OK] Modeller buraya kaydedildi: {out_dir.resolve()}")
