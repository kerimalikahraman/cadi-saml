"""
cadi_saml.simulation.coupling

Multi-physics coupling engine: CFD/Pipe Flow to FEA Structural Transfer.
Calculates fluid momentum thrust forces and internal pressure loads at pipe bends,
maps them onto structural support brackets, and executes coupled FEA stress verification.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, Union, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from ..core.assembly import Assembly
    from ..analysis.fea import FEAResult


@dataclass
class FlowThrustResult:
    bend_angle_deg: float
    fluid_density_kg_m3: float
    flow_rate_m3_s: float
    velocity_m_s: float
    pressure_pa: float
    internal_area_m2: float
    momentum_force_n: float    # Dynamic force = 2 * rho * Q * v * sin(theta/2)
    pressure_force_n: float    # Static pressure force = 2 * P * A * sin(theta/2)
    resultant_thrust_n: float  # Total resultant vector magnitude
    force_vector_n: Tuple[float, float, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bend_angle_deg": self.bend_angle_deg,
            "velocity_m_s": round(self.velocity_m_s, 2),
            "momentum_force_n": round(self.momentum_force_n, 2),
            "pressure_force_n": round(self.pressure_force_n, 2),
            "resultant_thrust_n": round(self.resultant_thrust_n, 2),
            "force_vector_n": [round(f, 2) for f in self.force_vector_n],
        }


def calc_pipe_bend_fluid_thrust(
    inner_diameter_mm: float,
    flow_rate_l_s: float,
    fluid_pressure_bar: float,
    bend_angle_deg: float = 90.0,
    fluid_density_kg_m3: float = 998.2,
    inlet_direction: Tuple[float, float, float] = (1.0, 0.0, 0.0),
    outlet_direction: Tuple[float, float, float] = (0.0, 1.0, 0.0),
) -> FlowThrustResult:
    """
    Calculate the net reaction force exerted by flowing fluid on a pipe bend.
    Based on the integral momentum equation for control volume:
      F_ext = m_dot * (v_out - v_in) + (P_out * A * n_out - P_in * A * n_in)
      F_fluid_on_pipe = - F_ext = m_dot * (v_in - v_out) + P * A * (n_in - n_out)
    """
    d_m = inner_diameter_mm * 1e-3
    area_m2 = (math.pi / 4.0) * (d_m ** 2)
    q_m3_s = flow_rate_l_s * 1e-3
    v_m_s = q_m3_s / area_m2 if area_m2 > 0 else 0.0
    m_dot = fluid_density_kg_m3 * q_m3_s
    p_pa = fluid_pressure_bar * 1e5

    u_in = np.array(inlet_direction, dtype=np.float64)
    u_out = np.array(outlet_direction, dtype=np.float64)
    norm_in = np.linalg.norm(u_in)
    norm_out = np.linalg.norm(u_out)
    if norm_in > 0:
        u_in /= norm_in
    if norm_out > 0:
        u_out /= norm_out

    # Dynamic momentum force vector: F_mom = m_dot * (v_in - v_out)
    f_mom_vec = m_dot * v_m_s * (u_in - u_out)

    # Static pressure force vector: F_press = P * A * (u_in - u_out)
    f_press_vec = p_pa * area_m2 * (u_in - u_out)

    # Total net force exerted by fluid onto the bend
    f_total_vec = f_mom_vec + f_press_vec
    total_thrust = float(np.linalg.norm(f_total_vec))

    theta_rad = math.radians(bend_angle_deg)
    scalar_factor = 2.0 * math.sin(theta_rad / 2.0)
    mom_scalar = m_dot * v_m_s * scalar_factor
    press_scalar = p_pa * area_m2 * scalar_factor

    return FlowThrustResult(
        bend_angle_deg=bend_angle_deg,
        fluid_density_kg_m3=fluid_density_kg_m3,
        flow_rate_m3_s=q_m3_s,
        velocity_m_s=v_m_s,
        pressure_pa=p_pa,
        internal_area_m2=area_m2,
        momentum_force_n=mom_scalar,
        pressure_force_n=press_scalar,
        resultant_thrust_n=total_thrust,
        force_vector_n=(float(f_total_vec[0]), float(f_total_vec[1]), float(f_total_vec[2])),
    )


def couple_flow_to_fea_bracket(
    assembly: "Assembly",
    pipe_name: str,
    bracket_name: str,
    flow_rate_l_s: float,
    inlet_pressure_bar: float = 2.0,
    bracket_fixed_face: str = "bottom",
    bracket_load_face: str = "top",
    mesh_size: float = 4.0,
    required_safety_factor: float = 2.0,
) -> Dict[str, Any]:
    """
    Complete CFD-to-FEA multi-physics execution:
    1. Analyzes fluid dynamics and thrust forces in the pipe route.
    2. Maps the resulting hydro-mechanical load vector onto the support bracket.
    3. Runs 3D linear elasticity FEA on the bracket.
    4. Evaluates structural safety under real fluid operational loads.
    """
    from ..macros.piping_macros import analyze_pipe_route_flow
    from ..analysis.fea import FEAStudy

    # 1. Evaluate pipe flow
    flow_res = analyze_pipe_route_flow(assembly, pipe_name=pipe_name, flow_rate_l_s=flow_rate_l_s)
    
    # Extract pipe inner diameter
    pipe_ref = assembly._parts[pipe_name]
    od = float(pipe_ref.node.parameters.get("outer_dia", 33.7))
    wt = float(pipe_ref.node.parameters.get("wall_thickness", 2.6))
    id_mm = max(1.0, od - 2.0 * wt)

    # 2. Compute bend fluid thrust
    thrust = calc_pipe_bend_fluid_thrust(
        inner_diameter_mm=id_mm,
        flow_rate_l_s=flow_rate_l_s,
        fluid_pressure_bar=inlet_pressure_bar,
        bend_angle_deg=90.0,
    )

    # 3. Setup and solve FEA on support bracket
    fea = assembly.add_fea_study(
        part_name=bracket_name,
        mesh_size=mesh_size,
    )
    fea.fix_face(bracket_fixed_face)
    fea.apply_force(face=bracket_load_face, force_vector=thrust.force_vector_n)
    fea_res = fea.solve()

    return {
        "pipe_name": pipe_name,
        "bracket_name": bracket_name,
        "flow_analysis": flow_res,
        "thrust_analysis": thrust.to_dict(),
        "fea_summary": {
            "max_von_mises_mpa": round(fea_res.max_von_mises_mpa, 2),
            "max_displacement_mm": round(fea_res.max_displacement_mm, 4),
            "safety_factor": round(fea_res.safety_factor, 2),
            "is_safe": fea_res.safety_factor >= required_safety_factor,
            "status": fea_res.status,
        },
        "raw_fea_result": fea_res,
    }
