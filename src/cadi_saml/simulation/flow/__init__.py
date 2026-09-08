"""
cadi_saml.simulation.flow

Fluid mechanics and hydraulics sub-package:
  - pipe_flow: Incompressible Darcy-Weisbach (single-phase)
  - fluid_properties: Temperature-dependent fluid properties (12 fluids)
  - fittings: Minor loss coefficients and fitting K-factors
  - pump: Pump sizing, NPSH cavitation check
  - compressible: Fanno flow (compressible adiabatic pipe, Mach-dependent)
  - two_phase: Lockhart-Martinelli two-phase pressure drop
  - open_channel: Manning's equation (rectangular, trapezoidal, circular)
  - network: Hardy Cross pipe network solver (loops, pumps, reservoirs)
"""

from .fluid_properties import (
    FluidState,
    get_water_properties,
    get_air_properties,
    get_hydraulic_oil_properties,
    get_glycol_properties,
    get_seawater_properties,
    get_r134a_properties,
    get_fuel_properties,
    get_nitrogen_properties,
    get_co2_properties,
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
from .compressible import (
    CompressibleFlowResult,
    FannoPoint,
    analyze_compressible_pipe_flow,
)
from .two_phase import (
    TwoPhaseFlowResult,
    analyze_two_phase_flow,
)
from .open_channel import (
    OpenChannelResult,
    MANNING_N,
    analyze_open_channel_flow,
)
from .network import (
    PipeNetwork,
    PipeSegment,
    PumpCurve,
    NetworkSolution,
    NodeResult,
)

__all__ = [
    # Fluid properties
    "FluidState",
    "get_water_properties",
    "get_air_properties",
    "get_hydraulic_oil_properties",
    "get_glycol_properties",
    "get_seawater_properties",
    "get_r134a_properties",
    "get_fuel_properties",
    "get_nitrogen_properties",
    "get_co2_properties",
    "resolve_fluid",
    # Incompressible pipe flow
    "PipeFlowResult",
    "solve_friction_factor_colebrook",
    "analyze_pipe_flow",
    # Fittings
    "FittingItem",
    "STANDARD_FITTING_K",
    "calc_sudden_expansion_k",
    "calc_sudden_contraction_k",
    "calc_piping_system_loss",
    # Pump
    "PumpAnalysisResult",
    "analyze_pump_requirements",
    # Compressible flow
    "CompressibleFlowResult",
    "FannoPoint",
    "analyze_compressible_pipe_flow",
    # Two-phase flow
    "TwoPhaseFlowResult",
    "analyze_two_phase_flow",
    # Open channel
    "OpenChannelResult",
    "MANNING_N",
    "analyze_open_channel_flow",
    # Pipe network
    "PipeNetwork",
    "PipeSegment",
    "PumpCurve",
    "NetworkSolution",
    "NodeResult",
]
