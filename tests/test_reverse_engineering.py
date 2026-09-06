"""
tests/test_reverse_engineering.py
=================================
Verification for Step-to-SAML reverse engineering pipeline.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cadi_saml import Assembly, Fastener, OCCTBackend, STEPReverseEngineer


if __name__ == "__main__":
    from pathlib import Path
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    td = str(out_dir)

    # 1. Create a dummy test STEP part
    with Assembly("ReverseTestPart") as asm:
        asm.add_box("block", length=50.0, width=40.0, height=20.0)
        bolt = Fastener.ISO4762(name="b1", size="M4", length=15.0)
        asm._ir.add_part(bolt)
        asm.connect("block:face:top", "b1:port:under_head", mate_type="FLUSH")
        ir = asm.to_ir()

    step_file = os.path.join(td, "reverse_sample_part.step")
    backend = OCCTBackend()
    backend.export_step(ir, step_file)
    assert os.path.exists(step_file)

    # 2. Reverse Engineer STEP file back to SAML
    result = STEPReverseEngineer.inspect_and_to_saml(step_file, part_name="extracted_flange")

    # Save generated SAML code to a .py file
    py_out = os.path.join(td, "extracted_flange_generated.py")
    with open(py_out, "w", encoding="utf-8") as f:
        f.write(result["saml_code"])

    print("\n--- Auto-Generated SAML Code from STEP ---")
    print(result["saml_code"])
    print("------------------------------------------")
    print(f"[OK] Reverse engineering dosyalari kaydedildi: {out_dir.resolve()}")
