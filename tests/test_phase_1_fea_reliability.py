"""
tests/test_phase_1_fea_reliability.py
=====================================
Mandatory Phase 1 Exit Gate Acceptance Tests for FEA Fundamental Reliability:
1. Boundary elements: First element (1->0), last element (N->N-1), no dropped elements
2. Mixed index base rejection (0-based and 1-based in same model/run)
3. Invalid element ID rejection (negative IDs, out-of-bounds IDs)
4. Empty material region rejection
5. Overlapping material regions rejection
6. Missing material definition & unassigned element rejection
7. Linear isotropic elasticity solver preservation
"""

import os
import sys
import tempfile
import numpy as np
import pytest
from pathlib import Path

# Ensure library/src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadi_saml.analysis import (
    Material,
    get_material,
    CalculiXModel,
    MaterialRegion,
    CalculiXRunner,
    generate_structured_beam_mesh,
    BenchmarkValidator,
    FEAResult,
)
from cadi_saml.analysis.frd_reader import (
    _normalize_element_sets,
    write_frd,
    frd_to_fea_result,
)


@pytest.fixture
def sample_mesh():
    """Generates a small 10-element structured beam mesh (40x10x10 mm)."""
    nodes, elements = generate_structured_beam_mesh(
        length_mm=40.0, width_mm=10.0, height_mm=10.0, nx=2, ny=1, nz=1
    )
    return nodes, elements


def test_first_and_last_boundary_elements_coverage(sample_mesh):
    """
    Kabul Testi 1: İlk ve son element doğrulaması.
    CalculiX 1-based ID'leri (1..N) eksiksiz 0-based array indekslerine (0..N-1) eşlenmeli;
    ne ilk eleman ne de son eleman dışarıda kalmamalıdır.
    """
    nodes, elements = sample_mesh
    num_elems = len(elements)  # 10
    assert num_elems == 10

    # 1-based sets covering exactly 1..5 and 6..10
    sets_1based = {
        "steel_zone": [1, 2, 3, 4, 5],
        "alu_zone": [6, 7, 8, 9, 10],
    }

    norm = _normalize_element_sets(sets_1based, num_elems=num_elems, index_base="one")
    assert norm["steel_zone"] == [0, 1, 2, 3, 4]
    assert norm["alu_zone"] == [5, 6, 7, 8, 9]

    # Boundary elements check
    assert 0 in norm["steel_zone"], "İlk eleman (0) steel_zone içinde olmalıdır"
    assert 9 in norm["alu_zone"], "Son eleman (N-1 = 9) alu_zone içinde olmalıdır"


def test_mixed_base_rejection(sample_mesh):
    """
    Kabul Testi 2: Karışık taban (mixed index base) kesin ret.
    Aynı modelde veya kümelerde hem 0 hem de N elemanı bulunması anında ValueError fırlatmalıdır.
    """
    num_elems = 10
    mixed_sets = {
        "zone_a": [0, 1, 2],         # 0 indicates 0-based
        "zone_b": [7, 8, 9, 10],     # 10 indicates 1-based for 10-element mesh
    }

    with pytest.raises(ValueError, match=r"Conflicting / mixed element index base"):
        _normalize_element_sets(mixed_sets, num_elems=num_elems, index_base="auto")


def test_invalid_and_out_of_bounds_element_id_rejection(sample_mesh):
    """
    Kabul Testi 3: Geçersiz ID (negatif ve sınır dışı) kesin ret.
    Sessizce filtrelenmemeli, anında fail-fast ValueError üretilmelidir.
    """
    num_elems = 10

    # Negatif ID
    neg_sets = {"steel": [-1, 1, 2], "alu": [3, 4, 5, 6, 7, 8, 9, 10]}
    with pytest.raises(ValueError, match=r"Negative element ID -1"):
        _normalize_element_sets(neg_sets, num_elems=num_elems)

    # Sınır dışı ID
    oob_sets = {"steel": [1, 2, 3], "alu": [4, 5, 6, 7, 8, 9, 999]}
    with pytest.raises(ValueError, match=r"exceeds mesh element count|out of bounds"):
        _normalize_element_sets(oob_sets, num_elems=num_elems)


def test_empty_material_region_rejection(sample_mesh):
    """
    Kabul Testi 4: Boş region (empty element set) kesin ret.
    Bir bölgeye hiçbir eleman düşmüyorsa veya küme boşsa model doğrulaması hata fırlatmalıdır.
    """
    nodes, elements = sample_mesh
    model = CalculiXModel("EmptyRegionModel", nodes, elements)
    model.add_material("steel", "S235JR")
    model.add_material("alu", "AL6061_T6")

    # steel covers all, alu covers none
    model.element_sets["steel"] = list(range(1, len(elements) + 1))
    model.element_sets["alu"] = []

    with pytest.raises(ValueError, match=r"Element set 'alu' is empty"):
        model.validate_multi_material()


def test_overlapping_material_regions_rejection(sample_mesh):
    """
    Kabul Testi 5: Çakışan region (overlapping element sets) kesin ret.
    Aynı eleman iki farklı malzeme bölgesine atanmışsa hata fırlatılmalıdır.
    """
    nodes, elements = sample_mesh
    model = CalculiXModel("OverlapModel", nodes, elements)
    model.add_material("steel", "S235JR")
    model.add_material("alu", "AL6061_T6")

    # Element 5 is assigned to both steel and alu
    model.element_sets["steel"] = [1, 2, 3, 4, 5]
    model.element_sets["alu"] = [5, 6, 7, 8, 9, 10]

    with pytest.raises(ValueError, match=r"Overlapping material regions detected"):
        model.validate_multi_material()


def test_missing_material_definition_and_unassigned_elements(sample_mesh):
    """
    Kabul Testi 6: Eksik malzeme durumları:
    a) Tanımsız malzeme adı verilen element seti
    b) Hiçbir malzeme atanmamış sahipsiz elemanlar
    """
    nodes, elements = sample_mesh

    # Durum a: Küme var fakat materyal tanımı yok
    model_a = CalculiXModel("MissingMatDefModel", nodes, elements)
    model_a.add_material("steel", "S235JR")
    model_a.element_sets["steel"] = [1, 2, 3, 4, 5]
    model_a.element_sets["ghost_material"] = [6, 7, 8, 9, 10]

    with pytest.raises(ValueError, match=r"does not correspond to any defined material"):
        model_a.validate_multi_material()

    # Durum b: Bazı elemanlar hiçbir malzemeye atanmamış (sahipsiz elemanlar)
    model_b = CalculiXModel("UnassignedElemsModel", nodes, elements)
    model_b.add_material("steel", "S235JR")
    model_b.add_material("alu", "AL6061_T6")
    model_b.element_sets["steel"] = [1, 2, 3]
    model_b.element_sets["alu"] = [4, 5]
    # Elemanlar 6..10 sahipsiz kaldı

    with pytest.raises(ValueError, match=r"Not all elements assigned"):
        model_b.validate_multi_material()


def test_linear_isotropic_solver_preservation(sample_mesh):
    """
    Kabul Testi 7: Mevcut izotropik lineer solver ve analitik çekme benchmarkı korunmalıdır.
    """
    bench = BenchmarkValidator.run_uniaxial_tension_benchmark(
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        axial_force_n=5000.0,
        material="S235JR",
        tolerance_pct=6.0,
    )
    assert bench.is_verified is True
    assert bench.solver_backend == "builtin"
    assert bench.disp_error_pct <= 6.0
    assert bench.stress_error_pct <= 1.0
