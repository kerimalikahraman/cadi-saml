"""
CADI-SAML Reverse Engineering & STEP Feature Recognition Package.
"""

from cadi_saml.reverse.step_importer import STEPReverseEngineer
from cadi_saml.reverse.step_recognizer import STEPFeatureRecognizer
from cadi_saml.reverse.feature_classifier import (
    BRepFeatureClassifier,
    ClassifiedFeatures,
    RecognizedBaseSolid,
    RecognizedHole,
    RecognizedPCDPattern,
)
from cadi_saml.reverse.geometry_matcher import (
    verify_geometric_equivalence,
    GeomMatchReport,
)
from cadi_saml.reverse.standalone_generator import (
    generate_standalone_python_code,
    reconstruct_as_assembly,
    reverse_engineer_step_to_code,
    load_step_shape,
)
from cadi_saml.reverse.transaction import (
    ReverseEngineeringTransaction,
    TransactionResult,
)

from cadi_saml.reverse.inspection import (
    inspect_step,
    STEPParseError,
)
from cadi_saml.reverse.reconstruction import (
    reconstruct_step,
    ParametricFeature,
    ParametricFeatureTree,
    ReconstructionResult,
    generate_independent_cadi_code,
)

__all__ = [
    "STEPReverseEngineer",
    "STEPFeatureRecognizer",
    "BRepFeatureClassifier",
    "ClassifiedFeatures",
    "RecognizedBaseSolid",
    "RecognizedHole",
    "RecognizedPCDPattern",
    "verify_geometric_equivalence",
    "GeomMatchReport",
    "generate_standalone_python_code",
    "reconstruct_as_assembly",
    "reverse_engineer_step_to_code",
    "load_step_shape",
    "ReverseEngineeringTransaction",
    "TransactionResult",
    "inspect_step",
    "STEPParseError",
    "reconstruct_step",
    "ParametricFeature",
    "ParametricFeatureTree",
    "ReconstructionResult",
    "generate_independent_cadi_code",
]
