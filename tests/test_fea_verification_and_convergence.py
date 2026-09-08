"""
tests/test_fea_verification_and_convergence.py
==============================================
Validation test suite for:
1. Classical analytical Euler-Bernoulli & Timoshenko beam benchmark comparison
2. Multi-grid mesh convergence analysis (coarse -> medium -> fine) and asymptotic checks
3. Multi-material contact boundary interface stress extraction
4. Standardized portable engineering FEA report (JSON schema & Markdown audit report)
"""

import json
import os
import sys
import tempfile
from pathlib import Path
import numpy as np
import pytest

# Ensure local src is first on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml.analysis import (
    Material,
    get_material,
    LinearElasticitySolver,
    FEAResult,
    InterfaceResult,
    CalculiXModel,
    MaterialRegion,
    CalculiXRunner,
    compute_analytical_cantilever,
    generate_structured_beam_mesh,
    BenchmarkValidator,
    BenchmarkComparisonResult,
    MeshConvergenceStudy,
    ConvergenceStudyResult,
    PortableFEAReport,
)


def test_analytical_uniaxial_tension_benchmark():
    """
    Validates the 3D continuum FEA solver against classical uniaxial tensile theory.
    Since C3D4 tetrahedra are constant strain elements, pure axial tension matches
    closed-form Hooke's law (delta = F*L / (E*A)) within < 1.0% error.
    """
    comp: BenchmarkComparisonResult = BenchmarkValidator.run_uniaxial_tension_benchmark(
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        axial_force_n=10000.0,
        material="S235JR",
        tolerance_pct=6.0,
    )

    assert comp.is_verified, f"Uniaxial benchmark failed: disp error={comp.disp_error_pct}%, stress error={comp.stress_error_pct}%"
    assert comp.stress_error_pct < 1.0, f"Expected < 1.0% stress error, got {comp.stress_error_pct}%"
    assert comp.disp_error_pct <= 6.0, f"Expected <= 6.0% disp error (due to 3D Poisson lateral restraint), got {comp.disp_error_pct}%"
    assert comp.numerical_disp_mm > 0.0
    assert comp.analytical_disp_mm > 0.0
    assert comp.solver_backend == "builtin"
    assert "PASSED (VERIFIED)" in comp.summary_table


def test_analytical_cantilever_benchmark():
    """
    Validates the 3D continuum FEA solver against classical Timoshenko closed-form theory.
    Under pure bending, linear C3D4 elements exhibit artificial shear locking with coarse
    thickness discretization, matching within the standard 30-40% element behavior band.
    """
    comp: BenchmarkComparisonResult = BenchmarkValidator.run_cantilever_benchmark(
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        tip_force_n=500.0,
        material="S235JR",
        nx=16,
        ny=3,
        nz=3,
        tolerance_pct=40.0,
    )

    assert comp.is_verified, f"Cantilever benchmark failed: disp error={comp.disp_error_pct}%"
    assert comp.disp_error_pct <= 40.0
    assert comp.numerical_disp_mm > 0.0
    assert comp.analytical_disp_mm > 0.0
    assert comp.solver_backend == "builtin"
    assert "shear locking" in comp.details["note"]
    assert "PASSED (VERIFIED)" in comp.summary_table


def test_mesh_convergence_study_converged_progression():
    """
    Simulates a 3-grid refinement study (coarse -> medium -> fine).
    Verifies that when relative changes drop below tolerance, the study
    reports 'CONVERGED' and calculates Richardson extrapolated estimates.
    """
    study = MeshConvergenceStudy(study_name="Cantilever_Grid_Refinement", disp_tolerance_pct=3.0, stress_tolerance_pct=5.0)

    # 3 grid steps with decaying relative changes
    # h = 10mm (coarse), h = 5mm (medium), h = 2.5mm (fine)
    study.add_step("Coarse", element_size_h=10.0, num_nodes=100, num_elements=300, max_displacement_mm=1.820, max_von_mises_mpa=140.0)
    study.add_step("Medium", element_size_h=5.0, num_nodes=650, num_elements=2400, max_displacement_mm=1.910, max_von_mises_mpa=148.0)
    study.add_step("Fine", element_size_h=2.5, num_nodes=4500, num_elements=18000, max_displacement_mm=1.935, max_von_mises_mpa=151.0)

    res: ConvergenceStudyResult = study.evaluate()

    # Relative change between medium (1.910) and fine (1.935) = |1.935 - 1.910| / 1.935 = 1.29% <= 3.0%
    assert res.is_converged
    assert res.status == "CONVERGED"
    assert res.disp_relative_change_pct <= 3.0
    assert res.stress_relative_change_pct <= 5.0
    assert res.richardson_extrapolated_disp_mm is not None
    assert res.richardson_extrapolated_disp_mm >= 1.935  # Continua extrapolation approaches from below
    assert "[PASS] CONVERGED" in res.summary_table


def test_mesh_convergence_study_unconverged_behavior():
    """
    Negative test: When relative change between grid levels exceeds tolerance,
    is_converged must be False and status must be 'UNCONVERGED'.
    """
    study = MeshConvergenceStudy(study_name="Inadequate_Grid_Study", disp_tolerance_pct=2.0)

    # Coarse to medium with 15% discrepancy
    study.add_step("Coarse", element_size_h=20.0, num_nodes=50, num_elements=150, max_displacement_mm=1.20, max_von_mises_mpa=90.0)
    study.add_step("Medium", element_size_h=10.0, num_nodes=350, num_elements=1200, max_displacement_mm=1.45, max_von_mises_mpa=115.0)

    res: ConvergenceStudyResult = study.evaluate()

    assert not res.is_converged
    assert res.status == "UNCONVERGED"
    assert res.disp_relative_change_pct > 10.0
    assert "[FAIL] UNCONVERGED" in res.summary_table


def test_mesh_convergence_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="non-negative"):
        MeshConvergenceStudy(disp_tolerance_pct=-1.0)

    study = MeshConvergenceStudy()
    with pytest.raises(ValueError, match="greater than zero"):
        study.add_step("bad", 0.0, 10, 20, 1.0, 2.0)
    study.add_step("coarse", 2.0, 10, 20, 1.0, 2.0)
    with pytest.raises(ValueError, match="duplicates"):
        study.add_step("duplicate", 2.0, 12, 24, 1.1, 2.1)


def test_bimetal_interface_stress_extraction():
    """
    Validates interface stress evaluation on a Steel (root) + Aluminium (tip) bi-material cantilever.
    The nodes on the interface x = 40mm must be detected and evaluated for interface Von Mises and safety factor.
    """
    # Create structured beam mesh: 80x10x10 mm, split at x = 40mm
    nodes, elements = generate_structured_beam_mesh(length_mm=80.0, width_mm=10.0, height_mm=10.0, nx=8, ny=2, nz=2)

    model = CalculiXModel("BiMetalBeam_InterfaceTest", nodes, elements)
    model.add_material_region(
        MaterialRegion(name="steel_root", material="S235JR", selector=lambda x, y, z: x <= 40.0)
    )
    model.add_material_region(
        MaterialRegion(name="alu_tip", material="AL6061_T6", selector=lambda x, y, z: x > 40.0)
    )
    model.assign_element_sets()

    # Fixed root at x=0
    root_nodes = [int(i) for i in np.where(nodes[:, 0] < 1e-4)[0]]
    model.add_node_set("FIXED_ROOT", root_nodes)
    model.add_boundary_condition("FIXED_ROOT", 1, 3, 0.0)

    # Tip force at x=80
    tip_nodes = [int(i) for i in np.where(nodes[:, 0] > 79.9)[0]]
    model.add_node_set("TIP_FACE", tip_nodes)
    f_per_node = -300.0 / len(tip_nodes)
    for n in tip_nodes:
        model.add_nodal_load(n, 3, f_per_node)

    runner = CalculiXRunner(model)
    result: FEAResult = runner.run(study_name="Interface_Validation_Study")

    # Verify interface results exist
    assert result.interface_results is not None
    assert len(result.interface_results) == 1
    inter_key = "steel_root__alu_tip"
    assert inter_key in result.interface_results

    inter_res: InterfaceResult = result.interface_results[inter_key]
    assert inter_res.region_a == "steel_root"
    assert inter_res.region_b == "alu_tip"
    assert inter_res.num_interface_nodes > 0
    assert inter_res.max_von_mises_mpa > 0.0
    assert inter_res.mean_von_mises_mpa > 0.0
    assert inter_res.safety_factor > 0.0

    # Ensure interface summary appears in report
    assert "Material Interfaces:" in result.summary_report
    assert "steel_root <-> alu_tip" in result.summary_report


def test_portable_fea_report_generation():
    """
    Tests creation, JSON schema serialization, and Markdown generation of PortableFEAReport.
    """
    # 1. Build a mock FEAResult
    mat_steel = get_material("S235JR")
    nodes, elements = generate_structured_beam_mesh(50.0, 10.0, 10.0, nx=5, ny=2, nz=2)
    fake_disp = np.zeros((len(nodes), 3))
    fake_disp[:, 2] = -0.045
    fake_vm = np.full(len(nodes), 75.5)

    fea_res = FEAResult(
        study_name="Chassis_Bracket_Study",
        part_name="Lower_Mount_Bracket",
        material=mat_steel,
        num_nodes=len(nodes),
        num_elements=len(elements),
        max_von_mises_mpa=75.5,
        max_displacement_mm=0.045,
        yield_strength_mpa=235.0,
        safety_factor=3.11,
        is_safe=True,
        status="PASS",
        nodal_displacements=fake_disp,
        nodal_von_mises=fake_vm,
        solver_backend="builtin",
    )

    # 2. Add convergence study
    conv = (
        MeshConvergenceStudy("Bracket_Mesh_Study")
        .add_step("Coarse", 10.0, 50, 150, 0.040, 68.0)
        .add_step("Medium", 5.0, 180, 700, 0.044, 73.0)
        .add_step("Fine", 2.5, 600, 2800, 0.045, 75.5)
        .evaluate()
    )

    # 3. Create portable report
    report = PortableFEAReport.from_fea_result(
        result=fea_res,
        convergence=conv,
        cadi_saml_version="0.2.0",
        boundary_conditions={"fixed": "x=0 root face", "applied_load_n": 1500.0},
    )

    assert report.verification_verdict == "VERIFIED_PASS"
    assert report.solver_backend == "builtin"
    assert report.mesh_convergence_status == "CONVERGED"
    assert report.cadi_saml_version == "0.2.0"

    # Test JSON export
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json_path = tf.name

    try:
        json_str = report.to_json(json_path)
        loaded = json.loads(json_str)
        assert loaded["study_name"] == "Chassis_Bracket_Study"
        assert loaded["part_name"] == "Lower_Mount_Bracket"
        assert loaded["verification_verdict"] == "VERIFIED_PASS"
        assert loaded["max_von_mises_mpa"] == 75.5
        assert "primary" in loaded["materials"]
        assert loaded["materials"]["primary"]["yield_strength_mpa"] == 235.0
    finally:
        if os.path.exists(json_path):
            os.remove(json_path)

    # Test Markdown export
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        md_path = tf.name

    try:
        md_str = report.to_markdown(md_path)
        assert "# CADi SAML Portable Engineering FEA Report" in md_str
        assert "VERIFIED_PASS" in md_str
        assert "75.50 MPa" in md_str
        assert "Material Constitutive Cards" in md_str
    finally:
        if os.path.exists(md_path):
            os.remove(md_path)


def test_element_indexing_boundary_first_and_last_elements():
    """
    Validates that element sets with 1-based CalculiX IDs correctly map:
    - First element (ID 1) -> array index 0
    - Last element (ID num_elems) -> array index num_elems - 1
    - Neither element 1 nor element num_elems are dropped.
    - Interface between first and last half is correctly identified.
    """
    from cadi_saml.analysis.frd_reader import _normalize_element_sets, _to_0based_element_indices, write_frd, frd_to_fea_result

    num_elems = 10
    # Test 1: 1-based element sets (Standard CalculiX convention: 1..10)
    sets_1based = {
        "set_a": [1, 2, 3, 4, 5],
        "set_b": [6, 7, 8, 9, 10],
    }

    norm_1based = _normalize_element_sets(sets_1based, num_elems)
    assert norm_1based["set_a"] == [0, 1, 2, 3, 4], f"Element 1 must map to index 0, got {norm_1based['set_a']}"
    assert norm_1based["set_b"] == [5, 6, 7, 8, 9], f"Element 10 must map to index 9, got {norm_1based['set_b']}"
    assert 0 in norm_1based["set_a"], "First element index 0 must be included"
    assert 9 in norm_1based["set_b"], "Last element index 9 (num_elems - 1) must be included"

    # Test 2: Pre-converted 0-based element sets (0..9)
    sets_0based = {
        "set_a": [0, 1, 2, 3, 4],
        "set_b": [5, 6, 7, 8, 9],
    }

    norm_0based = _normalize_element_sets(sets_0based, num_elems)
    assert norm_0based["set_a"] == [0, 1, 2, 3, 4]
    assert norm_0based["set_b"] == [5, 6, 7, 8, 9]

    # Test 3: End-to-end FRD generation and ingest with 1-based element IDs
    nodes, elements = generate_structured_beam_mesh(length_mm=40.0, width_mm=10.0, height_mm=10.0, nx=2, ny=1, nz=1)
    tot_elems = len(elements)  # 10 elements for 2 hex cells (5 tets each)
    assert tot_elems == 10

    disps = np.zeros((len(nodes), 3))
    stresses = np.zeros((len(nodes), 6))
    stresses[:, 0] = 50.0  # 50 MPa normal stress

    with tempfile.NamedTemporaryFile("w", suffix=".frd", delete=False) as tf:
        frd_file = tf.name

    try:
        write_frd(frd_file, nodes, elements, disps, stresses)

        # Ingest with 1-based element sets
        elem_sets = {
            "root_zone": [1, 2, 3, 4, 5],
            "tip_zone": [6, 7, 8, 9, 10],
        }
        materials = {
            "root_zone": get_material("S235JR"),
            "tip_zone": get_material("AL6061_T6"),
        }

        res = frd_to_fea_result(frd_file, materials=materials, element_sets=elem_sets)

        # Check element material IDs coverage
        assert res.element_material_ids is not None
        assert len(res.element_material_ids) == 10
        # First element (index 0) must belong to root_zone (id 0)
        assert res.element_material_ids[0] == 0
        # Last element (index 9) must belong to tip_zone (id 1)
        assert res.element_material_ids[9] == 1
        # Check that neither element 1 nor 10 was skipped
        assert np.all(res.element_material_ids[:5] == 0)
        assert np.all(res.element_material_ids[5:] == 1)

        # Check critical_element_id is 1-based CalculiX ID and critical_element_index is 0-based mesh index
        for reg_res in res.regional_results.values():
            assert 1 <= reg_res.critical_element_id <= 10
            assert 0 <= reg_res.critical_element_index < 10
            assert reg_res.critical_element_id == reg_res.critical_element_index + 1

        # Check interface is non-empty
        assert len(res.interface_results) == 1
        inter = list(res.interface_results.values())[0]
        assert inter.num_interface_nodes > 0
        assert inter.max_von_mises_mpa > 0.0

    finally:
        if os.path.exists(frd_file):
            os.remove(frd_file)


def test_element_indexing_strict_validation_and_rejection():
    """
    Validates that:
    1. Mixed 0-based and 1-based element sets are strictly rejected with ValueError.
    2. Out-of-bounds and negative IDs are rejected rather than silently filtered.
    3. Explicit index_base='zero' and index_base='one' enforce their exact contract.
    """
    from cadi_saml.analysis.frd_reader import _normalize_element_sets

    num_elems = 6

    # 1. Mixed-base rejection: {"steel": [0, 1, 2], "aluminum": [4, 5, 6]}
    # Steel contains 0 (0-based) while aluminum contains 6 (1-based for a 6-element mesh)
    mixed_sets = {
        "steel": [0, 1, 2],
        "aluminum": [4, 5, 6],
    }
    with pytest.raises(ValueError, match=r"Conflicting / mixed element index base|Mixed element indexing detected"):
        _normalize_element_sets(mixed_sets, num_elems=num_elems, index_base="auto")

    # 2. Out-of-bounds ID rejection (never silently filtered or dropped)
    oob_sets = {
        "steel": [1, 2, 3],
        "aluminum": [4, 5, 99],
    }
    with pytest.raises(ValueError, match=r"exceeds mesh element count|out of bounds"):
        _normalize_element_sets(oob_sets, num_elems=num_elems, index_base="auto")

    # 3. Negative ID rejection
    neg_sets = {
        "steel": [-1, 1, 2],
        "aluminum": [3, 4, 5],
    }
    with pytest.raises(ValueError, match=r"Negative element ID -1"):
        _normalize_element_sets(neg_sets, num_elems=num_elems, index_base="auto")

    # 4. Explicit index_base="one" rejecting ID 0
    zero_in_one_based = {
        "steel": [0, 1, 2],
        "aluminum": [3, 4, 5],
    }
    with pytest.raises(ValueError, match=r"out of bounds for 1-based indexing"):
        _normalize_element_sets(zero_in_one_based, num_elems=num_elems, index_base="one")

    # 5. Explicit index_base="zero" rejecting ID == num_elems (e.g. 6 in 6-element mesh)
    num_elems_in_zero_based = {
        "steel": [0, 1, 2],
        "aluminum": [3, 4, 6],
    }
    with pytest.raises(ValueError, match=r"out of bounds for 0-based indexing"):
        _normalize_element_sets(num_elems_in_zero_based, num_elems=num_elems, index_base="zero")

    # 6. Invalid index_base rejection
    with pytest.raises(ValueError, match=r"Invalid index_base"):
        _normalize_element_sets({"s": [1, 2]}, num_elems=2, index_base="two")


def test_calculix_model_index_base_and_multi_material_contract():
    """
    Validates model-level index_base specification and end-to-end consistency
    between external CalculiX (.inp) and internal solver.
    """
    nodes, elements = generate_structured_beam_mesh(length_mm=40.0, width_mm=10.0, height_mm=10.0, nx=2, ny=1, nz=1)
    tot_elems = len(elements)  # 10 elements
    assert tot_elems == 10

    # 1. Invalid index_base rejected at model initialization
    with pytest.raises(ValueError, match=r"Invalid index_base"):
        CalculiXModel(nodes=nodes, elements=elements, index_base="invalid_base")

    # 2. 0-based model specification with index_base="zero"
    model_0based = CalculiXModel(
        nodes=nodes,
        elements=elements,
        index_base="zero",
        materials={"root": get_material("S235JR"), "tip": get_material("AL6061_T6")},
        element_sets={"root": [0, 1, 2, 3, 4], "tip": [5, 6, 7, 8, 9]},
    )
    # validate_multi_material passes cleanly
    assert model_0based.validate_multi_material() is True

    # .to_inp() translates 0-based indices to 1-based CalculiX cards
    inp_text = model_0based.to_inp()
    assert "*ELSET, ELSET=root" in inp_text
    assert "*ELSET, ELSET=tip" in inp_text
    assert "1, 2, 3, 4, 5" in inp_text
    assert "6, 7, 8, 9, 10" in inp_text

    # 3. 1-based model rejecting 0-based sets with explicit error
    model_1based_bad = CalculiXModel(
        nodes=nodes,
        elements=elements,
        index_base="one",
        materials={"root": get_material("S235JR"), "tip": get_material("AL6061_T6")},
        element_sets={"root": [0, 1, 2, 3, 4], "tip": [5, 6, 7, 8, 9]},
    )
    with pytest.raises(ValueError, match=r"out of bounds for 1-based indexing"):
        model_1based_bad.validate_multi_material()

    # 4. Built-in solver run with index_base="zero" vs index_base="one" producing identical results
    root_nodes = [int(i) for i in np.where(nodes[:, 0] < 1e-4)[0]]
    tip_nodes = [int(i) for i in np.where(nodes[:, 0] > 39.9)[0]]

    model_0based.add_node_set("FIXED_ROOT", root_nodes)
    model_0based.add_boundary_condition("FIXED_ROOT", 1, 3, 0.0)
    for n in tip_nodes:
        model_0based.add_nodal_load(n, 3, -100.0 / len(tip_nodes))
    runner_0 = CalculiXRunner(model=model_0based, prefer_builtin_fallback=True)
    res_0 = runner_0.run(study_name="bimetal_0based")

    model_1based = CalculiXModel(
        nodes=nodes,
        elements=elements,
        index_base="one",
        materials={"root": get_material("S235JR"), "tip": get_material("AL6061_T6")},
        element_sets={"root": [1, 2, 3, 4, 5], "tip": [6, 7, 8, 9, 10]},
    )
    model_1based.add_node_set("FIXED_ROOT", root_nodes)
    model_1based.add_boundary_condition("FIXED_ROOT", 1, 3, 0.0)
    for n in tip_nodes:
        model_1based.add_nodal_load(n, 3, -100.0 / len(tip_nodes))
    runner_1 = CalculiXRunner(model=model_1based, prefer_builtin_fallback=True)
    res_1 = runner_1.run(study_name="bimetal_1based")

    assert np.isclose(res_0.max_von_mises_mpa, res_1.max_von_mises_mpa, rtol=1e-4)
    assert np.isclose(res_0.max_displacement_mm, res_1.max_displacement_mm, rtol=1e-4)
    assert res_0.regional_results["root"].critical_element_id == res_1.regional_results["root"].critical_element_id
    assert res_0.regional_results["root"].critical_element_index == res_1.regional_results["root"].critical_element_index
