"""
Structured Error Model for CADI-SAML.
Provides standardized machine-readable diagnostic payloads for LLMs and automated solvers.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


# Standard error codes
E_DIMENSION_CONFLICT = "E_DIMENSION_CONFLICT"
E_UNDER_CONSTRAINED = "E_UNDER_CONSTRAINED"
E_OVER_CONSTRAINED = "E_OVER_CONSTRAINED"
E_COLLISION = "E_COLLISION"
E_DFM_VIOLATION = "E_DFM_VIOLATION"
E_TOLERANCE_STACKUP = "E_TOLERANCE_STACKUP"
E_STANDARDS_MISMATCH = "E_STANDARDS_MISMATCH"
E_PROVENANCE_MISMATCH = "E_PROVENANCE_MISMATCH"
E_KINEMATIC_INCONSISTENCY = "E_KINEMATIC_INCONSISTENCY"
E_FEATURE_FAILURE = "E_FEATURE_FAILURE"
E_PATCH_CONFLICT = "E_PATCH_CONFLICT"


@dataclass
class CADIErrorPayload:
    """Standardized machine-readable diagnostic error returned to LLMs."""
    code: str
    path: str
    provided: Any
    expected: str
    message: str
    suggested_fix: str
    related_parts: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def __str__(self) -> str:
        return f"[{self.code}] {self.path}: {self.message} (Suggested fix: {self.suggested_fix})"
