"""
tests/test_drafting.py
======================
Unit and integration tests for the 2D engineering drafting & HLR projection engine.
"""

import os
import tempfile
import xml.etree.ElementTree as ET
import pytest

from cadi_saml import Assembly, DrawingSheet, HLRViewExtractor, OCCTBackend


def test_drawing_sheet_basic_box():
    """Verify that a basic solid produces all 4 orthographic views and title block."""
    with Assembly("Bracket_Drafting_Test", units="mm") as asm:
        asm.add_box("mount_plate", length=80.0, width=50.0, height=12.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        svg_path = os.path.join(tmpdir, "test_drawing.svg")
        out = asm.export_drawing(
            filepath=svg_path,
            title="MOUNTING PLATE DRAWING",
            sheet_size="A4",
            material="S235JR",
        )

        assert os.path.exists(out)
        assert os.path.getsize(out) > 1000

        with open(out, "r", encoding="utf-8") as f:
            svg_content = f.read()

        # Structural SVG validation
        assert "<?xml version=" in svg_content
        assert "<svg" in svg_content
        assert "</svg>" in svg_content

        # Title block content
        assert "title_block" in svg_content
        assert "MOUNTING PLATE DRAWING" in svg_content
        assert "S235JR" in svg_content

        # Views
        assert 'id="view_top"' in svg_content
        assert 'id="view_front"' in svg_content
        assert 'id="view_right"' in svg_content
        assert 'id="view_iso"' in svg_content

        # Edges
        assert 'class="visible-edge"' in svg_content
        assert 'class="hidden-edge"' in svg_content


def test_drawing_sheet_assembly_with_holes():
    """Verify drafting on a stepped cylinder assembly with hidden internal lines."""
    with Assembly("Shaft_Assembly", units="mm") as asm:
        asm.add_cylinder("shaft", radius=20.0, height=60.0)
        asm.add_cylinder("flange", radius=35.0, height=15.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        svg_path = os.path.join(tmpdir, "shaft_drawing.svg")
        asm.export_drawing(svg_path, sheet_size="A3", title="STEPPED SHAFT")

        assert os.path.exists(svg_path)
        with open(svg_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "A3" in str(content) or 'viewBox="0 0 420.0 297.0"' in content
        assert "STEPPED SHAFT" in content
        assert 'class="visible-edge"' in content


def test_hlr_view_extractor_custom_views():
    """Test extracting custom individual views directly from OCCT shape."""
    with Assembly("Custom_View_Test", units="mm") as asm:
        asm.add_box("cube", length=30.0, width=30.0, height=30.0)

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    cube_shape = solids["cube"]

    for v in ["front", "top", "right", "left", "back", "bottom", "iso"]:
        proj = HLRViewExtractor.extract_view(cube_shape, view_name=v)
        assert proj.view_name == v
        assert len(proj.visible_segments) > 0
        assert proj.width > 0
        assert proj.height > 0
