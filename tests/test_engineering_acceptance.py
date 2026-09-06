import math
import numpy as np
import pytest
from cadi_saml import (Assembly, OCCTBackend, FEAStudy, get_material, ToleranceStack,
                       DesignStudy, KinematicMechanism, RevoluteJoint, PrismaticJoint,
                       GearRelation, ScrewRelation, STEPReverseEngineer)
from cadi_saml.analysis.solver import LinearElasticitySolver


def tetra_study():
    study = FEAStudy('tetra')
    study.nodes = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    study.elements = np.array([[0, 1, 2, 3]])
    return study


def test_missing_conditions_and_material_are_errors():
    with pytest.raises(ValueError, match='Unknown material'):
        get_material('alumnium_typo')
    s = tetra_study()
    with pytest.raises(ValueError, match='restraints'):
        s.solve()
    s.fix_face('z_min')
    with pytest.raises(ValueError, match='No loads'):
        s.solve()
    s.apply_force('missing_face', (0, 0, -1))
    with pytest.raises(ValueError, match='matched no nodes'):
        s.solve()


def test_pressure_uses_triangle_area_and_normal():
    s = tetra_study().fix_face('z_min').apply_pressure(lambda x, y, z: abs(x+y+z-1) < 1e-9, 2)
    preview = s.preview_boundary_conditions()
    assert preview['loads'][0]['area_mm2'] == pytest.approx(math.sqrt(3) / 2)
    assert preview['resultant_n'] == pytest.approx([-1, -1, -1])
    result = s.solve()
    assert result.solution_valid
    assert result.raw_solution.reaction_forces.sum(axis=0) == pytest.approx([1, 1, 1], abs=1e-9)
    assert result.raw_solution.relative_residual < 1e-10


def test_solver_rotation_invariance_and_moment_balance():
    s = tetra_study()
    forces = {3: (0., 0., -100.)}
    result = LinearElasticitySolver(s.nodes, s.elements, get_material('S235JR')).solve({0, 1, 2}, forces)
    theta = 0.7
    R = np.array([[math.cos(theta), 0, math.sin(theta)], [0, 1, 0], [-math.sin(theta), 0, math.cos(theta)]])
    rotated = LinearElasticitySolver(s.nodes @ R.T, s.elements, get_material('S235JR')).solve({0, 1, 2}, {3: tuple(R @ forces[3])})
    assert rotated.displacements == pytest.approx(result.displacements @ R.T, abs=1e-10)
    assert rotated.max_von_mises == pytest.approx(result.max_von_mises)
    external = np.zeros((4, 3)); external[3] = forces[3]
    assert np.cross(s.nodes, result.reaction_forces + external).sum(axis=0) == pytest.approx([0, 0, 0], abs=1e-9)


def test_solver_rejects_rigid_body_and_degenerate_mesh():
    s = tetra_study()
    with pytest.raises(ValueError, match='Underconstrained'):
        LinearElasticitySolver(s.nodes, s.elements, get_material('S235JR')).solve({0}, {3: (0, 0, -1)})
    s.nodes[3] = [1, 1, 0]
    with pytest.raises(ValueError, match='Degenerate'):
        LinearElasticitySolver(s.nodes, s.elements, get_material('S235JR')).solve({0, 1, 2}, {3: (0, 0, -1)})


def test_configurable_acceptance():
    s = tetra_study().fix_face('z_min').apply_force('z_max', (0, 0, -1))
    s.max_displacement_limit_mm = 1e-20
    result = s.solve()
    assert result.solution_valid and not result.is_safe
    assert result.status == 'WARNING_DISPLACEMENT'
    assert result.criteria_passed['safety_factor']


def test_stackup_negative_coefficients_and_shim():
    s = ToleranceStack().add_dimension_tolerance('housing', 100, -.1, .2)
    s.add_dimension_tolerance('shaft', 98, -.05, .05, coefficient=-1)
    report = s.analyze_stackup()
    assert report['nominal_mm'] == 2
    assert report['minimum_mm'] == pytest.approx(1.85)
    assert report['maximum_mm'] == pytest.approx(2.25)
    recommendation = s.recommend_shim(.3, .8, [1, 1.5, 2])
    assert recommendation['recommendation']['thickness_mm'] == 1.5
    assert not s.recommend_shim(.5, .6, [1, 1.5, 2])['feasible']


def test_design_search_tracks_failures_and_budget():
    def evaluate(p):
        if p['thickness'] == 0:
            raise ValueError('invalid geometry')
        return {'mass': p['thickness'] * 2, 'deflection': 1 / p['thickness']**3}
    study = DesignStudy(evaluate, 'mass', max_trials=4).add_design_constraint('deflection', maximum=.2)
    result = study.optimize_design({'thickness': [0, 1, 2, 3]})
    assert [t['status'] for t in result['trials']] == ['FAILED', 'INFEASIBLE', 'FEASIBLE', 'FEASIBLE']
    assert result['best']['parameters'] == {'thickness': 2}
    with pytest.raises(ValueError, match='budget'):
        study.optimize_design({'thickness': range(5)})


def mechanism():
    m = KinematicMechanism()
    for name in ('a', 'b', 'c'):
        m.add_joint(RevoluteJoint(name, name))
    m.add_relation(GearRelation('a', 'b', .5, False))
    m.add_relation(GearRelation('b', 'c', .5, False))
    return m


def test_loop_closure_and_conflict_at_zero():
    m = mechanism()
    m.add_relation(GearRelation('a', 'c', .25, False))
    assert m.solve_loop_closure('a', 100)['values'] == pytest.approx({'a': 100, 'b': 50, 'c': 25})
    m.relations[-1].ratio = .3
    assert not m.validate_mechanism('a')['valid']
    with pytest.raises(ValueError, match='Inconsistent'):
        m.solve('a', 0)


def test_screw_reverse_and_invalid_trajectory():
    m = KinematicMechanism()
    m.add_joint(RevoluteJoint('s', 's'))
    m.add_joint(PrismaticJoint('n', 'n'))
    m.add_relation(ScrewRelation('s', 'n', 5))
    assert m.solve('n', 10)['s'].angle_deg == 720
    with pytest.raises(ValueError):
        m.solve_trajectory('s', step_deg=0)
    with pytest.raises(ValueError):
        RevoluteJoint('bad', 'bad', axis=(0, 0, 0))


def test_sampled_motion_collisions_and_envelope():
    asm = Assembly('motion')
    asm.add_box('moving', 2, 2, 2)
    asm.add_box('fixed', 2, 2, 2, origin=(5, 0, 0))
    asm.add_prismatic_joint('moving', axis=(1, 0, 0))
    report = asm.check_motion_clearances('moving', [0, 2, 5], min_clearance_mm=1.5)
    assert report['sample_count'] == 3 and report['continuous'] is False
    assert any(e['status'] == 'COLLISION' and e['driver_value'] == 5 for e in report['events'])
    assert any(e['status'] == 'WARNING_PROXIMITY' for e in report['events'])
    assert asm.get_motion_envelope('moving', [0, 5])['bounds_mm'][3] >= 6


def write_step(shape, path):
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone


def test_step_external_cylinder_not_hole(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    path = tmp_path / 'shaft.step'
    write_step(BRepPrimAPI_MakeCylinder(5, 10).Shape(), path)
    result = STEPReverseEngineer.inspect_and_to_saml(str(path))
    assert result['num_holes'] == 0
    assert len(result['external_cylinders']) == 1


def test_step_tilted_pcd_roundtrip_preserves_volume_and_ports(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Trsf, gp_Ax1
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    shape = BRepPrimAPI_MakeCylinder(20, 5).Shape()
    for angle in (0, math.pi/2, math.pi, 3*math.pi/2):
        hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(12*math.cos(angle), 12*math.sin(angle), -1), gp_Dir(0,0,1)), 2, 7).Shape()
        shape = BRepAlgoAPI_Cut(shape, hole).Shape()
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(1,0,0)), .7)
    shape = BRepBuilderAPI_Transform(shape, tr, True).Shape()
    path = tmp_path / 'tilted.step'; write_step(shape, path)
    report = STEPReverseEngineer.inspect_and_to_saml(str(path), part_name='tilted')
    assert report['num_holes'] == 4
    assert report['pcd_patterns'][0]['pcd'] == pytest.approx(24, abs=1e-4)
    assert 'add_pcd_holes' not in report['saml_code']
    namespace = {}; exec(report['saml_code'], namespace)
    imported = OCCTBackend().compile(namespace['asm'].to_ir())['tilted']
    before, after = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, before); BRepGProp.VolumeProperties_s(imported, after)
    assert after.Mass() == pytest.approx(before.Mass(), rel=1e-8)
    assert len(namespace['asm'].to_ir().parts['tilted'].ports) >= 4


def test_fea_mesh_refinement_converges(tmp_path):
    asm = Assembly('convergence'); asm.add_box('beam', 40, 10, 10)
    shape = OCCTBackend().compile(asm.to_ir())['beam']
    values, counts = [], []
    for mesh in (5., 3., 2.):
        s = FEAStudy('beam', shape, mesh_size=mesh).fix_face('x_min').apply_force('x_max', (100, 0, 0))
        result = s.solve()
        values.append(result.max_displacement_mm); counts.append(result.num_elements)
        assert result.raw_solution.reaction_forces.sum(axis=0) == pytest.approx([-100, 0, 0], abs=1e-6)
    expected = 100 * 40 / (100 * 210000)
    assert counts[0] < counts[-1]
    assert abs(values[-1] - expected) / expected < .08
    assert abs(values[-1] - values[-2]) / values[-1] < .03
