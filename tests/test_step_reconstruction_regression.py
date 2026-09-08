"""
tests/test_step_reconstruction_regression.py
============================================
Comprehensive regression test suite for CADi SAML STEP reverse-engineering pipeline:
1. Simple box (Basit kutu)
2. Simple cylinder (Basit silindir)
3. Stepped shaft without holes (Kademeli mil)
4. Cylinder with holes (Delikli silindir)
5. Stepped shaft with holes (Delikli kademeli mil - operation order regression)
6. Flange and bolt pattern (Flanş ve PCD bolt pattern)
7. Oblique-axis cylinder (Eğik eksenli silindir - safe rejection)
8. Zero-STEP runtime dependency (STEP silindikten sonra bağımsız çalışan kod)
"""

import os
import sys
import math
import tempfile
import pytest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cadi_saml import Assembly, OCCTBackend
from cadi_saml.reverse.inspection import inspect_step, reconstruct_step, verify_geometric_equivalence


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


# ==============================================================================
# 1. Basit Kutu (Simple Box)
# ==============================================================================
def test_regression_simple_box(temp_dir):
    step_path = os.path.join(temp_dir, "simple_box.step")
    with Assembly("box_assembly", units="mm") as asm:
        asm.add_box("box_part", length=60.0, width=40.0, height=20.0, origin=(5.0, 5.0, 5.0))
    OCCTBackend().export_step(asm.to_ir(), step_path)
    assert os.path.exists(step_path)

    res = reconstruct_step(step_path, part_name="box_part")
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True
    assert res["reconstruction_kind"] == "axis_aligned_box"
    assert "add_box" in res["saml_code"]

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005
    assert geom["area_rel_error"] < 0.01
    assert geom["com_shift_mm"] < 0.5
    assert geom["boolean_diff_volume_mm3"] < 0.5


# ==============================================================================
# 2. Basit Silindir (Simple Cylinder)
# ==============================================================================
def test_regression_simple_cylinder(temp_dir):
    step_path = os.path.join(temp_dir, "simple_cylinder.step")
    with Assembly("cyl_assembly", units="mm") as asm:
        asm.add_cylinder("cyl_part", radius=20.0, height=50.0, origin=(0.0, 0.0, 0.0))
    OCCTBackend().export_step(asm.to_ir(), step_path)

    res = reconstruct_step(step_path, part_name="cyl_part")
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True
    assert res["reconstruction_kind"] == "cylinder"
    assert "add_cylinder" in res["saml_code"]

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005
    assert geom["com_shift_mm"] < 0.5


# ==============================================================================
# 3. Kademeli Mil (Stepped Shaft without Holes)
# ==============================================================================
def test_regression_stepped_shaft(temp_dir):
    step_path = os.path.join(temp_dir, "stepped_shaft.step")
    with Assembly("shaft_assembly", units="mm") as asm:
        asm.add_cylinder("step0", radius=30.0, height=30.0, origin=(0.0, 0.0, 0.0))
        asm.add_cylinder("step1", radius=18.0, height=40.0, origin=(0.0, 0.0, 30.0))
        asm.fuse("step0", "step1")
    OCCTBackend().export_step(asm.to_ir(), step_path)

    res = reconstruct_step(step_path, part_name="shaft_part")
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True
    assert res["reconstruction_kind"] == "stepped_cylinder"
    assert "asm.fuse" in res["saml_code"]

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005
    assert geom["com_shift_mm"] < 0.5


# ==============================================================================
# 4. Delikli Silindir (Cylinder with Axial Hole)
# ==============================================================================
def test_regression_cylinder_with_holes(temp_dir):
    step_path = os.path.join(temp_dir, "cyl_with_hole.step")
    with Assembly("cyl_hole_assembly", units="mm") as asm:
        asm.add_cylinder("cyl_body", radius=25.0, height=60.0, origin=(0.0, 0.0, 0.0))
        asm.add_cylinder("cyl_body", radius=8.0, height=60.0, origin=(0.0, 0.0, 0.0), operation="cut")
    OCCTBackend().export_step(asm.to_ir(), step_path)

    res = reconstruct_step(step_path, part_name="cyl_body")
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True
    assert res["reconstruction_kind"] == "cylinder_with_cylindrical_cuts"
    assert "operation='cut'" in res["saml_code"]

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005
    assert geom["holes_verified"] is True


# ==============================================================================
# 5. Delikli Kademeli Mil (Stepped Shaft with Holes - Key Regression Fix)
# ==============================================================================
def test_regression_stepped_shaft_with_holes(temp_dir):
    step_path = os.path.join(temp_dir, "stepped_with_hole.step")
    with Assembly("stepped_hole_assembly", units="mm") as asm:
        asm.add_cylinder("shaft", radius=35.0, height=30.0, origin=(0.0, 0.0, 0.0))
        asm.add_cylinder("shaft_ext", radius=20.0, height=50.0, origin=(0.0, 0.0, 30.0))
        asm.fuse("shaft", "shaft_ext")
        # Center through-hole along the entire length (80mm)
        asm.add_cylinder("shaft", radius=6.0, height=80.0, origin=(0.0, 0.0, 0.0), operation="cut")
    OCCTBackend().export_step(asm.to_ir(), step_path)

    res = reconstruct_step(step_path, part_name="shaft")
    # Must NOT fail into UNSUPPORTED_RECONSTRUCTION!
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True
    assert res["reconstruction_kind"] == "stepped_cylinder_with_holes"

    code = res["saml_code"]
    assert "asm.fuse" in code
    assert "operation='cut'" in code

    # Verify operation ordering: outer cylinders -> fuse -> cut
    fuse_idx = code.index("asm.fuse")
    cut_idx = code.index("operation='cut'")
    assert fuse_idx < cut_idx, "fuse must occur before cut in the reconstruction sequence"

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005
    assert geom["holes_verified"] is True
    assert geom["boolean_diff_volume_mm3"] < 0.5


# ==============================================================================
# 6. Flanş ve PCD Bolt Pattern (Flange with Pitch Circle Diameter Pattern)
# ==============================================================================
def test_regression_flange_and_bolt_pattern(temp_dir):
    step_path = os.path.join(temp_dir, "flange_pattern.step")
    with Assembly("flange_assembly", units="mm") as asm:
        asm.add_cylinder("flange", radius=50.0, height=15.0, origin=(0.0, 0.0, 0.0))
        pcd_radius = 35.0
        for i in range(4):
            ang = i * (math.pi / 2.0)
            hx = pcd_radius * math.cos(ang)
            hy = pcd_radius * math.sin(ang)
            asm.add_cylinder("flange", radius=4.0, height=15.0, origin=(hx, hy, 0.0), operation="cut")
    OCCTBackend().export_step(asm.to_ir(), step_path)

    res = reconstruct_step(step_path, part_name="flange")
    assert res["status"] == "RECONSTRUCTED"
    assert res["independent"] is True

    # PCD Pattern must be recognized
    assert len(res["pcd_patterns"]) >= 1
    pattern = res["pcd_patterns"][0]
    assert pattern["count"] == 4
    assert pattern["pcd"] == pytest.approx(70.0, abs=0.5)

    # Generated code must cut all 4 holes and include pattern metadata
    assert res["saml_code"].count("operation='cut'") == 4
    assert "PCD Pattern" in res["saml_code"]

    geom = res.get("geometric_equivalence")
    assert geom is not None
    assert geom["passed"] is True
    assert geom["volume_rel_error"] < 0.005


# ==============================================================================
# 7. Eğik Eksenli Silindir (Oblique-Axis Cylinder - Safe Rejection)
# ==============================================================================
def test_regression_oblique_axis_cylinder(temp_dir):
    step_path = os.path.join(temp_dir, "tilted_cyl.step")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs

    # Tilted axis at 45 degrees (non-cardinal / non-principal)
    ax = gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(1.0 / math.sqrt(2.0), 0.0, 1.0 / math.sqrt(2.0)))
    cyl = BRepPrimAPI_MakeCylinder(ax, 15.0, 40.0).Solid()

    writer = STEPControl_Writer()
    writer.Transfer(cyl, STEPControl_AsIs)
    writer.Write(step_path)
    assert os.path.exists(step_path)

    res = reconstruct_step(step_path, part_name="tilted_cyl")
    # Must be safely rejected, not generating faulty geometry
    assert res["status"] == "UNSUPPORTED_RECONSTRUCTION"
    assert res["independent"] is False
    assert res["saml_code"] is None
    assert "cylinder axis is not aligned" in res["error"]


# ==============================================================================
# 8. STEP Silindikten Sonra Bağımsız Çalışan Kod (Zero-STEP Dependency)
# ==============================================================================
def test_regression_zero_step_dependency_after_file_deletion(temp_dir):
    step_path = os.path.join(temp_dir, "ephemeral_source.step")
    with Assembly("source_assembly", units="mm") as asm:
        asm.add_cylinder("body", radius=30.0, height=25.0, origin=(0.0, 0.0, 0.0))
        asm.add_cylinder("neck", radius=15.0, height=35.0, origin=(0.0, 0.0, 25.0))
        asm.fuse("body", "neck")
        asm.add_cylinder("body", radius=6.0, height=60.0, origin=(0.0, 0.0, 0.0), operation="cut")
    OCCTBackend().export_step(asm.to_ir(), step_path)
    assert os.path.exists(step_path)

    # 1. Synthesize standalone CADi SAML code
    res = reconstruct_step(step_path, part_name="ephemeral_part")
    assert res["status"] == "RECONSTRUCTED"
    code = res["saml_code"]

    # 2. DELETE the original STEP file
    os.remove(step_path)
    assert not os.path.exists(step_path), "STEP file must be deleted to prove zero runtime dependency"

    # 3. Verify generated code contains NO step paths or references
    assert ".step" not in code.lower()
    assert "add_step_part" not in code
    assert "import_step" not in code

    # 4. Execute the code in an isolated namespace
    isolated_namespace = {}
    exec(code, isolated_namespace)
    rebuilt_asm = isolated_namespace.get("asm")
    assert isinstance(rebuilt_asm, Assembly)

    # 5. Compile to B-Rep solid
    solids = OCCTBackend().compile(rebuilt_asm.to_ir())
    assert len(solids) == 1
    solid_shape = list(solids.values())[0]
    assert solid_shape is not None and not solid_shape.IsNull()
