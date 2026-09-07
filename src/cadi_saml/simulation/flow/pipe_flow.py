"""
cadi_saml.simulation.flow.pipe_flow

Rigorous internal pipe flow calculations using Darcy-Weisbach and Colebrook-White.
Provides Reynolds regime detection, friction factor, major pressure drop,
wall shear stress, and automated diameter recommendation for CAD models.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union
from .fluid_properties import FluidState, resolve_fluid
from ..results import AnalysisResult, AcceptanceCriteria, ProvenanceRecord, SensitivityReport
from ..load_cases import STANDARD_ROUGHNESS


def solve_friction_factor_colebrook(reynolds: float, relative_roughness: float) -> float:
    """
    Solve the Colebrook-White equation for Darcy friction factor 'f' using Newton-Raphson:
      1 / sqrt(f) = -2 * log10( (epsilon/D)/3.7 + 2.51 / (Re * sqrt(f)) )
    Accurate to within 1e-7 relative error.
    """
    if reynolds < 2300.0:
        # Laminar flow: exact Hagen-Poiseuille formula
        if reynolds <= 0.0:
            return 0.0
        return 64.0 / reynolds

    ed = max(0.0, relative_roughness) / 3.7

    # Initial guess using Haaland explicit formula (1983)
    # 1/sqrt(f) ≈ -1.8 * log10( (epsilon/D / 3.7)^1.11 + 6.9 / Re )
    term_h = (max(0.0, relative_roughness) / 3.7) ** 1.11 + 6.9 / reynolds
    inv_sqrt_f = -1.8 * math.log10(max(1e-12, term_h))
    f = 1.0 / (inv_sqrt_f ** 2)

    # Newton-Raphson iteration on x = 1/sqrt(f)
    # Let g(x) = x + 2 * log10(ed + 2.51 * x / Re) = 0
    # g'(x) = 1 + 2 / ln(10) * (2.51 / Re) / (ed + 2.51 * x / Re)
    c1 = 2.0 / math.log(10.0)
    c2 = 2.51 / reynolds
    x = 1.0 / math.sqrt(f)

    for _ in range(25):
        arg = ed + c2 * x
        if arg <= 0.0:
            break
        g = x + 2.0 * math.log10(arg)
        g_prime = 1.0 + (c1 * c2) / arg
        step = g / g_prime
        x -= step
        if abs(step) < 1e-7:
            break

    f_final = 1.0 / (x ** 2)
    return max(0.005, min(0.15, f_final))


@dataclass
class PipeFlowResult:
    """Detailed hydraulic calculation output for a pipe run."""
    diameter_m: float
    length_m: float
    flow_rate_m3_s: float
    velocity_m_s: float
    reynolds: float
    flow_regime: str  # "LAMINAR", "TRANSITIONAL", "TURBULENT"
    friction_factor: float
    pressure_drop_pa: float
    pressure_drop_bar: float
    wall_shear_stress_pa: float
    hydraulic_power_w: float
    fluid: FluidState
    recommended_diameter_mm: Optional[float] = None
    pass_criteria: bool = True

    def to_analysis_result(self, criteria: Optional[AcceptanceCriteria] = None) -> AnalysisResult:
        crit = criteria or AcceptanceCriteria()
        status = "PASS"
        crit_metric = None
        crit_val = None
        thresh_val = None
        changes: List[Dict[str, Any]] = []
        warnings: List[str] = []

        if crit.max_pressure_drop_bar is not None and self.pressure_drop_bar > crit.max_pressure_drop_bar:
            status = "FAIL"
            crit_metric = "pressure_drop_bar"
            crit_val = self.pressure_drop_bar
            thresh_val = crit.max_pressure_drop_bar
            if self.recommended_diameter_mm:
                changes.append({
                    "parameter": "pipe_inner_diameter_mm",
                    "current": self.diameter_m * 1e3,
                    "proposed": self.recommended_diameter_mm,
                    "reason": f"Pressure drop ({self.pressure_drop_bar:.2f} bar) exceeds max allowed ({crit.max_pressure_drop_bar:.2f} bar)",
                })

        if crit.max_velocity_m_s is not None and self.velocity_m_s > crit.max_velocity_m_s:
            if status != "FAIL":
                status = "FAIL"
                crit_metric = "velocity_m_s"
                crit_val = self.velocity_m_s
                thresh_val = crit.max_velocity_m_s
            warnings.append(f"Flow velocity {self.velocity_m_s:.2f} m/s exceeds max {crit.max_velocity_m_s:.2f} m/s")

        if self.flow_regime == "TRANSITIONAL":
            warnings.append("Flow is in transitional regime (2300 < Re < 4000); flow behavior may be unsteady.")

        # Sensitivity metrics
        sens = SensitivityReport(influences={
            "diameter": "extreme (d^-5 relationship with pressure drop)",
            "flow_rate": "high (Q^2 relationship with pressure drop)",
            "roughness": "medium (turbulent regime)",
            "viscosity": "medium (laminar) / low (fully turbulent)",
        })

        prov = ProvenanceRecord(
            solver_name="DarcyWeisbachColebrookSolver",
            solver_version="1.0.0",
            assumptions=[
                "1D steady incompressible single-phase Newtonian flow",
                "Fully developed velocity profile along pipe length",
                "Isothermal fluid properties at specified bulk temperature",
            ],
        )

        return AnalysisResult(
            study_type="pipe_flow",
            status=status,
            metrics={
                "diameter_mm": self.diameter_m * 1e3,
                "length_m": self.length_m,
                "flow_rate_l_s": self.flow_rate_m3_s * 1e3,
                "velocity_m_s": self.velocity_m_s,
                "reynolds": self.reynolds,
                "flow_regime": self.flow_regime,
                "friction_factor": self.friction_factor,
                "pressure_drop_bar": self.pressure_drop_bar,
                "pressure_drop_pa": self.pressure_drop_pa,
                "hydraulic_power_w": self.hydraulic_power_w,
            },
            critical_metric=crit_metric,
            critical_value=crit_val,
            threshold_value=thresh_val,
            provenance=prov,
            sensitivity=sens,
            suggested_changes=changes,
            warnings=warnings,
        )


def analyze_pipe_flow(
    diameter_mm: float,
    length_mm: float,
    flow_rate_l_s: Optional[float] = None,
    velocity_m_s: Optional[float] = None,
    fluid: Union[str, FluidState] = "water",
    temperature_c: float = 20.0,
    material_roughness: Union[str, float] = "commercial_steel",
    max_allowable_dp_bar: Optional[float] = None,
    max_allowable_velocity: float = 3.0,
) -> PipeFlowResult:
    """
    Perform complete hydraulic calculation for a straight pipe section.

    Parameters:
    -----------
    diameter_mm: Inner pipe diameter in millimeters.
    length_mm: Pipe length in millimeters.
    flow_rate_l_s: Volumetric flow rate in Liters per second (L/s).
    velocity_m_s: Fluid velocity in m/s (alternative to flow_rate_l_s).
    fluid: Fluid name ('water', 'air', 'hydraulic_oil_vg46') or custom FluidState.
    temperature_c: Fluid bulk temperature in degrees Celsius.
    material_roughness: Material key from STANDARD_ROUGHNESS or absolute roughness in meters.
    max_allowable_dp_bar: Target maximum pressure loss to calculate recommended diameter.
    """
    # 1. Resolve fluid properties
    if isinstance(fluid, str):
        state = resolve_fluid(fluid, temp_c=temperature_c)
    else:
        state = fluid

    d_m = diameter_mm * 1e-3
    l_m = length_mm * 1e-3
    area_m2 = (math.pi / 4.0) * (d_m ** 2)

    # 2. Determine velocity and flow rate
    if flow_rate_l_s is not None:
        q_m3_s = flow_rate_l_s * 1e-3
        v_m_s = q_m3_s / area_m2 if area_m2 > 0 else 0.0
    elif velocity_m_s is not None:
        v_m_s = velocity_m_s
        q_m3_s = v_m_s * area_m2
    else:
        raise ValueError("Either 'flow_rate_l_s' or 'velocity_m_s' must be provided.")

    # 3. Resolve surface roughness
    if isinstance(material_roughness, str):
        rough_key = material_roughness.lower().strip()
        eps_m = STANDARD_ROUGHNESS.get(rough_key, 4.5e-5)
    else:
        eps_m = float(material_roughness)

    rel_roughness = eps_m / d_m if d_m > 0 else 0.0

    # 4. Reynolds number
    # Re = rho * v * D / mu = v * D / nu
    re = (v_m_s * d_m) / state.kinematic_viscosity if state.kinematic_viscosity > 0 else 0.0

    if re < 2300.0:
        regime = "LAMINAR"
    elif re <= 4000.0:
        regime = "TRANSITIONAL"
    else:
        regime = "TURBULENT"

    # 5. Friction factor
    f = solve_friction_factor_colebrook(reynolds=re, relative_roughness=rel_roughness)

    # 6. Darcy-Weisbach pressure drop: Delta P = f * (L/D) * (rho * v^2 / 2)
    dynamic_pressure = 0.5 * state.density * (v_m_s ** 2)
    dp_pa = f * (l_m / d_m) * dynamic_pressure if d_m > 0 else 0.0
    dp_bar = dp_pa / 1e5

    # 7. Wall shear stress: tau_w = f * rho * v^2 / 8
    tau_w = (f * state.density * (v_m_s ** 2)) / 8.0

    # 8. Hydraulic power: P_h = Q * Delta P (Watts)
    hyd_power = q_m3_s * dp_pa

    # 9. Automated diameter recommendation if pressure drop or velocity exceeds limits
    rec_d_mm = None
    target_dp = max_allowable_dp_bar
    needs_resize = (target_dp is not None and dp_bar > target_dp) or (v_m_s > max_allowable_velocity)

    if needs_resize and q_m3_s > 0:
        # Standard pipe diameters (internal diameter in mm) from ISO 4200 / standard schedule
        standard_ids = [
            10.0, 12.0, 15.0, 20.0, 25.0, 32.0, 40.0, 50.0, 65.0, 80.0,
            100.0, 125.0, 150.0, 200.0, 250.0, 300.0
        ]
        # Iterate over standard larger diameters until criteria are met
        for cand_d in standard_ids:
            if cand_d <= diameter_mm:
                continue
            cand_d_m = cand_d * 1e-3
            cand_area = (math.pi / 4.0) * (cand_d_m ** 2)
            cand_v = q_m3_s / cand_area
            cand_re = (cand_v * cand_d_m) / state.kinematic_viscosity
            cand_f = solve_friction_factor_colebrook(cand_re, eps_m / cand_d_m)
            cand_dp = cand_f * (l_m / cand_d_m) * (0.5 * state.density * (cand_v ** 2)) / 1e5
            
            ok_dp = (target_dp is None) or (cand_dp <= target_dp)
            ok_v = cand_v <= max_allowable_velocity
            if ok_dp and ok_v:
                rec_d_mm = cand_d
                break

    return PipeFlowResult(
        diameter_m=d_m,
        length_m=l_m,
        flow_rate_m3_s=q_m3_s,
        velocity_m_s=v_m_s,
        reynolds=re,
        flow_regime=regime,
        friction_factor=f,
        pressure_drop_pa=dp_pa,
        pressure_drop_bar=dp_bar,
        wall_shear_stress_pa=tau_w,
        hydraulic_power_w=hyd_power,
        fluid=state,
        recommended_diameter_mm=rec_d_mm,
    )
