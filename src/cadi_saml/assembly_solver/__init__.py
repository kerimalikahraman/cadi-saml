"""
CADI-SAML 3D Assembly Mate & Kinematic Solver Engine.
Provides 3D mates and degrees of freedom (DOF) mobility analysis.
"""

from cadi_saml.assembly_solver.mates import (
    AssemblyMate,
    CoincidentMate,
    ConcentricMate,
    DistanceMate,
    AngleMate,
    ParallelMate,
    PerpendicularMate,
    TangentMate,
    GearMeshMate,
    BeltChainMate,
    RackAndPinionMate,
    ScrewMate,
    LimitMate,
)
from cadi_saml.assembly_solver.dof_solver import AssemblyMateSolver

__all__ = [
    "AssemblyMate",
    "CoincidentMate",
    "ConcentricMate",
    "DistanceMate",
    "AngleMate",
    "ParallelMate",
    "PerpendicularMate",
    "TangentMate",
    "GearMeshMate",
    "BeltChainMate",
    "RackAndPinionMate",
    "ScrewMate",
    "LimitMate",
    "AssemblyMateSolver",
]
