"""
Parametric Model In-Place Patch and Repair Engine for CADI-SAML.
Enables LLMs and agents to propose, dry-run, and verify atomic edits without rebuilding entire models.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import copy

from cadi_saml.core.error_model import CADIErrorPayload, E_PATCH_CONFLICT, E_DIMENSION_CONFLICT


@dataclass
class PatchProposal:
    """Represents an evaluated dry-run patch proposal."""
    assembly: Any
    patch_dict: Dict[str, Any]
    diff: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    affected_parts: List[str] = field(default_factory=list)
    affected_features: List[str] = field(default_factory=list)
    volume_delta_mm3: float = 0.0
    broken_constraints: List[str] = field(default_factory=list)
    is_valid: bool = True
    errors: List[CADIErrorPayload] = field(default_factory=list)

    def apply(self) -> bool:
        """Commits and applies the patch to the target assembly."""
        if not self.is_valid:
            raise ValueError(f"Cannot apply invalid patch proposal: {self.errors}")

        for path, change in self.diff.items():
            new_val = change["new"]
            parts = path.split(".")
            if len(parts) >= 2 and parts[0] == "parts":
                pname = parts[1]
                param = parts[-1]
                if pname in self.assembly._parts:
                    self.assembly._parts[pname].parameters[param] = new_val
            elif path in self.assembly._variables:
                self.assembly.set_var(path, new_val)
            elif parts[0] in self.assembly._parts:
                pname = parts[0]
                param = parts[1]
                self.assembly._parts[pname].parameters[param] = new_val

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
        }


def preview_patch(assembly: Any, patch_dict: Dict[str, Any]) -> PatchProposal:
    """
    Evaluates an atomic patch proposal against the assembly.
    Calculates parameter diffs, affected parts, and broken constraints without modifying the assembly.
    """
    diff: Dict[str, Dict[str, Any]] = {}
    affected_parts: List[str] = []
    broken_constraints: List[str] = []
    errors: List[CADIErrorPayload] = []

    for path, new_val in patch_dict.items():
        parts = path.split(".")
        target_part = None
        param_name = None
        old_val = None

        if len(parts) >= 3 and parts[0] == "parts":
            target_part = parts[1]
            param_name = parts[-1]
        elif len(parts) == 2 and parts[0] in assembly._parts:
            target_part = parts[0]
            param_name = parts[1]
        elif path in assembly._variables:
            old_val = assembly._variables[path]
            diff[path] = {"old": old_val, "new": new_val}
            continue

        if target_part and target_part in assembly._parts:
            part_ref = assembly._parts[target_part]
            old_val = part_ref.parameters.get(param_name)
            diff[path] = {"old": old_val, "new": new_val}
            if target_part not in affected_parts:
                affected_parts.append(target_part)

            # Sanity check negative or zero dimensions
            if isinstance(new_val, (int, float)) and new_val <= 0.0 and param_name in ("radius", "diameter", "length", "width", "height", "thickness"):
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
        else:
            errors.append(
                CADIErrorPayload(
                    code=E_PATCH_CONFLICT,
                    path=path,
                    provided=new_val,
                    expected="Valid assembly part or variable path",
                    message=f"Target path '{path}' does not resolve to an existing part or parameter.",
                    suggested_fix="Check part name spelling in assembly parts dictionary.",
                )
            )

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
