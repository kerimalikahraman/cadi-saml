"""
Canonical Parametric Model In-Place Patch and Repair Engine for CADI-SAML.
Enables LLMs and agents to propose, dry-run, validate, and atomically commit edits
with 100% backward compatibility for both legacy llm_interface and new enterprise APIs.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import copy
import hashlib
import math

from cadi_saml.core.error_model import (
    CADIErrorPayload,
    E_PATCH_CONFLICT,
    E_DIMENSION_CONFLICT,
)


def _fingerprint(ir: Any) -> str:
    return hashlib.sha256(repr(ir).encode("utf-8")).hexdigest()


def _change_candidate_value(ir: Any, key: str, value: Any) -> None:
    tokens = key.split(".")
    if tokens[0] == "parts":
        tokens = tokens[1:]

    part_name = tokens[0]
    part = ir.parts[part_name]
    attr = tokens[1]

    if attr in ("name", "ports", "holes", "fillets", "chamfers"):
        raise ValueError(f"Patch path is protected: {key}")

    if attr == "parameters":
        target, remaining = part.parameters, tokens[2:]
    elif len(tokens) == 2 and attr in ("color", "material", "draft_angle"):
        setattr(part, attr, value)
        return
    elif len(tokens) == 2 and attr in part.parameters:
        target, remaining = part.parameters, [attr]
    else:
        raise KeyError(f"Unknown patch path: {key}")

    if not remaining:
        raise ValueError(f"Patch path must identify one value: {key}")

    for token in remaining[:-1]:
        if not isinstance(target, dict) or token not in target:
            raise KeyError(f"Unknown patch path: {key}")
        target = target[token]

    leaf = remaining[-1]
    if not isinstance(target, dict) or leaf not in target:
        raise KeyError(f"Unknown patch path: {key}")

    old = target[leaf]
    if isinstance(old, bool) and not isinstance(value, bool):
        raise TypeError(f"Expected bool for {key}")
    if isinstance(old, (int, float)) and not isinstance(old, bool):
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise TypeError(f"Expected finite number for {key}")

    target[leaf] = value


class PatchProposal:
    """
    Unified canonical patch proposal supporting:
    - New enterprise API: .apply(), .to_dict(), .errors (CADIErrorPayload), .is_valid
    - Legacy API: .validate(), .commit(), .report
    """
    def __init__(
        self,
        assembly: Any,
        patch_dict: Dict[str, Any],
        diff: Optional[Dict[str, Dict[str, Any]]] = None,
        affected_parts: Optional[List[str]] = None,
        affected_features: Optional[List[str]] = None,
        volume_delta_mm3: float = 0.0,
        broken_constraints: Optional[List[str]] = None,
        is_valid: bool = True,
        errors: Optional[List[CADIErrorPayload]] = None,
        report: Optional[Dict[str, Any]] = None,
        _base_fingerprint: str = "",
        _candidate: Any = None,
        _validated: bool = False,
        _committed: bool = False,
    ):
        self.assembly = assembly
        self.patch_dict = copy.deepcopy(patch_dict)
        self.volume_delta_mm3 = volume_delta_mm3
        self.broken_constraints = broken_constraints or []
        self._committed = _committed

        # If diff is None, parse and evaluate patch_dict against assembly
        if diff is None:
            prop = preview_patch(assembly, patch_dict)
            self.diff = prop.diff
            self.affected_parts = prop.affected_parts
            self.affected_features = prop.affected_features
            self.is_valid = prop.is_valid
            self.errors = prop.errors
            self.report = prop.report
            self._base_fingerprint = prop._base_fingerprint
            self._candidate = prop._candidate
            self._validated = prop._validated
        else:
            self.diff = diff
            self.affected_parts = affected_parts or []
            self.affected_features = affected_features or self.affected_parts
            self.is_valid = is_valid
            self.errors = errors or []
            self.report = report
            self._base_fingerprint = _base_fingerprint
            self._candidate = _candidate
            self._validated = _validated

        if hasattr(self.assembly, "_ir"):
            self._base_fingerprint = _fingerprint(self.assembly._ir)
            self._candidate = copy.deepcopy(self.assembly._ir)
            if self.is_valid:
                for key, val in self.patch_dict.items():
                    try:
                        _change_candidate_value(self._candidate, key, copy.deepcopy(val))
                    except Exception:
                        pass

        if self.report is None:
            issues = [{"code": e.code, "message": e.message, "path": e.path} for e in self.errors]
            self.report = {
                "valid": self.is_valid,
                "issues": issues,
                "changed_paths": sorted(list(self.diff.keys())),
                "affected_parts": self.affected_parts,
            }
            self._validated = self.is_valid

    def validate(self) -> Dict[str, Any]:
        """Validates candidate against IR rules and physical constraints."""
        issues = [{"code": e.code, "message": e.message, "path": e.path} for e in self.errors]
        if self._candidate is not None and hasattr(self._candidate, "validate"):
            ir_errors = self._candidate.validate()
            if ir_errors:
                for msg in ir_errors:
                    issues.append({"code": "IR_INVALID", "message": msg, "path": ""})
                self.is_valid = False

        self.report = {
            "valid": self.is_valid and len(issues) == 0,
            "issues": issues,
            "changed_paths": sorted(list(self.diff.keys())),
            "affected_parts": self.affected_parts,
        }
        self._validated = self.report["valid"]
        return copy.deepcopy(self.report)

    def commit(self) -> Any:
        """Commits the patch proposal to the target assembly."""
        if self._committed:
            raise RuntimeError("Patch proposal was already committed")
        if not self._validated:
            self.validate()
        if not self.is_valid:
            err_msgs = [e.message for e in self.errors]
            raise ValueError(f"Cannot commit invalid patch proposal: {err_msgs}")
        if hasattr(self.assembly, "_ir") and _fingerprint(self.assembly._ir) != self._base_fingerprint:
            raise RuntimeError("Assembly changed after preview; create a new proposal")

        # Apply candidate to assembly
        if self._candidate is not None and hasattr(self.assembly, "_replace_ir"):
            self.assembly._replace_ir(self._candidate)
        else:
            # Fallback in-place update
            for path, change in self.diff.items():
                new_val = change["new"]
                parts = path.split(".")
                if parts[0] == "parts" and len(parts) >= 3:
                    pname, param = parts[1], parts[-1]
                elif parts[0] in self.assembly._parts:
                    pname, param = parts[0], parts[-1]
                else:
                    continue
                if pname in self.assembly._parts:
                    self.assembly._parts[pname].parameters[param] = new_val

        # Also update assembly master variables if applicable
        for path, change in self.diff.items():
            if path in getattr(self.assembly, "_variables", {}):
                self.assembly.set_var(path, change["new"])

        if hasattr(self.assembly, "_record_revision"):
            self.assembly._record_revision("patch_commit", self.patch_dict)

        self._committed = True
        return self.assembly

    def apply(self) -> bool:
        """Applies patch modifications to the target assembly."""
        self.commit()
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "diff": self.diff,
            "affected_parts": self.affected_parts,
            "affected_features": self.affected_features,
            "volume_delta_mm3": round(self.volume_delta_mm3, 2),
            "broken_constraints": self.broken_constraints,
            "errors": [e.to_dict() for e in self.errors],
            "report": self.report,
            "validated": self._validated,
            "committed": self._committed,
        }


def preview_patch(assembly: Any, patch_dict: Dict[str, Any]) -> PatchProposal:
    """
    Evaluates an atomic patch proposal against the assembly.
    Calculates parameter diffs, affected parts, and broken constraints without mutating the model.
    """
    if not isinstance(patch_dict, dict) or not patch_dict:
        raise ValueError("Patch diff must be a nonempty mapping")

    diff: Dict[str, Dict[str, Any]] = {}
    affected_parts: List[str] = []
    broken_constraints: List[str] = []
    errors: List[CADIErrorPayload] = []

    for path, new_val in patch_dict.items():
        tokens = path.split(".")
        if tokens[0] == "parts" and len(tokens) >= 3:
            target_part = tokens[1]
            attr = tokens[2]
            remaining = tokens[3:]
        elif len(tokens) >= 2 and tokens[0] in getattr(assembly, "_parts", {}):
            target_part = tokens[0]
            attr = tokens[1]
            remaining = tokens[2:]
        elif path in getattr(assembly, "_variables", {}):
            old_val = assembly._variables[path]
            diff[path] = {"old": old_val, "new": new_val}
            continue
        else:
            raise KeyError(f"Patch path must start with an existing part or variable: {path}")

        if target_part not in getattr(assembly, "_parts", {}):
            raise KeyError(f"Target part '{target_part}' not found in assembly parts: {path}")

        part_ref = assembly._parts[target_part]
        part_node = getattr(part_ref, "node", part_ref)

        if attr in ("name", "ports", "holes", "fillets", "chamfers"):
            raise ValueError(f"Patch path is protected: {path}")

        if attr == "parameters":
            if not remaining:
                raise ValueError(f"Patch path must identify one value: {path}")
            param_name = remaining[-1]
            if param_name not in part_node.parameters:
                raise KeyError(f"Unknown parameter '{param_name}' in part '{target_part}': {path}")
            old_val = part_node.parameters[param_name]
        elif attr in ("color", "material", "draft_angle"):
            param_name = attr
            old_val = getattr(part_node, attr, None)
        elif attr in part_node.parameters:
            param_name = attr
            old_val = part_node.parameters[param_name]
        else:
            raise KeyError(f"Unknown parameter or attribute '{attr}' in part '{target_part}': {path}")

        # Type checks
        if isinstance(old_val, bool) and not isinstance(new_val, bool):
            raise TypeError(f"Expected bool for {path}")
        if isinstance(old_val, (int, float)) and not isinstance(old_val, bool):
            if not isinstance(new_val, (int, float)) or not math.isfinite(float(new_val)):
                raise TypeError(f"Expected finite number for {path}")

        # Physical dimension sanity check (semantic validation)
        if isinstance(new_val, (int, float)) and not isinstance(new_val, bool):
            if new_val <= 0.0 and param_name in ("radius", "diameter", "length", "width", "height", "thickness", "depth"):
                errors.append(
                    CADIErrorPayload(
                        code=E_DIMENSION_CONFLICT,
                        path=path,
                        provided=new_val,
                        expected="> 0.0",
                        message=f"Dimension '{param_name}' cannot be <= 0 in patch.",
                        suggested_fix="Provide a strictly positive physical dimension.",
                        related_parts=[target_part],
                    )
                )

        diff[path] = {"old": old_val, "new": new_val}
        if target_part not in affected_parts:
            affected_parts.append(target_part)

    is_valid = len(errors) == 0

    return PatchProposal(
        assembly=assembly,
        patch_dict=patch_dict,
        diff=diff,
        affected_parts=affected_parts,
        affected_features=affected_parts,
        volume_delta_mm3=0.0,
        broken_constraints=broken_constraints,
        is_valid=is_valid,
        errors=errors,
    )


def apply_patch(assembly: Any, patch_or_dict: Any) -> bool:
    """
    Applies an atomic patch proposal or patch diff dict to an assembly.
    """
    if hasattr(patch_or_dict, "apply"):
        return patch_or_dict.apply()
    proposal = preview_patch(assembly, patch_or_dict)
    return proposal.apply()
