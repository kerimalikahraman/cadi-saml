"""
tests/test_fea_analysis.py
==========================
Comprehensive validation tests for the 3D Finite Element Analysis (FEA) engine.
Includes classical Euler-Bernoulli analytical beam benchmarking,
sheet metal bracket structural simulation, and material yield safety factor validation.
"""

import sys
import math
import pytest
from pathlib import Path

# Ensure library/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml import Assembly, OCCTBackend, FEAStudy, FEAResult, Material, get_material


def test_cantilever_beam_analytical_benchmark():
    """
    Benchmark test: Cantilever beam under end load.
    Dimensions: L = 100 mm, width = 20 mm, height = 10 mm.
    Material: S235JR (E = 210,000 MPa, Sy = 235 MPa).
    Applied load: F = 500 N at tip (Z = -500 N).
    
    Euler-Bernoulli Analytical Theory:
    - Bending moment at root: M = F * L = 500 * 100 = 50,000 N*mm
    - Section modulus: Z_sect = (width * height^2) / 6 = (20 * 100) / 6 = 333.33 mm^3
    - Analytical max bending stress: sigma_max = M / Z_sect = 50,000 / 333.33 = 150.0 MPa
    - Moment of inertia: I = 20 * 10^3 / 12 = 1,666.67 mm^4
    - Analytical max tip deflection: delta_max = (F * L^3) / (3 * E * I) = (500 * 10^6) / (3 * 210,000 * 1666.67) = 0.476 mm
    """
    with Assembly("Beam_FEA_Benchmark", units="mm") as asm:
        beam = asm.add_box("test_beam", length=100.0, width=20.0, height=10.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "test_beam" in solids

    # Set up FEA study with fine mesh
    fea = FEAStudy(
        part_name="test_beam",
        solid_shape=solids["test_beam"],
        material="S235JR",
        mesh_size=3.5,
    )
    # Fix root at x=0
    fea.fix_face("x_min")
    # Apply 500 N tip load in -Z direction
    fea.apply_force(face="x_max", force_vector=(0.0, 0.0, -500.0))

    result: FEAResult = fea.solve()

    # Analytical values
    theoretical_stress = 150.0  # MPa
    theoretical_deflection = 0.476  # mm

    # Verify mesh statistics
    assert result.num_nodes > 100
    assert result.num_elements > 300

    # 3D continuum elements are subject to Poisson contractions, root constraint,
    # and shear stiffness inherent to C3D4 linear tetrahedrons compared to 1D Euler-Bernoulli theory.
    assert abs(result.max_von_mises_mpa - theoretical_stress) / theoretical_stress < 0.40
    assert abs(result.max_displacement_mm - theoretical_deflection) / theoretical_deflection < 0.40

    # Check Factor of Safety: Sy = 235 MPa, stress ~150 MPa -> FoS ~ 1.55 - 1.60
    assert result.safety_factor > 1.2
    assert result.is_safe is True
    assert result.status == "PASS"


def test_assembly_add_fea_study_sheet_metal_bracket():
    """Verify Assembly.add_fea_study method on a bent sheet metal bracket."""
    with Assembly("Bracket_Structural_Test", units="mm") as asm:
        bracket = asm.add_sheet_metal_bracket(
            "flanged_bracket",
            bracket_type="L",
            width=50.0,
            length1=60.0,
            length2=40.0,
            thickness=2.0,
            inner_radius=2.0,
            material="S235JR",
        )

        # Directly call add_fea_study on the assembly
        fea = asm.add_fea_study("flanged_bracket", material="S235JR", mesh_size=4.0)
        fea.fix_face("z_min")
        fea.apply_force(face="x_max", force_vector=(0.0, 0.0, -300.0))

    result = fea.solve()

    assert result.num_nodes > 50
    assert result.num_elements > 100
    assert result.max_von_mises_mpa > 0.0
    assert result.max_displacement_mm > 0.0
    assert isinstance(result.summary_report, str)
    assert "CADi FEA STRUCTURAL SIMULATION REPORT" in result.summary_report


def test_material_overload_yield_failure_detection():
    """Verify that excessive load triggers WARNING_YIELD and is_safe = False."""
    with Assembly("Overload_Test", units="mm") as asm:
        asm.add_box("pin", length=30.0, width=10.0, height=10.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    # Aluminum 6061-T6 (Yield strength = 276 MPa)
    fea = FEAStudy(
        part_name="pin",
        solid_shape=solids["pin"],
        material="Alu6061-T6",
        mesh_size=4.0,
    )
    fea.fix_face("x_min")
    # Apply massive load: 25,000 N (2.5 tonnes)
    fea.apply_force(face="x_max", force_vector=(0.0, -25000.0, 0.0))

    result = fea.solve()

    assert result.max_von_mises_mpa > result.yield_strength_mpa
    assert result.safety_factor < 1.0
    assert result.is_safe is False
    assert result.status == "WARNING_YIELD"
