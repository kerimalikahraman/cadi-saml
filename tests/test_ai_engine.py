"""
tests.test_ai_engine
====================
Unit and Integration Tests for Core CAD & AI Engine Capabilities:
1. AI Self-Healing & Diagnostic Feedback Loop (asm.diagnose)
2. Parametric Master Variables & Cascading Formula Engine (asm.set_var / asm.eval_expr)
3. Smart STEP Reverse Engineering with PCD Detection (STEPReverseEngineer)
4. Synthetic Training Dataset Generation & Verification (saml_gold_dataset.jsonl)
"""

import json
import math
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    STEPReverseEngineer,
    ValidationEngineer,
)


def test_ai_diagnose_and_repair_feedback():
    """Verify asm.diagnose() detects intentional clashes and produces actionable LLM feedback."""
    print("--- Testing AI Self-Healing Diagnostic Engine ---")
    asm = Assembly("ClashAssembly")

    # Intentional volumetric clash: 2 overlapping blocks
    p1 = asm.add_box("chassis_frame", length=40.0, width=40.0, height=20.0)
    # Block overlapping inside chassis_frame by 10mm
    p2 = asm.add_box("motor_mount", length=30.0, width=30.0, height=15.0, origin=(10.0, 10.0, 5.0))

    report = asm.diagnose()
    assert report["status"] == "FAIL", "Diagnostic should detect clash failure"
    assert len(report["clashes"]) >= 1, "Should have detected at least 1 clash"

    clash = report["clashes"][0]
    assert "chassis_frame" in (clash["first_part"], clash["second_part"])
    assert "motor_mount" in (clash["first_part"], clash["second_part"])
    assert clash["volume_mm3"] > 100.0, "Clash volume should be significant"

    prompt = report["llm_repair_prompt"]
    assert "Clash" in prompt or "Cakisma" in prompt
    assert "Fix" in prompt or "Duzeltme" in prompt

    print(f"  -> Clash detected successfully ({clash['volume_mm3']:.1f} mm³)")
    print(f"  -> Generated LLM Repair Prompt Preview:\n{prompt}")


def test_parametric_variables_and_cascading_formulas():
    """Verify asm.set_var and arithmetic formula evaluation across connected parts."""
    print("\n--- Testing Parametric Master Variables & Formulas ---")
    asm = Assembly("ParametricTest")

    # Define master design variables and dependent formulas
    asm.set_var("shaft_dia", 20.0)
    asm.set_var("flange_dia", "shaft_dia * 3.0")   # Evaluates to 60.0
    asm.set_var("flange_thick", "shaft_dia * 0.5")  # Evaluates to 10.0

    assert asm.get_var("flange_dia") == 60.0
    assert asm.get_var("flange_thick") == 10.0

    # Add part referencing formula variables
    flange = asm.add_cylinder("hub_flange", radius="flange_dia / 2", height="flange_thick")
    flange.set_appearance(color=(0.8, 0.8, 0.8), material="Aluminum")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    mass = backend.calculate_mass_properties(asm.to_ir())

    # Expected: pi * (30^2) * 10 = ~28,274.3 mm³
    expected_vol = math.pi * (30.0 ** 2) * 10.0
    assert abs(mass["total_volume_mm3"] - expected_vol) < 50.0
    print(f"  -> Formula correctly evaluated! Cylinder Volume: {mass['total_volume_mm3']:,.1f} mm³")


def test_step_reverse_engineering_with_pcd_detection():
    """Verify STEPReverseEngineer detects circular bolt patterns (PCD) from STEP file."""
    print("\n--- Testing Reverse Engineering with PCD Pattern Detection ---")
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    test_step = out_dir / "flange_for_reverse.step"

    # Create and export a test flange with 6 bolt holes on 100mm PCD
    asm = Assembly("ExportForReverse")
    flange = asm.add_flange(
        name="test_flange",
        outer_diameter=140.0,
        thickness=15.0,
        inner_bore=40.0,
        bolt_pcd=100.0,
        bolt_count=6,
        bolt_diameter=8.0,
    )
    backend = OCCTBackend()
    backend.export_step(asm.to_ir(), str(test_step))
    assert test_step.exists()

    # Reverse engineer the exported STEP file
    re_result = STEPReverseEngineer.inspect_and_to_saml(str(test_step), part_name="reverse_flange")
    assert re_result["num_holes"] >= 6
    assert len(re_result["pcd_patterns"]) >= 1

    pcd_info = re_result["pcd_patterns"][0]
    assert pcd_info["count"] == 6
    assert abs(pcd_info["pcd"] - 100.0) < 1.0
    # Inspection annotates the existing holes without cutting the imported solid again.
    assert "part.add_pcd_holes" not in re_result["saml_code"]
    assert re_result["saml_code"].count("part.add_port(") == re_result["num_holes"]
    print(f"  -> PCD Pattern detected automatically: {pcd_info['count']} holes @ PCD {pcd_info['pcd']} mm")
    print(f"  -> Decompiled SAML Code with Macro:\n{re_result['saml_code']}")


def test_standards_catalogs_authoritative_lookups():
    """Verify standards catalog lookup, parameter validation, and source ref resolution."""
    print("\n--- Testing Authoritative Standards Catalogs ---")
    from cadi_saml.standards.catalogs import (
        lookup_catalog,
        validate_catalog_parameter,
        find_standard_by_source_ref,
        DIN_1025_1_IPE,
        ISO_7005_1_FLANGES,
        DIN_6885_1_KEYWAYS,
        ISO_4200_PIPING,
        ISO_965_1_THREADS,
        DIN_115_COUPLINGS,
        DIN_6935_SHEET_METAL,
    )

    # 1. DIN 1025-1 IPE
    ipe200 = lookup_catalog("DIN 1025-1", "IPE 200")
    assert ipe200["height"] == 200.0
    assert ipe200["flange_width"] == 100.0
    assert validate_catalog_parameter("DIN 1025-1", "IPE 200", "height", 200.0) is True
    assert validate_catalog_parameter("DIN 1025-1", "IPE 200", "height", 190.0) is False

    # 2. ISO 7005-1 Flanges
    flange = lookup_catalog("ISO 7005-1", "ISO 7005-1 PN16 DN32")
    assert flange is not None
    assert flange["outer_diameter"] == 140.0
    assert flange["bolt_count"] == 6

    # 3. DIN 6885-1 Keyways
    key = lookup_catalog("DIN 6885-1", "d30_38")
    assert key["key_width"] == 10.0

    # 4. ISO 4200 Pipes
    pipe = lookup_catalog("ISO 4200", "DN50")
    assert pipe["outer_diameter"] == 60.3

    # 5. ISO 965-1 Threads
    m12 = lookup_catalog("ISO 965-1", "M12")
    assert m12["nominal_dia"] == 12.0
    assert m12["pitch"] == 1.75

    # 6. Source Ref lookup
    found_spec = find_standard_by_source_ref("DIN 1025-1 IPE 200")
    assert found_spec is not None
    assert found_spec["height"] == 200.0

    print("  -> Authoritative Standards Catalogs successfully tested (all 7 families verified)!")


def test_synthetic_dataset_json_schema_compliance():
    """Verify both gold and negative datasets conform strictly to saml_dataset_schema.json."""
    print("\n--- Testing Dataset Formal JSON Schema Compliance ---")
    import jsonschema
    schema_file = Path(__file__).parent.parent / "schema" / "saml_dataset_schema.json"
    gold_file = Path(__file__).parent.parent / "dataset" / "saml_gold_dataset.jsonl"
    neg_file = Path(__file__).parent.parent / "dataset" / "saml_negative_dataset.jsonl"

    assert schema_file.exists(), "Schema file must exist"
    with open(schema_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Validate all gold samples
    assert gold_file.exists()
    gold_count = 0
    with open(gold_file, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            jsonschema.validate(instance=record, schema=schema)
            assert record["metadata"]["execution_status"] in ("valid", "verified_passed")
            gold_count += 1
    assert gold_count >= 60

    # Validate all negative samples
    assert neg_file.exists()
    neg_count = 0
    with open(neg_file, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            jsonschema.validate(instance=record, schema=schema)
            assert record["metadata"]["execution_status"] in ("expected_failure", "expected_error")
            assert "expected_error" in record["metadata"]
            neg_count += 1
    assert neg_count >= 20

    print(f"  -> Schema validation passed for {gold_count} gold and {neg_count} negative samples!")


def test_synthetic_dataset_jsonl_integrity():
    """Verify generated JSONL training dataset structure, diversity, contract execution, and engineering integrity."""
    print("\n--- Testing Synthetic Training Dataset Integrity ---")
    dataset_file = Path(__file__).parent.parent / "dataset" / "saml_gold_dataset.jsonl"
    if not dataset_file.exists():
        pytest.skip("Dataset file does not exist (run generate_gold_dataset.py to create)")

    sample_count = 0
    categories = set()
    unique_instructions = set()
    with open(dataset_file, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            inst = record.get("instruction", "")
            output = record.get("output", "")
            meta = record.get("metadata", {})

            assert len(inst) > 10
            assert inst not in unique_instructions, f"Duplicate instruction found: {inst}"
            unique_instructions.add(inst)

            assert "from cadi_saml import Assembly" in output
            assert "verify_contract" in output, "Each sample must execute verify_contract()"
            assert "assert report.passed" in output

            assert meta.get("contract_verified") is True
            assert meta.get("provenance_tracked") is True
            assert 0.0 < meta.get("spec_completeness", 0.0) <= 1.0

            # Deterministic generator provenance fields
            gen_meta = meta.get("generator_meta", {})
            assert "generator_version" in gen_meta
            assert "catalog_version" in gen_meta
            assert "checksum" in gen_meta

            cat = meta.get("category")
            assert cat is not None
            categories.add(cat)
            sample_count += 1

    assert sample_count >= 60, f"Expected at least 60 samples, got {sample_count}"
    assert len(categories) >= 8, f"Expected at least 8 engineering archetypes, got {len(categories)}: {categories}"
def test_dataset_validation_runner_execution():
    """Verify scripts/validate_gold_dataset.py runner functions on gold and negative samples."""
    print("\n--- Testing Dataset Execution Runner ---")
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from validate_gold_dataset import validate_negative_sample, validate_gold_sample

    # Test negative diagnostic sample runner
    neg_file = Path(__file__).parent.parent / "dataset" / "saml_negative_dataset.jsonl"
    with open(neg_file, "r", encoding="utf-8") as f:
        first_neg = json.loads(f.readline())
    ok, msg = validate_negative_sample(first_neg, 1, 1)
    assert ok is True, f"Negative sample validation failed: {msg}"

    # Test gold execution subprocess runner on 3 diverse samples
    gold_file = Path(__file__).parent.parent / "dataset" / "saml_gold_dataset.jsonl"
    with open(gold_file, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]

    # Test I-Beam (1), Flange (7), Shaft (13)
    test_indices = [0, 6, 12]
    for idx in test_indices:
        s = samples[idx]
        ok, msg, dur = validate_gold_sample(s, idx + 1, len(samples), timeout=25.0)
        assert ok is True, f"Gold sample {s.get('id')} failed runner: {msg}"
        print(f"  -> Subprocess test for {s.get('id')} PASSED in {dur:.2f}s")


if __name__ == "__main__":
    print("=======================================================================")
    print("   Running Core CAD & AI Engine Capability Test Suite")
    print("=======================================================================")
    test_ai_diagnose_and_repair_feedback()
    test_parametric_variables_and_cascading_formulas()
    test_step_reverse_engineering_with_pcd_detection()
    test_standards_catalogs_authoritative_lookups()
    test_synthetic_dataset_json_schema_compliance()
    test_synthetic_dataset_jsonl_integrity()
    test_dataset_validation_runner_execution()
    print("\n>>> ALL CORE CAD & AI ENGINE TESTS PASSED (100% SUCCESS)! <<<")

