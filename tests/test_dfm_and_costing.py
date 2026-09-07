"""
tests/test_dfm_and_costing.py

Unit tests for Design for Manufacturing (DFM) rules and machining cost estimation:
- CNC Hole aspect ratio checks (L/D limits, gun drilling warnings)
- Sheet metal bend radius, flange length, and hole proximity rules
- Rough machining cycle time (MRR) and manufacturing cost breakdown
"""

import pytest
from cadi_saml.systems.dfm import DFMAnalyzer


def test_cnc_hole_aspect_ratio_rules():
    dfm = DFMAnalyzer()

    # 1. Standard optimal hole: Dia=10mm, Depth=30mm (L/D = 3.0)
    std_check = dfm.check_cnc_hole_drilling(diameter_mm=10.0, depth_mm=30.0)
    assert std_check.passed is True
    assert std_check.score == 100.0
    assert len(std_check.warnings) == 0
    assert len(std_check.errors) == 0

    # 2. Deep hole: Dia=10mm, Depth=60mm (L/D = 6.0) -> Warning for peck drilling
    deep_check = dfm.check_cnc_hole_drilling(diameter_mm=10.0, depth_mm=60.0)
    assert deep_check.passed is True
    assert deep_check.score < 100.0
    assert any("peck drilling" in w.lower() for w in deep_check.warnings)

    # 3. Severe hole: Dia=4mm, Depth=40mm (L/D = 10.0 > 8.0) -> Error and tooling recommendation
    severe_check = dfm.check_cnc_hole_drilling(diameter_mm=4.0, depth_mm=40.0)
    assert severe_check.passed is False
    assert len(severe_check.errors) >= 1
    assert any("aspect ratio" in e.lower() for e in severe_check.errors)
    assert len(severe_check.recommendations) >= 1


def test_sheet_metal_bending_rules():
    dfm = DFMAnalyzer()

    # 1. Valid bend: t=2.0mm, r=2.5mm, flange=12mm (min flange = 4*2 = 8mm)
    valid_bend = dfm.check_sheet_metal_bend(
        sheet_thickness_mm=2.0,
        bend_radius_mm=2.5,
        flange_length_mm=12.0,
        hole_edge_distance_mm=15.0,
    )
    assert valid_bend.passed is True
    assert valid_bend.score == 100.0

    # 2. Defective bend: t=3.0mm, r=1.5mm (< t -> cracking), flange=8.0mm (< 12mm)
    defective_bend = dfm.check_sheet_metal_bend(
        sheet_thickness_mm=3.0,
        bend_radius_mm=1.5,
        flange_length_mm=8.0,
        hole_edge_distance_mm=5.0,  # Too close to bend
    )
    assert defective_bend.passed is False
    assert len(defective_bend.errors) >= 2  # radius and flange
    assert any("cracking" in e.lower() for e in defective_bend.errors)
    assert any("flange length" in e.lower() for e in defective_bend.errors)
    assert any("too close to bend" in w.lower() for w in defective_bend.warnings)


def test_machining_cost_and_mrr_estimation():
    dfm = DFMAnalyzer(machine_hour_rate_usd=80.0, setup_time_hours=0.5)

    # 100 x 60 x 25 mm bracket in Aluminum 6061 with 40% removed volume
    stock_bbox = (100.0, 60.0, 25.0)
    final_vol_mm3 = 100.0 * 60.0 * 25.0 * 0.6  # 90,000 mm3

    # Cost for single prototype (qty=1)
    cost_proto = dfm.estimate_machining_cost(
        part_volume_mm3=final_vol_mm3,
        bounding_box_mm=stock_bbox,
        material="aluminum_6061",
        quantity=1,
    )

    assert cost_proto.material_name == "aluminum_6061"
    assert cost_proto.part_mass_kg > 0.0
    assert cost_proto.stock_mass_kg > cost_proto.part_mass_kg
    assert cost_proto.raw_material_cost > 0.0
    assert cost_proto.machining_time_minutes > 0.0
    assert cost_proto.setup_cost == 40.0  # 0.5h * $80/h / 1
    assert cost_proto.total_cost > cost_proto.setup_cost

    # Cost for production batch (qty=50) -> Setup amortized across 50 parts
    cost_batch = dfm.estimate_machining_cost(
        part_volume_mm3=final_vol_mm3,
        bounding_box_mm=stock_bbox,
        material="aluminum_6061",
        quantity=50,
    )
    assert cost_batch.setup_cost == 40.0 / 50.0  # $0.80 per part
    assert cost_batch.total_cost < cost_proto.total_cost
