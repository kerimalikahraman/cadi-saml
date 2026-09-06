"""
tests/test_kinematics.py
========================
Unit and integration tests for kinematic mechanism mates, gear trains,
rack & pinion, and interactive 3D WebGL motion animation.
"""

import math
import os
import tempfile
import pytest

from cadi_saml import (
    Assembly,
    GearRelation,
    KinematicMechanism,
    PrismaticJoint,
    RackPinionRelation,
    RevoluteJoint,
)


def test_two_gear_mesh_kinematics():
    """Verify 1:2 speed reduction and opposite rotation for two meshing spur gears."""
    with Assembly("Two_Gears", units="mm") as asm:
        asm.add_spur_gear("pinion", module=2.0, teeth=20, width=12.0)
        asm.add_spur_gear("wheel", module=2.0, teeth=40, width=12.0)

        asm.add_revolute_joint("pinion", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))
        asm.add_revolute_joint("wheel", origin=(60.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

        # Auto-detects ratio from teeth: 20/40 = 0.5
        asm.add_gear_relation("pinion", "wheel")

    # Rotate pinion by +90 degrees
    states = asm.solve_motion("pinion", value=90.0)

    assert "pinion" in states
    assert "wheel" in states

    assert abs(states["pinion"].angle_deg - 90.0) < 1e-6
    # Driven wheel must rotate in reverse direction with half speed (-45 deg)
    assert abs(states["wheel"].angle_deg - (-45.0)) < 1e-6

    # Verify 4x4 transformation matrix is orthogonal rotation
    R = states["wheel"].transform_matrix[:3, :3]
    np_eye = R @ R.T
    assert abs(np_eye[0, 0] - 1.0) < 1e-5
    assert abs(np_eye[1, 1] - 1.0) < 1e-5


def test_three_gear_train_with_idler():
    """
    Verify 3-gear train: Gear1 (driver) -> Gear2 (idler) -> Gear3 (driven).
    Because of the idler, Gear1 and Gear3 rotate in the SAME direction!
    """
    with Assembly("Three_Gear_Train", units="mm") as asm:
        asm.add_spur_gear("g1", module=2.0, teeth=24, width=10.0)
        asm.add_spur_gear("g2", module=2.0, teeth=12, width=10.0)
        asm.add_spur_gear("g3", module=2.0, teeth=48, width=10.0)

        asm.add_revolute_joint("g1", origin=(0.0, 0.0, 0.0))
        asm.add_revolute_joint("g2", origin=(36.0, 0.0, 0.0))
        asm.add_revolute_joint("g3", origin=(96.0, 0.0, 0.0))

        asm.add_gear_relation("g1", "g2")  # ratio = 24/12 = 2.0
        asm.add_gear_relation("g2", "g3")  # ratio = 12/48 = 0.25

    states = asm.solve_motion("g1", value=120.0)

    # g1: +120 deg
    # g2: -120 * (24/12) = -240 deg
    # g3: -(-240) * (12/48) = +60 deg
    assert abs(states["g1"].angle_deg - 120.0) < 1e-6
    assert abs(states["g2"].angle_deg - (-240.0)) < 1e-6
    assert abs(states["g3"].angle_deg - 60.0) < 1e-6


def test_rack_and_pinion_motion():
    """Verify linear translation of gear rack driven by rotational pinion."""
    with Assembly("Steering_Mechanism", units="mm") as asm:
        # Module = 2.0, Teeth = 20 -> Pitch radius = (2.0 * 20) / 2 = 20.0 mm
        asm.add_spur_gear("pinion", module=2.0, teeth=20, width=15.0)
        asm.add_box("rack_bar", length=120.0, width=15.0, height=15.0)

        asm.add_revolute_joint("pinion", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))
        asm.add_prismatic_joint("rack_bar", origin=(0.0, -20.0, 0.0), axis=(1.0, 0.0, 0.0))

        asm.add_rack_pinion_relation("pinion", "rack_bar")

    # Rotate pinion by 90 degrees (pi/2 radians)
    # Expected linear displacement: r * theta = 20.0 * (pi / 2) = 10 * pi ~= 31.4159 mm
    states = asm.solve_motion("pinion", value=90.0)
    expected_disp = 20.0 * (math.pi / 2.0)

    assert abs(states["rack_bar"].translation_mm - expected_disp) < 1e-4


def test_export_motion_html_viewer():
    """Verify interactive 3D WebGL motion HTML export."""
    with Assembly("Gearbox_HTML_Demo", units="mm") as asm:
        asm.add_spur_gear("pinion", module=2.0, teeth=16, width=10.0)
        asm.add_spur_gear("gear", module=2.0, teeth=32, width=10.0)

        asm.add_revolute_joint("pinion", origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))
        asm.add_revolute_joint("gear", origin=(48.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))
        asm.add_gear_relation("pinion", "gear")

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "gearbox_motion.html")
        out = asm.export_motion_html(html_path, title="DUAL SPUR GEARBOX")

        assert os.path.exists(out)
        assert os.path.getsize(out) > 2000

        with open(out, "r", encoding="utf-8") as f:
            html = f.read()

        assert "<!DOCTYPE html>" in html
        assert "<canvas id=\"canvas3d\">" in html
        assert "DUAL SPUR GEARBOX" in html
        assert "playBtn" in html
        assert "angleSlider" in html
        assert "speedSlider" in html
        assert '"pinion"' in html
        assert '"gear"' in html
        assert '"factor": -0.5' in html
