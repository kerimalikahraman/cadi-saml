"""
cadi_saml.simulation.results

Common result data structures, provenance records, and acceptance criteria.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time


@dataclass
class ProvenanceRecord:
    """Detailed origin and environment tracking for engineering calculations."""
    solver_name: str
    solver_version: str = "1.0.0"
    geometry_hash: Optional[str] = None
    mesh_elements: Optional[int] = None
    assumptions: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "solver_name": self.solver_name,
            "solver_version": self.solver_version,
            "geometry_hash": self.geometry_hash,
            "mesh_elements": self.mesh_elements,
            "assumptions": self.assumptions,
            "timestamp": self.timestamp,
        }


@dataclass
class AcceptanceCriteria:
    """Engineering thresholds for design pass/fail."""
    max_pressure_drop_pa: Optional[float] = None
    max_pressure_drop_bar: Optional[float] = None
    min_velocity_m_s: Optional[float] = None
    max_velocity_m_s: Optional[float] = None
    min_safety_factor: Optional[float] = None
    require_no_cavitation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_pressure_drop_bar": self.max_pressure_drop_bar,
            "min_velocity_m_s": self.min_velocity_m_s,
            "max_velocity_m_s": self.max_velocity_m_s,
            "min_safety_factor": self.min_safety_factor,
            "require_no_cavitation": self.require_no_cavitation,
        }


@dataclass
class SensitivityReport:
    """Sensitivity analysis mapping input parameters to output metrics."""
    influences: Dict[str, str] = field(default_factory=dict)  # e.g. {"diameter": "extreme", "viscosity": "medium"}

    def to_dict(self) -> Dict[str, Any]:
        return {"influences": self.influences}


@dataclass
class AnalysisResult:
    """Unified result contract for simulation and physical analysis."""
    study_type: str  # e.g. "pipe_flow", "modal", "fea_static"
    status: str      # "PASS", "FAIL", "WARNING"
    metrics: Dict[str, Any] = field(default_factory=dict)
    critical_metric: Optional[str] = None
    critical_value: Optional[float] = None
    threshold_value: Optional[float] = None
    critical_location: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None
    sensitivity: Optional[SensitivityReport] = None
    suggested_changes: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status.upper() == "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study_type": self.study_type,
            "status": self.status,
            "metrics": self.metrics,
            "critical_metric": self.critical_metric,
            "critical_value": self.critical_value,
            "threshold_value": self.threshold_value,
            "critical_location": self.critical_location,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "sensitivity": self.sensitivity.to_dict() if self.sensitivity else None,
            "suggested_changes": self.suggested_changes,
            "warnings": self.warnings,
        }
