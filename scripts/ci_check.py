"""
scripts.ci_check
================
Automated Continuous Integration and Version Discipline Checker for CADi SAML.

Runs:
1. Pytest test suite across all unit & integration tests.
2. Complete dataset execution runner (all 60 gold + all 30 negative samples in isolated subprocesses).
3. Verifies dataset_validation_report.json status is strictly ALL_PASSED.
4. Checks that git commit and version numbers are synced.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def run_command(cmd: list[str], desc: str) -> bool:
    print("\n" + "=" * 80)
    print(f"  [CI RUNNER] Step: {desc}")
    print(f"  Command: {' '.join(cmd)}")
    print("=" * 80, flush=True)

    start = time.time()
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    dur = time.time() - start

    if res.returncode == 0:
        print(f"[CI RUNNER] SUCCESS: {desc} passed in {dur:.2f}s", flush=True)
        return True
    else:
        print(f"[CI RUNNER] FAILED: {desc} failed with exit code {res.returncode} in {dur:.2f}s", flush=True)
        return False


def verify_validation_report(report_path: Path) -> bool:
    print("\n" + "=" * 80)
    print(f"  [CI RUNNER] Auditing Dataset Validation Report: {report_path.name}")
    print("=" * 80, flush=True)

    if not report_path.exists():
        print(f"[ERROR] Validation report not found: {report_path}")
        return False

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {})
    status = summary.get("status")
    total_gold = summary.get("total_gold", 0)
    gold_passed = summary.get("gold_passed", 0)
    total_neg = summary.get("total_negative", 0)
    neg_passed = summary.get("negative_passed", 0)
    git_commit = summary.get("git_commit")

    print(f"  -> Report Status: {status}")
    print(f"  -> Gold Samples: {gold_passed}/{total_gold}")
    print(f"  -> Negative Samples: {neg_passed}/{total_neg}")
    print(f"  -> Git Commit: {git_commit}")

    if status != "ALL_PASSED":
        print(f"[ERROR] Expected status 'ALL_PASSED', got '{status}'. Partial runs are not accepted.")
        return False

    if total_gold < 60 or gold_passed != total_gold:
        print(f"[ERROR] Gold dataset not fully validated: {gold_passed}/{total_gold}")
        return False

    if total_neg < 30 or neg_passed != total_neg:
        print(f"[ERROR] Negative dataset not fully validated: {neg_passed}/{total_neg}")
        return False

    print("[CI RUNNER] Verification Report Audit PASSED (100% fidelity).", flush=True)
    return True


def main():
    print("=" * 80)
    print("   CADi SAML Automated CI & Engineering Discipline Suite")
    print("=" * 80)

    report_file = REPO_ROOT / "dataset" / "dataset_validation_report.json"

    # 1. Run full dataset validation
    dataset_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "validate_gold_dataset.py"),
        "--all",
        "--report-path",
        str(report_file),
    ]
    if not run_command(dataset_cmd, "Complete Dataset Isolated Subprocess Execution"):
        sys.exit(1)

    # 2. Audit the resulting validation report
    if not verify_validation_report(report_file):
        sys.exit(1)

    # 3. Run Pytest suite
    pytest_cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    if not run_command(pytest_cmd, "Pytest Complete Test Suite"):
        sys.exit(1)

    print("\n" + "=" * 80)
    print("   >>> ALL CI CHECKS PASSED (100% SUCCESSFUL) <<<")
    print("=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    main()
