"""
tests/test_heterogeneous_fea.py
===============================
Comprehensive validation tests for multi-material heterogeneous FEA,
CalculiX runner, .frd result ingestion, regional safety factors, and image export.
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
from pathlib import Path

# Ensure library/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml import Assembly, OCCTBackend
from cadi_saml.analysis import (
    Material,
    get_material,
    CalculiXModel,
    MaterialRegion,
    CalculiXRunner,
    parse_frd,
    write_frd,
    frd_to_fea_result,
    calc_von_mises,
    export_image,
    FEAResult,
)
from cadi_saml.analysis.solver import LinearElasticitySolver


def _create_two_zone_beam_mesh(nx=10, ny=2, nz=2, lx=100.0, ly=10.0, lz=10.0):
    """
    Generates a structured 3D tetrahedral mesh of a beam split in half along X:
    - Region 1 (Steel): X in [0, 50]
    - Region 2 (Aluminium): X in [50, 100]
    Returns nodes, elements, steel_elem_ids, alu_elem_ids
    """
    xs = np.linspace(0, lx, nx + 1)
    ys = np.linspace(0, ly, ny + 1)
    zs = np.linspace(0, lz, nz + 1)

    nodes = []
    node_idx = {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            for k, z in enumerate(zs):
                node_idx[(i, j, k)] = len(nodes)
                nodes.append((x, y, z))
    nodes = np.array(nodes, dtype=np.float64)

    elements = []
    steel_elems = []
    alu_elems = []

    # Divide each brick into 5 or 6 tetrahedra
    for i in range(nx):
        x_mid = 0.5 * (xs[i] + xs[i + 1])
        is_steel = x_mid <= (lx / 2.0)

        for j in range(ny):
            for k in range(nz):
                n0 = node_idx[(i, j, k)]
                n1 = node_idx[(i + 1, j, k)]
                n2 = node_idx[(i + 1, j + 1, k)]
                n3 = node_idx[(i, j + 1, k)]
                n4 = node_idx[(i, j, k + 1)]
                n5 = node_idx[(i + 1, j, k + 1)]
                n6 = node_idx[(i + 1, j + 1, k + 1)]
                n7 = node_idx[(i, j + 1, k + 1)]

                # Standard 5-tet decomposition of a hexahedron
                tets = [
                    (n0, n1, n3, n4),
                    (n1, n2, n3, n6),
                    (n1, n4, n5, n6),
                    (n3, n4, n6, n7),
                    (n1, n3, n4, n6),
                ]
                for tet in tets:
                    eid = len(elements)
                    elements.append(tet)
                    if is_steel:
                        steel_elems.append(eid)
                    else:
                        alu_elems.append(eid)

    elements = np.array(elements, dtype=np.int32)
    return nodes, elements, steel_elems, alu_elems


def test_material_region_automatic_element_mapping():
    """Verify that mesh elements are automatically partitioned into correct MaterialRegions."""
    nodes, elements, exp_steel, exp_alu = _create_two_zone_beam_mesh(nx=6, ny=2, nz=2)

    model = CalculiXModel("BiMaterialBeam", nodes, elements)

    # Add two material regions with spatial selectors
    model.add_material_region(
        MaterialRegion(
            name="steel_root",
            material="S235JR",
            selector=lambda x, y, z: x <= 50.0,
        )
    )
    model.add_material_region(
        MaterialRegion(
            name="alu_tip",
            material="AL6061_T6",
            selector=lambda x, y, z: x > 50.0,
        )
    )

    # Auto assign elements
    model.assign_element_sets()

    assert "steel_root" in model.element_sets
    assert "alu_tip" in model.element_sets
    assert len(model.element_sets["steel_root"]) == len(exp_steel)
    assert len(model.element_sets["alu_tip"]) == len(exp_alu)

    # Validate multi-material consistency
    assert model.validate_multi_material() is True

    # Check generated .inp content has ELSET and MATERIAL blocks for both
    inp_content = model.to_inp()
    assert "*MATERIAL, NAME=steel_root" in inp_content
    assert "*MATERIAL, NAME=alu_tip" in inp_content
    assert "*SOLID SECTION, ELSET=steel_root, MATERIAL=steel_root" in inp_content
    assert "*SOLID SECTION, ELSET=alu_tip, MATERIAL=alu_tip" in inp_content


@pytest.mark.synthetic_parser
def test_frd_file_write_parse_and_conversion():
    """Verify writing, parsing, and converting .frd results to FEAResult with reaction forces."""
    nodes, elements, steel_elems, alu_elems = _create_two_zone_beam_mesh(nx=4, ny=2, nz=2)
    num_nodes = len(nodes)

    # Synthetic displacements and stresses
    displacements = np.zeros((num_nodes, 3), dtype=np.float64)
    displacements[:, 2] = -0.05 * (nodes[:, 0] / 100.0) ** 2  # Parabolic beam deflection

    stresses = np.zeros((num_nodes, 6), dtype=np.float64)
    # Tension at top (+Z), compression at bottom (-Z)
    stresses[:, 0] = 120.0 * (nodes[:, 2] - 5.0) / 5.0

    # Reaction forces at root (x = 0)
    rf = np.zeros((num_nodes, 3), dtype=np.float64)
    root_nodes = np.where(nodes[:, 0] < 1e-4)[0]
    rf[root_nodes, 2] = 500.0 / len(root_nodes)

    with tempfile.TemporaryDirectory() as tmpdir:
        frd_path = os.path.join(tmpdir, "test_simulation.frd")
        write_frd(frd_path, nodes, elements, displacements, stresses, reaction_forces=rf)

        assert os.path.isfile(frd_path)
        data = parse_frd(frd_path)

        assert len(data.nodes) == num_nodes
        assert len(data.elements) == len(elements)
        assert data.displacements.shape == (num_nodes, 3)
        assert data.stresses.shape == (num_nodes, 6)
        assert data.reaction_forces is not None
        assert np.isclose(np.sum(data.reaction_forces[:, 2]), 500.0)

        # Ingest to FEAResult
        elem_sets = {"steel_root": steel_elems, "alu_tip": alu_elems}
        materials = {
            "steel_root": get_material("S235JR"),
            "alu_tip": get_material("AL6061_T6"),
        }
        res: FEAResult = frd_to_fea_result(
            frd_path,
            materials=materials,
            element_sets=elem_sets,
            study_name="FRD_Ingest_Study",
            part_name="bi_beam",
        )

        assert res.num_nodes == num_nodes
        assert res.num_elements == len(elements)
        assert res.max_displacement_mm > 0.0
        assert res.max_von_mises_mpa > 0.0
        assert res.regional_results is not None
        assert "steel_root" in res.regional_results
        assert "alu_tip" in res.regional_results

        # Verify regional results
        steel_res = res.regional_results["steel_root"]
        alu_res = res.regional_results["alu_tip"]
        assert steel_res.yield_strength_mpa == 235.0
        assert alu_res.yield_strength_mpa == 276.0
        assert steel_res.safety_factor > 0.0
        assert alu_res.safety_factor > 0.0


def test_heterogeneous_steel_aluminum_compliance_difference():
    """
    Physical validation test:
    Compare a pure Steel beam vs a pure Aluminium beam vs a Bi-material (Steel root + Aluminium tip) beam.
    Young's modulus:
    - Steel: E = 210,000 MPa
    - Aluminium: E = 70,000 MPa (~3x more compliant)
    Under identical load, tip deflection must follow:
    delta_steel < delta_bimetal < delta_aluminum
    """
    nodes, elements, steel_elems, alu_elems = _create_two_zone_beam_mesh(nx=8, ny=2, nz=2, lx=60.0, ly=8.0, lz=8.0)
    root_nodes = set(np.where(nodes[:, 0] < 1e-4)[0])
    tip_nodes = np.where(nodes[:, 0] > 59.9)[0]
    nodal_forces = {int(n): (0.0, 0.0, -100.0 / len(tip_nodes)) for n in tip_nodes}

    mat_steel = get_material("S235JR")
    mat_alu = get_material("AL6061_T6")

    # 1. Pure Steel Solve
    sol_steel = LinearElasticitySolver(nodes, elements, mat_steel).solve(root_nodes, nodal_forces)

    # 2. Pure Aluminium Solve
    sol_alu = LinearElasticitySolver(nodes, elements, mat_alu).solve(root_nodes, nodal_forces)

    # 3. Bi-Material Solve (Steel at root, Aluminium at tip)
    elem_materials = []
    for eid in range(len(elements)):
        if eid in steel_elems:
            elem_materials.append(mat_steel)
        else:
            elem_materials.append(mat_alu)

    solver_bimetal = LinearElasticitySolver(nodes, elements, mat_steel, element_materials=elem_materials)
    sol_bimetal = solver_bimetal.solve(root_nodes, nodal_forces)

    # Deflection hierarchy check
    assert sol_alu.max_displacement > sol_bimetal.max_displacement > sol_steel.max_displacement
    # Pure aluminium should deflect ~3x as much as pure steel
    ratio = sol_alu.max_displacement / sol_steel.max_displacement
    assert 2.8 <= ratio <= 3.2, f"Expected deflection ratio ~3.0, got {ratio:.2f}"


def test_calculix_runner_end_to_end_bimetal():
    """
    Full pipeline test for CalculiXRunner:
    Model definition -> .inp generation -> execution -> .frd reader -> FEAResult
    """
    nodes, elements, steel_elems, alu_elems = _create_two_zone_beam_mesh(nx=6, ny=2, nz=2, lx=80.0, ly=10.0, lz=10.0)

    model = CalculiXModel("RunnerBiBeam", nodes, elements)
    model.add_material_region(
        MaterialRegion(name="steel_base", material="S235JR", selector=lambda x, y, z: x <= 40.0)
    )
    model.add_material_region(
        MaterialRegion(name="alu_extension", material="AL6061_T6", selector=lambda x, y, z: x > 40.0)
    )
    model.assign_element_sets()

    # Fixed boundary at x=0
    root_nodes = [int(i) for i in np.where(nodes[:, 0] < 1e-4)[0]]
    model.add_node_set("FIXED_ROOT", root_nodes)
    model.add_boundary_condition("FIXED_ROOT", 1, 3, 0.0)

    # Tip force at x=80
    tip_nodes = [int(i) for i in np.where(nodes[:, 0] > 79.9)[0]]
    model.add_node_set("TIP_FACE", tip_nodes)
    f_per_node = -250.0 / len(tip_nodes)
    for n in tip_nodes:
        model.add_nodal_load(n, 3, f_per_node)

    runner = CalculiXRunner(model)
    result: FEAResult = runner.run(study_name="BiMaterial_Cantilever")

    assert result.num_nodes == len(nodes)
    assert result.num_elements == len(elements)
    assert result.max_displacement_mm > 0.0
    assert result.max_von_mises_mpa > 0.0
    assert result.regional_results is not None
    assert "steel_base" in result.regional_results
    assert "alu_extension" in result.regional_results

    # Both regions must have their specific material limits evaluated
    assert result.regional_results["steel_base"].material_name == "S235JR"
    assert "6061" in result.regional_results["alu_extension"].material_name
    assert result.solver_backend == "builtin"
    assert "Solver Backend   : builtin" in result.summary_report


def test_invalid_material_region_and_unassigned_elements():
    """Negative test: unassigned element sets or invalid material names raise proper exceptions."""
    nodes, elements, _, _ = _create_two_zone_beam_mesh(nx=4, ny=2, nz=2)
    model = CalculiXModel("FaultyModel", nodes, elements)

    # 1. Invalid material name
    with pytest.raises((KeyError, ValueError)):
        model.add_material_region(
            MaterialRegion(name="bad_mat", material="VIBRANIUM_UNOBTANIUM", selector="left")
        )

    # 2. Incomplete coverage (only cover x <= 20, rest of beam unassigned)
    model.add_material_region(
        MaterialRegion(name="partial_zone", material="S235JR", selector=lambda x, y, z: x <= 20.0)
    )
    model.assign_element_sets()

    with pytest.raises(ValueError, match="Not all elements assigned"):
        model.validate_multi_material()


def test_solver_error_conditions():
    """Negative test: underconstrained system (no boundary conditions) raises singular error."""
    nodes, elements, _, _ = _create_two_zone_beam_mesh(nx=3, ny=1, nz=1)
    solver = LinearElasticitySolver(nodes, elements, get_material("S235JR"))

    # Empty fixed nodes -> singular stiffness matrix / rigid body motion
    with pytest.raises(ValueError):
        solver.solve(fixed_nodes=set(), nodal_forces={0: (0.0, 0.0, -10.0)})


def test_fea_image_generation_and_export():
    """Verify export_image creates a high-res PNG with Von Mises stress and safety card."""
    nodes, elements, _, _ = _create_two_zone_beam_mesh(nx=6, ny=2, nz=2, lx=60.0, ly=10.0, lz=10.0)
    model = CalculiXModel("ImageTestModel", nodes, elements)
    model.add_material_region(
        MaterialRegion(name="steel_sec", material="S235JR", selector=lambda x, y, z: x <= 30.0)
    )
    model.add_material_region(
        MaterialRegion(name="alu_sec", material="AL6061_T6", selector=lambda x, y, z: x > 30.0)
    )
    model.assign_element_sets()

    root_nodes = [int(i) for i in np.where(nodes[:, 0] < 1e-4)[0]]
    model.add_node_set("ROOT", root_nodes)
    model.add_boundary_condition("ROOT", 1, 3, 0.0)

    tip_nodes = [int(i) for i in np.where(nodes[:, 0] > 59.9)[0]]
    for n in tip_nodes:
        model.add_nodal_load(n, 3, -150.0 / len(tip_nodes))

    runner = CalculiXRunner(model)
    result = runner.run(study_name="BiMaterial_Image_Test")

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "fea_result.png")
        exported = result.export_image(img_path, deformation_scale=15.0, dpi=120)

        assert os.path.isfile(exported)
        assert os.path.getsize(exported) > 10_000  # Valid PNG image size > 10KB


def test_boundary_condition_explicit_dofs_and_values():
    """Verify that add_boundary_condition writes explicit start_dof, end_dof and non-zero values to .inp."""
    nodes = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 10.0]], dtype=np.float64)
    elements = np.array([[0, 1, 2, 3]], dtype=np.int32)
    model = CalculiXModel("BCTest", nodes, elements)
    model.add_material("steel", "S235JR")

    # 1. Single DOF (e.g. DOF 1 only fixed)
    model.add_boundary_condition(node_set_or_id=1, start_dof=1, end_dof=1, value=0.0)
    # 2. DOF range 1 to 2
    model.add_boundary_condition(node_set_or_id=2, start_dof=1, end_dof=2, value=0.0)
    # 3. Prescribed non-zero displacement in DOF 3
    model.add_boundary_condition(node_set_or_id=3, start_dof=3, end_dof=3, value=-1.5)

    inp = model.to_inp()
    assert "*BOUNDARY" in inp
    assert "1, 1" in inp
    assert "2, 1, 2" in inp
    assert "3, 3, 3, -1.5" in inp

    # Invalid DOF ranges raise ValueError
    with pytest.raises(ValueError, match="Invalid DOF range"):
        model.add_boundary_condition(node_set_or_id=1, start_dof=4, end_dof=2)


def test_overlapping_material_regions_raise_error():
    """Verify that two material regions claiming the same element raise a clear ValueError."""
    nodes, elements, _, _ = _create_two_zone_beam_mesh(nx=4, ny=2, nz=2, lx=40.0)
    model = CalculiXModel("OverlapTest", nodes, elements)

    # Region 1 claims x <= 25
    model.add_material_region(
        MaterialRegion(name="zone1", material="S235JR", selector=lambda x, y, z: x <= 25.0)
    )
    # Region 2 overlaps and claims x >= 15 (overlapping in 15 <= x <= 25)
    model.add_material_region(
        MaterialRegion(name="zone2", material="Alu6061-T6", selector=lambda x, y, z: x >= 15.0)
    )
    model.assign_element_sets()

    with pytest.raises(ValueError, match="Overlapping material regions detected"):
        model.validate_multi_material()


def test_fiber_direction_rejection_not_implemented():
    """Verify that fiber_direction is explicitly rejected with NotImplementedError."""
    with pytest.raises(NotImplementedError, match="Orthotropic material with fiber_direction is not yet supported"):
        MaterialRegion(
            name="composite_ply",
            material="S235JR",
            fiber_direction=(1.0, 0.0, 0.0),
        )


@pytest.mark.requires_ccx
def test_calculix_runner_mocked_external_ccx():
    """Verify that CalculiXRunner properly invokes external ccx binary via subprocess and parses the resulting .frd."""
    from unittest.mock import patch
    nodes, elements, _, _ = _create_two_zone_beam_mesh(nx=3, ny=1, nz=1)
    model = CalculiXModel("MockCCXModel", nodes, elements)
    model.add_material("mat", "S235JR")
    model.add_boundary_condition(1, 1, 3)

    runner = CalculiXRunner(model=model, executable="C:\\opt\\ccx\\ccx.exe", prefer_builtin_fallback=False)

    with tempfile.TemporaryDirectory() as work_dir:
        # Create a mock subprocess runner that creates the expected .frd file when called
        def fake_subprocess_run(cmd, cwd, capture_output, text, timeout):
            # cmd is [executable, job_name]
            job = cmd[1]
            frd_out = os.path.join(cwd, f"{job}.frd")
            write_frd(
                frd_out,
                nodes=np.array([[float(n[1]), float(n[2]), float(n[3])] for n in model.nodes]),
                elements=np.array([[int(x) - 1 for x in e[1:5]] for e in model.elements]),
                displacements=np.zeros((len(model.nodes), 3)),
                stresses=np.ones((len(model.nodes), 6)) * 25.0,
            )
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Job finished successfully"
            mock_res.stderr = ""
            return mock_res

        with patch("subprocess.run", side_effect=fake_subprocess_run) as mock_run:
            result = runner.run(work_dir=work_dir, job_name="test_external_job")
            assert mock_run.called
            call_cmd = mock_run.call_args[0][0]
            assert call_cmd == ["C:\\opt\\ccx\\ccx.exe", "test_external_job"]
            assert result.num_nodes == len(model.nodes)
            assert result.max_von_mises_mpa > 0.0
            assert result.solver_backend == "calculix_ccx"
            assert result.solver_command == "C:\\opt\\ccx\\ccx.exe test_external_job"
            assert "Solver Backend   : calculix_ccx" in result.summary_report
            assert "Solver Command   : C:\\opt\\ccx\\ccx.exe test_external_job" in result.summary_report


@pytest.mark.synthetic_parser
def test_frd_reader_multi_step_and_element_stress_regression():
    """Regression test: multi-step loading sequences, integration/element stress mapping to nodes."""
    raw_frd = """    1C                                                      1
    2C             NODES
   -1          1 0.000000E+00 0.000000E+00 0.000000E+00
   -1          2 1.000000E+01 0.000000E+00 0.000000E+00
   -1          3 0.000000E+00 1.000000E+01 0.000000E+00
   -1          4 0.000000E+00 0.000000E+00 1.000000E+01
   -3
    1C                                                      1
    2C             ELEMENTS
   -1          1         3         1         1
   -2          1          2          3          4
   -3
    1PSTEP                        1
  100CL        1.00000E+00
    -4  DISP        4    1
   -1          1 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
   -1          2 1.00000E-02 0.00000E+00 0.00000E+00 1.00000E-02
   -3
    1PSTEP                        2
  100CL        2.00000E+00
    -4  DISP        4    1
   -1          1 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
   -1          2 2.50000E-02 0.00000E+00 0.00000E+00 2.50000E-02
   -3
    -4  STRESS      6    1
   -1          1 5.00000E+01 0.00000E+00 0.00000E+00 0.00000E+00
   -2 0.00000E+00 0.00000E+00
   -3
"""
    with tempfile.NamedTemporaryFile("w", suffix=".frd", delete=False) as tf:
        tf.write(raw_frd)
        frd_file = tf.name

    try:
        # Default parse returns latest step (step 2)
        data_latest = parse_frd(frd_file)
        assert data_latest.total_steps == 2
        assert data_latest.step == 2
        assert np.isclose(data_latest.displacements[1, 0], 2.50000e-02)

        # Parse specific step 1
        data_step1 = parse_frd(frd_file, step=1)
        assert data_step1.step == 1
        assert np.isclose(data_step1.displacements[1, 0], 1.00000e-02)

        # Element-based stress entity mapping (entity_id=1 mapped to element 1 nodes 1..4)
        assert data_latest.nodal_von_mises[0] > 0.0
    finally:
        if os.path.exists(frd_file):
            os.remove(frd_file)


@pytest.mark.synthetic_parser
def test_frd_reader_partial_blocks_and_cramped_tokens():
    """Verify parse_frd gracefully handles missing blocks (e.g. displacement only) and cramped tokens."""
    cramped_frd = """    2C             NODES
   -1 1 0.00000E+00-1.23456E-05 2.00000E+01
   -1 2 5.00000E+00 0.00000E+00 0.00000E+00
   -1 3 0.00000E+00 5.00000E+00 0.00000E+00
   -1 4 0.00000E+00 0.00000E+00 5.00000E+00
   -3
    2C             ELEMENTS
   -1 1 3 1 1
   -2 1 2 3 4
   -3
    -4  DISP 4 1
   -1 1 0.00000E+00-5.00000E-03 0.00000E+00 5.00000E-03
   -3
"""
    with tempfile.NamedTemporaryFile("w", suffix=".frd", delete=False) as tf:
        tf.write(cramped_frd)
        frd_file = tf.name

    try:
        data = parse_frd(frd_file)
        assert len(data.nodes) == 4
        # Negative exponential parsed without whitespace
        assert np.isclose(data.nodes[0, 1], -1.23456e-05)
        # Displacement parsed
        assert np.isclose(data.displacements[0, 1], -5.00000e-03)
        # Stress block was missing -> zeros, no error
        assert data.stresses.shape == (4, 6)
        assert np.all(data.stresses == 0.0)
        # Reaction forces missing -> None
        assert data.reaction_forces is None
    finally:
        if os.path.exists(frd_file):
            os.remove(frd_file)


def test_fea_result_permanent_dataclass_fields():
    """Verify regional_results, materials, etc. are permanent dataclass fields on FEAResult."""
    from dataclasses import fields
    res = FEAResult(
        study_name="TestStudy",
        part_name="TestPart",
        material=get_material("S235JR"),
        num_nodes=10,
        num_elements=5,
        max_von_mises_mpa=120.0,
        max_displacement_mm=0.05,
        yield_strength_mpa=235.0,
        safety_factor=1.96,
        is_safe=True,
        status="PASS",
        nodal_displacements=np.zeros((10, 3)),
        nodal_von_mises=np.zeros(10),
    )

    field_names = {f.name for f in fields(res)}
    assert "regional_results" in field_names
    assert "materials" in field_names
    assert "element_material_ids" in field_names
    assert "reaction_forces" in field_names
    assert "solver_backend" in field_names
    assert "solver_version" in field_names
    assert "solver_command" in field_names

    # Check default factories & values
    assert isinstance(res.regional_results, dict)
    assert isinstance(res.materials, dict)
    assert res.element_material_ids is None
    assert res.reaction_forces is None
    assert res.solver_backend == "builtin"
    assert "Solver Backend   : builtin" in res.summary_report
    assert "Solver Version   : N/A" in res.summary_report
    assert "Solver Command   : N/A" in res.summary_report
