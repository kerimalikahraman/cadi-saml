import pytest

from cadi_saml import AssemblyMateSolver, DistanceMate, GearMeshMate, LimitMate


def test_mate_inputs_and_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="distinct"):
        DistanceMate("shaft", "shaft", 1)
    with pytest.raises(ValueError, match="non-negative"):
        DistanceMate("a", "b", -1)
    with pytest.raises(ValueError, match="non-zero"):
        GearMeshMate("a", "b", 0)
    with pytest.raises(ValueError, match="min_val"):
        LimitMate("a", "b", 3, 1)

    solver = AssemblyMateSolver()
    first = DistanceMate("a", "b", 1)
    solver.add_mate(first)
    with pytest.raises(ValueError, match="duplicate"):
        solver.add_mate(first)
