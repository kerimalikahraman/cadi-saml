"""
tests.test_strict_mode
======================
Unit tests verifying Strict Mode enforcement across all CADi-SAML macros:
- Zero hallucinated geometry / silent fallbacks.
- Missing, unknown, or contradictory parameters raise CADISpecificationError.
- Specification provenance tracking.
"""

import pytest
from cadi_saml.core.assembly import Assembly
from cadi_saml.core.exceptions import CADISpecificationError
from cadi_saml.ir.nodes import ProvenanceRecord
from cadi_saml.macros.hole_wizard import add_threaded_hole
from cadi_saml.macros.piping_macros import add_pipe_route
from cadi_saml.macros.planetary_macros import add_planetary_stage
from cadi_saml.macros.cam_macros import add_disk_cam, evaluate_motion_law
from cadi_saml.macros.shaft_features import add_shaft_keyway, add_circlip_groove


def test_hole_wizard_strict_mode():
    """Hole wizard must raise CADISpecificationError for unknown thread standards."""
    asm = Assembly("TestStrictHole")
    asm.add_box("base", 100, 100, 30)

    # Valid thread standard
    add_threaded_hole(asm, target_part="base", thread="M8", depth=15.0)
    assert any("tap" in port_name for port_name in asm._ir.parts["base"].ports)

    # Unknown thread standard must NOT silently fallback to M8
    with pytest.raises(CADISpecificationError) as exc_info:
        add_threaded_hole(asm, target_part="base", thread="UNKNOWN_THREAD_99")
    
    err = exc_info.value
    assert err.parameter_name == "thread"
    assert err.provided_value == "UNKNOWN_THREAD_99"
    assert "M8" in err.valid_options
    assert err.suggested_fix is not None
    assert "error_type" in err.to_dict()


def test_piping_macros_strict_mode():
    """Piping macro must raise CADISpecificationError for degenerate route or invalid standard."""
    asm = Assembly("TestStrictPipe")

    # Coincident route points
    with pytest.raises(CADISpecificationError) as exc_info:
        add_pipe_route(asm, "bad_pipe", from_port=(0, 0, 0), to_port=(0, 0, 0), standard="DN25")
    assert exc_info.value.parameter_name == "route_points"

    # Degenerate waypoints (< 2 points)
    with pytest.raises(CADISpecificationError) as exc_info2:
        add_pipe_route(asm, "bad_pipe_wp", from_port=(0, 0, 0), to_port=(100, 0, 0), waypoints=[(0, 0, 0)], standard="DN25")
    assert exc_info2.value.parameter_name == "route_points"

    # Unknown pipe standard
    with pytest.raises(CADISpecificationError) as exc_info3:
        add_pipe_route(asm, "unknown_pipe", from_port=(0, 0, 0), to_port=(100, 0, 0), standard="UNKNOWN_DN999")
    assert exc_info3.value.parameter_name == "standard"


def test_planetary_macro_strict_mode():
    """Planetary gear macro must raise CADISpecificationError when teeth cannot be solved."""
    asm = Assembly("TestStrictPlanetary")

    # Valid ratio
    res = add_planetary_stage(asm, "valid_stage", module=2.0, ratio=4.0)
    assert res["ratio"] == 4.0
    assert res["sun_teeth"] > 0
    assert res["ring_teeth"] == res["sun_teeth"] + 2 * res["planet_teeth"]

    # Impossible gear ratio (e.g. ratio < 2.0 is mechanically unsolvable for fixed ring)
    with pytest.raises(CADISpecificationError) as exc_info:
        add_planetary_stage(asm, "impossible_stage", module=2.0, ratio=1.2)
    assert exc_info.value.parameter_name == "ratio"


def test_cam_macro_strict_mode():
    """Cam macro must raise CADISpecificationError for unknown motion laws."""
    asm = Assembly("TestStrictCam")

    # Valid motion law evaluation
    s, v, a = evaluate_motion_law("cycloidal", 0.5, lift=10.0)
    assert abs(s - 5.0) < 1e-4

    # Unknown motion law must NOT fall back to linear
    with pytest.raises(CADISpecificationError) as exc_info:
        evaluate_motion_law("magic_polynomial_law", 0.5, lift=10.0)
    assert exc_info.value.parameter_name == "law"
    assert "cycloidal" in exc_info.value.valid_options

    # Unknown motion law in add_disk_cam must also raise CADISpecificationError
    with pytest.raises(CADISpecificationError) as exc_info2:
        add_disk_cam(
            asm,
            "invalid_cam",
            segments=[
                {"type": "rise", "angle_deg": 180.0, "law": "unknown_law"},
                {"type": "fall", "angle_deg": 180.0, "law": "unknown_law"},
            ],
        )
    assert exc_info2.value.parameter_name == "law"


def test_specification_provenance_tracking():
    """Parameters must track full structured provenance with all mandatory fields."""
    asm = Assembly("TestProvenance")
    box = asm.add_box("bracket", 100, 50, 20)

    # Add full structured provenance trace via fluent interface
    box.track_provenance(
        parameter="length",
        source="llm_json",
        source_ref="payload.dimensions.length_mm",
        original_value=100.0,
        effective_value=100.0,
        unit="mm",
        transformation="exact",
        confidence=0.99,
        details={"prompt_field": "chassis_length"},
    )

    prov = box.node.spec_provenance
    assert "length" in prov
    assert prov["length"]["source"] == "llm_json"
    assert prov["length"]["source_ref"] == "payload.dimensions.length_mm"
    assert prov["length"]["original_value"] == 100.0
    assert prov["length"]["effective_value"] == 100.0
    assert prov["length"]["unit"] == "mm"
    assert prov["length"]["transformation"] == "exact"
    assert prov["length"]["confidence"] == 0.99
    assert prov["length"]["details"]["prompt_field"] == "chassis_length"
    assert prov["length"]["value"] == 100.0

    # Direct ProvenanceRecord creation on PartNode
    rec = box.node.track_provenance(
        parameter="width",
        source="catalog",
        source_ref="DIN 1025-1",
        original_value=50.0,
        effective_value=50.0,
        unit="mm",
        transformation="catalog_lookup",
        confidence=0.95,
    )
    assert isinstance(rec, ProvenanceRecord)
    assert rec.source == "catalog"
    assert rec.transformation == "catalog_lookup"


def test_shaft_features_strict_mode():
    """Shaft features must raise CADISpecificationError when location is unspecified or references missing parts."""
    asm = Assembly("TestStrictShaft")
    asm.add_cylinder("drive_shaft", radius=15.0, height=120.0)

    # 1. Unspecified location must NOT fall back to center of shaft
    with pytest.raises(CADISpecificationError) as exc_info:
        add_shaft_keyway(asm, shaft_part="drive_shaft")
    assert exc_info.value.parameter_name == "z_position"
    assert "under_part" in exc_info.value.valid_options
    assert exc_info.value.suggested_fix is not None

    # 2. Non-existent under_part must raise CADISpecificationError
    with pytest.raises(CADISpecificationError) as exc_info2:
        add_shaft_keyway(asm, shaft_part="drive_shaft", under_part="phantom_gear")
    assert exc_info2.value.parameter_name == "under_part"
    assert "drive_shaft" in exc_info2.value.valid_options

    # 3. Non-existent against_part for circlip must raise CADISpecificationError
    with pytest.raises(CADISpecificationError) as exc_info3:
        add_circlip_groove(asm, shaft_part="drive_shaft", against_part="phantom_bearing")
    assert exc_info3.value.parameter_name == "against_part"

    # 4. Valid placement records calculated provenance
    asm.add_box("gear_hub", length=30.0, width=30.0, height=20.0, origin=(0.0, 0.0, 40.0))
    res = add_shaft_keyway(asm, shaft_part="drive_shaft", under_part="gear_hub")
    assert res["z_position"] > 0
    assert "feature_z_position" in asm._parts["drive_shaft"].node.spec_provenance
    assert asm._parts["drive_shaft"].node.spec_provenance["feature_z_position"]["source"] == "calculated"


def test_piping_macros_strict_port_resolution():
    """Piping macros must raise CADISpecificationError for missing parts or unknown port selectors."""
    asm = Assembly("TestStrictPipePorts")
    asm.add_box("tank", length=100.0, width=100.0, height=80.0)

    # 1. Missing target part
    with pytest.raises(CADISpecificationError) as exc_info:
        add_pipe_route(asm, "pipe_bad_part", from_port="ghost_pump:top", to_port="tank:top", standard="DN25")
    assert exc_info.value.parameter_name == "port_specification"

    # 2. Unknown face selector on existing part
    with pytest.raises(CADISpecificationError) as exc_info2:
        add_pipe_route(asm, "pipe_bad_face", from_port="tank:non_existent_face", to_port=(100, 100, 100), standard="DN25")
    assert exc_info2.value.parameter_name == "port_selector"

