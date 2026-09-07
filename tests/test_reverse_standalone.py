"""
tests/test_reverse_standalone.py

Comprehensive test suite for CADi SAML Reverse Engineering:
- B-Rep feature classification (Box, Cylinder, Holes)
- Standalone Python code synthesis (zero STEP file dependencies at runtime)
- Geometric equivalence verification (volume, bounding box, CoG)
- Atomic transactions and automatic rollback on failure
"""

import os
import tempfile
import pytest
import numpy as np

from cadi_saml.core.assembly import Assembly
from cadi_saml.reverse.feature_classifier import BRepFeatureClassifier
from cadi_saml.reverse.geometry_matcher import verify_geometric_equivalence
from cadi_saml.reverse.standalone_generator import (
    load_step_shape,
    generate_standalone_python_code,
    reconstruct_as_assembly,
    reverse_engineer_step_to_code,
)
from cadi_saml.reverse.transaction import ReverseEngineeringTransaction


@pytest.fixture
def sample_box_with_holes_step():
    """Generates a temporary STEP file with a box and 2 through holes."""
    tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
    tmp.close()

    asm = Assembly("source_bracket")
    box = asm.add_box("body", length=100.0, width=60.0, height=25.0)
    # Add two holes
    box.add_hole("h1", diameter=10.0, depth=25.0, position=(25.0, 15.0), face="top")
    box.add_hole("h2", diameter=12.0, depth=25.0, position=(-25.0, -15.0), face="top")
    
    asm.export_step(tmp.name)
    yield tmp.name
    if os.path.exists(tmp.name):
        os.remove(tmp.name)


@pytest.fixture
def sample_cylinder_step():
    """Generates a temporary STEP file with a solid cylinder."""
    tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
    tmp.close()

    asm = Assembly("source_puck")
    asm.add_cylinder("flange", radius=30.0, height=45.0)
    asm.export_step(tmp.name)
    yield tmp.name
    if os.path.exists(tmp.name):
        os.remove(tmp.name)


# ==============================================================================
# 1. Feature Classifier Tests
# ==============================================================================

def test_classify_box_and_holes(sample_box_with_holes_step):
    shape = load_step_shape(sample_box_with_holes_step)
    classifier = BRepFeatureClassifier(shape)
    classified = classifier.classify()

    # 1. Base solid must be identified as box
    assert classified.base_solid.base_type == "box"
    params = classified.base_solid.parameters
    assert pytest.approx(params["length"], abs=0.5) == 100.0
    assert pytest.approx(params["width"], abs=0.5) == 60.0
    assert pytest.approx(params["height"], abs=0.5) == 25.0

    # 2. Holes must be extracted
    assert len(classified.holes) == 2
    hole_dias = sorted([h.diameter for h in classified.holes])
    assert pytest.approx(hole_dias[0], abs=0.2) == 10.0
    assert pytest.approx(hole_dias[1], abs=0.2) == 12.0

    # Dictionary serialization
    d = classified.to_dict()
    assert d["base_solid"]["type"] == "box"
    assert len(d["holes"]) == 2


def test_classify_cylinder(sample_cylinder_step):
    shape = load_step_shape(sample_cylinder_step)
    classifier = BRepFeatureClassifier(shape)
    classified = classifier.classify()

    assert classified.base_solid.base_type == "cylinder"
    params = classified.base_solid.parameters
    assert pytest.approx(params["radius"], abs=0.5) == 30.0
    assert pytest.approx(params["height"], abs=0.5) == 45.0


# ==============================================================================
# 2. Standalone Code Generation and Execution Test
# ==============================================================================

def test_standalone_code_synthesis_and_execution(sample_box_with_holes_step):
    shape = load_step_shape(sample_box_with_holes_step)
    classifier = BRepFeatureClassifier(shape)
    classified = classifier.classify()

    # Synthesize clean standalone Python code
    py_code = generate_standalone_python_code(classified, part_name="my_part")
    
    # Must contain CADi SAML assembly construction and NO step import calls
    assert "from cadi_saml.core.assembly import Assembly" in py_code
    assert "add_box" in py_code
    assert "add_hole" in py_code
    assert "import_step" not in py_code
    assert "STEPControl" not in py_code

    # Execute the generated Python code in an isolated clean namespace
    ns = {}
    exec(py_code, ns)
    assert "build_my_part" in ns
    rebuilt_asm = ns["build_my_part"]()
    assert isinstance(rebuilt_asm, Assembly)
    assert len(rebuilt_asm._parts) == 1


# ==============================================================================
# 3. Geometric Equivalence Verification Test
# ==============================================================================

def test_reverse_engineer_and_verify_pipeline(sample_box_with_holes_step):
    py_code, rebuilt_asm, match_report = reverse_engineer_step_to_code(
        step_file_path=sample_box_with_holes_step,
        part_name="verified_bracket",
    )
    
    assert len(py_code) > 0
    assert isinstance(rebuilt_asm, Assembly)
    # The reconstructed model should match the original within tight tolerances
    assert match_report.passed
    assert match_report.volume_rel_error < 0.005  # < 0.5% difference
    assert match_report.cog_shift_mm < 1.0


# ==============================================================================
# 4. Transaction and Rollback Tests
# ==============================================================================

def test_transaction_commit_and_rollback():
    asm = Assembly("engine_block")
    asm.add_box("housing", length=120.0, width=80.0, height=50.0)

    tx = ReverseEngineeringTransaction(asm)

    # 1. Valid parametric modification: commit succeeds
    res1 = tx.apply_parametric_patch(
        part_name="housing",
        param_updates={"length": 140.0},
        description="Enlarge housing length",
    )
    assert res1.committed
    assert res1.contract_passed
    assert asm._parts["housing"].node.parameters["length"] == 140.0

    # 2. Manual rollback to step 0
    rolled_back = tx.rollback_to_step(0)
    assert rolled_back
    assert asm._parts["housing"].node.parameters["length"] == 120.0
