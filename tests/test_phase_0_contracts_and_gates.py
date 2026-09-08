"""
tests/test_phase_0_contracts_and_gates.py
=========================================
Validation test suite for Faz 0:
1. Canonical repository manifest verification
2. Versioned contract schemas (Units, Coordinates, Indexing, Tolerances, Solvers, Failure Modes, Provenance)
3. Negative failure scenarios (invalid index_base, mixed base rejection)
4. Exit Gate execution and deterministic reporting
"""

import json
import os
import sys
from pathlib import Path
import pytest

# Ensure library/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml.spec import (
    CANONICAL_CONTRACT,
    CONTRACTS_SCHEMA_VERSION,
    UnitContract,
    CoordinateContract,
    IndexContract,
    ToleranceContract,
    SolverContract,
    FailureContract,
    ProvenanceContract,
)
from cadi_saml.analysis.frd_reader import _normalize_element_sets
from cadi_saml.validation.gate_validator import GateValidator, PhaseGateReport


def test_manifest_schema_and_canonical_mapping():
    """Verify that cadi_manifest.json specifies single canonical source and mirrors."""
    manifest_path = Path(__file__).resolve().parents[1] / "cadi_manifest.json"
    assert manifest_path.is_file(), f"Manifest not found at {manifest_path}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["manifest_version"] == "1.0.0"
    assert manifest["contracts_version"] == "1.0.0"

    # Verify canonical source is library
    canonical = manifest["canonical_source"]
    assert canonical["name"] == "cadi-saml"
    assert "library" in canonical["local_path"]
    assert canonical["editable_installed"] is True

    # Verify downstream mirrors
    mirrors = manifest["downstream_mirrors"]
    assert len(mirrors) >= 1
    assert any("Project-CAD-" in m["name"] for m in mirrors)


def test_contracts_immutability_and_schemas():
    """Verify all versioned contract schemas match engineering specifications."""
    assert CONTRACTS_SCHEMA_VERSION == "1.0.0"

    # 1. Units
    u: UnitContract = CANONICAL_CONTRACT.units
    assert u.length == "mm"
    assert u.force == "N"
    assert u.stress == "MPa"
    assert u.pressure == "MPa"
    assert u.mass == "kg"
    assert u.time == "s"

    # 2. Coordinates
    c: CoordinateContract = CANONICAL_CONTRACT.coordinates
    assert c.system == "right_handed_cartesian"
    assert c.up_axis == "+Z"
    assert c.forward_axis == "+X"
    assert c.lateral_axis == "+Y"

    # 3. Indexing
    idx: IndexContract = CANONICAL_CONTRACT.indexing
    assert idx.default_model_base == "one"
    assert idx.allowed_bases == ("one", "zero", "auto")
    assert idx.calculix_id_base == 1
    assert idx.memory_array_base == 0
    assert not idx.silent_filtering_allowed
    assert not idx.mixed_base_allowed

    # 4. Tolerances
    tol: ToleranceContract = CANONICAL_CONTRACT.tolerances
    assert tol.linear_abs_tol_mm == 1e-4
    assert tol.angular_abs_tol_rad == 1e-4
    assert tol.displacement_convergence_pct == 3.0
    assert tol.stress_convergence_pct == 5.0
    assert tol.solver_benchmark_match_pct == 5.0

    # 5. Solvers
    sol: SolverContract = CANONICAL_CONTRACT.solvers
    assert sol.default_backend == "builtin"
    assert "calculix_ccx" in sol.allowed_backends

    # 6. Failure Modes
    fail: FailureContract = CANONICAL_CONTRACT.failures
    assert fail.fail_fast_on_invalid_id is True
    assert fail.fail_fast_on_mixed_base is True
    assert fail.allow_approximate_geometry_substitution is False

    # 7. Provenance
    prov: ProvenanceContract = CANONICAL_CONTRACT.provenance
    env = prov.capture_environment()
    assert env["schema_version"] == "1.0.0"
    assert "python_version" in env
    assert "os_system" in env
    assert "timestamp_utc" in env


def test_negative_invalid_index_base_rejection():
    """Negative test: invalid index_base must raise ValueError immediately."""
    idx = CANONICAL_CONTRACT.indexing
    with pytest.raises(ValueError, match="Invalid index base 'two'"):
        idx.validate_base("two")

    with pytest.raises(ValueError, match="Invalid index base '123'"):
        idx.validate_base("123")


def test_negative_mixed_base_rejection():
    """Negative test: mixed 0-based and 1-based element sets must raise ValueError."""
    # 6-element mesh: steel has 0 (0-based) while aluminum has 6 (1-based)
    mixed_sets = {
        "steel": [0, 1, 2],
        "aluminum": [4, 5, 6],
    }
    with pytest.raises(ValueError, match=r"Conflicting / mixed element index base"):
        _normalize_element_sets(mixed_sets, num_elems=6, index_base="auto")


def test_gate_validator_phase_0_execution():
    """Verify GateValidator successfully validates Phase 0 exit gate."""
    validator = GateValidator()
    report: PhaseGateReport = validator.validate_phase(0)

    assert report.is_approved is True
    assert report.verdict == "GATE_PASSED"
    assert report.failed_count == 0
    assert report.blocked_count == 0
    assert report.manifest_verified is True
    assert report.negative_scenarios_verified is True
    assert report.contracts_schema_version == "1.0.0"

    # Check Markdown report generation
    md = report.to_markdown()
    assert "GATE_PASSED" in md
    assert "CADi SAML Faz 0" in md
    assert "Çalışma Ortamı (Environment)" in md
    assert report.environment["python_version"]
    assert len(report.executed_node_ids) >= 2


def test_gate_validator_missing_target_test_rejection():
    """Verify that GateValidator rejects phases with missing or unexecuted target tests."""
    from cadi_saml.validation.gate_validator import PHASE_REGISTRY, PhaseGateDefinition
    
    # Register dummy phase 99 with a missing test
    PHASE_REGISTRY[99] = PhaseGateDefinition(
        phase_number=99,
        phase_name="NonExistentPhaseTest",
        target_tests=[
            "tests/test_non_existent_file.py::test_that_does_not_exist",
        ],
        negative_tests=[
            "tests/test_non_existent_file.py::test_negative_that_does_not_exist",
        ],
    )
    try:
        validator = GateValidator()
        report: PhaseGateReport = validator.validate_phase(99)

        # Must NOT be approved!
        assert report.is_approved is False
        assert report.verdict in ("GATE_BLOCKED", "GATE_FAILED")
        assert len(report.missing_node_ids) >= 2
        assert "tests/test_non_existent_file.py::test_that_does_not_exist" in report.missing_node_ids
    finally:
        del PHASE_REGISTRY[99]

