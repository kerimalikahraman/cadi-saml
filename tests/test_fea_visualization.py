"""
tests/test_fea_visualization.py
================================
Unit and integration tests for FEA 3D visualization:
- VTK Unstructured Grid (.vtk) export
- Standalone interactive 3D WebGL HTML simulation viewer
"""

import os
import tempfile
import pytest

from cadi_saml import Assembly, OCCTBackend, FEAStudy, FEAResult


@pytest.fixture
def solved_fea_beam() -> FEAResult:
    """Fixture providing a solved cantilever beam FEA result."""
    with Assembly("Viz_Beam", units="mm") as asm:
        asm.add_box("beam", length=60.0, width=15.0, height=10.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    fea = FEAStudy("beam", solids["beam"], material="Alu6061-T6", mesh_size=4.0)
    fea.fix_face("x_min")
    fea.apply_force("x_max", (0.0, 0.0, -300.0))
    return fea.solve()


def test_export_vtk_format(solved_fea_beam: FEAResult):
    """Verify that export_vtk produces a valid, complete VTK 3.0 file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vtk_path = os.path.join(tmpdir, "simulation_result.vtk")
        out = solved_fea_beam.export_vtk(vtk_path)

        assert os.path.exists(out)
        assert os.path.getsize(out) > 500

        with open(out, "r", encoding="utf-8") as f:
            lines = f.readlines()

        text = "".join(lines)
        # Check standard VTK sections
        assert "# vtk DataFile Version 3.0" in text
        assert "DATASET UNSTRUCTURED_GRID" in text
        assert f"POINTS {solved_fea_beam.num_nodes} float" in text
        assert f"CELLS {solved_fea_beam.num_elements}" in text
        assert f"CELL_TYPES {solved_fea_beam.num_elements}" in text
        assert "SCALARS Von_Mises_Stress_MPa float 1" in text
        assert "VECTORS Displacement_mm float" in text


def test_export_interactive_html(solved_fea_beam: FEAResult):
    """Verify that export_html creates a standalone 3D WebGL viewer with engineering stats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "simulation_viewer.html")
        out = solved_fea_beam.export_html(html_path, deformation_scale=15.0)

        assert os.path.exists(out)
        assert os.path.getsize(out) > 2000

        with open(out, "r", encoding="utf-8") as f:
            html = f.read()

        # HTML Structure and UI
        assert "<!DOCTYPE html>" in html
        assert "<canvas id=\"canvas3d\">" in html
        assert solved_fea_beam.study_name in html
        assert "Alu6061-T6" in html
        assert f"{solved_fea_beam.max_von_mises_mpa:.1f}" in html

        # WebGL & Shaders
        assert "attribute vec3 aPosition;" in html
        assert "gl.drawArrays" in html
        assert "scaleSlider" in html
        assert "wireBtn" in html
        assert "resetBtn" in html

        # Embedded simulation data
        assert '"nodes":' in html
        assert '"displacements":' in html
        assert '"triangles":' in html
        assert '"colors":' in html
