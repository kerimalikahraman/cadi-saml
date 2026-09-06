"""
tests/test_architectural_improvements.py
=========================================
Unit tests for the 6 architectural enhancements and risk mitigations:
1. DOF-aware multi-mate compound resolution (COAXIAL + FLUSH).
2. OverConstrainedError detection on contradictory mates.
3. StalePortError detection on invalidated geometric ports.
4. Static DAG cycle detection and topological sorting in SafeEvaluator.
5. Scale-adaptive fuzzy boolean tolerance.
6. 1D Sweep-and-Prune collision broad-phase detection.
7. Solid caching on incremental patch compilation.
"""

import pytest
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
    SafeEvaluator,
    CircularDependencyError,
    OverConstrainedError,
    StalePortError,
    ConstraintStatus,
    PortStatus,
)


def test_multi_mate_compound_coaxial_and_flush():
    """Verify COAXIAL + FLUSH compound mate combines constraints without destructive overwriting."""
    print("\n--- Testing Multi-Mate Compound Resolution (COAXIAL + FLUSH) ---")
    asm = Assembly("CompoundMateTest")
    
    # Base shaft with step_1 port
    shaft = asm.add_stepped_shaft(
        name="shaft",
        steps=[(20.0, 50.0), (35.0, 40.0), (25.0, 60.0)],
    )
    
    # Pinion gear with bore and back_face ports
    pinion = asm.add_spur_gear(
        name="pinion",
        module=2.5,
        teeth=20,
        face_width=25.0,
        bore_dia=35.0,
    )
    
    # Connect with both COAXIAL and FLUSH (with 5mm offset)
    asm.connect(shaft.port("step_1"), pinion.port("bore_axis"), mate_type="COAXIAL")
    asm.connect(shaft.port("step_1"), pinion.port("back_face"), mate_type="FLUSH", offset=5.0)
    
    status = asm.get_constraint_status()
    assert "pinion" in status
    p_stat = status["pinion"]
    assert p_stat["remaining_dof"] == 1  # 1 rotational DOF around axis remaining
    assert "rotation_around_axis" in p_stat["free_dofs"]
    print("  -> Pinion compound mate verified: COAXIAL + FLUSH successfully constrained with 1 rotational DOF free!")


def test_over_constrained_error_detection():
    """Verify OverConstrainedError is raised when two contradictory hole alignments have mismatched pitch."""
    print("\n--- Testing OverConstrainedError on Contradictory Alignments ---")
    asm = Assembly("OverConstrainedTest")
    
    # Base plate with 2 holes separated by 60mm
    p1 = asm.add_box("plate1", length=100.0, width=50.0, height=10.0)
    p1.add_hole("h1", diameter=8.0, position=(-30.0, 0.0))
    p1.add_hole("h2", diameter=8.0, position=(30.0, 0.0))
    
    # Secondary plate with 2 holes separated by 80mm (incompatible pitch!)
    p2 = asm.add_box("plate2", length=100.0, width=50.0, height=10.0)
    p2.add_hole("h1", diameter=8.0, position=(-40.0, 0.0))
    p2.add_hole("h2", diameter=8.0, position=(40.0, 0.0))
    
    asm.connect(p1.port("h1"), p2.port("h1"), mate_type="ALIGN_HOLES")
    asm.connect(p1.port("h2"), p2.port("h2"), mate_type="ALIGN_HOLES")
    
    backend = OCCTBackend()
    with pytest.raises(OverConstrainedError) as exc_info:
        backend.compile(asm.to_ir())
    
    assert "Hole spacing mismatch" in str(exc_info.value)
    print(f"  -> OverConstrainedError caught as expected: {exc_info.value}")


def test_stale_port_detection():
    """Verify StalePortError is raised when trying to mate with a port invalidated by geometry modification."""
    print("\n--- Testing StalePortError on Invalidated Port ---")
    asm = Assembly("StalePortTest")
    
    box = asm.add_box("cut_box", length=50.0, width=50.0, height=20.0)
    # Manually register a port far outside the geometry
    box.add_port("remote_port", position=(200.0, 200.0, 200.0), normal=(0.0, 0.0, 1.0))
    
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    
    # The remote port must be marked STALE
    node = asm.to_ir().parts["cut_box"]
    stale_port = node.get_port("remote_port")
    assert stale_port is not None
    assert stale_port.status == "STALE"
    
    # Attempting to query port() on a stale port must raise StalePortError
    with pytest.raises(StalePortError):
        box.port("remote_port")
    print("  -> StalePortError correctly raised when accessing invalidated port!")


def test_static_dag_cycle_detection():
    """Verify SafeEvaluator static DAG analysis catches cycles before execution."""
    print("\n--- Testing Static DAG Cycle Detection ---")
    vars_with_cycle = {
        "x": "y + 10",
        "y": "z * 2",
        "z": "x - 5",
        "independent": 42.0,
    }
    
    dag = SafeEvaluator.build_dependency_dag(vars_with_cycle)
    assert "y" in dag["x"]
    assert "z" in dag["y"]
    assert "x" in dag["z"]
    
    cycle = SafeEvaluator.detect_cycles(vars_with_cycle)
    assert cycle is not None
    assert len(cycle) >= 3
    
    # Topo sort must raise CircularDependencyError
    with pytest.raises(CircularDependencyError):
        SafeEvaluator.topological_sort(vars_with_cycle)
        
    # Clean DAG must sort properly
    clean_vars = {
        "length": 100.0,
        "width": "length * 0.5",
        "height": "width / 2 + 5",
    }
    order = SafeEvaluator.topological_sort(clean_vars)
    assert order == ["length", "width", "height"]
    print("  -> Static DAG cycle detection and topological sorting verified!")


def test_adaptive_fuzzy_boolean():
    """Verify adaptive fuzzy boolean tolerance scales dynamically with geometry size."""
    print("\n--- Testing Scale-Adaptive Fuzzy Tolerance ---")
    backend = OCCTBackend()
    
    # Small micro-part (2mm cube)
    asm_small = Assembly("Small")
    asm_small.add_box("s1", length=2.0, width=2.0, height=2.0)
    solids_small = backend.compile(asm_small.to_ir())
    fuzzy_small = backend.compute_adaptive_fuzzy_tolerance(solids_small["s1"])
    
    # Large structural part (500mm beam)
    asm_large = Assembly("Large")
    asm_large.add_box("b1", length=500.0, width=100.0, height=100.0)
    solids_large = backend.compile(asm_large.to_ir())
    fuzzy_large = backend.compute_adaptive_fuzzy_tolerance(solids_large["b1"])
    
    # Tolerance for large part must be greater than micro part
    assert fuzzy_small == 1e-4  # Clamped to minimum safe tolerance
    assert fuzzy_large > fuzzy_small
    assert fuzzy_large <= 0.05
    print(f"  -> Adaptive fuzzy tolerance verified: Small={fuzzy_small} mm, Large={round(fuzzy_large, 6)} mm")


def test_sweep_and_prune_clash_detection():
    """Verify 1D Sweep-and-Prune correctly catches clashes while pruning separated solids."""
    print("\n--- Testing 1D Sweep-and-Prune Clash Detection ---")
    asm = Assembly("SAPTest")
    
    # Separated boxes along X
    asm.add_box("b1", length=20.0, width=20.0, height=20.0, origin=(0.0, 0.0, 0.0))
    asm.add_box("b2", length=20.0, width=20.0, height=20.0, origin=(100.0, 0.0, 0.0))
    asm.add_box("b3", length=20.0, width=20.0, height=20.0, origin=(200.0, 0.0, 0.0))
    
    # Clashing box with b1
    asm.add_box("b1_clash", length=20.0, width=20.0, height=20.0, origin=(10.0, 0.0, 0.0))
    
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    
    val = ValidationEngineer()
    clashes = val.check_clashes(solids)
    
    assert len(clashes) == 1
    c = clashes[0]
    pair = {c.first_part, c.second_part}
    assert pair == {"b1", "b1_clash"}
    assert c.clash_volume > 0.0
    print(f"  -> Sweep-and-Prune correctly identified exact clash pair: {pair} (Volume: {c.clash_volume} mm³)")


def test_solid_caching_on_incremental_patch():
    """Verify OCCTBackend caches unmodified parts during patch revisions."""
    print("\n--- Testing Solid B-Rep Caching on Incremental Patch ---")
    asm = Assembly("CacheTest")
    asm.add_box("box_fixed", length=30.0, width=30.0, height=30.0)
    asm.add_cylinder("cyl_variable", radius=10.0, height=40.0)
    
    backend = OCCTBackend()
    solids1 = backend.compile(asm.to_ir())
    shape_fixed_1 = solids1["box_fixed"]
    
    # Patch only the cylinder parameter
    asm.patch({"cyl_variable.parameters.radius": 15.0})
    solids2 = backend.compile(asm.to_ir())
    shape_fixed_2 = solids2["box_fixed"]
    
    # box_fixed shape must be identical cached instance
    assert shape_fixed_1.IsSame(shape_fixed_2)
    print("  -> Unmodified part 'box_fixed' was successfully reused from B-Rep solid cache!")
