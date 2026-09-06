"""
tests/test_catia_features.py
============================
Unit test suite for CATIA-grade engineering modules:
1. Composites Design (CPD): Classical Laminate Theory (CLT) & Tsai-Wu Failure
2. KnowledgeWare Design Rules Guard Engine & LLM Repair Suggestions
3. Class-A Surface Continuity Inspector (G0/G1/G2)
4. DMU Kinematics Swept Envelope & Dynamic Clearance Collision Detection
"""

import math
import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    LaminateLayup,
    CompositeMaterial,
    COMPOSITE_MATERIALS,
    add_composite_panel,
    DesignRuleEngine,
    check_design_rules,
    HoleEdgeDistanceRule,
    check_surface_continuity,
    compute_swept_envelope,
    check_dynamic_clearance,
)


def test_composites_clt_and_failure():
    """Test Classical Laminate Theory ABD matrices, quasi-isotropy, and Tsai-Wu failure."""
    # 1. Quasi-isotropic aerospace stacking sequence: [0, 45, -45, 90]_s
    layup = LaminateLayup(
        angles=[0.0, 45.0, -45.0, 90.0],
        material="Carbon_T300_Epoxy",
        ply_thickness=0.20,
        symmetric=True,
    )

    assert layup.num_plies == 8
    assert abs(layup.total_thickness - 1.60) < 1e-6

    # Symmetric laminates must have coupling matrix B ~= 0
    assert np_max_abs(layup.B) < 1e-4

    # Quasi-isotropic laminates must have Ex ~= Ey
    assert abs(layup.Ex - layup.Ey) / layup.Ex < 0.05

    # 2. Evaluate Tsai-Wu failure index under moderate in-plane tension
    # Nx = 150 N/mm -> stress sigma_x ~= 150 / 1.6 = 93.75 MPa (well below 1500 MPa strength)
    res = layup.evaluate_failure(Nx=150.0, Ny=0.0, Nxy=0.0)
    assert res["status"] == "PASS"
    assert res["max_tsai_wu_index"] < 1.0
    assert res["safety_factor"] > 1.0

    # 3. Add 3D composite panel to assembly
    asm = Assembly(name="composite_wing_panel")
    panel_report = asm.add_composite_panel(
        name="upper_skin",
        length=250.0,
        width=120.0,
        material="Carbon_T300_Epoxy",
        symmetric=True,
    )
    assert "upper_skin" in asm._parts
    assert "tooling_surface_bottom" in asm._parts["upper_skin"].ports
    assert "bag_surface_top" in asm._parts["upper_skin"].ports

    # Verify B-Rep compile
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "upper_skin" in solids
    assert not solids["upper_skin"].IsNull()


def test_knowledgeware_design_rules():
    """Test KnowledgeWare design rules and AI self-correction prompt generation."""
    # 1. Non-compliant assembly: hole placed too close to the edge
    asm_violating = Assembly(name="violating_bracket")
    asm_violating.add_box(name="flange_plate", length=50.0, width=50.0, height=5.0)
    # Add hole with dia 8mm, center at x=23mm (only 2mm away from 25mm boundary, but req is >= 1.5*8=12mm)
    asm_violating._parts["flange_plate"].node.parameters["holes"] = [
        {"x": 23.0, "y": 0.0, "diameter": 8.0}
    ]

    report = asm_violating.check_design_rules()
    assert report["passed"] is False
    assert report["error_count"] >= 1
    assert len(report["violations"]) >= 1
    assert "RULE_HOLE_EDGE_DISTANCE" in report["violations"][0]["rule_id"]
    assert "LLM" in report["llm_repair_prompt"] or "Action:" in report["llm_repair_prompt"]

    # 2. Compliant assembly: hole centered with safe margin
    asm_safe = Assembly(name="safe_bracket")
    asm_safe.add_box(name="flange_plate", length=50.0, width=50.0, height=5.0)
    # Hole at center (0, 0): distance to edge is 25mm >= 12mm
    asm_safe._parts["flange_plate"].node.parameters["holes"] = [
        {"x": 0.0, "y": 0.0, "diameter": 8.0}
    ]
    safe_report = asm_safe.check_design_rules()
    assert safe_report["passed"] is True
    assert safe_report["error_count"] == 0
    assert safe_report["score_percent"] == 100.0


def test_class_a_surface_continuity():
    """Test G0/G1 surface continuity inspection on B-Rep models."""
    asm = Assembly(name="continuity_check")
    # Sharp box: all adjacent faces meet at 90° angle (G0 crease)
    asm.add_box(name="test_cube", length=20.0, width=20.0, height=20.0)

    report = asm.check_surface_continuity(part_name="test_cube")
    assert report["total_shared_seams"] == 12
    assert report["g0_sharp_creases_count"] == 12
    assert report["g1_tangent_edges_count"] == 0
    assert abs(report["max_tangent_deviation_deg"] - 90.0) < 1.0
    assert report["class_a_rating"] == "PRISMATIC_FACETED"


def test_dmu_swept_envelope_and_dynamic_clearance():
    """Test DMU motion swept bounding volume and dynamic clash detection."""
    asm = Assembly(name="dmu_mechanism")
    # Rotating crank arm extending from X=0 to X=30 (origin at center x=15)
    asm.add_box(name="crank_arm", length=30.0, width=10.0, height=10.0, origin=(15.0, 0.0, 0.0))

    # Stationary obstacle placed outside rotation radius (r=30mm, placed at x=50mm)
    asm.add_box(name="safe_housing", length=15.0, width=15.0, height=15.0, origin=(50.0, 0.0, 0.0))

    # Stationary obstacle placed inside rotation path (placed at x=20mm)
    asm.add_box(name="clashing_pin", length=10.0, width=10.0, height=10.0, origin=(15.0, 0.0, 0.0))

    # 1. Test Swept Envelope calculation
    envelope = asm.compute_swept_envelope(
        moving_part="crank_arm",
        axis=(0.0, 0.0, 1.0),
        origin=(0.0, 0.0, 0.0),
        angle_range=(0.0, 360.0),
        steps=12,
    )
    assert envelope["moving_part"] == "crank_arm"
    # Full rotation of 30mm arm sweeps at least dx >= 50mm, dy >= 50mm
    dims = envelope["swept_envelope_dimensions_mm"]
    assert dims["dx"] >= 50.0
    assert dims["dy"] >= 50.0

    # 2. Dynamic Clearance Check with safe housing -> PASS
    safe_clearance = asm.check_dynamic_clearance(
        moving_part="crank_arm",
        static_part="safe_housing",
        axis=(0.0, 0.0, 1.0),
        origin=(0.0, 0.0, 0.0),
        angle_range=(0.0, 360.0),
        steps=12,
        min_clearance_mm=2.0,
    )
    assert safe_clearance["has_clash"] is False
    assert safe_clearance["status"] == "PASS"
    assert safe_clearance["min_dynamic_clearance_mm"] >= 10.0

    # 3. Dynamic Clearance Check with clashing pin -> COLLISION
    clash_clearance = asm.check_dynamic_clearance(
        moving_part="crank_arm",
        static_part="clashing_pin",
        axis=(0.0, 0.0, 1.0),
        origin=(0.0, 0.0, 0.0),
        angle_range=(0.0, 360.0),
        steps=12,
    )
    assert clash_clearance["has_clash"] is True
    assert clash_clearance["status"] == "COLLISION"
    assert len(clash_clearance["clash_angles_deg"]) >= 1


def np_max_abs(matrix):
    import numpy as np
    return float(np.max(np.abs(matrix)))
