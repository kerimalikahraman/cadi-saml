"""
3D Assembly Kinematic Rigidity and Degrees of Freedom (DOF) Solver for CADI-SAML.
Analyzes rigid body mobility, under-constrained mechanisms, and missing kinematic mates.
"""

from typing import Any, Dict, List, Optional, Set
from cadi_saml.assembly_solver.mates import AssemblyMate, CoincidentMate, ConcentricMate, DistanceMate, GearMeshMate


class AssemblyMateSolver:
    """
    Solves 3D assembly mate networks and evaluates remaining degrees of freedom (DOF).
    """

    def __init__(self, name: str = "Assembly"):
        self.name = name
        self.parts: Set[str] = set()
        self.grounded_parts: Set[str] = set()
        self.mates: List[AssemblyMate] = []

    def add_part(self, part_name: str, grounded: bool = False) -> None:
        self.parts.add(part_name)
        if grounded:
            self.grounded_parts.add(part_name)

    def ground(self, part_name: str) -> None:
        self.parts.add(part_name)
        self.grounded_parts.add(part_name)

    def add_mate(self, mate: AssemblyMate) -> AssemblyMate:
        if any(existing.name == mate.name for existing in self.mates):
            raise ValueError(f"duplicate mate name: {mate.name}")
        self.parts.add(mate.part_a)
        self.parts.add(mate.part_b)
        self.mates.append(mate)
        return mate

    def analyze_dof(self) -> Dict[str, Any]:
        """
        Calculates total assembly DOFs according to Chebyshev-Grübler-Kutzbach criterion.
        DOF = 6 * (N - 1 - j_ground) - sum(c_i)
        """
        if not self.parts:
            return {"status": "empty", "free_dof": 0, "missing_constraints": []}

        # If no part explicitly grounded, default first part to ground
        effective_ground = set(self.grounded_parts)
        if not effective_ground and self.parts:
            effective_ground.add(sorted(list(self.parts))[0])

        moving_parts = [p for p in self.parts if p not in effective_ground]
        total_initial_dof = len(moving_parts) * 6

        part_removed_dof: Dict[str, int] = {p: 0 for p in moving_parts}
        for mate in self.mates:
            c = mate.constrained_dof()
            if mate.part_a in part_removed_dof:
                part_removed_dof[mate.part_a] += c
            if mate.part_b in part_removed_dof:
                part_removed_dof[mate.part_b] += c

        part_remaining_dof = {
            p: max(0, 6 - part_removed_dof[p]) for p in moving_parts
        }
        total_free_dof = sum(part_remaining_dof.values())

        missing: List[str] = []
        for p, rem in part_remaining_dof.items():
            if rem > 0:
                mates_on_p = [m for m in self.mates if m.part_a == p or m.part_b == p]
                has_concentric = any(isinstance(m, ConcentricMate) for m in mates_on_p)
                has_planar = any(isinstance(m, (CoincidentMate, DistanceMate)) for m in mates_on_p)
                if not has_concentric:
                    missing.append(f"Axial alignment (Concentric mate) missing for part '{p}'")
                if not has_planar:
                    missing.append(f"Planar/axial positioning mate missing for part '{p}'")

        if total_free_dof == 0:
            status = "fully_constrained"
        elif total_free_dof > 0:
            status = "under_constrained"
        else:
            status = "over_constrained"

        return {
            "status": status,
            "free_dof": total_free_dof,
            "grounded_parts": list(effective_ground),
            "moving_parts": moving_parts,
            "part_dof": part_remaining_dof,
            "missing_constraints": missing[:6],
        }
