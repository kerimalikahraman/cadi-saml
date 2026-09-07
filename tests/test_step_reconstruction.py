"""
tests/test_step_reconstruction.py

Comprehensive tests for:
1. Pure inspection API (cadi_saml.reverse.inspection.inspect_step)
2. Standalone STEP Reconstruction (cadi_saml.reverse.reconstruction.reconstruct_step)
3. Zero STEP runtime dependency verification in generated code
4. Geometric equivalence diff (volume, area, CoG shift)
5. Visual QA INCONCLUSIVE status on missing rendering
6. Strict PARSE_ERROR reporting on corrupt or missing files
"""

import os
import tempfile
import pytest

from cadi_saml.core.assembly import Assembly
from cadi_saml.reverse.inspection import inspect_step, STEPParseError
from cadi_saml.reverse.reconstruction import (
    reconstruct_step,
    ReconstructionResult,
    ParametricFeatureTree,
)


@pytest.fixture
def sample_plate_with_holes_step():
    """Generates a temporary STEP file with a plate and through holes."""
    tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
    tmp.close()

    asm = Assembly("plate_src")
    box = asm.add_box("body", length=120.0, width=80.0, height=20.0)
    box.add_hole("h1", diameter=10.0, depth=20.0, position=(30.0, 20.0), face="top")
    box.add_hole("h2", diameter=14.0, depth=20.0, position=(-30.0, -20.0), face="top")

    asm.export_step(tmp.name)
    yield tmp.name
    if os.path.exists(tmp.name):
        os.remove(tmp.name)


@pytest.fixture
def corrupt_step_file():
    """Generates a corrupt text file posing as STEP."""
    tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
    tmp.write(b"NOT A VALID ISO-10303 STEP FILE CONTENT GARBAGE")
    tmp.close()
    yield tmp.name
    if os.path.exists(tmp.name):
        os.remove(tmp.name)


# ==============================================================================
# 1. Pure Inspection Tests
# ==============================================================================

def test_inspect_step_pure_inspection(sample_plate_with_holes_step):
    result = inspect_step(sample_plate_with_holes_step, part_name="test_plate")
    
    assert result["status"] == "INSPECTED"
    assert result["part_name"] == "test_plate"
    assert result["num_holes"] == 2
    assert "dimensions" in result
    assert result["dimensions"]["dx"] == pytest.approx(120.0, abs=0.5)
    assert result["dimensions"]["dy"] == pytest.approx(80.0, abs=0.5)
    assert result["dimensions"]["dz"] == pytest.approx(20.0, abs=0.5)

    # Must NOT produce fake assembly code referencing add_step_part
    assert "saml_code" not in result
    assert "add_step_part" not in str(result)


def test_inspect_step_parse_error_handling(corrupt_step_file):
    # Strict mode should raise STEPParseError
    with pytest.raises(STEPParseError):
        inspect_step(corrupt_step_file, strict=True)

    # Non-strict mode should return structured PARSE_ERROR
    res = inspect_step(corrupt_step_file, strict=False)
    assert res["status"] == "PARSE_ERROR"
    assert "error" in res


# ==============================================================================
# 2. Standalone Code Generation & Zero-STEP Dependency Tests
# ==============================================================================

def test_reconstruct_step_standalone_code_no_step_dependency(sample_plate_with_holes_step):
    res: ReconstructionResult = reconstruct_step(
        step_file_path=sample_plate_with_holes_step,
        part_name="verified_plate",
    )

    assert res.status == "SUCCESS"
    assert isinstance(res.feature_tree, ParametricFeatureTree)
    assert res.feature_tree.base_solid.feature_type == "box"
    assert len(res.feature_tree.modifications) == 2

    # Verify generated Python code
    code = res.saml_code
    assert len(code) > 0
    assert "from cadi_saml.core.assembly import Assembly" in code
    assert "def build_verified_plate()" in code
    assert "add_box" in code
    assert "add_hole" in code

    # MUST NOT contain any STEP references
    assert "add_step_part" not in code
    assert ".step" not in code.lower()
    assert "import_step" not in code
    assert "STEPControl" not in code


# ==============================================================================
# 3. Clean Execution & Geometric Diff Tests
# ==============================================================================

def test_reconstruct_step_clean_execution_and_geometric_diff(sample_plate_with_holes_step):
    res: ReconstructionResult = reconstruct_step(
        step_file_path=sample_plate_with_holes_step,
        part_name="clean_exec_part",
    )

    # Execute generated code in a completely isolated namespace
    isolated_ns = {}
    exec(res.saml_code, isolated_ns)
    assert "build_clean_exec_part" in isolated_ns

    built_asm = isolated_ns["build_clean_exec_part"]()
    assert isinstance(built_asm, Assembly)
    assert len(built_asm._parts) == 1

    # Geometric match checks
    assert res.geometric_match is not None
    assert res.geometric_match.passed is True
    assert res.geometric_match.volume_rel_error < 0.005  # < 0.5%
    assert res.geometric_match.cog_shift_mm < 1.0


# ==============================================================================
# 4. Visual QA Inconclusive Semantics Tests
# ==============================================================================

def test_reconstruct_step_visual_qa_inconclusive(sample_plate_with_holes_step):
    # Request visual QA but provide a non-existent image path
    res: ReconstructionResult = reconstruct_step(
        step_file_path=sample_plate_with_holes_step,
        part_name="qa_plate",
        visual_qa=True,
        rendered_image_path="C:/non_existent_render_path.png",
    )

    # Must NOT report silent success when visual QA was requested but image is missing!
    assert res.status == "INCONCLUSIVE"
    assert res.visual_qa_status == "INCONCLUSIVE"
    assert any("INCONCLUSIVE" in w for w in res.warnings)


# ==============================================================================
# 5. Corrupted File Error Reporting
# ==============================================================================

def test_reconstruct_step_corrupted_file_parse_error(corrupt_step_file):
    res: ReconstructionResult = reconstruct_step(
        step_file_path=corrupt_step_file,
        part_name="broken_model",
    )

    assert res.status == "PARSE_ERROR"
    assert len(res.errors) >= 1
    assert res.rebuilt_assembly is None
