"""
cadi_saml.simulation.base

Base simulation study abstraction uniting CFD, FEA, and multi-physics analysis.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from .results import AnalysisResult, AcceptanceCriteria, ProvenanceRecord


class AnalysisStudy:
    """Base class for multi-disciplinary physical simulation studies."""

    def __init__(
        self,
        name: str,
        study_type: str,
        criteria: Optional[AcceptanceCriteria] = None,
        notes: Optional[str] = None,
    ):
        self.name = name
        self.study_type = study_type
        self.criteria = criteria or AcceptanceCriteria()
        self.notes = notes
        self.provenance: Optional[ProvenanceRecord] = None
        self._result: Optional[AnalysisResult] = None

    def solve(self) -> AnalysisResult:
        """Run the simulation/calculation. Subclasses must implement."""
        raise NotImplementedError("Subclasses must implement solve()")

    @property
    def result(self) -> Optional[AnalysisResult]:
        return self._result
