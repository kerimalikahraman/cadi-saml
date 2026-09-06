"""
CADI-SAML 2D Parametric Sketch & Geometric Constraint Engine.
Provides parametric points, lines, circles, arcs, non-linear constraint solver, and DOF analyzer.
"""

from cadi_saml.sketch.entities import (
    SketchPoint,
    SketchLine,
    SketchCircle,
    SketchArc,
)
from cadi_saml.sketch.constraints import (
    SketchConstraint,
    CoincidentConstraint,
    HorizontalConstraint,
    VerticalConstraint,
    DistanceConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    ConcentricConstraint,
    EqualConstraint,
    TangentConstraint,
    AngleConstraint,
)
from cadi_saml.sketch.solver import SketchSolver
from cadi_saml.sketch.profile import sketch_to_occt_wire, sketch_to_occt_face

__all__ = [
    "SketchPoint",
    "SketchLine",
    "SketchCircle",
    "SketchArc",
    "SketchConstraint",
    "CoincidentConstraint",
    "HorizontalConstraint",
    "VerticalConstraint",
    "DistanceConstraint",
    "ParallelConstraint",
    "PerpendicularConstraint",
    "ConcentricConstraint",
    "EqualConstraint",
    "TangentConstraint",
    "AngleConstraint",
    "SketchSolver",
    "sketch_to_occt_wire",
    "sketch_to_occt_face",
]
