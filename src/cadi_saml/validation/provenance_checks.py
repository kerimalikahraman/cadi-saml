"""
cadi_saml.validation.provenance_checks
=======================================
Audit and validation routines for engineering parameter provenance.
Verifies source fidelity, prompt extraction, and mathematical equation derivation.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def audit_provenance_coverage(
    assembly: Any,
    required_parameters: Optional[Dict[str, List[str]]] = None,
    valid_sources: Optional[List[str]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Audits complete provenance tracking for all assembly parts.
    Returns (passed, errors, details).
    """
    if valid_sources is None:
        valid_sources = ["user", "catalog", "calculated"]

    errors: List[str] = []
    details: Dict[str, Any] = {
        "parts_checked": 0,
        "parameters_verified": 0,
        "provenance_records": {},
    }

    parts = getattr(assembly, "_parts", {})
    details["parts_checked"] = len(parts)

    for p_name, p_ref in parts.items():
        prov = getattr(p_ref, "_provenance", {})
        p_params = getattr(p_ref, "parameters", {})
        node = getattr(p_ref, "node", None)

        details["provenance_records"][p_name] = len(prov)

        # 1. Reject extraneous provenance records for nonexistent parameters
        for p_k in prov.keys():
            if p_k not in p_params:
                errors.append(
                    f"Part '{p_name}' contains extraneous provenance record for nonexistent parameter '{p_k}' (available: {list(p_params.keys())})."
                )

        # 2. Check required parameters
        target_req = []
        if required_parameters and p_name in required_parameters:
            target_req = required_parameters[p_name]
        else:
            for k in p_params.keys():
                if k.startswith("_") or k in ("color", "material", "points", "waypoints", "wire_dia"):
                    continue
                if k in ("hub_diameter", "bolt_pcd", "flange_thickness") and (
                    getattr(node, "shape", "") == "rigid_flange_coupling" or "coupling" in p_name
                ):
                    continue
                target_req.append(k)

        if not prov:
            errors.append(
                f"Part '{p_name}' lacks specification provenance records (zero recorded entries)."
            )
        else:
            missing = [p for p in target_req if p not in prov]
            if missing:
                errors.append(
                    f"Part '{p_name}' missing provenance for required parameters: {missing}."
                )

        # 3. Validate each recorded provenance entry
        for p_k, rec in prov.items():
            details["parameters_verified"] += 1
            if hasattr(rec, "source"):
                src = rec.source
                sref = rec.source_ref
                conf = rec.confidence
                eq = getattr(rec, "equation", None)
            elif isinstance(rec, dict):
                src = rec.get("source")
                sref = rec.get("source_ref")
                conf = rec.get("confidence", 1.0)
                eq = rec.get("equation")
            else:
                src, sref, conf, eq = None, None, None, None

            if src not in valid_sources:
                errors.append(
                    f"Part '{p_name}' parameter '{p_k}' has invalid provenance source '{src}' (allowed: {valid_sources})."
                )
            if not sref:
                errors.append(
                    f"Part '{p_name}' parameter '{p_k}' has empty provenance source_ref."
                )
            if conf is not None:
                try:
                    cf = float(conf)
                    if not math.isfinite(cf) or not (0.0 <= cf <= 1.0):
                        errors.append(
                            f"Part '{p_name}' parameter '{p_k}' has invalid confidence score '{conf}' (must be 0.0-1.0)."
                        )
                except (ValueError, TypeError):
                    errors.append(
                        f"Part '{p_name}' parameter '{p_k}' has non-numeric confidence score '{conf}'."
                    )

            # Check equation on calculated sources
            if src == "calculated" and not eq and not (sref and ("=" in sref or "*" in sref or "/" in sref or "+" in sref or "-" in sref or "formula" in sref or "derived" in sref)):
                errors.append(
                    f"Part '{p_name}' parameter '{p_k}' has source='calculated' but lacks mathematical equation or derivation formula in source_ref."
                )

            # 4. Validate effective_value matches actual parameter value on part
            if p_k in p_params:
                act_param_val = p_params[p_k]
                eff_val = (
                    getattr(rec, "effective_value", None)
                    if hasattr(rec, "effective_value")
                    else rec.get("effective_value")
                    if isinstance(rec, dict)
                    else None
                )
                if eff_val is not None:
                    try:
                        eff_float = float(eff_val)
                        act_float = float(act_param_val)
                        if not math.isfinite(eff_float):
                            errors.append(
                                f"Part '{p_name}' parameter '{p_k}' provenance effective_value is non-finite."
                            )
                        elif abs(eff_float - act_float) > 0.01:
                            errors.append(
                                f"Part '{p_name}' parameter '{p_k}' provenance effective_value ({eff_float}) does not match actual part parameter ({act_float})."
                            )
                    except (ValueError, TypeError):
                        pass

    passed = len(errors) == 0
    return passed, errors, details
