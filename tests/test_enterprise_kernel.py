"""
Unit and Integration Tests for CADI-SAML Enterprise Parametric Kernel Extensions.
Verifies all 10 priority tracks:
1. Feature Tree & Parametric DAG Recompute
2. 2D Sketch & Geometric Constraint Solver (DOF Tracking)
3. 3D Assembly Mate & Kinematic DOF System
4. Geometry Query & Introspection API
5. Manufacturability (DFM) & GD&T System
6. Analytical Involute Gear & Mechanism Geometries
7. Engineering Calculation Macros & Materials DB
8. Patch, Repair & Structured Error Model for LLMs
9. Large Assembly Performance (Incremental Cache & BVH)
10. Reverse Engineering & B-Rep Feature Recognition
"""

import pytest
import math
from cadi_saml import (
    Assembly,
    EngineeringSpecification,
    FeatureTree,
    PadFeature,
    HoleFeature,
    FilletFeature,
    SketchSolver,
    AssemblyMateSolver,
    ConcentricMate,
    DistanceMate,
    GearMeshMate,
    calculate_iso_fit,
    ToleranceStack,
    InvoluteGearParameters,
    calculate_shaft_diameter,
    calculate_keyway_stresses,
    calculate_bearing_l10h_life,
    calculate_bolt_preload,
    calculate_pressure_vessel_wall_thickness,
    get_material,
    ShapeCache,
    SpatialIndex,
    AABB,
    STEPFeatureRecognizer,
    CADIErrorPayload,
    E_DIMENSION_CONFLICT,
    E_DFM_VIOLATION,
)
from cadi_saml.manufacturing import check_hole_aspect_ratios


def test_feature_tree_dag_recompute():
    """1. Feature Tree & Parametric DAG Recompute."""
    tree = FeatureTree("ParametricBox")
    pad = PadFeature(name="base_pad", length=80.0, width=60.0, height=20.0)
    tree.add_feature(pad)

    hole = HoleFeature(parent=pad, diameter=10.0, depth=25.0, origin=(20.0, 0.0, 0.0), name="hole1")
    tree.add_feature(hole)

    shape1 = tree.recompute()
    assert shape1 is not None
    assert not pad.is_dirty
    assert not hole.is_dirty

    # Parametric modification
    pad.update_input("length", 120.0)
    assert pad.is_dirty
    assert hole.is_dirty

    shape2 = tree.recompute()
    assert shape2 is not None
    assert not pad.is_dirty
    assert not hole.is_dirty


def test_2d_sketch_constraint_solver():
    """2. 2D Sketch & Geometric Constraint Solver."""
    solver = SketchSolver("TestTriangle")
    p1 = solver.add_point(0.0, 0.0, fixed=True)
    p2 = solver.add_point(10.0, 2.0)
    p3 = solver.add_point(5.0, 8.0)

    l1 = solver.add_line(p1, p2)
    l2 = solver.add_line(p2, p3)
    l3 = solver.add_line(p3, p1)

    solver.constrain_horizontal(l1)
    solver.constrain_distance(p1, p2, 50.0)
    solver.constrain_distance(p1, p3, 40.0)
    solver.constrain_distance(p2, p3, 30.0)

    res = solver.solve()
    assert res["converged"]
    assert res["status"] == "fully_constrained"
    assert res["free_dof"] == 0
    assert abs(p1.x - 0.0) < 1e-3 and abs(p1.y - 0.0) < 1e-3
    assert abs(p2.x - 50.0) < 1e-3
    assert abs(p3.x - 32.0) < 1e-2
    assert abs(p3.y - 24.0) < 1e-2


def test_3d_assembly_mate_solver():
    """3. 3D Assembly Mate & Kinematic DOF System."""
    solver = AssemblyMateSolver("GearTrain")
    solver.ground("chassis")
    solver.add_part("motor_shaft")

    # Only concentric mate -> 2 free DOFs (axial translation + spin)
    solver.add_mate(ConcentricMate("chassis", "motor_shaft"))
    dof1 = solver.analyze_dof()
    assert dof1["status"] == "under_constrained"
    assert dof1["free_dof"] == 2

    # Add distance mate -> 1 free DOF (spin only)
    solver.add_mate(DistanceMate("chassis", "motor_shaft", 15.0))
    dof2 = solver.analyze_dof()
    assert dof2["free_dof"] == 1


def test_geometry_inspection_query():
    """4. Geometry Query & Introspection API."""
    asm = Assembly("QueryTest")
    asm.add_box("b1", 30.0, 30.0, 15.0, origin=(0.0, 0.0, 0.0))
    asm.add_cylinder("c1", radius=4.0, height=25.0, origin=(50.0, 0.0, 0.0))

    # Inspect
    info = asm.inspect("b1")
    assert info["volume_mm3"] == 13500.0
    assert info["face_count"] == 6

    # Closest distance
    dist = asm.closest_distance("b1", "c1")
    # b1 extends to x=15, c1 center=50, radius=4 -> edge=46. Dist = 46 - 15 = 31.0
    assert abs(dist - 31.0) < 0.1


def test_dfm_audit_and_iso_fits():
    """5. Manufacturability (DFM) & GD&T Tolerance System."""
    # ISO Fit calculation
    fit = calculate_iso_fit(30.0, "H7", "g6")
    assert fit["fit_type"] == "clearance"
    assert fit["nominal_diameter_mm"] == 30.0
    assert fit["clearance_min_um"] >= 0.0

    # Tolerance Stackup
    stack = ToleranceStack("TestStack")
    stack.add(50.0, 0.05, 0.05, direction=1)
    stack.add(20.0, 0.02, 0.02, direction=-1)
    stack.add(29.0, 0.02, 0.02, direction=-1)
    res = stack.analyze()
    assert res["nominal_gap"] == 1.0
    assert res["worst_case"]["min_gap"] == 0.91
    assert res["worst_case"]["max_gap"] == 1.09


def test_involute_gear_kinematics():
    """6. Analytical Involute Gear & Mechanism Geometries."""
    pinion = InvoluteGearParameters(module=2.0, teeth=20)
    gear = InvoluteGearParameters(module=2.0, teeth=60)

    mesh = pinion.calculate_mesh(gear)
    assert mesh["center_distance_mm"] == 80.0
    assert mesh["gear_ratio"] == 3.0
    assert mesh["is_continuous_mesh"]
    assert mesh["contact_ratio"] > 1.2


def test_machinery_formulas():
    """7. Engineering Calculation Macros & Materials Database."""
    mat = get_material("S355J2")
    assert mat is not None
    assert mat.yield_strength_mpa == 355.0

    shaft = calculate_shaft_diameter(torque_nm=200.0, allowable_shear_stress_mpa=40.0)
    assert shaft["calculated_min_diameter_mm"] > 25.0
    assert shaft["recommended_standard_diameter_mm"] >= shaft["calculated_min_diameter_mm"]

    key = calculate_keyway_stresses(torque_nm=150.0, shaft_dia_mm=30.0, key_width_mm=8.0, key_height_mm=7.0, key_length_mm=40.0)
    assert key["shear_safe"]
    assert key["pressure_safe"]

    bearing = calculate_bearing_l10h_life(dynamic_load_rating_c_kn=30.0, equivalent_radial_load_p_kn=3.0, speed_rpm=1000)
    assert bearing["l10h_hours"] > 10000.0


def test_patch_preview_engine():
    """8. Patch, Repair & Structured Error Model."""
    asm = Assembly("PatchTest")
    asm.add_box("part1", 40.0, 40.0, 20.0)

    # Valid patch
    valid_patch = asm.preview_patch({"parts.part1.parameters.length": 60.0})
    assert valid_patch.is_valid
    valid_patch.apply()
    assert asm._parts["part1"].parameters["length"] == 60.0

    # Invalid patch (negative dimension)
    invalid_patch = asm.preview_patch({"parts.part1.parameters.length": -10.0})
    assert not invalid_patch.is_valid
    assert len(invalid_patch.errors) > 0
    assert invalid_patch.errors[0].code == E_DIMENSION_CONFLICT


def test_performance_shape_cache_and_bvh():
    """9. Large Assembly Performance (Incremental Cache & BVH)."""
    h1 = ShapeCache.compute_hash("cylinder", {"radius": 10.0, "height": 40.0})
    h2 = ShapeCache.compute_hash("cylinder", {"height": 40.0, "radius": 10.0})
    assert h1 == h2

    spatial = SpatialIndex()
    spatial.boxes.append(AABB(0, 0, 0, 10, 10, 10, tag="boxA"))
    spatial.boxes.append(AABB(5, 5, 5, 15, 15, 15, tag="boxB"))
    spatial.boxes.append(AABB(200, 200, 200, 220, 220, 220, tag="boxC"))

    clashes = spatial.find_potential_clashes()
    assert clashes == [("boxA", "boxB")]


def test_reverse_engineering_recognizer():
    """10. Reverse Engineering & B-Rep Feature Recognition."""
    asm = Assembly("ReverseTest")
    asm.add_flange("test_flange", outer_diameter=100.0, thickness=12.0, bolt_count=4, bolt_pcd=75.0, bolt_diameter=8.0)
    solids = asm.compile_solids()
    shape = solids["test_flange"]

    recognizer = STEPFeatureRecognizer(shape=shape)
    report = recognizer.recognize()
    assert report["volume_mm3"] > 0.0
    assert len(report["detected_holes"]) == 4


def test_engineering_specification_compiler():
    """Full Declarative Engineering Specification to Assembly Compiler."""
    spec_dict = {
        "name": "SpecAssembly",
        "derived_parameters": {
            "shaft_d": 30.0,
            "flange_dia": "shaft_d * 3.5",
        },
        "parts": [
            {
                "name": "shaft",
                "type": "cylinder",
                "parameters": {"radius": "shaft_d / 2.0", "height": 100.0}
            },
            {
                "name": "flange",
                "type": "flange",
                "parameters": {
                    "outer_diameter": "flange_dia",
                    "thickness": 16.0,
                    "bolt_count": 4,
                    "bolt_pcd": "flange_dia - 25.0",
                    "bolt_diameter": 10.0
                }
            }
        ],
        "constraints": [
            {"type": "concentric", "part_a": "flange", "part_b": "shaft"}
        ]
    }

    spec = EngineeringSpecification.from_dict(spec_dict)
    asm = spec.compile()
    assert "shaft" in asm._parts
    assert "flange" in asm._parts
    assert asm._parts["shaft"].parameters["radius"] == 15.0
    assert asm._parts["flange"].parameters["outer_diameter"] == 105.0

    dof = asm.analyze_assembly_dof()
    assert dof["status"] == "under_constrained"
    assert dof["free_dof"] == 2
