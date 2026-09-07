"""
cadi_saml.simulation.flow.pump

Hydraulic pump power requirements, motor sizing, and cavitation (NPSH) checks.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
from .fluid_properties import FluidState


@dataclass
class PumpAnalysisResult:
    flow_rate_m3_s: float
    total_head_m: float
    total_pressure_increase_bar: float
    hydraulic_power_w: float
    shaft_power_kw: float
    recommended_motor_power_kw: float
    npsh_available_m: Optional[float] = None
    cavitation_risk: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_rate_l_s": self.flow_rate_m3_s * 1e3,
            "total_head_m": self.total_head_m,
            "pressure_increase_bar": self.total_pressure_increase_bar,
            "hydraulic_power_w": self.hydraulic_power_w,
            "shaft_power_kw": self.shaft_power_kw,
            "recommended_motor_power_kw": self.recommended_motor_power_kw,
            "npsh_available_m": self.npsh_available_m,
            "cavitation_risk": self.cavitation_risk,
            "notes": self.notes,
        }


def analyze_pump_requirements(
    flow_rate_l_s: float,
    total_system_dp_bar: float,
    fluid: FluidState,
    pump_efficiency: float = 0.75,
    motor_efficiency: float = 0.90,
    suction_pressure_bar: float = 1.013, # Ambient atmospheric suction by default
    static_suction_lift_m: float = 0.0,  # Vertical distance below pump inlet
    required_npsh_m: Optional[float] = 3.0, # Typical manufacturer NPSH_r
) -> PumpAnalysisResult:
    """
    Calculate pump sizing, electrical motor power, and cavitation risk.
    """
    g = 9.80665
    q_m3_s = flow_rate_l_s * 1e-3
    dp_pa = total_system_dp_bar * 1e5

    # Total head H = Delta P / (rho * g)
    total_head_m = dp_pa / (fluid.density * g) if fluid.density > 0 else 0.0

    # Hydraulic power P_h = Q * Delta P
    p_hyd_w = q_m3_s * dp_pa

    # Shaft power P_shaft = P_h / eta_pump
    eta_p = max(0.1, min(0.98, pump_efficiency))
    p_shaft_w = p_hyd_w / eta_p
    p_shaft_kw = p_shaft_w * 1e-3

    # Motor power with standard safety margin (IEC standards recommend 10-20% margin)
    p_electric_kw = (p_shaft_kw / max(0.5, motor_efficiency)) * 1.15

    # Standard IEC motor powers (kW)
    standard_motors = [
        0.18, 0.25, 0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0, 4.0, 5.5, 7.5,
        11.0, 15.0, 18.5, 22.0, 30.0, 37.0, 45.0, 55.0, 75.0, 90.0, 110.0
    ]
    rec_motor_kw = standard_motors[-1]
    for m in standard_motors:
        if m >= p_electric_kw:
            rec_motor_kw = m
            break

    # Cavitation check: NPSH_available = (P_suction - P_vapor) / (rho * g) - z_lift
    p_suction_pa = suction_pressure_bar * 1e5
    p_vap_pa = fluid.vapor_pressure
    npsh_a = ((p_suction_pa - p_vap_pa) / (fluid.density * g)) - static_suction_lift_m

    cavitation_risk = False
    notes_list = []
    if required_npsh_m is not None:
        # Standard safety margin requires NPSH_a >= NPSH_r + 0.5m
        if npsh_a < (required_npsh_m + 0.5):
            cavitation_risk = True
            notes_list.append(
                f"HIGH CAVITATION RISK: Available NPSH ({npsh_a:.2f} m) is less than required ({required_npsh_m:.2f} m + 0.5m margin)."
            )
        else:
            notes_list.append(f"Safe from cavitation: NPSH_a = {npsh_a:.2f} m > NPSH_r = {required_npsh_m:.2f} m.")

    return PumpAnalysisResult(
        flow_rate_m3_s=q_m3_s,
        total_head_m=total_head_m,
        total_pressure_increase_bar=total_system_dp_bar,
        hydraulic_power_w=p_hyd_w,
        shaft_power_kw=p_shaft_kw,
        recommended_motor_power_kw=rec_motor_kw,
        npsh_available_m=npsh_a,
        cavitation_risk=cavitation_risk,
        notes=" ".join(notes_list),
    )
