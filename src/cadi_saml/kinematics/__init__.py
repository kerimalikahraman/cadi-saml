"""
cadi_saml.kinematics
===================
Kinematic mechanism analysis, mechanical relations, and forward motion simulation.
Supports Revolute/Prismatic joints, Gear mates, Rack & Pinion, Belt drives,
interactive 3D WebGL motion animation, and DMU dynamic swept volume & clearance analysis.
"""

from .joints import JointType, RevoluteJoint, PrismaticJoint
from .relations import (
    RelationType,
    GearRelation,
    RackPinionRelation,
    BeltRelation,
    ScrewRelation,
    SliderCrankRelation,
    FourBarRelation,
    PlanetaryRelation,
    SynchronizedGroupRelation,
)
from .motion_solver import KinematicMechanism, KinematicState
from .webgl_motion import export_motion_html
from .debugger import ConstraintDebugger, ConstraintDebugReport, PartConstraintDiagnostic
from .swept_envelope import compute_swept_envelope, check_dynamic_clearance

__all__ = [
    "JointType",
    "RevoluteJoint",
    "PrismaticJoint",
    "RelationType",
    "GearRelation",
    "RackPinionRelation",
    "BeltRelation",
    "ScrewRelation",
    "SliderCrankRelation",
    "FourBarRelation",
    "PlanetaryRelation",
    "SynchronizedGroupRelation",
    "KinematicMechanism",
    "KinematicState",
    "export_motion_html",
    "ConstraintDebugger",
    "ConstraintDebugReport",
    "PartConstraintDiagnostic",
    "compute_swept_envelope",
    "check_dynamic_clearance",
]
