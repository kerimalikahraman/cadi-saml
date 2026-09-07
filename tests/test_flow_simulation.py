"""
tests/test_flow_simulation.py

Comprehensive test suite for CADi SAML CFD, fluid mechanics, Darcy-Weisbach / Colebrook-White solvers,
piping macro flow integration, and PostBuildContract validation.
"""

import math
import pytest
from cadi_saml.simulation.units import Quantity, ensure_quantity
from cadi_saml.simulation.flow.fluid_properties import (
    get_water_properties,
    get_air_properties,
    get_hydraulic_oil_properties,
    resolve_fluid,
)
from cadi_saml.simulation.flow.pipe_flow import (
    solve_friction_factor_colebrook,
    analyze_pipe_flow,
)
from cadi_saml.simulation.flow.fittings import (
    FittingItem,
    calc_sudden_expansion_k,
    calc_sudden_contraction_k,
    calc_piping_system_loss,
)
from cadi_saml.simulation.flow.pump import analyze_pump_requirements
from cadi_saml.core.assembly import Assembly
from cadi_saml.macros.piping_macros import add_pipe_route, analyze_pipe_route_flow
from cadi_saml.validation.contract import PostBuildContract


# ==============================================================================
# 1. Physical Units and Dimensional Consistency Tests
# ==============================================================================

def test_units_conversion():
    # Pressure: bar to Pa and kPa
    q_p = Quantity(value=2.5, unit="bar", dimension="pressure")
    assert pytest.approx(q_p.to_si(), rel=1e-4) == 250000.0  # 2.5e5 Pa
    q_kpa = q_p.convert_to("kpa")
    assert pytest.approx(q_kpa.value, rel=1e-4) == 250.0

    # Flow Rate: l/s to m3/s and m3/h
    q_flow = Quantity(value=5.0, unit="l/s", dimension="flow_rate")
    assert pytest.approx(q_flow.to_si(), rel=1e-4) == 0.005
    q_m3h = q_flow.convert_to("m3/h")
    assert pytest.approx(q_m3h.value, rel=1e-4) == 18.0

    # Temperature: C to K
    q_temp = Quantity(value=20.0, unit="C", dimension="temperature")
    assert pytest.approx(q_temp.to_si(), rel=1e-4) == 293.15
    q_f = q_temp.convert_to("F")
    assert pytest.approx(q_f.value, rel=1e-4) == 68.0

    # Strict dimensional mismatch check
    with pytest.raises(ValueError):
        Quantity(value=10.0, unit="bar", dimension="force")


# ==============================================================================
# 2. Thermophysical Fluid Properties Database Tests
# ==============================================================================

def test_fluid_database_water():
    # Water at 20 C: density ~ 998 kg/m3, viscosity ~ 1.002e-3 Pa*s
    w20 = get_water_properties(20.0)
    assert 995.0 < w20.density < 1000.0
    assert 0.95e-3 < w20.dynamic_viscosity < 1.05e-3
    assert w20.vapor_pressure > 2000.0  # ~2.3 kPa

    # Water at 80 C: viscosity decreases significantly (~0.35e-3 Pa*s)
    w80 = get_water_properties(80.0)
    assert w80.density < w20.density
    assert w80.dynamic_viscosity < w20.dynamic_viscosity
    assert w80.vapor_pressure > 40000.0  # ~47 kPa


def test_fluid_database_air_and_oil():
    # Air at 20 C: density ~ 1.2 kg/m3
    air20 = get_air_properties(20.0)
    assert 1.15 < air20.density < 1.25
    assert 1.7e-5 < air20.dynamic_viscosity < 1.9e-5

    # Air viscosity increases with temperature (Sutherland's law)
    air100 = get_air_properties(100.0)
    assert air100.dynamic_viscosity > air20.dynamic_viscosity

    # Hydraulic oil VG46 at 40 C: kinematic viscosity ~ 46 cSt = 4.6e-5 m2/s
    oil40 = get_hydraulic_oil_properties(vg_grade=46, temp_c=40.0)
    assert pytest.approx(oil40.kinematic_viscosity * 1e6, rel=0.1) == 46.0

    # Generic resolver
    assert resolve_fluid("water").name == "water"
    assert resolve_fluid("hydraulic_oil_vg32").name == "hydraulic_oil_vg32"


# ==============================================================================
# 3. Colebrook-White and Pipe Flow Hydraulic Tests
# ==============================================================================

def test_colebrook_white_laminar_and_turbulent():
    # Laminar flow (Re = 1000): f = 64 / 1000 = 0.064
    f_lam = solve_friction_factor_colebrook(reynolds=1000.0, relative_roughness=0.001)
    assert pytest.approx(f_lam, rel=1e-3) == 0.064

    # Smooth pipe turbulent (Re = 1e5, eps/D = 0): Moody chart ~ 0.018
    f_turb_smooth = solve_friction_factor_colebrook(reynolds=1e5, relative_roughness=0.0)
    assert 0.017 < f_turb_smooth < 0.019

    # Rough pipe turbulent (Re = 1e5, eps/D = 0.002): Moody chart ~ 0.024
    f_turb_rough = solve_friction_factor_colebrook(reynolds=1e5, relative_roughness=0.002)
    assert 0.022 < f_turb_rough < 0.026


def test_analyze_pipe_flow():
    # Test case: 25 mm inner diameter, 10 m length, 1.5 L/s water flow
    res = analyze_pipe_flow(
        diameter_mm=25.0,
        length_mm=10000.0,
        flow_rate_l_s=1.5,
        fluid="water",
        temperature_c=20.0,
        material_roughness="commercial_steel",
    )
    assert res.flow_regime == "TURBULENT"
    assert res.reynolds > 50000.0
    assert 2.5 < res.velocity_m_s < 3.5  # v ~ 3.06 m/s
    assert res.pressure_drop_bar > 0.05
    assert res.wall_shear_stress_pa > 0.0

    # Conversion to structured AnalysisResult
    crit = res.to_analysis_result()
    assert crit.study_type == "pipe_flow"
    assert crit.status == "PASS"
    assert "DarcyWeisbachColebrookSolver" in crit.provenance.solver_name


def test_pipe_flow_automatic_resizing():
    # Intentionally small pipe (10 mm ID) with high flow (3 L/s water) causes massive pressure drop
    res = analyze_pipe_flow(
        diameter_mm=10.0,
        length_mm=5000.0,
        flow_rate_l_s=3.0,
        fluid="water",
        max_allowable_dp_bar=1.0,
    )
    assert res.pressure_drop_bar > 5.0
    # Solver must recommend a larger standard diameter
    assert res.recommended_diameter_mm is not None
    assert res.recommended_diameter_mm > 10.0


# ==============================================================================
# 4. Fittings and Minor Loss Tests
# ==============================================================================

def test_fittings_and_minor_losses():
    res = analyze_pipe_flow(
        diameter_mm=50.0,
        length_mm=20000.0,
        flow_rate_l_s=5.0,
        fluid="water",
    )
    # Add four 90-degree long radius elbows (K = 0.45 each) + one open gate valve (K = 0.17)
    fittings = [
        FittingItem(fitting_type="elbow_90_long_radius", count=4),
        FittingItem(fitting_type="valve_gate_open", count=1),
    ]
    sys_loss = calc_piping_system_loss(res, fittings)
    expected_k = 4 * 0.45 + 0.17
    assert pytest.approx(sys_loss["total_k_factor"], rel=1e-3) == expected_k
    assert sys_loss["minor_loss_bar"] > 0.0
    assert sys_loss["total_pressure_drop_bar"] > sys_loss["major_loss_bar"]


def test_sudden_expansion_and_contraction():
    # Expansion from 25mm to 50mm
    k_exp = calc_sudden_expansion_k(d_in_mm=25.0, d_out_mm=50.0)
    # K = (1 - (25/50)^2)^2 = (1 - 0.25)^2 = 0.75^2 = 0.5625
    assert pytest.approx(k_exp, rel=1e-3) == 0.5625

    # Contraction from 50mm to 25mm
    k_con = calc_sudden_contraction_k(d_in_mm=50.0, d_out_mm=25.0)
    # K = 0.5 * (1 - (25/50)^2) = 0.5 * 0.75 = 0.375
    assert pytest.approx(k_con, rel=1e-3) == 0.375


# ==============================================================================
# 5. Pump Sizing and Cavitation Tests
# ==============================================================================

def test_pump_analysis_and_cavitation():
    water = get_water_properties(20.0)
    # Flow: 4 L/s against 3 bar system pressure drop
    pump = analyze_pump_requirements(
        flow_rate_l_s=4.0,
        total_system_dp_bar=3.0,
        fluid=water,
        suction_pressure_bar=1.013,
        static_suction_lift_m=1.0,
        required_npsh_m=3.0,
    )
    assert pump.hydraulic_power_w > 1000.0  # ~1200 W
    assert pump.recommended_motor_power_kw >= 1.5
    assert not pump.cavitation_risk

    # High temperature (95 C water) with suction lift causes boiling / cavitation risk
    water_hot = get_water_properties(95.0)
    pump_hot = analyze_pump_requirements(
        flow_rate_l_s=4.0,
        total_system_dp_bar=3.0,
        fluid=water_hot,
        suction_pressure_bar=1.013,
        static_suction_lift_m=2.0,
        required_npsh_m=3.0,
    )
    assert pump_hot.cavitation_risk
    assert "HIGH CAVITATION RISK" in pump_hot.notes


# ==============================================================================
# 6. Piping CAD Macro and PostBuildContract Integration Test
# ==============================================================================

def test_piping_cad_route_and_flow_contract():
    asm = Assembly("cooling_circuit")
    # Add pump box and tank box
    asm.add_box("pump", length=80.0, width=80.0, height=100.0)
    asm.add_box("tank", length=120.0, width=120.0, height=150.0, origin=(400.0, 300.0, 50.0))

    # Add 3D pipe route connecting pump to tank
    pipe_info = asm.add_pipe_route(
        name="coolant_line",
        from_port="pump:top",
        to_port="tank:top",
        standard="DN25",  # OD 33.7mm, Wall 2.6mm -> ID ~ 28.5mm
    )
    assert pipe_info["pipe_name"] == "coolant_line"
    assert pipe_info["cut_length_mm"] > 500.0

    # 1. Run direct flow analysis on the 3D route
    flow_rep = asm.analyze_pipe_flow(
        pipe_name="coolant_line",
        flow_rate_l_s=1.0,
        fluid="water",
        max_allowable_dp_bar=0.5,
    )
    assert flow_rep["status"] == "PASS"
    assert flow_rep["num_bends"] >= 2
    assert flow_rep["total_pressure_drop_bar"] < 0.5

    # 2. Verify PostBuildContract with test_flow=True
    contract = PostBuildContract(asm)
    report = contract.verify(
        check_clash=False,
        test_step_roundtrip=False,
        test_flow=True,
        flow_max_pressure_drop_bar=0.5,
        strict=True,
    )
    assert report.passed
    assert "flow_simulation" in report.stages
    assert report.stages["flow_simulation"].passed

    # 3. Trigger contract failure with an unrealistically low max pressure drop limit
    report_fail = contract.verify(
        check_clash=False,
        test_step_roundtrip=False,
        test_flow=True,
        flow_max_pressure_drop_bar=0.0001,  # Unrealistically tight limit to force failure
        strict=True,
    )
    assert not report_fail.passed
    assert not report_fail.stages["flow_simulation"].passed
    assert len(report_fail.stages["flow_simulation"].errors) > 0
