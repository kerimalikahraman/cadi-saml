"""
tests/test_advanced_occt_capabilities.py
========================================
Automated unit tests validating OpenCASCADE advanced capabilities:
1. Proximity & Minimum Clearance Inspection (BRepExtrema_DistShapeShape & asm.check_clearances)
2. Robust Tolerant / Fuzzy Booleans (SetFuzzyValue on BRepAlgoAPI)
3. Automated Shape Healing and Sewing (ShapeFix_Shape & BRepBuilderAPI_Sewing)
4. Dynamic Planar Cross-Sectioning & Slicing (BRepAlgoAPI_Section & asm.get_cross_section_edges)
"""

import pytest
import OCP.BRepPrimAPI as BRepPrimAPI
import OCP.gp as gp
import OCP.BRepAlgoAPI as BRepAlgoAPI

from cadi_saml.core.assembly import Assembly
from cadi_saml.backend.occt_backend import OCCTBackend
from cadi_saml.validation.validation_engineer import ValidationEngineer


def test_clearance_inspection():
    """Verify clearance computation and proximity detection."""
    asm = Assembly("test_clearance")
    
    # Cube 1: from -10 to +10 (length=20), centered at (0, 0, 0) -> X spans [-10, 10]
    asm.add_box("cube1", length=20.0, width=20.0, height=20.0, origin=(0.0, 0.0, 0.0))
    # Cube 2: centered at (25, 0, 0), length=10 -> X spans [20, 30]
    # Distance between X=10 and X=20 is exactly 10.0 mm
    asm.add_box("cube2", length=10.0, width=20.0, height=20.0, origin=(25.0, 0.0, 0.0))

    # Check with min_clearance = 5.0 mm -> distance is 10.0 mm -> should be CLEAR
    reports_clear = asm.check_clearances(min_clearance_mm=5.0)
    assert len(reports_clear) == 1
    rep = reports_clear[0]
    assert abs(rep.distance_mm - 10.0) < 0.01, f"Expected 10.0 mm clearance, got {rep.distance_mm}"
    assert rep.status == "CLEAR"

    # Check with min_clearance = 15.0 mm -> distance 10.0 mm is less than 15.0 -> should be WARNING_PROXIMITY
    reports_warn = asm.check_clearances(min_clearance_mm=15.0)
    assert reports_warn[0].status == "WARNING_PROXIMITY"


def test_fuzzy_boolean():
    """Verify fuzzy boolean handling for tangent and micro-touching faces."""
    asm = Assembly("test_fuzzy")
    # Base plate
    asm.add_box("base", length=50.0, width=50.0, height=10.0, origin=(0.0, 0.0, 5.0))
    # Boss touching exactly flush on top face at Z=10
    asm.add_cylinder("boss", radius=10.0, height=15.0)  # spans Z=0 to 15, intersecting bottom 10mm
    asm.fuse("base", "boss")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "base" in solids
    
    val = ValidationEngineer()
    assert val.check_manifold(solids["base"]), "Fuzzy fused solid should be watertight and manifold"


def test_shape_healing():
    """Verify ShapeFix and Sewing healing functionality."""
    val = ValidationEngineer()
    box = BRepPrimAPI.BRepPrimAPI_MakeBox(15.0, 15.0, 15.0).Shape()
    
    healed = val.heal_shape(box, tolerance=1e-3)
    assert not healed.IsNull()
    assert val.check_manifold(healed)


def test_planar_cross_section():
    """Verify planar slicing with BRepAlgoAPI_Section."""
    asm = Assembly("test_section")
    asm.add_cylinder("column", radius=12.0, height=40.0)

    # Slice horizontally through Z=20
    edges = asm.get_cross_section_edges(origin=(0.0, 0.0, 20.0), normal=(0.0, 0.0, 1.0))
    assert len(edges) > 0, "Expected intersection edges from planar section"
