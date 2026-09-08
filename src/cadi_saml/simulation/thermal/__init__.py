"""
cadi_saml.simulation.thermal

Thermal analysis sub-package:
  - heat_transfer: Forced/natural convection, Nusselt number correlations,
                   pipe wall heat transfer, log-mean temperature difference.
  - thermal_stress: Thermal expansion stresses, steady-state thermal gradients.
"""

from .heat_transfer import (
    ConvectionResult,
    HeatExchangerResult,
    analyze_pipe_heat_transfer,
    analyze_heat_exchanger_lmtd,
    calc_nusselt_dittus_boelter,
    calc_nusselt_gnielinski,
)
from .thermal_stress import (
    ThermalStressResult,
    analyze_thermal_stress,
    analyze_pipe_thermal_expansion,
)

__all__ = [
    # Heat transfer
    "ConvectionResult",
    "HeatExchangerResult",
    "analyze_pipe_heat_transfer",
    "analyze_heat_exchanger_lmtd",
    "calc_nusselt_dittus_boelter",
    "calc_nusselt_gnielinski",
    # Thermal stress
    "ThermalStressResult",
    "analyze_thermal_stress",
    "analyze_pipe_thermal_expansion",
]
