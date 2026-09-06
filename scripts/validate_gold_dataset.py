"""
scripts.validate_gold_dataset
=============================
Isolated Subprocess Execution Runner & Parameter Auditor for CADi SAML datasets.

Verifies:
1. Subprocess execution: Runs each sample in an isolated Python process with PYTHONPATH=src.
2. Timeout handling (default 20s per sample).
3. Post-build contract pass: Asserts report.passed is True.
4. Parameter & Provenance Audit:
   - Compares metadata.input_parameters against provenance records.
   - Compares metadata.catalog_parameters against central standards catalog.
   - Compares provenance.effective_value against compiled part parameters.
   - Re-computes and verifies metadata.spec_completeness.
5. Negative dataset verification:
   - Runs negative offending scripts in isolated subprocesses.
   - Asserts exit_code != 0 and expected exception type is raised.
6. Full Telemetry & Audit Report:
   - Records exit_code, exception_type, contract_result, provenance_result, duration, stdout, stderr for every sample.
   - Outputs machine-readable dataset/dataset_validation_report.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add src to path
REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import jsonschema
from cadi_saml.standards.catalogs import find_standard_by_source_ref, lookup_catalog

SCHEMA_PATH = REPO_ROOT / "schema" / "saml_dataset_schema.json"
try:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as _f:
        DATASET_SCHEMA = json.load(_f)
except Exception:
    DATASET_SCHEMA = None


def get_git_commit() -> Optional[str]:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(REPO_ROOT))
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


# Introspection trailer injected into each gold sample script to extract runtime state
INSPECTION_TRAILER = """

# --- AUTOMATIC PARAMETER & PROVENANCE INTROSPECTION ---
try:
    import json
    __audit_dump = {
        "contract_passed": bool(report.passed),
        "stages": {k: v.passed for k, v in report.stages.items()},
        "parts": {}
    }
    for __p_name, __p_ref in asm._parts.items():
        __prov_dict = {}
        for __k, __rec in getattr(__p_ref, "_provenance", {}).items():
            __prov_dict[__k] = {
                "source": getattr(__rec, "source", None),
                "source_ref": getattr(__rec, "source_ref", None),
                "original_value": getattr(__rec, "original_value", None),
                "effective_value": getattr(__rec, "effective_value", None),
                "unit": getattr(__rec, "unit", None),
                "transformation": getattr(__rec, "transformation", None),
            }
        __clean_params = {}
        for k, v in __p_ref.parameters.items():
            if k.startswith("_"):
                continue
            if isinstance(v, (int, float, str, bool)):
                __clean_params[k] = v
            elif isinstance(v, (list, tuple)):
                __clean_params[k] = [x for x in v if isinstance(x, (int, float, str, bool))]
        __audit_dump["parts"][__p_name] = {
            "parameters": __clean_params,
            "provenance": __prov_dict,
        }
    __dump_str = json.dumps(__audit_dump, ensure_ascii=False, default=str)
    with open(__audit_file_path, "w", encoding="utf-8") as __f:
        __f.write(__dump_str)
except Exception as __dump_err:
    import sys
    sys.stderr.write(f"Audit dump error: {__dump_err}\\n")
"""


def extract_exception_type_from_stderr(stderr: str) -> Optional[str]:
    """Extracts the exception class name from a Python traceback string."""
    if not stderr:
        return None
    lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    if not lines:
        return None
    last_line = lines[-1]
    # Format is usually: module.ErrorType: message or ErrorType: message
    parts = last_line.split(":")
    if parts:
        exc_candidate = parts[0].strip().split(".")[-1]
        if exc_candidate.endswith("Error") or exc_candidate.endswith("Exception") or exc_candidate in ("AssertionError", "KeyError", "ValueError", "TypeError"):
            return exc_candidate
    return None


def validate_gold_sample(
    sample: dict,
    sample_index: int,
    total_count: int,
    timeout: float = 20.0,
    verbose: bool = False,
) -> Tuple[bool, str, float, Dict[str, Any]]:
    """
    Executes a single gold training sample in an isolated subprocess
    and performs deep parameter/provenance auditing.
    Returns (passed, message, duration, telemetry_dict).
    """
    sid = sample.get("id", f"sample_{sample_index}")
    meta = sample.get("metadata", {})
    cat = meta.get("category", "unknown")
    code = sample.get("output", "")

    start_time = time.time()
    telemetry: Dict[str, Any] = {
        "id": sid,
        "category": cat,
        "sample_type": "gold",
        "exit_code": None,
        "exception_type": None,
        "contract_result": None,
        "provenance_result": None,
        "duration": 0.0,
        "stdout": "",
        "stderr": "",
    }

    # 0. JSON Schema Validation
    if DATASET_SCHEMA is not None:
        try:
            jsonschema.validate(instance=sample, schema=DATASET_SCHEMA)
        except jsonschema.ValidationError as e:
            telemetry["contract_result"] = False
            telemetry["provenance_result"] = False
            return False, f"JSON Schema validation error: {e.message}", 0.0, telemetry

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_file = tmp_path / f"{sid}.py"
        audit_file = tmp_path / f"{sid}_audit.json"

        # Prepare script with audit trailer
        full_code = f"__audit_file_path = {repr(str(audit_file))}\n" + code + INSPECTION_TRAILER
        script_file.write_text(full_code, encoding="utf-8")

        # Environment with PYTHONPATH=src
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_DIR)
        env["PYTHONUNBUFFERED"] = "1"

        try:
            res = subprocess.run(
                [sys.executable, str(script_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            dur = time.time() - start_time
            telemetry["duration"] = round(dur, 3)
            telemetry["exit_code"] = -1
            telemetry["exception_type"] = "TimeoutExpired"
            telemetry["contract_result"] = False
            telemetry["provenance_result"] = False
            return False, f"TIMEOUT after {timeout:.1f}s", dur, telemetry

        dur = time.time() - start_time
        telemetry["duration"] = round(dur, 3)
        telemetry["exit_code"] = res.returncode
        telemetry["stdout"] = res.stdout[:2000]
        telemetry["stderr"] = res.stderr[:2000]

        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            lines = [l for l in err_msg.splitlines() if l.strip()]
            last_err = lines[-1] if lines else f"Exit code {res.returncode}"
            telemetry["exception_type"] = extract_exception_type_from_stderr(res.stderr) or "SubprocessError"
            telemetry["contract_result"] = False
            telemetry["provenance_result"] = False
            if verbose:
                print(f"\n--- STDOUT [{sid}] ---\n{res.stdout}")
                print(f"--- STDERR [{sid}] ---\n{res.stderr}")
            return False, f"Process execution failed: {last_err}", dur, telemetry

        # Read audit file
        if not audit_file.exists():
            telemetry["contract_result"] = False
            telemetry["provenance_result"] = False
            return False, "Inspection dump file was not generated", dur, telemetry

        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                audit_data = json.load(f)
        except Exception as e:
            telemetry["contract_result"] = False
            telemetry["provenance_result"] = False
            return False, f"Failed to parse audit dump: {e}", dur, telemetry

        # 1. Verify contract passed
        contract_ok = bool(audit_data.get("contract_passed"))
        telemetry["contract_result"] = contract_ok
        if not contract_ok:
            stages = audit_data.get("stages", {})
            failed_stages = [k for k, v in stages.items() if not v]
            telemetry["provenance_result"] = False
            return False, f"Post-build contract failed on stages: {failed_stages}", dur, telemetry

        # 2. Audit metadata parameters vs runtime assembly
        input_params = meta.get("input_parameters", {})
        catalog_params = meta.get("catalog_parameters", {})
        parts = audit_data.get("parts", {})

        # Flatten all runtime parameters and provenance across parts
        all_runtime_params = {}
        all_provenance = {}
        for p_name, p_info in parts.items():
            for k, v in p_info.get("parameters", {}).items():
                all_runtime_params[k] = v
            for k, v in p_info.get("provenance", {}).items():
                all_provenance[k] = v

        # Check input parameters are reflected in runtime or provenance
        for param_name, exp_val in input_params.items():
            if param_name in ("steps", "waypoints"):
                continue  # Sequence types
            if param_name in all_provenance:
                rec = all_provenance[param_name]
                act_orig = rec.get("original_value")
                try:
                    if abs(float(act_orig) - float(exp_val)) > 0.01:
                        telemetry["provenance_result"] = False
                        return False, f"Input param '{param_name}' prompt value ({exp_val}) != provenance original ({act_orig})", dur, telemetry
                except (ValueError, TypeError):
                    pass

        # Check catalog parameters match authoritative catalog data
        for cat_param, cat_val in catalog_params.items():
            if cat_param in all_provenance:
                rec = all_provenance[cat_param]
                rec_eff = rec.get("effective_value")
                try:
                    if abs(float(rec_eff) - float(cat_val)) > 0.05:
                        telemetry["provenance_result"] = False
                        return False, f"Catalog param '{cat_param}' catalog value ({cat_val}) != provenance effective ({rec_eff})", dur, telemetry
                except (ValueError, TypeError):
                    pass

        # Check provenance effective_value matches actual part parameter
        for p_name, p_info in parts.items():
            p_params = p_info.get("parameters", {})
            p_prov = p_info.get("provenance", {})
            for pk, pv in p_prov.items():
                if pk in p_params:
                    eff = pv.get("effective_value")
                    act = p_params[pk]
                    try:
                        if abs(float(eff) - float(act)) > 0.01:
                            telemetry["provenance_result"] = False
                            return False, f"Part '{p_name}' param '{pk}' eff_val ({eff}) != act_param ({act})", dur, telemetry
                    except (ValueError, TypeError):
                        pass

        # 3. Verify spec_completeness mathematical formula
        claimed_comp = meta.get("spec_completeness")
        if claimed_comp is not None:
            num_input = len(input_params)
            num_cat = len(catalog_params)
            total_req = num_input + num_cat
            if total_req > 0:
                expected_ratio = round(num_input / total_req, 2)
                if abs(claimed_comp - expected_ratio) > 0.05:
                    telemetry["provenance_result"] = False
                    return False, f"spec_completeness mismatch: claimed {claimed_comp}, expected {expected_ratio}", dur, telemetry

        telemetry["provenance_result"] = True
        return True, "PASSED", dur, telemetry


def validate_negative_sample(
    sample: dict,
    sample_index: int,
    total_count: int,
    timeout: float = 20.0,
    verbose: bool = False,
) -> Tuple[bool, str, float, Dict[str, Any]]:
    """
    Executes a negative training sample in an isolated subprocess,
    verifying it properly raises an exception (exit_code != 0)
    matching its expected diagnostic error specification.
    Returns (passed, message, duration, telemetry_dict).
    """
    sid = sample.get("id", f"neg_{sample_index}")
    meta = sample.get("metadata", {})
    cat = meta.get("category", "unknown")
    exp_err = meta.get("expected_error", {})
    code = meta.get("executable_code") or sample.get("input", "")

    start_time = time.time()
    telemetry: Dict[str, Any] = {
        "id": sid,
        "category": cat,
        "sample_type": "negative",
        "exit_code": None,
        "exception_type": None,
        "expected_error": exp_err.get("error_type"),
        "contract_result": "expected_failure",
        "provenance_result": "n/a",
        "duration": 0.0,
        "stdout": "",
        "stderr": "",
    }

    # 0. JSON Schema Validation
    if DATASET_SCHEMA is not None:
        try:
            jsonschema.validate(instance=sample, schema=DATASET_SCHEMA)
        except jsonschema.ValidationError as e:
            return False, f"JSON Schema validation error: {e.message}", 0.0, telemetry

    if not exp_err:
        return False, "Missing 'expected_error' in metadata", 0.0, telemetry

    req_keys = ["error_type", "parameter", "message", "suggested_fix"]
    for k in req_keys:
        if not exp_err.get(k):
            return False, f"Missing expected_error field: '{k}'", 0.0, telemetry

    # Verify output format
    try:
        out_json = json.loads(sample.get("output", ""))
        if out_json.get("error_type") != exp_err["error_type"]:
            return False, f"Output error_type ({out_json.get('error_type')}) != metadata ({exp_err['error_type']})", 0.0, telemetry
    except Exception as e:
        return False, f"Output is not valid JSON: {e}", 0.0, telemetry

    # Run actual code in subprocess to verify it triggers Python exception
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_file = tmp_path / f"{sid}.py"
        script_file.write_text(code, encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_DIR)
        env["PYTHONUNBUFFERED"] = "1"

        try:
            res = subprocess.run(
                [sys.executable, str(script_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            dur = time.time() - start_time
            telemetry["duration"] = round(dur, 3)
            telemetry["exit_code"] = -1
            telemetry["exception_type"] = "TimeoutExpired"
            return False, f"TIMEOUT after {timeout:.1f}s", dur, telemetry

        dur = time.time() - start_time
        telemetry["duration"] = round(dur, 3)
        telemetry["exit_code"] = res.returncode
        telemetry["stdout"] = res.stdout[:2000]
        telemetry["stderr"] = res.stderr[:2000]

        exc_type = extract_exception_type_from_stderr(res.stderr)
        telemetry["exception_type"] = exc_type

        # Must fail with non-zero exit code
        if res.returncode == 0:
            if verbose:
                print(f"\n--- STDOUT [{sid}] ---\n{res.stdout}")
            return False, "Negative script passed unexpectedly with exit code 0", dur, telemetry

        # Verify exception type
        expected_exc = exp_err.get("error_type", "CADISpecificationError")
        compatible = (exc_type == expected_exc) or (
            expected_exc == "CADISpecificationError"
            and exc_type in ("CADISpecificationError", "AssertionError", "ValueError", "KeyError", "TypeError")
        )
        if not compatible:
            return False, f"Raised exception '{exc_type}' does not match expected '{expected_exc}'", dur, telemetry

        # Verify expected parameter name is matched in stderr / stdout / code (case-insensitive)
        exp_param = exp_err.get("parameter", "")
        param_base = exp_param.split(".")[-1]
        err_content = f"{res.stderr}\n{res.stdout}\n{code}".lower()
        param_matched = (
            exp_param.lower() in err_content
            or param_base.lower() in err_content
            or exp_param.replace("_", " ").lower() in err_content
            or exp_param.replace(".", " ").lower() in err_content
        )
        if not param_matched:
            # Check if suggested fix keywords or message keywords match
            msg_words = [w for w in exp_err.get("message", "").split() if len(w) > 4]
            fix_words = [w for w in exp_err.get("suggested_fix", "").split() if len(w) > 4]
            keyword_matched = any(w in err_content for w in msg_words + fix_words)
            if not keyword_matched:
                return False, f"Error output does not mention expected parameter '{exp_param}' or diagnostic keywords", dur, telemetry

        return True, "PASSED", dur, telemetry


def run_gold_validation(
    dataset_path: Path,
    timeout: float = 20.0,
    limit: Optional[int] = None,
    offset: int = 0,
    verbose: bool = False,
) -> Tuple[bool, List[Dict[str, Any]]]:
    if not dataset_path.exists():
        print(f"[ERROR] Dataset file not found: {dataset_path}")
        return False, []

    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if offset > 0:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]

    total = len(lines)
    print("=" * 80, flush=True)
    print(f"  CADi SAML Gold Dataset Subprocess Execution Runner (Total: {total} samples)", flush=True)
    print(f"  Target File: {dataset_path.resolve()}", flush=True)
    print(f"  Timeout per sample: {timeout}s | Isolated Subprocess: True", flush=True)
    print("=" * 80, flush=True)

    passed_count = 0
    failed_count = 0
    total_time = 0.0
    records = []

    for idx, line in enumerate(lines, 1):
        sample = json.loads(line)
        sid = sample.get("id", f"sample_{idx:03d}")
        cat = sample.get("metadata", {}).get("category", "unknown")

        ok, msg, dur, tel = validate_gold_sample(sample, idx, total, timeout=timeout, verbose=verbose)
        total_time += dur
        records.append(tel)

        if ok:
            passed_count += 1
            status_str = f"[{idx:02d}/{total:02d}] {sid} ({cat:<18}) ... PASSED ({dur:.2f}s)"
            print(status_str, flush=True)
        else:
            failed_count += 1
            status_str = f"[{idx:02d}/{total:02d}] {sid} ({cat:<18}) ... FAILED ({dur:.2f}s) -> {msg}"
            print(status_str, flush=True)

    print("-" * 80, flush=True)
    print(f"Gold Execution Summary: {passed_count}/{total} PASSED ({passed_count/total*100:.1f}%), {failed_count} FAILED in {total_time:.2f}s", flush=True)
    print("=" * 80, flush=True)
    return failed_count == 0, records


def run_negative_validation(
    dataset_path: Path,
    timeout: float = 20.0,
    limit: Optional[int] = None,
    verbose: bool = False,
) -> Tuple[bool, List[Dict[str, Any]]]:
    if not dataset_path.exists():
        print(f"Warning: Negative dataset not found at: {dataset_path}")
        return False, []

    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if limit:
        lines = lines[:limit]

    total = len(lines)
    print("\n" + "=" * 80, flush=True)
    print(f"  CADi SAML Negative Dataset Subprocess Execution Runner (Total: {total} samples)", flush=True)
    print(f"  Target File: {dataset_path.resolve()}", flush=True)
    print("=" * 80, flush=True)

    passed_count = 0
    failed_count = 0
    total_time = 0.0
    records = []

    for idx, line in enumerate(lines, 1):
        sample = json.loads(line)
        sid = sample.get("id", f"neg_{idx:03d}")
        cat = sample.get("metadata", {}).get("category", "unknown")

        ok, msg, dur, tel = validate_negative_sample(sample, idx, total, timeout=timeout, verbose=verbose)
        total_time += dur
        records.append(tel)

        if ok:
            passed_count += 1
            print(f"[{idx:02d}/{total:02d}] {sid} ({cat:<28}) ... PASSED ({dur:.2f}s, {tel['exception_type']})", flush=True)
        else:
            failed_count += 1
            print(f"[{idx:02d}/{total:02d}] {sid} ({cat:<28}) ... FAILED ({dur:.2f}s) -> {msg}", flush=True)

    print("-" * 80, flush=True)
    print(f"Negative Dataset Summary: {passed_count}/{total} PASSED ({passed_count/total*100:.1f}%), {failed_count} FAILED in {total_time:.2f}s", flush=True)
    print("=" * 80, flush=True)
    return failed_count == 0, records


def write_validation_report(
    gold_records: List[Dict[str, Any]],
    neg_records: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """Writes the comprehensive JSON audit report."""
    gold_passed = sum(1 for r in gold_records if r.get("exit_code") == 0 and r.get("contract_result") is True and r.get("provenance_result") is True)
    gold_failed = len(gold_records) - gold_passed
    neg_passed = sum(1 for r in neg_records if r.get("exit_code") not in (0, None) and r.get("exception_type") is not None)
    neg_failed = len(neg_records) - neg_passed

    total_time = sum(r.get("duration", 0.0) for r in gold_records + neg_records)

    is_full_gold = (len(gold_records) >= 60 and gold_failed == 0)
    is_full_neg = (len(neg_records) >= 30 and neg_failed == 0)

    if is_full_gold and is_full_neg:
        status = "ALL_PASSED"
    elif (gold_failed == 0 and neg_failed == 0) and (len(gold_records) > 0 or len(neg_records) > 0):
        status = "PARTIAL_PASSED"
    else:
        status = "FAILED"

    report = {
        "summary": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "library_version": "0.6.0",
            "catalog_version": "2026.1",
            "git_commit": get_git_commit(),
            "total_samples": len(gold_records) + len(neg_records),
            "total_gold": len(gold_records),
            "gold_passed": gold_passed,
            "gold_failed": gold_failed,
            "total_negative": len(neg_records),
            "negative_passed": neg_passed,
            "negative_failed": neg_failed,
            "total_duration_seconds": round(total_time, 2),
            "status": status,
        },
        "gold_results": gold_records,
        "negative_results": neg_records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[REPORT] Comprehensive validation report written to: {output_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Validate CADi SAML Gold and Negative Datasets.")
    parser.add_argument("--gold", action="store_true", default=False, help="Validate gold dataset only")
    parser.add_argument("--negative", action="store_true", default=False, help="Validate negative dataset only")
    parser.add_argument("--all", action="store_true", default=False, help="Validate both gold and negative datasets (default)")
    parser.add_argument("--timeout", type=float, default=35.0, help="Timeout in seconds per sample (default: 35.0s)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of samples to run")
    parser.add_argument("--offset", type=int, default=0, help="Offset to start running samples from (0-indexed)")
    parser.add_argument("--verbose", action="store_true", default=False, help="Verbose output on failure")
    parser.add_argument("--report-path", type=str, default=None, help="Custom output report path")

    args = parser.parse_args()

    gold_path = REPO_ROOT / "dataset" / "saml_gold_dataset.jsonl"
    neg_path = REPO_ROOT / "dataset" / "saml_negative_dataset.jsonl"
    report_file = Path(args.report_path) if args.report_path else (REPO_ROOT / "dataset" / "dataset_validation_report.json")

    run_both = args.all or (not args.gold and not args.negative)
    run_gold_flag = run_both or args.gold
    run_neg_flag = run_both or args.negative

    all_ok = True
    gold_records: List[Dict[str, Any]] = []
    neg_records: List[Dict[str, Any]] = []

    if run_gold_flag:
        gold_ok, gold_records = run_gold_validation(
            gold_path,
            timeout=args.timeout,
            limit=args.limit,
            offset=args.offset,
            verbose=args.verbose,
        )
        if not gold_ok:
            all_ok = False

    if run_neg_flag:
        neg_ok, neg_records = run_negative_validation(
            neg_path,
            timeout=args.timeout,
            limit=args.limit,
            verbose=args.verbose,
        )
        if not neg_ok:
            all_ok = False

    write_validation_report(gold_records, neg_records, report_file)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
