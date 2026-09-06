"""
cadi_saml.core.exceptions
=========================
Structured error taxonomy for CADi SAML.
Ensures Strict LLM Mode: No silent fallbacks, no geometric guessing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class CADISpecificationError(ValueError):
    """
    Raised when an LLM or user specification contains missing, unknown,
    physically impossible, or contradictory parameters.
    Prevents silent geometric fallbacks and forces explicit error correction.
    """

    def __init__(
        self,
        message: Optional[str] = None,
        parameter_name: Optional[str] = None,
        provided_value: Optional[Any] = None,
        valid_options: Optional[List[Any]] = None,
        suggested_fix: Optional[str] = None,
        parameter: Optional[str] = None,
        **kwargs: Any,
    ):
        p_name = parameter_name or parameter or kwargs.get("param")
        if message is None:
            if p_name:
                message = f"Invalid or unspecified value for parameter '{p_name}': {provided_value!r}"
            else:
                message = "Invalid or missing CAD specification."
        super().__init__(message)
        self.message = message
        self.parameter_name = p_name
        self.provided_value = provided_value
        self.valid_options = valid_options or []
        self.suggested_fix = suggested_fix

    def to_dict(self) -> Dict[str, Any]:
        """Structured error dictionary for programmatic LLM feedback loops."""
        return {
            "error_type": "CADISpecificationError",
            "message": self.message,
            "parameter_name": self.parameter_name,
            "provided_value": str(self.provided_value) if self.provided_value is not None else None,
            "valid_options": self.valid_options,
            "suggested_fix": self.suggested_fix,
        }

    def __str__(self) -> str:
        base = self.message
        details = []
        if self.parameter_name:
            details.append(f"Parametre: '{self.parameter_name}'")
        if self.provided_value is not None:
            details.append(f"Verilen Değer: {self.provided_value!r}")
        if self.valid_options:
            details.append(f"Geçerli Seçenekler: {self.valid_options}")
        if self.suggested_fix:
            details.append(f"Düzeltme Önerisi: {self.suggested_fix}")
        if details:
            return f"{base} | " + " | ".join(details)
        return base
