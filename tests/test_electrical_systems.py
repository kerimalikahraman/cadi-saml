"""
tests/test_electrical_systems.py

Unit tests for electromechanical wire harness and DIN rail enclosures:
- Wire harness routing, ampacity, and voltage drop calculations
- Cable minimum bend radius rule checking (R_bend >= 6 * D)
- DIN rail modular layout, space occupancy, and thermal airflow sizing
- 3D CAD Assembly synthesis and OCCT solid compilation
"""

import pytest
from cadi_saml.systems.electrical import (
    CableSpecification,
    WireHarnessRoute,
    DINComponent,
    DINRailEnclosure,
)
from cadi_saml.backend.occt_backend import OCCTBackend


def test_wire_harness_voltage_drop_and_ampacity():
    # 2.5 mm2 copper cable, 230V single phase, 16A load, 15m route
    cable = CableSpecification(
        name="control_power_wire",
        cross_section_mm2=2.5,
        outer_diameter_mm=3.6,
        rated_current_a=24.0,
        voltage_rating_v=600.0,
    )

    waypoints = [
        (0.0, 0.0, 0.0),
        (5000.0, 0.0, 0.0),
        (5000.0, 5000.0, 0.0),
        (5000.0, 5000.0, 5000.0),
    ]  # 15 meters total

    harness = WireHarnessRoute(
        name="cabinet_to_pump_feed",
        cable=cable,
        waypoints=waypoints,
        operating_current_a=16.0,
        supply_voltage_v=230.0,
    )

    assert pytest.approx(harness.total_length_m, abs=0.1) == 15.0

    res = harness.analyze_voltage_drop()
    assert res["ampacity_ok"] is True
    # 2x 15m = 30m loop. Resistance = 30 * (0.0175 / 2.5) = 0.21 ohm. V_drop = 16 * 0.21 = 3.36V (~1.46%)
    assert res["voltage_drop_percent"] < 3.0
    assert res["compliant_with_3pct_rule"] is True
    assert res["is_safe"] is True


def test_wire_harness_bend_radius_check():
    cable = CableSpecification(
        name="flex_sensor_cable",
        cross_section_mm2=0.75,
        outer_diameter_mm=5.0,  # Min bend radius = 30.0 mm
    )

    # Valid route with generous spacing (> 30mm)
    valid_waypoints = [
        (0.0, 0.0, 0.0),
        (100.0, 0.0, 0.0),
        (100.0, 100.0, 0.0),
    ]
    harness_valid = WireHarnessRoute(name="safe_harness", cable=cable, waypoints=valid_waypoints)
    check_valid = harness_valid.verify_bend_radii()
    assert check_valid["passed"] is True

    # Violating route with a tiny 5mm segment before 90-deg turn
    violating_waypoints = [
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        (5.0, 5.0, 0.0),
    ]
    harness_violating = WireHarnessRoute(name="sharp_harness", cable=cable, waypoints=violating_waypoints)
    check_violating = harness_violating.verify_bend_radii()
    assert check_violating["passed"] is False
    assert check_violating["violations_count"] >= 1


def test_din_rail_enclosure_space_and_thermal():
    enclosure = DINRailEnclosure(
        name="main_plc_cabinet",
        width_mm=600.0,
        height_mm=800.0,
        depth_mm=250.0,
        num_din_rails=3,
    )

    # Add components to Rail 0 (Top rail: MCBs & Power supply)
    enclosure.add_component(0, DINComponent(name="main_breaker", component_type="mcb", width_mm=54.0, power_loss_watts=4.5))
    enclosure.add_component(0, DINComponent(name="psu_24v", component_type="power_supply", width_mm=70.0, power_loss_watts=15.0))

    # Add components to Rail 1 (Middle rail: Contactors)
    for i in range(4):
        enclosure.add_component(1, DINComponent(name=f"contactor_{i+1}", component_type="contactor", width_mm=45.0, power_loss_watts=6.0))

    # Add components to Rail 2 (Bottom rail: Terminal blocks)
    for i in range(20):
        enclosure.add_component(2, DINComponent(name=f"term_{i+1}", component_type="terminal_block", width_mm=6.0, power_loss_watts=0.2))

    # 1. Space Occupancy Check
    occ = enclosure.calculate_rail_space_occupancy()
    assert occ["all_rails_fit"] is True
    assert occ["total_component_count"] == 26
    assert occ["total_internal_heat_loss_watts"] > 40.0

    # 2. Thermal Cooling Airflow Sizing
    thermal = enclosure.estimate_cabinet_cooling_airflow(ambient_temperature_c=30.0, max_internal_temperature_c=45.0)
    assert thermal["delta_t_c"] == 15.0
    assert thermal["required_airflow_m3_per_hour"] > 0.0

    # 3. 3D Assembly & OpenCASCADE Solid compilation
    asm = enclosure.to_assembly()
    assert len(asm._parts) >= 20

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert len(solids) >= 20
    for shape in solids.values():
        assert not shape.IsNull()
