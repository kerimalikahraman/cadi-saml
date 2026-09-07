"""
cadi_saml.simulation

Engineering simulation, CFD, structural analysis, and multi-physics engine.
"""

from .units import Quantity, UNIT_CONVERSIONS, ensure_quantity
from .results import (
    AnalysisResult,
    AcceptanceCriteria,
    ProvenanceRecord,
    SensitivityReport,
)
from .load_cases import FlowBoundaryCondition, STANDARD_ROUGHNESS
from .base import AnalysisStudy
from .coupling import (
    FlowThrustResult,
    calc_pipe_bend_fluid_thrust,
    couple_flow_to_fea_bracket,
)

__all__ = [
    "Quantity",
    "UNIT_CONVERSIONS",
    "ensure_quantity",
    "AnalysisResult",
    "AcceptanceCriteria",
    "ProvenanceRecord",
    "SensitivityReport",
    "FlowBoundaryCondition",
    "STANDARD_ROUGHNESS",
    "AnalysisStudy",
    "FlowThrustResult",
    "calc_pipe_bend_fluid_thrust",
    "couple_flow_to_fea_bracket",
]
