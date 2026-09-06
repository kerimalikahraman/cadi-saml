"""
tests.test_sprint1_features
===========================
Comprehensive test suite for Sprint 1 engineering modules:
1. Automated Bill of Materials (BOM) Generation (Markdown, CSV, JSON, HTML)
2. Standard Seals Library (O-Ring Torus, Radial Shaft Seal DIN 3760)
3. Standard Couplings Library (Flexible Jaw, Rigid Flange DIN 115, Oldham)
4. Batch Parametric Variant Export Pipeline
5. Constraint & Port Debugger Diagnostics with HTML Report
"""

import json
import os
import tempfile
import pytest

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
    BOMReport,
    BOMItem,
    Seal,
    Coupling,
    BatchExportPipeline,
    ConstraintDebugger,
)


class TestBOMGeneration:
    """Test Bill of Materials extraction, aggregation, and multi-format export."""

    def test_bom_extraction_and_markdown(self):
        with Assembly("Transmission_Gearbox", units="mm", material="Al6061") as asm:
            # Structural housing
            asm.add_box("gearbox_casing", length=120.0, width=100.0, height=80.0)
            # Shafts
            asm.add_cylinder("input_shaft", radius=10.0, height=140.0)
            asm.add_cylinder("output_shaft", radius=15.0, height=160.0)
            # Bearings
            asm.add_bearing("bearing_in_1", standard="SKF", code="6000")
            asm.add_bearing("bearing_in_2", standard="SKF", code="6000")
            # Fasteners
            asm.add_bolt("cover_bolt_1", size="M6", length=25.0)
            asm.add_bolt("cover_bolt_2", size="M6", length=25.0)
            asm.add_bolt("cover_bolt_3", size="M6", length=25.0)
            asm.add_bolt("cover_bolt_4", size="M6", length=25.0)

        # 1. Raw report
        raw_bom: BOMReport = asm.generate_bom(format="raw")
        assert raw_bom.assembly_name == "Transmission_Gearbox"
        assert raw_bom.total_parts_count == 9
        assert raw_bom.unique_parts_count == 5  # casing, input_shaft, output_shaft, bearing_in, cover_bolt
        assert raw_bom.total_mass_kg > 0.1

        # Check grouped fastener
        fastener_item = next(it for it in raw_bom.items if "Bolt" in it.name)
        assert fastener_item.quantity == 4
        assert fastener_item.category == "Fastener"
        assert "M6" in fastener_item.standard_code

        # Check grouped bearing
        bearing_item = next(it for it in raw_bom.items if "Bearing" in it.name)
        assert bearing_item.quantity == 2
        assert bearing_item.category == "Bearing"

        # 2. Markdown output
        md = asm.generate_bom(format="markdown")
        assert "| Item | Name / Description |" in md
        assert "Transmission_Gearbox" in md
        assert f"{raw_bom.total_mass_kg:.4f} kg" in md

    def test_bom_csv_json_and_html_export(self):
        with Assembly("Pump_Assembly", units="mm", material="CastIron") as asm:
            asm.add_cylinder("pump_housing", radius=40.0, height=60.0)
            asm.add_seal("housing_oring", seal_type="oring", inner_dia=50.0, cross_section=3.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bom.csv")
            json_path = os.path.join(tmpdir, "bom.json")
            html_path = os.path.join(tmpdir, "bom.html")

            # CSV
            csv_str = asm.generate_bom(format="csv", filepath=csv_path)
            assert os.path.exists(csv_path)
            assert "Item No,Part Name,Standard Code" in csv_str
            assert "Housing Oring" in csv_str

            # JSON
            json_str = asm.generate_bom(format="json", filepath=json_path)
            assert os.path.exists(json_path)
            data = json.loads(json_str)
            assert data["assembly_name"] == "Pump_Assembly"
            assert len(data["items"]) == 2

            # HTML
            html_str = asm.generate_bom(format="html", filepath=html_path)
            assert os.path.exists(html_path)
            assert "<!DOCTYPE html>" in html_str
            assert "Bill of Materials: Pump_Assembly" in html_str
            assert "badge-seal" in html_str


class TestStandardSeals:
    """Test Seal factory and B-Rep compilation (O-Ring Torus & DIN 3760 Radial Seal)."""

    def test_oring_geometry_and_ports(self):
        with Assembly("Sealing_Test", units="mm") as asm:
            oring = asm.add_seal(
                "head_oring",
                seal_type="oring",
                inner_dia=30.0,
                cross_section=3.5,
                material="FKM75",
            )
            assert "bore" in oring.ports
            assert "groove" in oring.ports
            assert "center" in oring.ports
            assert oring.ports["bore"].diameter == 30.0
            assert oring.ports["groove"].diameter == 37.0  # 30 + 2*3.5

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())
        assert "head_oring" in solids
        solid = solids["head_oring"]

        val = ValidationEngineer()
        assert val.check_manifold(solid) is True

        # Torus volume analytical: V = 2 * pi^2 * R * r^2
        # R = 15 + 1.75 = 16.75, r = 1.75 -> V ~= 2 * pi^2 * 16.75 * 3.0625 ~= 1012.3 mm³
        props = asm.get_mass_properties()
        vol = props["parts"]["head_oring"]["volume_mm3"]
        assert 950.0 < vol < 1100.0

    def test_radial_shaft_seal_geometry_and_ports(self):
        with Assembly("Shaft_Seal_Test", units="mm") as asm:
            seal = asm.add_seal(
                "crank_oil_seal",
                seal_type="radial_shaft_seal",
                shaft_dia=25.0,
                outer_dia=42.0,
                width=7.0,
                material="NBR70",
            )
            assert "shaft_bore" in seal.ports
            assert "housing_seat" in seal.ports
            assert "front_face" in seal.ports
            assert "rear_face" in seal.ports

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())
        assert "crank_oil_seal" in solids
        solid = solids["crank_oil_seal"]

        val = ValidationEngineer()
        assert val.check_manifold(solid) is True


class TestStandardCouplings:
    """Test Coupling factory: Flexible Jaw, Rigid Flange DIN 115, and Oldham."""

    def test_rigid_flange_coupling_compilation(self):
        with Assembly("Rigid_Coupling_Test", units="mm") as asm:
            cpl = asm.add_coupling(
                "motor_drive_coupling",
                coupling_type="rigid_flange",
                shaft1_dia=20.0,
                shaft2_dia=25.0,
                outer_dia=80.0,
                length=70.0,
                bolt_count=4,
                bolt_pcd=60.0,
            )
            assert "hub1_bore" in cpl.ports
            assert "hub2_bore" in cpl.ports
            assert "flange_interface" in cpl.ports

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())
        assert "motor_drive_coupling" in solids
        solid = solids["motor_drive_coupling"]

        val = ValidationEngineer()
        assert val.check_manifold(solid) is True

    def test_flexible_jaw_coupling_compilation(self):
        with Assembly("Jaw_Coupling_Test", units="mm") as asm:
            cpl = asm.add_coupling(
                "cnc_spindle_coupling",
                coupling_type="flexible_jaw",
                shaft1_dia=14.0,
                shaft2_dia=16.0,
                outer_dia=55.0,
                length=66.0,
            )
            assert "hub1_bore" in cpl.ports
            assert "hub2_bore" in cpl.ports
            assert "center" in cpl.ports

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())
        assert "cnc_spindle_coupling" in solids
        solid = solids["cnc_spindle_coupling"]

        val = ValidationEngineer()
        assert val.check_manifold(solid) is True

    def test_oldham_coupling_compilation(self):
        with Assembly("Oldham_Coupling_Test", units="mm") as asm:
            cpl = asm.add_coupling(
                "stepper_lead_coupling",
                coupling_type="oldham",
                shaft1_dia=8.0,
                shaft2_dia=8.0,
                outer_dia=30.0,
                length=40.0,
            )
            assert "hub1_bore" in cpl.ports
            assert "hub2_bore" in cpl.ports

        backend = OCCTBackend()
        solids = backend.compile(asm.to_ir())
        assert "stepper_lead_coupling" in solids
        solid = solids["stepper_lead_coupling"]

        val = ValidationEngineer()
        assert val.check_manifold(solid) is True


class TestBatchExportPipeline:
    """Test Batch Parametric Sweep and multi-format compilation."""

    def test_batch_export_variants(self):
        def build_shaft(params):
            asm = Assembly("Parametric_Shaft", units="mm")
            asm.add_cylinder("main_body", radius=params["radius"], height=params["length"])
            return asm

        variants = [
            {"name": "shaft_short", "radius": 10.0, "length": 50.0},
            {"name": "shaft_medium", "radius": 15.0, "length": 100.0},
            {"name": "shaft_heavy", "radius": 20.0, "length": 150.0},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            report = BatchExportPipeline.run(
                model_or_factory=build_shaft,
                variants=variants,
                output_dir=tmpdir,
                formats=["step", "stl"],
            )

            assert report.total_variants == 3
            assert report.successful_count == 3
            assert report.failed_count == 0

            # Check individual outputs
            for var_res in report.variants:
                assert var_res.status == "SUCCESS"
                assert "step" in var_res.output_files
                assert "stl" in var_res.output_files
                assert os.path.exists(var_res.output_files["step"])
                assert os.path.exists(var_res.output_files["stl"])
                assert var_res.mass_kg > 0.0

            # Check summary manifest
            summary_path = os.path.join(tmpdir, "batch_summary.json")
            assert os.path.exists(summary_path)
            with open(summary_path, "r") as f:
                data = json.load(f)
            assert data["successful_count"] == 3


class TestConstraintDebugger:
    """Test Degrees-of-Freedom (DOF) diagnostics and HTML report."""

    def test_constraint_audit_on_mixed_assembly(self):
        with Assembly("Motor_Mount_Assembly", units="mm") as asm:
            # 1. Base (grounded)
            asm.add_box("base_plate", length=150.0, width=120.0, height=15.0)
            # 2. Bracket (grounded/constrained)
            asm.add_box("bracket", length=40.0, width=40.0, height=60.0)
            asm.connect("bracket:face:bottom", "base_plate:face:top", mate_type="FLUSH")

            # 3. Floating spare bolt (no mates attached)
            asm.add_cylinder("loose_pin", radius=5.0, height=25.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_out = os.path.join(tmpdir, "constraint_audit.html")
            rep = asm.debug_constraints(html_filepath=html_out)

            assert rep.total_parts == 3
            assert rep.floating_count >= 1  # loose_pin is floating

            # Check loose pin diagnostic
            pin_diag = next(d for d in rep.diagnostics if d.part_name == "loose_pin")
            assert pin_diag.status == "FLOATING"
            assert pin_diag.remaining_dof == 6
            assert "Attach it to a mating port" in pin_diag.advice

            # Check base plate diagnostic
            base_diag = next(d for d in rep.diagnostics if d.part_name == "base_plate")
            assert base_diag.status == "FULLY_CONSTRAINED"
            assert base_diag.remaining_dof == 0

            # Check HTML export
            assert os.path.exists(html_out)
            with open(html_out, "r", encoding="utf-8") as f:
                html_text = f.read()
            assert "Assembly Constraint Debugger: Motor_Mount_Assembly" in html_text
            assert "FLOATING" in html_text
            assert "loose_pin" in html_text
