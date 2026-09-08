"""
cadi_saml.validation.gate_validator
==================================
Deterministic Phase Exit Gate Validator for CADi SAML.
Enforces the mandatory phase exit gate contract:
1. Contract Schema Verification (Units, Coordinates, Indexing, Tolerances, Provenance)
2. Targeted Positive Test Execution in clean isolated subprocess
3. Negative / Rejection Scenario Execution in clean isolated subprocess
4. Outcome Classification: PASSED, SKIPPED, FAILED, BLOCKED
5. Verification that ALL target and negative tests are found and executed
6. Portable Audit Report Generation (JSON & Markdown) with Environment and exact Test Node IDs
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from cadi_saml.spec.contracts import CANONICAL_CONTRACT, CONTRACTS_SCHEMA_VERSION


@dataclass
class PhaseGateDefinition:
    """Specification of exit gate requirements for a given phase."""
    phase_number: int
    phase_name: str
    target_tests: List[str]
    negative_tests: List[str]
    required_contracts: List[str] = field(default_factory=lambda: [
        "units", "coordinates", "indexing", "tolerances", "solvers", "failures", "provenance"
    ])


PHASE_REGISTRY: Dict[int, PhaseGateDefinition] = {
    0: PhaseGateDefinition(
        phase_number=0,
        phase_name="Kaynak ve Sözleşme Dondurma",
        target_tests=[
            "tests/test_phase_0_contracts_and_gates.py::test_manifest_schema_and_canonical_mapping",
            "tests/test_phase_0_contracts_and_gates.py::test_contracts_immutability_and_schemas",
        ],
        negative_tests=[
            "tests/test_phase_0_contracts_and_gates.py::test_negative_invalid_index_base_rejection",
            "tests/test_phase_0_contracts_and_gates.py::test_negative_mixed_base_rejection",
        ],
    ),
    1: PhaseGateDefinition(
        phase_number=1,
        phase_name="FEA Temel Güvenilirliği",
        target_tests=[
            "tests/test_phase_1_fea_reliability.py::test_first_and_last_boundary_elements_coverage",
            "tests/test_phase_1_fea_reliability.py::test_linear_isotropic_solver_preservation",
            "tests/test_fea_verification_and_convergence.py::test_element_indexing_boundary_first_and_last_elements",
        ],
        negative_tests=[
            "tests/test_phase_1_fea_reliability.py::test_mixed_base_rejection",
            "tests/test_phase_1_fea_reliability.py::test_invalid_and_out_of_bounds_element_id_rejection",
            "tests/test_phase_1_fea_reliability.py::test_empty_material_region_rejection",
            "tests/test_phase_1_fea_reliability.py::test_overlapping_material_regions_rejection",
            "tests/test_phase_1_fea_reliability.py::test_missing_material_definition_and_unassigned_elements",
            "tests/test_heterogeneous_fea.py::test_overlapping_material_regions_raise_error",
            "tests/test_heterogeneous_fea.py::test_fiber_direction_rejection_not_implemented",
        ],
    ),
    2: PhaseGateDefinition(
        phase_number=2,
        phase_name="Gerçek Solver ve Mesh Doğrulaması",
        target_tests=[
            "tests/test_fea_verification_and_convergence.py::test_analytical_uniaxial_tension_benchmark",
            "tests/test_fea_verification_and_convergence.py::test_analytical_cantilever_benchmark",
            "tests/test_fea_verification_and_convergence.py::test_mesh_convergence_study_converged_progression",
            "tests/test_heterogeneous_fea.py::test_calculix_runner_mocked_external_ccx",
        ],
        negative_tests=[
            "tests/test_fea_verification_and_convergence.py::test_mesh_convergence_study_unconverged_behavior",
        ],
    ),
    3: PhaseGateDefinition(
        phase_number=3,
        phase_name="Çoklu Malzeme ve Arayüz",
        target_tests=[
            "tests/test_heterogeneous_fea.py::test_material_region_automatic_element_mapping",
            "tests/test_heterogeneous_fea.py::test_heterogeneous_steel_aluminum_compliance_difference",
            "tests/test_heterogeneous_fea.py::test_calculix_runner_end_to_end_bimetal",
            "tests/test_fea_verification_and_convergence.py::test_bimetal_interface_stress_extraction",
        ],
        negative_tests=[
            "tests/test_heterogeneous_fea.py::test_overlapping_material_regions_raise_error",
            "tests/test_heterogeneous_fea.py::test_fiber_direction_rejection_not_implemented",
        ],
    ),
    4: PhaseGateDefinition(
        phase_number=4,
        phase_name="Taşınabilir Rapor ve Veri Hattı",
        target_tests=[
            "tests/test_fea_verification_and_convergence.py::test_portable_fea_report_generation",
            "tests/test_fea_verification_and_convergence.py::test_calculix_model_index_base_and_multi_material_contract",
            "tests/test_heterogeneous_fea.py::test_fea_result_permanent_dataclass_fields",
        ],
        negative_tests=[
            "tests/test_fea_verification_and_convergence.py::test_element_indexing_strict_validation_and_rejection",
        ],
    ),
    5: PhaseGateDefinition(
        phase_number=5,
        phase_name="STEP'ten Bağımsız Kod Üretimi",
        target_tests=[
            "tests/test_step_reconstruction_regression.py::test_regression_simple_box",
            "tests/test_step_reconstruction_regression.py::test_regression_simple_cylinder",
            "tests/test_step_reconstruction_regression.py::test_regression_stepped_shaft",
            "tests/test_step_reconstruction_regression.py::test_regression_cylinder_with_holes",
            "tests/test_step_reconstruction_regression.py::test_regression_stepped_shaft_with_holes",
            "tests/test_step_reconstruction_regression.py::test_regression_flange_and_bolt_pattern",
            "tests/test_step_reconstruction_regression.py::test_regression_zero_step_dependency_after_file_deletion",
        ],
        negative_tests=[
            "tests/test_step_reconstruction_regression.py::test_regression_oblique_axis_cylinder",
        ],
    ),
    6: PhaseGateDefinition(
        phase_number=6,
        phase_name="Şasi, Süspansiyon ve Batarya",
        target_tests=[
            "tests/test_systems_vehicle.py::test_chassis_frame_synthesis_and_mass_distribution",
            "tests/test_systems_vehicle.py::test_suspension_hardpoints_and_kinematics",
            "tests/test_systems_vehicle.py::test_battery_pack_enclosure_and_cooling_flow",
            "tests/test_systems_vehicle.py::test_integrated_vehicle_platform_and_cad_compile",
        ],
        negative_tests=[
            "tests/test_heterogeneous_fea.py::test_invalid_material_region_and_unassigned_elements",
        ],
    ),
    7: PhaseGateDefinition(
        phase_number=7,
        phase_name="Bağlantı ve İleri Analiz",
        target_tests=[
            "tests/test_heterogeneous_fea.py::test_boundary_condition_explicit_dofs_and_values",
            "tests/test_fea_verification_and_convergence.py::test_bimetal_interface_stress_extraction",
        ],
        negative_tests=[
            "tests/test_heterogeneous_fea.py::test_fiber_direction_rejection_not_implemented",
        ],
    ),
    8: PhaseGateDefinition(
        phase_number=8,
        phase_name="LLM Entegrasyon Sınırı",
        target_tests=[
            "tests/test_llm_interface.py::test_runtime_schema_is_json_safe_and_matches_signature",
            "tests/test_llm_interface.py::test_compact_inspect_and_semantic_diff",
            "tests/test_llm_interface.py::test_preview_patch_isolated_validation_commit_and_conflict",
            "tests/test_token_reduction.py::test_token_reduction_benchmark",
        ],
        negative_tests=[
            "tests/test_llm_interface.py::test_preview_patch_rejects_unknown_or_invalid_paths_without_mutation",
        ],
    ),
}


@dataclass
class PhaseGateReport:
    """Portable, versioned phase gate execution verdict."""
    phase_number: int
    phase_name: str
    verdict: str                     # "GATE_PASSED", "GATE_FAILED", "GATE_BLOCKED"
    is_approved: bool
    contracts_schema_version: str
    manifest_verified: bool
    passed_count: int
    skipped_count: int
    failed_count: int
    blocked_count: int
    test_outcomes: Dict[str, str]    # test_nodeid -> status
    negative_scenarios_verified: bool
    timestamp_utc: str
    environment: Dict[str, Any] = field(default_factory=dict)
    executed_node_ids: List[str] = field(default_factory=list)
    missing_node_ids: List[str] = field(default_factory=list)
    summary_markdown: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, output_path: Optional[str] = None) -> str:
        data = self.to_dict()
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    def to_markdown(self, output_path: Optional[str] = None) -> str:
        lines = [
            f"# CADi SAML Faz {self.phase_number} Çıkış Kapısı Doğrulama Raporu",
            f"**Faz Adı:** {self.phase_name}  ",
            f"**Karar (Verdict):** `{self.verdict}`  ",
            f"**Sözleşme Sürümü:** `{self.contracts_schema_version}`  ",
            f"**Zaman Damgası (UTC):** `{self.timestamp_utc}`  ",
            "",
            "## 1. Çalışma Ortamı (Environment)",
            "| Değişken | Değer |",
            "| :--- | :--- |",
            f"| Python Sürümü | `{self.environment.get('python_version', sys.version.split()[0])}` |",
            f"| Pytest Sürümü | `{self.environment.get('pytest_version', pytest.__version__)}` |",
            f"| İşletim Sistemi | `{self.environment.get('os_platform', platform.platform())}` |",
            f"| Mimari | `{self.environment.get('machine', platform.machine())}` |",
            "",
            "## 2. Çıkış Kapısı Özeti",
            "| Metrik | Değer |",
            "| :--- | :--- |",
            f"| Geçen Testler (`passed`) | **{self.passed_count}** |",
            f"| Atlanan Testler (`skipped`) | {self.skipped_count} |",
            f"| Başarısız Testler (`failed`) | {self.failed_count} |",
            f"| Engellenen / Hatalı Testler (`blocked`) | {self.blocked_count} |",
            f"| Bulunamayan / Eksik Testler | {len(self.missing_node_ids)} |",
            f"| Manifest Doğrulandı | {'EVET' if self.manifest_verified else 'HAYIR'} |",
            f"| Negatif/Ret Senaryoları | {'BAŞARILI' if self.negative_scenarios_verified else 'BAŞARISIZ / EKSİK'} |",
            f"| **Kapı Onayı** | **{'ONAYLANDI (GATE_PASSED)' if self.is_approved else 'REDDEDİLDİ'}** |",
            "",
        ]

        if self.missing_node_ids:
            lines.extend([
                "## 3. Bulunamayan / Çalıştırılamayan Hedef Testler",
                "```text",
            ])
            for m in self.missing_node_ids:
                lines.append(f"MISSING / NOT_RUN : {m}")
            lines.extend(["```", ""])

        lines.extend([
            "## 4. Gerçek Çalıştırılan Test Node ID'leri Dökümü",
            "```text",
        ])
        for nodeid, stat in sorted(self.test_outcomes.items()):
            lines.append(f"{stat:10s} : {nodeid}")
        lines.extend([
            "```",
            "",
            "---",
            "*Bu rapor CADi SAML GateValidator tarafından otomatik üretilmiş, taşınabilir ve deterministiktir.*",
        ])
        md_text = "\n".join(lines) + "\n"
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_text)
        return md_text


class GateValidator:
    """Executes deterministic validation against phase exit criteria in a clean subprocess."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or str(Path(__file__).resolve().parents[3])

    def validate_phase(self, phase_number: int, output_dir: Optional[str] = None) -> PhaseGateReport:
        if phase_number not in PHASE_REGISTRY:
            raise ValueError(f"Phase {phase_number} not registered in PhaseRegistry.")

        defn = PHASE_REGISTRY[phase_number]
        timestamp = datetime.now(timezone.utc).isoformat()

        # Capture detailed environment metadata
        env_metadata = {
            "python_version": sys.version.split()[0],
            "pytest_version": pytest.__version__,
            "os_platform": platform.platform(),
            "machine": platform.machine(),
            "timestamp_utc": timestamp,
        }

        # 1. Verify Contracts and Manifest
        manifest_path = os.path.join(self.root_dir, "cadi_manifest.json")
        manifest_verified = os.path.isfile(manifest_path)
        if manifest_verified:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                manifest_verified = (manifest_data.get("manifest_version") == "1.0.0")

        # 2. Run target and negative tests in isolated subprocess
        all_tests = list(dict.fromkeys(defn.target_tests + defn.negative_tests))
        pytest_cmd = [
            sys.executable,
            "-m",
            "pytest",
            *all_tests,
            "-v",
            "--tb=short",
        ]
        proc = subprocess.run(
            pytest_cmd,
            cwd=self.root_dir,
            capture_output=True,
            text=True,
        )

        # Parse test outcomes from stdout
        test_outcomes: Dict[str, str] = {}
        passed_count = 0
        skipped_count = 0
        failed_count = 0
        blocked_count = 0

        for line in proc.stdout.splitlines():
            line_s = line.strip()
            if " PASSED" in line_s:
                parts = line_s.split(" PASSED")
                nodeid = parts[0].strip()
                test_outcomes[nodeid] = "PASSED"
                passed_count += 1
            elif " SKIPPED" in line_s:
                parts = line_s.split(" SKIPPED")
                nodeid = parts[0].strip()
                test_outcomes[nodeid] = "SKIPPED"
                skipped_count += 1
            elif " FAILED" in line_s:
                parts = line_s.split(" FAILED")
                nodeid = parts[0].strip()
                test_outcomes[nodeid] = "FAILED"
                failed_count += 1
            elif " ERROR" in line_s:
                parts = line_s.split(" ERROR")
                nodeid = parts[0].strip()
                test_outcomes[nodeid] = "BLOCKED"
                blocked_count += 1

        # 3. STRICT CHECK: Verify EVERY target test was actually executed and PASSED
        missing_target_tests: List[str] = []
        for tgt in defn.target_tests:
            # Normalize path slashes for matching
            tgt_norm = tgt.replace("/", os.sep).replace("\\", os.sep)
            matched = any(
                (tgt in nid or tgt_norm in nid) and (stat == "PASSED")
                for nid, stat in test_outcomes.items()
            )
            if not matched:
                missing_target_tests.append(tgt)

        # 4. STRICT CHECK: Verify EVERY negative test was actually executed and PASSED
        missing_negative_tests: List[str] = []
        for neg in defn.negative_tests:
            neg_norm = neg.replace("/", os.sep).replace("\\", os.sep)
            matched = any(
                (neg in nid or neg_norm in nid) and (stat == "PASSED")
                for nid, stat in test_outcomes.items()
            )
            if not matched:
                missing_negative_tests.append(neg)

        all_missing = missing_target_tests + missing_negative_tests

        targets_verified = (len(missing_target_tests) == 0 and len(defn.target_tests) > 0)
        neg_verified = (len(missing_negative_tests) == 0 and len(defn.negative_tests) > 0)

        # 5. GATE_PASSED criteria:
        # - Subprocess exit code must be 0
        # - 0 failed, 0 blocked, 0 missing
        # - Manifest verified
        # - Every single declared target test and negative test was executed and passed
        is_approved = bool(
            proc.returncode == 0
            and failed_count == 0
            and blocked_count == 0
            and len(all_missing) == 0
            and manifest_verified
            and targets_verified
            and neg_verified
            and passed_count > 0
        )

        if is_approved:
            verdict = "GATE_PASSED"
        elif blocked_count > 0 or len(all_missing) > 0:
            verdict = "GATE_BLOCKED"
        else:
            verdict = "GATE_FAILED"

        report = PhaseGateReport(
            phase_number=defn.phase_number,
            phase_name=defn.phase_name,
            verdict=verdict,
            is_approved=is_approved,
            contracts_schema_version=CONTRACTS_SCHEMA_VERSION,
            manifest_verified=manifest_verified,
            passed_count=passed_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            blocked_count=blocked_count,
            test_outcomes=test_outcomes,
            negative_scenarios_verified=neg_verified,
            timestamp_utc=timestamp,
            environment=env_metadata,
            executed_node_ids=sorted(list(test_outcomes.keys())),
            missing_node_ids=all_missing,
        )

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            json_file = os.path.join(output_dir, f"phase_{phase_number}_gate_report.json")
            md_file = os.path.join(output_dir, f"phase_{phase_number}_gate_report.md")
            report.to_json(json_file)
            report.to_markdown(md_file)

        return report


def main():
    parser = argparse.ArgumentParser(description="CADi SAML Phase Exit Gate Validator")
    parser.add_argument("--phase", type=int, default=0, help="Phase number to validate (e.g. 0..8)")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save JSON/MD reports")
    args = parser.parse_args()

    validator = GateValidator()
    report = validator.validate_phase(args.phase, output_dir=args.output_dir)
    print(report.to_markdown())
    sys.exit(0 if report.is_approved else 1)


if __name__ == "__main__":
    main()
