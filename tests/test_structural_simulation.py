"""
tests/test_structural_simulation.py

Comprehensive test suite for CADi SAML extended structural simulation:
- 3D FEA and analytical modal vibration / resonance risk
- Euler & Johnson column buckling
- High-cycle fatigue, Marin modification factors, Goodman diagrams & S-N life
- CFD momentum thrust & coupled fluid-structure FEA interaction
"""

import math
import pytest
import numpy as np

from cadi_saml.simulation.structural.modal import (
    calc_cantilever_beam_natural_frequencies,
    ModalStudy,
)
from cadi_saml.simulation.structural.buckling import (
    analyze_column_buckling,
)
from cadi_saml.simulation.structural.fatigue import (
    analyze_fatigue_life,
    calc_marin_surface_factor,
    calc_marin_size_factor,
)
from cadi_saml.simulation.coupling import (
    calc_pipe_bend_fluid_thrust,
    couple_flow_to_fea_bracket,
)
from cadi_saml.analysis.materials import get_material
from cadi_saml.core.assembly import Assembly


# ==============================================================================
# 1. Modal Vibration and Resonance Tests
# ==============================================================================

def test_analytical_cantilever_beam_modal():
    # Steel cantilever beam: L=500mm, b=20mm, h=40mm
    # Material: S235JR (E=210 GPa, rho=7850 kg/m3)
    freqs = calc_cantilever_beam_natural_frequencies(
        length_mm=500.0,
        width_mm=20.0,
        height_mm=40.0,
        material="S235JR",
        num_modes=3,
    )
    assert len(freqs) == 3
    # Fundamental frequency for H=40mm, L=500mm cantilever beam is ~133.7 Hz
    f1, f2, f3 = freqs
    assert 120.0 < f1 < 150.0
    # Mode ratios for cantilever beam: f2/f1 ≈ 6.27, f3/f1 ≈ 17.55
    assert pytest.approx(f2 / f1, rel=0.05) == 6.27
    assert pytest.approx(f3 / f1, rel=0.05) == 17.55


def test_3d_fea_modal_study():
    asm = Assembly("modal_test_beam")
    asm.add_box("beam", length=200.0, width=20.0, height=20.0)

    fea = asm.add_fea_study("beam", mesh_size=8.0, material="S235JR")
    fea.fix_face("x_min")  # Clamp root face

    # Create and solve 3D ModalStudy via factory
    modal = ModalStudy.from_fea_study(fea)

    # Solve first 4 modes and check against operating motor RPM of 3000 RPM (50 Hz)
    result = modal.solve(num_modes=4, operating_rpm=[3000.0], resonance_tolerance=0.15)
    assert len(result.modes) == 4
    assert result.fundamental_frequency_hz > 0.0
    # Higher modes should have strictly increasing frequencies
    for i in range(len(result.modes) - 1):
        assert result.modes[i + 1].frequency_hz >= result.modes[i].frequency_hz

    rep_dict = result.to_dict()
    assert rep_dict["part_name"] == "beam"
    assert len(rep_dict["modes"]) == 4


# ==============================================================================
# 2. Compressive Column Stability and Buckling Tests
# ==============================================================================

def test_euler_elastic_buckling():
    # Slender steel column: Solid round rod D=15mm, L=1000mm (pinned-pinned)
    # Area ~ 176.7 mm2, I ~ 2485 mm4, r ~ 3.75 mm -> lambda = 1000 / 3.75 ~ 267 >> lambda_c ~ 100
    res = analyze_column_buckling(
        column_name="slender_strut",
        length_mm=1000.0,
        cross_section_type="solid_round",
        dimensions={"diameter": 15.0},
        material="S235JR",
        end_condition="pinned_pinned",
        applied_compressive_load_n=2000.0,  # 2 kN applied
        required_safety_factor=2.0,
    )
    assert res.buckling_regime == "EULER_ELASTIC"
    assert res.slenderness_ratio > res.critical_slenderness
    # Euler theoretical load: P_cr = pi^2 * E * I / L^2
    # P_cr = pi^2 * 210000 * 2485 / 1e6 ~ 5150 N ~ 5.15 kN
    assert 4800.0 < res.critical_load_n < 5500.0
    assert res.safety_factor is not None
    assert res.safety_factor > 2.0
    assert res.is_safe


def test_johnson_inelastic_buckling():
    # Stocky short steel column: Solid square 50x50mm, L=300mm (fixed-fixed)
    # Slenderness is very small -> Johnson parabolic regime
    res = analyze_column_buckling(
        column_name="short_pedestal",
        length_mm=300.0,
        cross_section_type="solid_square",
        dimensions={"width": 50.0},
        material="S235JR",
        end_condition="fixed_fixed",
        applied_compressive_load_n=400000.0,  # 400 kN applied
    )
    assert res.buckling_regime == "JOHNSON_INELASTIC"
    assert res.slenderness_ratio < res.critical_slenderness
    assert res.critical_load_n > 500000.0  # High capacity


def test_buckling_failure_detection():
    # Applied load exceeding capacity must flag failure
    res = analyze_column_buckling(
        column_name="overloaded_column",
        length_mm=800.0,
        cross_section_type="solid_round",
        dimensions={"diameter": 12.0},
        applied_compressive_load_n=10000.0,  # High load
        required_safety_factor=2.5,
    )
    assert not res.is_safe
    assert res.safety_factor < 2.5
    assert "BUCKLING RISK" in res.notes


# ==============================================================================
# 3. High-Cycle Fatigue and S-N Life Tests
# ==============================================================================

def test_marin_modification_factors():
    sut = 600.0  # MPa
    ka_ground = calc_marin_surface_factor("ground", sut)
    ka_machined = calc_marin_surface_factor("machined", sut)
    ka_forged = calc_marin_surface_factor("as_forged", sut)

    # Polished/ground finish must have higher endurance factor than forged
    assert ka_ground > ka_machined > ka_forged

    kb_small = calc_marin_size_factor(10.0)
    kb_large = calc_marin_size_factor(80.0)
    assert kb_small > kb_large  # Smaller parts have less volumetric flaw probability


def test_fatigue_goodman_and_cycles():
    # Cyclic loading: sigma_max = 120 MPa, sigma_min = 20 MPa (sigma_a = 50 MPa, sigma_m = 70 MPa)
    res_safe = analyze_fatigue_life(
        part_name="drive_shaft",
        sigma_max_mpa=120.0,
        sigma_min_mpa=20.0,
        material="42CrMo4",  # High strength alloy steel (Sut ~ 1000 MPa, Sy ~ 750 MPa)
        surface_finish="machined",
        part_diameter_mm=30.0,
        loading_type="bending",
        required_safety_factor=1.5,
    )
    assert res_safe.goodman_safety_factor > 1.5
    assert res_safe.is_infinite_life
    assert res_safe.status == "PASS"

    # Severe cyclic stress causing finite fatigue life
    res_finite = analyze_fatigue_life(
        part_name="high_stress_link",
        sigma_max_mpa=480.0,
        sigma_min_mpa=100.0,
        material="S235JR",  # Mild structural steel (Sut ~ 360 MPa, Sy ~ 235 MPa)
        surface_finish="hot_rolled",
        part_diameter_mm=25.0,
        required_safety_factor=1.5,
    )
    assert res_finite.status == "FAIL"
    assert not res_finite.is_infinite_life
    assert res_finite.estimated_cycles_to_failure < 1e6


# ==============================================================================
# 4. CFD Momentum Thrust and Coupled FEA Tests
# ==============================================================================

def test_pipe_bend_fluid_thrust_calculation():
    # DN50 pipe (ID ~ 54 mm), water flow 8 L/s, pressure 4 bar, 90 deg bend
    thrust = calc_pipe_bend_fluid_thrust(
        inner_diameter_mm=54.0,
        flow_rate_l_s=8.0,
        fluid_pressure_bar=4.0,
        bend_angle_deg=90.0,
        fluid_density_kg_m3=998.2,
    )
    # Total thrust should be non-zero and properly vector-summed
    assert thrust.resultant_thrust_n > 100.0  # Hundreds of Newtons
    assert thrust.momentum_force_n > 0.0
    assert thrust.pressure_force_n > 0.0
    assert len(thrust.force_vector_n) == 3


def test_coupled_flow_to_fea_bracket():
    asm = Assembly("pumping_station")
    # Add pipe route between two semantic points
    asm.add_box("inlet_nozzle", length=50.0, width=50.0, height=80.0)
    asm.add_box("outlet_tank", length=80.0, width=80.0, height=120.0, origin=(300.0, 250.0, 50.0))
    asm.add_pipe_route(
        name="discharge_pipe",
        from_port="inlet_nozzle:top",
        to_port="outlet_tank:top",
        standard="DN32",
    )

    # Add steel support bracket under the pipe
    asm.add_box("support_bracket", length=40.0, width=40.0, height=60.0, origin=(150.0, 100.0, 0.0))

    # Couple flow thrust to the support bracket FEA
    res = couple_flow_to_fea_bracket(
        assembly=asm,
        pipe_name="discharge_pipe",
        bracket_name="support_bracket",
        flow_rate_l_s=3.0,
        inlet_pressure_bar=3.5,
        bracket_fixed_face="bottom",
        bracket_load_face="top",
        mesh_size=10.0,
        required_safety_factor=2.0,
    )

    assert "flow_analysis" in res
    assert "thrust_analysis" in res
    assert "fea_summary" in res
    fea_sum = res["fea_summary"]
    assert fea_sum["max_von_mises_mpa"] > 0.0
    assert fea_sum["max_displacement_mm"] >= 0.0
    assert fea_sum["safety_factor"] > 0.0
