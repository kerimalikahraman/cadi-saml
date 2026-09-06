"""
cadi_saml.validation.catalog_checks
====================================
Catalog compliance and authoritative standards cross-referencing.
Validates part dimensions and catalog provenance against central engineering databases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..standards.catalogs import find_standard_by_source_ref, lookup_catalog


def audit_catalog_compliance(
    assembly: Any,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Audits catalog compliance by checking all provenance records with source='catalog'
    against the central authoritative engineering standards catalog.
    Returns (passed, errors, details).
    """
    errors: List[str] = []
    checked_standards: List[str] = []
    details: Dict[str, Any] = {
        "catalog_version": "2026.1",
        "checked_standards": [],
        "compliant_entries": 0,
    }

    parts = getattr(assembly, "_parts", {})

    for p_name, p_ref in parts.items():
        prov = getattr(p_ref, "_provenance", {})
        for p_k, rec in prov.items():
            src = getattr(rec, "source", None) if hasattr(rec, "source") else rec.get("source") if isinstance(rec, dict) else None
            sref = getattr(rec, "source_ref", None) if hasattr(rec, "source_ref") else rec.get("source_ref") if isinstance(rec, dict) else None
            eff = getattr(rec, "effective_value", None) if hasattr(rec, "effective_value") else rec.get("effective_value") if isinstance(rec, dict) else None

            if src == "catalog" and sref and eff is not None:
                cat_data = find_standard_by_source_ref(sref)
                if cat_data:
                    checked_standards.append(sref)
                    if p_k in cat_data:
                        exp_val = float(cat_data[p_k])
                        try:
                            if abs(float(eff) - exp_val) > 0.05:
                                errors.append(
                                    f"Part '{p_name}' param '{p_k}' catalog mismatch: standard '{sref}' specifies {exp_val}, but effective_value is {eff}."
                                )
                            else:
                                details["compliant_entries"] += 1
                        except (ValueError, TypeError):
                            pass

    details["checked_standards"] = list(set(checked_standards))
    passed = len(errors) == 0
    return passed, errors, details
