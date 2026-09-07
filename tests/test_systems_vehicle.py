"""
tests/test_systems_vehicle.py

Comprehensive test suite for Phase 5 System-Level Engineering:
- Chassis Spaceframe & Ladder Rails (cadi_saml.systems.chassis)
- Hardpoint-based Kinematic Suspension (cadi_saml.systems.suspension)
- EV Battery Pack Enclosure & Cooling (cadi_saml.systems.battery)
- Coordinated VehiclePlatform Integration & CAD compilation
"""

import pytest
import numpy as np

from cadi_saml.systems.chassis import ChassisFrame, StructuralProfile
from cadi_saml.systems.suspension import DoubleWishboneSuspension, SuspensionHardpoints
from cadi_saml.systems.battery import BatteryPackEnclosure, PackElectricalConfig, CellSpecification
from cadi_saml.systems import VehiclePlatform
from cadi_saml.backend.occt_backend import OCCTBackend


# ==============================================================================
# 1. Chassis Spaceframe Tests
# ==============================================================================

def test_chassis_frame_synthesis_and_mass_distribution():
    chassis = ChassisFrame(
        name="test_ladder_chassis",
        wheelbase_mm=2800.0,
        track_width_mm=1600.0,
        frame_width_mm=1000.0,
        nominal_ground_clearance_mm=200.0,
    )
    chassis.build_ladder_frame(num_crossmembers=5)

    # 1. Check member count (2 longitudinal + 5 crossmembers = 7)
    assert len(chassis.members) == 7

    # 2. Mass & Center of Gravity
    mass_kg, (cog_x, cog_y, cog_z) = chassis.calculate_mass_and_cog()
    assert mass_kg > 50.0  # Realistic steel ladder frame
    # Lateral symmetry: CoG Y must be near 0.0
    assert pytest.approx(cog_y, abs=1e-3) == 0.0
    # Longitudinal CoG should be between front and rear overhang
    assert 500.0 < cog_x < 2000.0

    # 3. Axle Load Distribution under gravity
    loads = chassis.calculate_axle_load_distribution()
    assert loads["total_mass_kg"] == pytest.approx(mass_kg, rel=1e-3)
    assert loads["front_weight_percent"] + loads["rear_weight_percent"] == pytest.approx(100.0, abs=0.1)

    # 4. Torsional Stiffness FEA load case generation
    t_case = chassis.generate_torsional_stiffness_load_case(applied_torque_kNm=6.0)
    assert t_case["test_type"] == "torsional_stiffness"
    assert "rear_left_mount" in t_case["boundary_conditions"]
    assert "front_left_load" in t_case["boundary_conditions"]
    assert t_case["force_per_side_N"] > 0.0

    # 5. CAD Assembly generation
    asm = chassis.to_assembly()
    assert len(asm._parts) == 7


# ==============================================================================
# 2. Suspension Hardpoints & Kinematics Tests
# ==============================================================================

def test_suspension_hardpoints_and_kinematics():
    susp = DoubleWishboneSuspension(
        name="front_sla_suspension",
        max_jounce_mm=50.0,
        max_rebound_mm=50.0,
    )

    # 1. Static Geometry
    static = susp.calculate_static_angles()
    assert static["static_caster_deg"] > 0.0  # Positive caster for directional stability
    assert static["static_kingpin_deg"] > 0.0 # Positive KPI
    assert susp.upper_wishbone_length_mm < susp.lower_wishbone_length_mm  # Short-Long Arm (SLA)

    # 2. Kinematics Simulation across wheel travel
    jounce_state = susp.solve_kinematics_at_travel(dz_wheel=40.0)
    rebound_state = susp.solve_kinematics_at_travel(dz_wheel=-40.0)

    # Camber in jounce must become more negative (camber gain to resist roll)
    assert jounce_state.camber_deg < static["static_camber_deg"]
    assert rebound_state.camber_deg > static["static_camber_deg"]

    # Damper motion ratio
    assert 0.4 <= jounce_state.motion_ratio <= 1.0

    # 3. Design contract verification
    contract = susp.verify_kinematics()
    assert contract["passed"] is True
    assert contract["max_bump_steer_deg"] < 0.5

    # 4. CAD Assembly generation
    asm = susp.to_assembly()
    assert len(asm._parts) >= 4  # upper, lower, knuckle, damper


# ==============================================================================
# 3. Battery Pack Enclosure & Cooling Tests
# ==============================================================================

def test_battery_pack_enclosure_and_cooling_flow():
    # 96S 4P pack with 21700 cells
    spec = CellSpecification(nominal_voltage_v=3.65, capacity_ah=4.8, mass_grams=68.0)
    config = PackElectricalConfig(series_cells=96, parallel_cells=4, cell=spec)
    pack = BatteryPackEnclosure(
        name="skate_battery",
        electrical_config=config,
        rows=16,
        cols=24,
    )

    # 1. Electrical Capacity checks
    assert config.total_cell_count == 384
    assert pytest.approx(config.nominal_voltage_v, abs=1.0) == 350.4  # ~350V
    assert config.total_capacity_kwh > 5.0  # Module/sub-pack capacity

    # 2. Physical sizing
    assert pack.outer_length > 600.0
    assert pack.outer_width > 400.0
    assert pack.estimated_total_pack_mass_kg > config.total_cell_mass_kg

    # 3. Coupled Cooling Flow Simulation
    flow_res = pack.analyze_thermal_cooling_flow(volumetric_flow_rate_lpm=12.0, coolant_temperature_c=25.0)
    assert flow_res["pressure_drop_bar"] < 1.0  # Clean low pressure drop
    assert flow_res["flow_velocity_m_s"] > 0.1
    assert flow_res["reynolds_number"] > 1000.0

    # 4. Clearances and CAD Assembly
    clearances = pack.get_keep_out_and_service_clearances()
    assert "msd" in clearances
    assert "hv_terminals" in clearances

    asm = pack.to_assembly()
    assert len(asm._parts) >= 2  # Tray + Lid


# ==============================================================================
# 4. Unified VehiclePlatform Integration & CAD Compilation
# ==============================================================================

def test_integrated_vehicle_platform_and_cad_compile():
    platform = VehiclePlatform(
        name="modular_ev_skate",
        wheelbase_mm=2800.0,
        track_width_mm=1600.0,
    )

    # 1. Multi-system Mass and Weight Balance
    balance = platform.evaluate_vehicle_mass_and_balance()
    assert balance["total_platform_mass_kg"] > 150.0
    # Balance should be close to 50:50 (+/- 5%)
    assert 45.0 <= balance["front_weight_percent"] <= 55.0
    assert balance["ideal_balance_within_limits"] is True

    # 2. Unified Contract Verification
    contracts = platform.verify_design_contracts()
    assert contracts["passed"] is True
    assert contracts["chassis_clearances"]["passed"] is True
    assert contracts["front_suspension"]["passed"] is True
    assert contracts["rear_suspension"]["passed"] is True

    # 3. Full CAD Compilation to OpenCASCADE solids
    full_asm = platform.to_assembly()
    assert len(full_asm._parts) >= 15  # Chassis (7) + Battery (2) + Front Susp (4) + Rear Susp (4) = 17 parts

    backend = OCCTBackend()
    compiled_solids = backend.compile(full_asm.to_ir())
    assert len(compiled_solids) >= 15
    for shape in compiled_solids.values():
        assert not shape.IsNull()
