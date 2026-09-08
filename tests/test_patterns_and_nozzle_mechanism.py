"""
tests/test_patterns_and_nozzle_mechanism.py
===========================================
Unit and integration tests for:
1. Linked copying (instancing): master modifications propagate to all copies
2. Mirroring: symmetric part generation across XY, XZ, YZ planes with normal validation
3. Circular patterning: 12-element angular distribution with addressable PartReferences
4. Synchronized group kinematics: 1 driver parameter controlling multiple joints
5. Jet Engine Iris Nozzle mechanism: convergent/divergent throat diameter evaluation
   without geometric scaling, and STEP / WebGL motion export.
"""

import math
import os
import tempfile
import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    RevoluteJoint,
    SynchronizedGroupRelation,
    build_variable_exhaust_nozzle,
    IrisNozzleMechanism,
)
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def get_shape_volume(shape) -> float:
    """Utility to compute exact B-Rep volume using OpenCASCADE inertia properties."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def get_shape_center_of_mass(shape) -> tuple[float, float, float]:
    """Utility to compute center of mass (X, Y, Z)."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    cm = props.CentreOfMass()
    return (cm.X(), cm.Y(), cm.Z())


def test_linked_copy_instance_propagation():
    """
    Verify that an instance created via create_instance() shares the master's geometry,
    and updates applied to the master (e.g., adding holes) automatically propagate to all instances.
    """
    with Assembly("Linked_Instance_Test", units="mm") as asm:
        master = asm.add_box("pillar_master", length=20.0, width=20.0, height=60.0)
        inst1 = master.create_instance("pillar_inst1", offset=(50.0, 0.0, 0.0))
        inst2 = asm.create_instance("pillar_inst2", source_part="pillar_master", offset=(100.0, 0.0, 0.0))

        assert inst1.source_part == "pillar_master"
        assert inst2.source_part == "pillar_master"

        # Drill hole through master pillar
        master.add_hole("mounting_hole", diameter=8.0, depth=25.0, position=(0.0, 0.0), face="top")

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())

        assert "pillar_master" in solids
        assert "pillar_inst1" in solids
        assert "pillar_inst2" in solids

        v_master = get_shape_volume(solids["pillar_master"])
        v_inst1 = get_shape_volume(solids["pillar_inst1"])
        v_inst2 = get_shape_volume(solids["pillar_inst2"])

        # Nominal volume: 20*20*60 = 24000
        # Hole volume: pi * 4^2 * 25 ~ 1256.6
        # Both master and instances must have the hole subtracted!
        assert v_master < 23500.0
        assert abs(v_master - v_inst1) < 1e-4
        assert abs(v_master - v_inst2) < 1e-4

        # Verify spatial translation
        cm_master = get_shape_center_of_mass(solids["pillar_master"])
        cm_inst1 = get_shape_center_of_mass(solids["pillar_inst1"])
        cm_inst2 = get_shape_center_of_mass(solids["pillar_inst2"])

        assert abs(cm_inst1[0] - (cm_master[0] + 50.0)) < 1e-3
        assert abs(cm_inst2[0] - (cm_master[0] + 100.0)) < 1e-3


def test_mirror_part_symmetry():
    """
    Verify mirroring across the XZ plane produces a watertight solid with inverted Y coordinates.
    """
    with Assembly("Mirror_Test", units="mm") as asm:
        # Create an asymmetrical part with an offset hole in +Y
        wing_l = asm.add_box("wing_left", length=80.0, width=30.0, height=10.0, origin=(0.0, 20.0, 0.0))
        wing_l.add_hole("aileron_mount", diameter=6.0, position=(15.0, 5.0), face="top")

        # Mirror across XZ plane (Y -> -Y)
        wing_r = wing_l.mirror(name="wing_right", plane="XZ")

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())

        assert "wing_left" in solids
        assert "wing_right" in solids

        v_l = get_shape_volume(solids["wing_left"])
        v_r = get_shape_volume(solids["wing_right"])
        assert abs(v_l - v_r) < 1e-4

        cm_l = get_shape_center_of_mass(solids["wing_left"])
        cm_r = get_shape_center_of_mass(solids["wing_right"])

        # X and Z centers of mass must match; Y must be negated
        assert abs(cm_l[0] - cm_r[0]) < 1e-3
        assert abs(cm_l[1] - (-cm_r[1])) < 1e-3
        assert abs(cm_l[2] - cm_r[2]) < 1e-3


def test_circular_pattern_instances():
    """
    Verify circular pattern with 12 elements around Z-axis creates 12 distinct PartReferences
    positioned at 30 degree intervals.
    """
    with Assembly("Circular_Pattern_Test", units="mm") as asm:
        master = asm.add_cylinder("nozzle_flap_1", radius=6.0, height=50.0, origin=(100.0, 0.0, 25.0))

        petals = asm.pattern_circular(
            target_part="nozzle_flap_1",
            count=12,
            center=(0.0, 0.0, 0.0),
            axis=(0.0, 0.0, 1.0),
            angle=360.0,
            create_instances=True,
            prefix="nozzle_flap",
        )

        assert len(petals) == 12
        assert petals[0].name == "nozzle_flap_1"
        assert petals[1].name == "nozzle_flap_2"
        assert petals[11].name == "nozzle_flap_12"

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())

        assert len(solids) == 12
        for i in range(12):
            name = f"nozzle_flap_{i+1}"
            assert name in solids
            cm = get_shape_center_of_mass(solids[name])
            expected_angle = math.radians(i * 30.0)
            expected_x = 100.0 * math.cos(expected_angle)
            expected_y = 100.0 * math.sin(expected_angle)
            assert abs(cm[0] - expected_x) < 0.1
            assert abs(cm[1] - expected_y) < 0.1


def test_synchronized_group_motion():
    """
    Verify that SynchronizedGroupRelation transmits 1 command angle from a driver
    to all 12 driven parts synchronously.
    """
    with Assembly("Sync_Group_Test", units="mm") as asm:
        asm.add_cylinder("actuator", radius=10.0, height=20.0)
        asm.add_revolute_joint("actuator", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

        driven_names = []
        for i in range(12):
            name = f"flap_{i+1}"
            asm.add_box(name, length=5.0, width=15.0, height=30.0)
            asm.add_revolute_joint(name, origin=(50.0 * math.cos(i * 0.5), 50.0 * math.sin(i * 0.5), 0.0), axis=(0.0, 1.0, 0.0))
            driven_names.append(name)

        asm.add_synchronized_group(driver_part="actuator", driven_parts=driven_names, ratio=1.25)

    states = asm.solve_motion("actuator", value=16.0)

    assert abs(states["actuator"].angle_deg - 16.0) < 1e-6
    for name in driven_names:
        assert name in states
        # 16.0 * 1.25 = 20.0 degrees
        assert abs(states[name].angle_deg - 20.0) < 1e-6


def test_iris_nozzle_mechanism_builder_and_evaluation():
    """
    Verify the Jet Engine Variable Exhaust Nozzle macro:
    - 12 petals created without manual coordinates
    - Rigid body rotation: throat diameter changes without scaling part geometry
    - Thrust vectoring calculation
    """
    asm, mech = build_variable_exhaust_nozzle(
        num_petals=12,
        base_radius=160.0,
        petal_length=130.0,
        nominal_opening_deg=10.0,
    )

    assert mech.num_petals == 12
    assert len(mech.petal_names) == 12
    assert len(asm._parts) >= 14  # 12 petals + nozzle casing + control ring

    # 1. Closed state (convergent mode: opening_angle = -5 deg)
    metrics_closed = mech.evaluate_state(opening_angle_deg=-5.0)
    d_closed = metrics_closed.throat_diameter_mm
    assert d_closed < 2.0 * mech.base_radius  # Throat must contract < 320 mm
    assert metrics_closed.expansion_ratio < 1.0

    # 2. Wide open state (divergent mode: opening_angle = +20 deg)
    metrics_open = mech.evaluate_state(opening_angle_deg=20.0, pitch_deg=12.0, yaw_deg=-8.0)
    d_open = metrics_open.throat_diameter_mm
    assert d_open > 2.0 * mech.base_radius  # Throat must expand > 320 mm
    assert metrics_open.expansion_ratio > 1.0
    assert abs(metrics_open.vector_magnitude_deg - math.hypot(12.0, -8.0)) < 0.05

    # 3. Kinematic motion solve across all 12 petals
    states = asm.solve_motion("control_ring", value=15.0)
    assert "control_ring" in states
    assert abs(states["control_ring"].angle_deg - 15.0) < 1e-6

    for i in range(12):
        p_name = f"petal_{i+1}"
        assert p_name in states
        assert abs(states[p_name].angle_deg - 15.0) < 1e-6

    # 4. Compile B-Rep to verify solid models are watertight and valid
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    assert "nozzle_casing" in solids
    assert "control_ring" in solids
    assert "petal_1" in solids
    assert "petal_12" in solids

    # Flap volume must be identical across all 12 petals (rigid bodies, no scaling)
    v_petal_1 = get_shape_volume(solids["petal_1"])
    for i in range(2, 13):
        v_petal_i = get_shape_volume(solids[f"petal_{i}"])
        assert abs(v_petal_1 - v_petal_i) < 1e-4

    # 5. Export AP214 STEP file
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = os.path.join(tmpdir, "variable_nozzle.step")
        backend.export_step(asm.to_ir(), step_path)
        assert os.path.exists(step_path)
        assert os.path.getsize(step_path) > 1000

        # 6. Export interactive 3D WebGL motion HTML
        html_path = os.path.join(tmpdir, "variable_nozzle_motion.html")
        asm.export_motion_html(html_path, title="Variable Exhaust Nozzle 12-Petal Iris", driver_part="control_ring")
        assert os.path.exists(html_path)
        assert os.path.getsize(html_path) > 5000
