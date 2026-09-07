"""
tests/test_advanced_features.py

Comprehensive tests for:
1. Parametric Dependency and Impact Analysis (cadi_saml.core.impact)
2. High-energy propulsion & rocket nozzle aerodynamics (cadi_saml.systems.propulsion)
3. External solver export plugins (OpenFOAM & CalculiX in cadi_saml.simulation.plugins)
"""

import os
import tempfile
import pytest
import numpy as np

from cadi_saml.core.assembly import Assembly
from cadi_saml.core.impact import DependencyImpactAnalyzer, ImpactReport
from cadi_saml.systems.propulsion import GasMixture, RocketNozzle, NozzleAeroState
from cadi_saml.simulation.plugins.openfoam import OpenFOAMCaseExporter
from cadi_saml.simulation.plugins.calculix import CalculiXInputExporter
from cadi_saml.backend.occt_backend import OCCTBackend


# ==============================================================================
# 1. Dependency & Impact Analysis Tests
# ==============================================================================

def test_dependency_impact_analyzer():
    asm = Assembly("gearbox_housing")
    asm.set_var("shaft_dia", 25.0)
    asm.set_var("bearing_bore", "shaft_dia + 0.05")
    asm.set_var("housing_flange", "bearing_bore * 2.0")

    box = asm.add_box("casing", length=120.0, width=80.0, height=50.0)
    box.add_hole("shaft_hole", diameter=25.0, depth=50.0)

    # 1. Preview a safe parameter change
    report = asm.preview_parameter_change("shaft_dia", 30.0)
    assert isinstance(report, ImpactReport)
    assert report.parameter == "shaft_dia"
    assert report.current_value == 25.0
    assert report.proposed_value == 30.0

    # Dependent cascading variables must be identified
    assert "bearing_bore" in report.dependent_variables
    assert "housing_flange" in report.dependent_variables
    assert "casing" in report.affected_parts
    assert report.volume_delta_mm3 > 0.0
    assert report.can_auto_commit is True

    # 2. Preview an illegal parameter change (negative value)
    illegal_report = asm.preview_parameter_change("shaft_dia", -5.0)
    assert illegal_report.can_auto_commit is False
    assert len(illegal_report.broken_constraints) >= 1


# ==============================================================================
# 2. Rocket Nozzle Propulsion Tests
# ==============================================================================

def test_rocket_nozzle_aerothermodynamics_and_cad():
    gas = GasMixture(
        name="LOX_Methane",
        gamma=1.22,
        molecular_weight_g_mol=20.5,
        chamber_pressure_bar=60.0,
        chamber_temperature_k=3350.0,
    )

    nozzle = RocketNozzle(
        name="upper_stage_engine",
        throat_diameter_mm=50.0,
        expansion_area_ratio=16.0,
        chamber_diameter_mm=100.0,
        gas_properties=gas,
        num_cooling_channels=48,
    )

    # 1. Aerothermodynamic gas dynamics
    aero = nozzle.calculate_aerothermodynamic_performance()
    assert isinstance(aero, NozzleAeroState)
    assert aero.mach_exit > 3.0  # Supersonic exit Mach
    assert aero.exhaust_velocity_m_s > 2500.0  # High specific velocity
    assert aero.isp_vacuum_s > 300.0  # Competitive vacuum Isp in seconds
    assert aero.thrust_vacuum_n > 10000.0  # > 10 kN thrust

    # 2. Regenerative Cooling Channel Pressure Drop
    cool_res = nozzle.analyze_regenerative_cooling_channels(coolant_mass_flow_kg_s=3.0)
    assert cool_res["num_channels"] == 48
    assert cool_res["flow_velocity_m_s"] > 1.0
    assert cool_res["is_cooling_pressure_drop_acceptable"] is True

    # 3. 3D CAD Geometry & Solid Compilation
    asm = nozzle.to_assembly()
    assert len(asm._parts) >= 3  # Chamber + Bell + Flange

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert len(solids) >= 3
    for shape in solids.values():
        assert not shape.IsNull()


# ==============================================================================
# 3. External Solver Export Plugins (OpenFOAM & CalculiX)
# ==============================================================================

def test_external_solvers_openfoam_and_calculix_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Test OpenFOAM Case Exporter
        of_dir = os.path.join(tmpdir, "openfoam_case")
        of_exporter = OpenFOAMCaseExporter(solver="simpleFoam", end_time=500.0)
        created_files = of_exporter.export_case(
            case_directory=of_dir,
            domain_length_m=2.0,
            domain_diameter_or_width_m=0.1,
            kinematic_viscosity_m2_s=1e-6,
        )

        assert len(created_files) == 5
        assert os.path.exists(os.path.join(of_dir, "system", "controlDict"))
        assert os.path.exists(os.path.join(of_dir, "system", "fvSchemes"))
        assert os.path.exists(os.path.join(of_dir, "system", "blockMeshDict"))
        assert os.path.exists(os.path.join(of_dir, "constant", "transportProperties"))

        # Verify content of controlDict
        with open(os.path.join(of_dir, "system", "controlDict"), "r", encoding="utf-8") as f:
            cd_text = f.read()
            assert "application     simpleFoam;" in cd_text
            assert "endTime         500.0;" in cd_text

        # 2. Test CalculiX Input Exporter
        ccx_file = os.path.join(tmpdir, "bracket.inp")
        ccx_exporter = CalculiXInputExporter(job_name="bracket_stress_study")

        nodes = np.array([
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ])
        elements = np.array([
            [0, 1, 2, 3],
        ])
        fixed_nodes = [1]
        forces = {4: (0.0, 0.0, -500.0)}

        exported_path = ccx_exporter.export_inp(
            filepath=ccx_file,
            nodes=nodes,
            elements=elements,
            fixed_node_ids=fixed_nodes,
            loaded_nodes_forces=forces,
            analysis_type="static",
        )

        assert os.path.exists(exported_path)
        with open(exported_path, "r", encoding="utf-8") as f:
            inp_text = f.read()
            assert "*NODE, NSET=NALL" in inp_text
            assert "*ELEMENT, TYPE=C3D4" in inp_text
            assert "*BOUNDARY" in inp_text
            assert "*CLOAD" in inp_text
            assert "-500.0000" in inp_text
