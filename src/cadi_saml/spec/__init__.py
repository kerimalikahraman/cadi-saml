"""
CADI-SAML Engineering Specification Engine.
Compiles pure declarative JSON specifications directly into executable Assemblies.
"""

from cadi_saml.spec.specification_engine import (
    EngineeringSpecification,
)
from cadi_saml.spec.contracts import (
    UnitContract,
    CoordinateContract,
    IndexContract,
    ToleranceContract,
    SolverContract,
    FailureContract,
    ProvenanceContract,
    MasterContract,
    CANONICAL_CONTRACT,
    CONTRACTS_SCHEMA_VERSION,
)

__all__ = [
    "EngineeringSpecification",
    "UnitContract",
    "CoordinateContract",
    "IndexContract",
    "ToleranceContract",
    "SolverContract",
    "FailureContract",
    "ProvenanceContract",
    "MasterContract",
    "CANONICAL_CONTRACT",
    "CONTRACTS_SCHEMA_VERSION",
]
