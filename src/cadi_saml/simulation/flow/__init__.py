"""
cadi_saml.simulation.flow

Fluid mechanics, CFD, internal pipe flow, fitting losses, and pump sizing engine.
"""

from .fluid_properties import (
    FluidState,
    get_water_properties,
    get_air_properties,
    get_hydraulic_oil_properties,
    resolve_fluid,
)
from .pipe_flow import (
    PipeFlowResult,
    solve_friction_factor_colebrook,
    analyze_pipe_flow,
)
from .fittings import (
    FittingItem,
    STANDARD_FITTING_K,
    calc_sudden_expansion_k,
    calc_sudden_contraction_k,
    calc_piping_system_loss,
)
from .pump import (
    PumpAnalysisResult,
    analyze_pump_requirements,
)

__all__ = [
    "FluidState",
    "get_water_properties",
    "get_air_properties",
    "get_hydraulic_oil_properties",
    "resolve_fluid",
    "PipeFlowResult",
    "solve_friction_factor_colebrook",
    "analyze_pipe_flow",
    "FittingItem",
    "STANDARD_FITTING_K",
    "calc_sudden_expansion_k",
    "calc_sudden_contraction_k",
    "calc_piping_system_loss",
    "PumpAnalysisResult",
    "analyze_pump_requirements",
]
