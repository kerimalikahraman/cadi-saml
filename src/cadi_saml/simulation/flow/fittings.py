"""
cadi_saml.simulation.flow.fittings

Minor loss coefficients (K factors) for piping fittings, valves, bends, and expansions/contractions.
Reference: Crane Technical Paper No. 410, Idelchik Handbook of Hydraulic Resistance.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
from .pipe_flow import PipeFlowResult, FluidState


# Loss coefficients K for standard fittings (fully turbulent reference)
STANDARD_FITTING_K: Dict[str, float] = {
    # Elbows and Bends
    "elbow_90_standard": 0.75,     # Standard 90 deg threaded/flanged elbow (R/D ~ 1.0)
    "elbow_90_long_radius": 0.45,  # Long radius 90 deg elbow (R/D ~ 1.5)
    "elbow_45_standard": 0.35,     # 45 deg elbow
    "bend_180_return": 1.50,       # 180 deg return bend

    # Tees
    "tee_through_flow": 0.40,      # Straight through branch
    "tee_branch_flow": 1.50,       # 90 deg flow into or out of branch

    # Valves (Fully open)
    "valve_ball_full_port": 0.05,  # Full bore ball valve
    "valve_ball_reduced": 0.50,    # Reduced bore ball valve
    "valve_gate_open": 0.17,       # Fully open gate valve
    "valve_globe_open": 6.00,      # Fully open globe valve
    "valve_butterfly_open": 0.60,  # Fully open butterfly valve
    "valve_check_swing": 2.00,     # Swing check valve
    
    # Inlets and Outlets
    "inlet_sharp_edged": 0.50,     # Pipe entering from reservoir (sharp edge)
    "inlet_rounded": 0.05,         # Rounded bellmouth inlet
    "outlet_pipe_to_tank": 1.00,   # Discharging into large reservoir/tank
}


def calc_sudden_expansion_k(d_in_mm: float, d_out_mm: float) -> float:
    """
    Borda-Carnot loss coefficient K for sudden pipe expansion (based on upstream velocity v1):
      K = (1 - (d_in / d_out)^2)^2
    """
    if d_out_mm <= d_in_mm or d_in_mm <= 0:
        return 0.0
    beta = (d_in_mm / d_out_mm) ** 2
    return (1.0 - beta) ** 2


def calc_sudden_contraction_k(d_in_mm: float, d_out_mm: float) -> float:
    """
    Loss coefficient K for sudden pipe contraction (based on downstream velocity v2):
      K ≈ 0.5 * (1 - (d_out / d_in)^2)
    """
    if d_out_mm >= d_in_mm or d_in_mm <= 0:
        return 0.0
    beta = (d_out_mm / d_in_mm) ** 2
    return 0.5 * (1.0 - beta)


@dataclass
class FittingItem:
    fitting_type: str
    count: int = 1
    custom_k: Optional[float] = None

    @property
    def total_k(self) -> float:
        if self.custom_k is not None:
            return self.custom_k * self.count
        k_val = STANDARD_FITTING_K.get(self.fitting_type.lower().strip(), 0.5)
        return k_val * self.count


def calc_piping_system_loss(
    pipe_result: PipeFlowResult,
    fittings: List[FittingItem],
) -> Dict[str, float]:
    """
    Calculate minor and total system pressure losses including all pipe fittings.
    """
    total_k = sum(item.total_k for item in fittings)
    dynamic_pressure = 0.5 * pipe_result.fluid.density * (pipe_result.velocity_m_s ** 2)
    minor_loss_pa = total_k * dynamic_pressure
    minor_loss_bar = minor_loss_pa / 1e5

    total_loss_pa = pipe_result.pressure_drop_pa + minor_loss_pa
    total_loss_bar = total_loss_pa / 1e5
    total_hyd_power = pipe_result.flow_rate_m3_s * total_loss_pa

    return {
        "total_k_factor": total_k,
        "major_loss_bar": pipe_result.pressure_drop_bar,
        "minor_loss_bar": minor_loss_bar,
        "total_pressure_drop_bar": total_loss_bar,
        "total_pressure_drop_pa": total_loss_pa,
        "total_hydraulic_power_w": total_hyd_power,
    }
