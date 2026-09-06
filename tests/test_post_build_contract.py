"""
tests.test_post_build_contract
==============================
Unit tests verifying the Post-Build Engineering Contract verification chain:
compile -> manifold -> dimension/volume -> interference -> kinematics -> step roundtrip -> provenance.
"""

from unittest.mock import patch
import pytest
from cadi_saml.core.assembly import Assembly
from cadi_saml.kinematics.relations import PlanetaryRelation
from cadi_saml.validation.contract import PostBuildContract, ContractReport


def test_post_build_contract_valid_assembly():
    """Valid multi-part assembly must pass all contract stages with STEP roundtrip."""
    asm = Assembly("ContractPassingAssembly")

    asm.add_box("mounting_base", length=120.0, width=80.0, height=15.0)
    asm.add_cylinder("pin", radius=8.0, height=40.0, origin=(60.0, 40.0, 15.0))
    asm.add_spur_gear("gear", module=2.0, teeth=24, face_width=12.0, origin=(60.0, 40.0, 20.0))

    report = asm.verify_contract(test_step_roundtrip=True, check_clash=False, strict=True)

    assert isinstance(report, ContractReport)
    assert report.passed is True
    assert report.assembly_name == "ContractPassingAssembly"
    assert report.total_parts_verified == 3
    assert report.total_volume_mm3 > 0.0

    # Verify each stage
    assert report.stages["compilation"].passed is True
    assert report.stages["manifold"].passed is True
    assert report.stages["dimensions"].passed is True
    assert report.stages["step_roundtrip"].passed is True

    # Volume & bounding box & solid count verified on STEP roundtrip
    step_details = report.stages["step_roundtrip"].details
    assert step_details["volume_delta_ratio"] < 0.005
    assert step_details["reopened_volume_mm3"] > 0.0
    assert step_details["original_solid_count"] == 3
    assert step_details["reopened_solid_count"] == 3
    assert step_details["bbox_delta_ratio"] < 0.005


def test_post_build_contract_kinematics():
    """Contract must inspect kinematic joints and relations with valid connectivity."""
    asm = Assembly("ContractKinematicAssembly")
    asm.add_cylinder("shaft1", radius=10.0, height=100.0, origin=(0.0, 0.0, 0.0))
    asm.add_cylinder("shaft2", radius=10.0, height=100.0, origin=(50.0, 0.0, 0.0))

    asm.add_revolute_joint("shaft1", axis=(0, 0, 1), origin=(0, 0, 0))
    asm.add_revolute_joint("shaft2", axis=(0, 0, 1), origin=(50, 0, 0))
    asm.add_gear_relation("shaft1", "shaft2", ratio=2.0)

    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False)
    assert report.passed is True
    assert report.stages["kinematics"].passed is True
    assert report.stages["kinematics"].details["relations_count"] == 1
    assert report.stages["kinematics"].details["joints_count"] == 2


def test_contract_fails_on_dimension_and_volume_mismatch():
    """Contract must fail DimensionAndVolume stage when actual solid differs from expected specs."""
    asm = Assembly("DimensionCheckAssembly")
    asm.add_box("plate", length=100.0, width=50.0, height=10.0)

    # Actual volume is 100 * 50 * 10 = 50,000 mm3
    # Specifying expected volume of 10,000 mm3 must fail
    wrong_specs = {
        "plate": {
            "volume": 10000.0,
            "tolerance": 0.05,
        }
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=wrong_specs)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("volume discrepancy" in err for err in report.stages["dimensions"].errors)

    # Specifying wrong bounding box must also fail
    wrong_bbox_specs = {
        "plate": {
            "bounding_box": (200.0, 50.0, 10.0),  # Actual dx is 100, not 200
            "tolerance": 0.05,
        }
    }
    report2 = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=wrong_bbox_specs)
    assert report2.passed is False
    assert report2.stages["dimensions"].passed is False
    assert any("bounding box discrepancy" in err for err in report2.stages["dimensions"].errors)


def test_contract_fails_on_clash_exception_in_strict_mode():
    """In strict mode, a crash in the interference detector must fail the contract, not silently pass."""
    asm = Assembly("ClashCrashAssembly")
    asm.add_box("part1", length=50, width=50, height=50)
    asm.add_box("part2", length=50, width=50, height=50, origin=(100, 0, 0))

    with patch("cadi_saml.validation.validation_engineer.ValidationEngineer.check_clashes", side_effect=RuntimeError("GPU/OCCT Kernal crash")):
        # Strict mode: must FAIL
        report_strict = asm.verify_contract(check_clash=True, test_step_roundtrip=False, strict=True)
        assert report_strict.passed is False
        assert report_strict.stages["interference"].passed is False
        assert any("Clash check failed with exception" in err for err in report_strict.stages["interference"].errors)

        # Non-strict mode: warns but does not fail stage
        report_loose = asm.verify_contract(check_clash=True, test_step_roundtrip=False, strict=False)
        assert report_loose.stages["interference"].passed is True
        assert len(report_loose.stages["interference"].warnings) > 0


def test_contract_fails_on_missing_or_conflicting_kinematics():
    """Kinematic relations with missing joints or conflicting loop ratios must fail contract."""
    asm = Assembly("BadKinematics")
    asm.add_cylinder("s1", radius=10, height=50)
    asm.add_cylinder("s2", radius=10, height=50, origin=(50, 0, 0))

    # Missing revolute joints when relation is added
    asm.add_gear_relation("s1", "s2", ratio=2.0)
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False)
    assert report.passed is False
    assert report.stages["kinematics"].passed is False
    assert any("Missing or incompatible joints" in err for err in report.stages["kinematics"].errors)

    # Conflicting closed transmission loop (s1 -> s2 ratio=2.0 and s1 -> s2 ratio=5.0)
    asm2 = Assembly("ConflictingKinematics")
    asm2.add_cylinder("g1", radius=10, height=50)
    asm2.add_cylinder("g2", radius=10, height=50, origin=(50, 0, 0))
    asm2.add_revolute_joint("g1", axis=(0, 0, 1), origin=(0, 0, 0))
    asm2.add_revolute_joint("g2", axis=(0, 0, 1), origin=(50, 0, 0))
    asm2.add_gear_relation("g1", "g2", ratio=2.0)
    asm2.add_gear_relation("g1", "g2", ratio=5.0)  # Contradictory constraint!

    report2 = asm2.verify_contract(test_step_roundtrip=False, check_clash=False)
    assert report2.passed is False
    assert report2.stages["kinematics"].passed is False
    assert any("Inconsistent closed transmission loop" in err for err in report2.stages["kinematics"].errors)


def test_contract_fails_on_inconsistent_planetary_teeth():
    """Planetary relation violating Willis epicyclic condition z_ring == z_sun + 2 * z_planet must fail."""
    asm = Assembly("BadPlanetaryAssembly")
    for name in ["sun", "carrier", "ring", "p1"]:
        asm.add_cylinder(name, radius=10, height=20)
        asm.add_revolute_joint(name, axis=(0, 0, 1), origin=(0, 0, 0))

    # Invalid teeth: z_ring (50) != z_sun (20) + 2 * z_planet (10) = 40
    asm.add_planetary_relation(
        sun_part="sun",
        carrier_part="carrier",
        ring_part="ring",
        planet_parts=["p1"],
        z_sun=20,
        z_ring=50,
        z_planet=10,
    )

    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False)
    assert report.passed is False
    assert report.stages["kinematics"].passed is False
    assert any("Planetary tooth count inconsistent" in err for err in report.stages["kinematics"].errors)


def test_contract_requires_provenance():
    """When require_provenance=True, parts without provenance must fail contract."""
    asm = Assembly("ProvenanceRequiredAssembly")
    box = asm.add_box("untracked_box", length=50, width=50, height=50)

    # Fails when provenance is required and empty
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, require_provenance=True)
    assert report.passed is False
    assert report.stages["provenance"].passed is False
    assert any("lacks specification provenance records" in err for err in report.stages["provenance"].errors)

    # Now add structured provenance for all required parameters (or specify required_parameters)
    box.track_provenance(
        parameter="length",
        source="llm_json",
        source_ref="specs.dimensions.length",
        original_value=50.0,
        effective_value=50.0,
        unit="mm",
        transformation="exact",
        confidence=0.98,
    )
    box.track_provenance(
        parameter="width",
        source="llm_json",
        source_ref="specs.dimensions.width",
        original_value=50.0,
        effective_value=50.0,
        unit="mm",
        transformation="exact",
        confidence=0.98,
    )
    box.track_provenance(
        parameter="height",
        source="llm_json",
        source_ref="specs.dimensions.height",
        original_value=50.0,
        effective_value=50.0,
        unit="mm",
        transformation="exact",
        confidence=0.98,
    )

    report2 = asm.verify_contract(test_step_roundtrip=False, check_clash=False, require_provenance=True)
    assert report2.passed is True
    assert report2.stages["provenance"].passed is True
    assert report2.stages["provenance"].details["total_parts"] == 1


def test_contract_fails_on_ghost_part_in_expected_specs():
    """Specification referencing ghost part not in assembly must fail DimensionAndVolume stage."""
    asm = Assembly("GhostPartAsm")
    asm.add_box("real_part", length=50, width=50, height=50)

    expected_specs = {
        "ghost_part": {
            "volume": 100.0,
            "tolerance": 0.05,
        }
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("ghost" in err.lower() for err in report.stages["dimensions"].errors)

    # Also test nested under 'parts'
    expected_specs_nested = {
        "parts": {
            "another_ghost": {"volume": 200.0}
        }
    }
    report2 = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs_nested)
    assert report2.passed is False
    assert report2.stages["dimensions"].passed is False
    assert any("another_ghost" in err for err in report2.stages["dimensions"].errors)


def test_contract_fails_on_dimension_parameter_typo():
    """Typo in dimension specification name (e.g. 'diameterr') must fail DimensionAndVolume stage."""
    asm = Assembly("TypoAsm")
    asm.add_cylinder("shaft", radius=10.0, height=100.0)

    # Nested under 'dimensions'
    expected_specs_nested = {
        "shaft": {
            "dimensions": {
                "diameterr": 20.0,  # Typo!
            }
        }
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs_nested)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("diameterr" in err for err in report.stages["dimensions"].errors)

    # Direct top-level parameter typo
    expected_specs_direct = {
        "shaft": {
            "diameterr": 20.0,  # Typo!
        }
    }
    report2 = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs_direct)
    assert report2.passed is False
    assert report2.stages["dimensions"].passed is False
    assert any("diameterr" in err for err in report2.stages["dimensions"].errors)


def test_contract_fails_on_nan_or_invalid_tolerance():
    """Specification with NaN or negative tolerance must fail DimensionAndVolume stage."""
    asm = Assembly("NanToleranceAsm")
    asm.add_box("block", length=50, width=50, height=50)

    # NaN tolerance on part volume
    expected_specs = {
        "block": {
            "volume": 999999.0,  # Deliberately wrong volume
            "tolerance": float("nan"),  # NaN tolerance must NOT allow comparison to pass
        }
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("tolerance" in err.lower() for err in report.stages["dimensions"].errors)

    # Top-level NaN tolerance
    expected_specs_top = {
        "total_volume": 999999.0,
        "tolerance": float("nan"),
    }
    report2 = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs_top)
    assert report2.passed is False
    assert report2.stages["dimensions"].passed is False
    assert any("tolerance" in err.lower() for err in report2.stages["dimensions"].errors)


def test_contract_fails_on_nonexistent_parameter_provenance():
    """Tracking provenance for nonexistent parameter must fail ProvenanceCoverage stage."""
    asm = Assembly("BogusProvAsm")
    shaft = asm.add_cylinder("shaft", radius=10.0, height=100.0)

    # Only track nonexistent parameter
    shaft.track_provenance(
        parameter="nonexistent_parameter",
        source="llm_json",
        source_ref="specs.bogus",
        original_value=123.0,
        effective_value=123.0,
        unit="mm",
        transformation="none",
        confidence=0.9,
    )

    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, require_provenance=True)
    assert report.passed is False
    assert report.stages["provenance"].passed is False
    assert any("nonexistent_parameter" in err for err in report.stages["provenance"].errors)


def test_planetary_kinematics_carrier_and_sun_fixed_ratios():
    """Planetary transmission inspection must correctly calculate planet gear ratios for carrier and sun fixed modes."""
    from cadi_saml.kinematics.inspection import linear_relations

    # 1. Carrier fixed mode: omega_p / omega_s = -zs / zp
    asm_carrier = Assembly("CarrierFixedAsm")
    for name in ["sun", "carrier", "ring", "p1"]:
        asm_carrier.add_cylinder(name, radius=10, height=20)
        asm_carrier.add_revolute_joint(name, axis=(0, 0, 1), origin=(0, 0, 0))

    asm_carrier.add_planetary_relation(
        sun_part="sun",
        carrier_part="carrier",
        ring_part="ring",
        planet_parts=["p1"],
        z_sun=20,
        z_ring=60,
        z_planet=20,
        fixed_component="carrier",
    )
    edges, errs = linear_relations(asm_carrier._mechanism)
    assert not errs
    # Sun to ring ratio: -20/60 = -1/3
    sun_ring_edge = [e for e in edges if e[0] == "sun" and e[1] == "ring"][0]
    assert pytest.approx(sun_ring_edge[2], rel=1e-5) == -20.0 / 60.0
    # Sun to planet ratio: -zs / zp = -20/20 = -1.0
    sun_p1_edge = [e for e in edges if e[0] == "sun" and e[1] == "p1"][0]
    assert pytest.approx(sun_p1_edge[2], rel=1e-5) == -20.0 / 20.0

    # 2. Sun fixed mode: omega_p / omega_r = (zr / (zs + zr)) * (1 + zs / zp)
    asm_sun = Assembly("SunFixedAsm")
    for name in ["sun", "carrier", "ring", "p1"]:
        asm_sun.add_cylinder(name, radius=10, height=20)
        asm_sun.add_revolute_joint(name, axis=(0, 0, 1), origin=(0, 0, 0))

    asm_sun.add_planetary_relation(
        sun_part="sun",
        carrier_part="carrier",
        ring_part="ring",
        planet_parts=["p1"],
        z_sun=20,
        z_ring=60,
        z_planet=20,
        fixed_component="sun",
    )
    edges_sun, errs_sun = linear_relations(asm_sun._mechanism)
    assert not errs_sun
    # Ring to carrier ratio: zr / (zs + zr) = 60 / 80 = 0.75
    ring_carrier_edge = [e for e in edges_sun if e[0] == "ring" and e[1] == "carrier"][0]
    assert pytest.approx(ring_carrier_edge[2], rel=1e-5) == 60.0 / 80.0
    # Ring to planet ratio: (60/80) * (1 + 20/20) = 0.75 * 2 = 1.5
    ring_p1_edge = [e for e in edges_sun if e[0] == "ring" and e[1] == "p1"][0]
    assert pytest.approx(ring_p1_edge[2], rel=1e-5) == 1.5


def test_post_build_contract_empty_assembly():
    """Empty assembly must fail compilation stage."""
    asm = Assembly("EmptyAssembly")
    contract = PostBuildContract(asm)
    report = contract.verify(test_step_roundtrip=False, check_clash=False)

    assert report.passed is False
    assert report.stages["compilation"].passed is False
    assert len(report.stages["compilation"].errors) > 0


def test_step_roundtrip_multi_solid_compound_support():
    """STEP roundtrip solid count must accurately count actual B-Rep solids, not dictionary keys."""
    from unittest.mock import patch
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Pnt

    asm = Assembly("MultiSolidAsm")
    asm.add_box("multi_solid_part", length=20.0, width=20.0, height=20.0)

    # Create compound with 2 disjoint solid boxes inside a single part
    b1 = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 20.0, 20.0, 20.0).Solid()
    b2 = BRepPrimAPI_MakeBox(gp_Pnt(50, 0, 0), 20.0, 20.0, 20.0).Solid()

    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    builder.Add(comp, b1)
    builder.Add(comp, b2)

    with patch("cadi_saml.backend.occt_backend.OCCTBackend.compile", return_value={"multi_solid_part": comp}):
        # 1 part in solids dict, but 2 actual solids in geometry!
        report = asm.verify_contract(test_step_roundtrip=True, check_clash=False, strict=True)
        assert report.passed is True
        assert report.stages["step_roundtrip"].passed is True
        assert report.stages["step_roundtrip"].details["original_solid_count"] == 2
        assert report.stages["step_roundtrip"].details["reopened_solid_count"] == 2


def test_contract_fails_on_nan_clash_threshold():
    """Clash threshold NaN or invalid must fail InterferenceAndClearance stage even with clashing parts."""
    asm = Assembly("NanClashAsm")
    asm.add_box("box1", length=50, width=50, height=50, origin=(0, 0, 0))
    asm.add_box("box2", length=50, width=50, height=50, origin=(0, 0, 0))  # 100% collision!

    report = asm.verify_contract(check_clash=True, max_clash_volume_mm3=float("nan"), test_step_roundtrip=False)
    assert report.passed is False
    assert report.stages["interference"].passed is False
    assert any("clash volume threshold" in err.lower() or "interference detected" in err.lower() for err in report.stages["interference"].errors)


def test_contract_fails_on_assembly_bounding_box_mismatch():
    """Total assembly bounding box specification mismatch must fail DimensionAndVolume stage."""
    asm = Assembly("AsmBBoxCheck")
    asm.add_box("small_box", length=20.0, width=20.0, height=20.0)

    # Actual assembly bbox is [20, 20, 20], expected is [999, 999, 999]
    expected_specs = {
        "bounding_box": [999.0, 999.0, 999.0],
        "tolerance": 0.05,
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("assembly bounding box discrepancy" in err.lower() for err in report.stages["dimensions"].errors)


def test_contract_fails_on_conflicting_duplicate_part_specs():
    """Conflicting part specs defined in both 'parts' and top-level must fail DimensionAndVolume stage."""
    asm = Assembly("ConflictingPartSpecsAsm")
    asm.add_box("box", length=50.0, width=50.0, height=50.0)

    expected_specs = {
        "parts": {
            "box": {"volume": 1.0}
        },
        "box": {
            "volume": 6000.0
        }
    }
    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, expected_specs=expected_specs)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("conflicting/duplicate" in err.lower() for err in report.stages["dimensions"].errors)


def test_contract_fails_when_provenance_effective_value_mismatches_part():
    """Provenance effective_value that does not match actual part parameter must fail ProvenanceCoverage."""
    asm = Assembly("ProvValueMismatchAsm")
    box = asm.add_box("test_box", length=50.0, width=40.0, height=30.0)

    # Length actual is 50.0, but provenance claims effective_value is 999999.0
    box.track_provenance(
        parameter="length",
        source="llm_json",
        source_ref="specs.length",
        original_value=999999.0,
        effective_value=999999.0,
        unit="mm",
    )
    box.track_provenance(
        parameter="width",
        source="llm_json",
        source_ref="specs.width",
        original_value=40.0,
        effective_value=40.0,
        unit="mm",
    )
    box.track_provenance(
        parameter="height",
        source="llm_json",
        source_ref="specs.height",
        original_value=30.0,
        effective_value=30.0,
        unit="mm",
    )

    report = asm.verify_contract(test_step_roundtrip=False, check_clash=False, require_provenance=True)
    assert report.passed is False
    assert report.stages["provenance"].passed is False
    assert any("does not match actual part parameter" in err for err in report.stages["provenance"].errors)


def test_contract_handles_invalid_volume_tolerance_ratio_gracefully():
    """Invalid volume_tolerance_ratio type (e.g. 'bad') must produce a failed report rather than TypeError."""
    asm = Assembly("BadTolTypeAsm")
    asm.add_box("box", length=30.0, width=30.0, height=30.0)

    # Passing string 'bad' as tolerance ratio
    report = asm.verify_contract(volume_tolerance_ratio="bad", test_step_roundtrip=False, check_clash=False)
    assert isinstance(report, ContractReport)
    assert report.passed is False
    assert report.stages["dimensions"].passed is False
    assert any("volume_tolerance_ratio" in err for err in report.stages["dimensions"].errors)
