"""
cadi_saml.spec.contracts
========================
Canonical, versioned engineering contracts and schemas for CADi SAML.
Establishes immutable definitions for:
1. Physical Units (Length, Force, Stress, Mass, Time, Temperature)
2. Coordinate Systems & Spatial Orientations
3. Element & Node Indexing Conventions (1-based CalculiX ID vs 0-based Array Index)
4. Engineering Tolerances & Convergence Thresholds
5. Solver Backends & Execution Metadata
6. Failure & Exception Handling (Strict Fail-Fast)
7. Provenance & Reproducibility Schemas
"""

from __future__ import annotations

import os
import sys
import platform
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


CONTRACTS_SCHEMA_VERSION = "1.0.0"
CANONICAL_REPOSITORY = "kerimalikahraman/cadi-saml"


@dataclass(frozen=True)
class UnitContract:
    """Canonical physical units used across all CAD and FEA calculations."""
    length: str = "mm"
    force: str = "N"
    stress: str = "MPa"              # 1 MPa = 1 N/mm^2
    pressure: str = "MPa"
    elastic_modulus: str = "MPa"
    density: str = "tonne/mm^3"      # Equivalent to kg/m^3 / 1e12
    density_alt: str = "kg/m^3"
    mass: str = "kg"
    time: str = "s"
    temperature: str = "C"
    angle: str = "rad"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CoordinateContract:
    """Spatial coordinate orientation contract."""
    system: str = "right_handed_cartesian"
    up_axis: str = "+Z"
    forward_axis: str = "+X"
    lateral_axis: str = "+Y"
    handedness: str = "right"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class IndexContract:
    """
    Finite element indexing convention contract.
    Enforces strict separation between CalculiX card IDs (1-based)
    and NumPy memory buffer indices (0-based).
    """
    allowed_bases: Tuple[str, ...] = ("one", "zero", "auto")
    default_model_base: str = "one"
    calculix_id_base: int = 1
    memory_array_base: int = 0
    silent_filtering_allowed: bool = False
    mixed_base_allowed: bool = False

    def validate_base(self, base: str) -> str:
        base_norm = str(base).strip().lower()
        if base_norm not in self.allowed_bases:
            raise ValueError(
                f"Invalid index base '{base}'. Supported bases: {self.allowed_bases}"
            )
        return base_norm

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_bases": list(self.allowed_bases),
            "default_model_base": self.default_model_base,
            "calculix_id_base": self.calculix_id_base,
            "memory_array_base": self.memory_array_base,
            "silent_filtering_allowed": self.silent_filtering_allowed,
            "mixed_base_allowed": self.mixed_base_allowed,
        }


@dataclass(frozen=True)
class ToleranceContract:
    """Standardized numerical, geometric, and FEA convergence tolerances."""
    linear_abs_tol_mm: float = 1e-4
    linear_rel_tol: float = 1e-4
    angular_abs_tol_rad: float = 1e-4
    mass_rel_tol: float = 1e-3
    displacement_convergence_pct: float = 3.0    # <= 3% relative change for grid convergence
    stress_convergence_pct: float = 5.0          # <= 5% relative change for grid convergence
    solver_benchmark_match_pct: float = 5.0      # <= 5% difference between ccx and builtin

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class SolverContract:
    """FEA and continuum mechanics solver backend contract."""
    allowed_backends: Tuple[str, ...] = ("builtin", "calculix_ccx")
    default_backend: str = "builtin"
    calculix_c3d4_card: str = "*ELEMENT, TYPE=C3D4"
    synthetic_parser_only_marker: str = "synthetic_parser"
    requires_gmsh_marker: str = "requires_gmsh"
    requires_ccx_marker: str = "requires_ccx"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_backends": list(self.allowed_backends),
            "default_backend": self.default_backend,
            "calculix_c3d4_card": self.calculix_c3d4_card,
            "synthetic_parser_only_marker": self.synthetic_parser_only_marker,
            "requires_gmsh_marker": self.requires_gmsh_marker,
            "requires_ccx_marker": self.requires_ccx_marker,
        }


@dataclass(frozen=True)
class FailureContract:
    """
    Strict Fail-Fast contract.
    Prohibits silent approximations, masked indexing bugs, or fake geometry substitution.
    """
    fail_fast_on_invalid_id: bool = True
    fail_fast_on_mixed_base: bool = True
    fail_fast_on_unassigned_elements: bool = True
    fail_fast_on_overlapping_regions: bool = True
    fail_fast_on_unsupported_topology: bool = True
    allow_approximate_geometry_substitution: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceContract:
    """Provenance metadata format for engineering audit trails."""
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    canonical_repository: str = CANONICAL_REPOSITORY
    package_name: str = "cadi_saml"

    def capture_environment(self) -> Dict[str, Any]:
        """Captures active runtime environment without recording ephemeral user paths."""
        return {
            "schema_version": self.schema_version,
            "canonical_repository": self.canonical_repository,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "os_system": platform.system(),
            "os_release": platform.release(),
            "os_machine": platform.machine(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonical_repository": self.canonical_repository,
            "package_name": self.package_name,
        }


@dataclass
class MasterContract:
    """Master registry aggregating all CADi SAML engineering contracts."""
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    units: UnitContract = field(default_factory=UnitContract)
    coordinates: CoordinateContract = field(default_factory=CoordinateContract)
    indexing: IndexContract = field(default_factory=IndexContract)
    tolerances: ToleranceContract = field(default_factory=ToleranceContract)
    solvers: SolverContract = field(default_factory=SolverContract)
    failures: FailureContract = field(default_factory=FailureContract)
    provenance: ProvenanceContract = field(default_factory=ProvenanceContract)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "units": self.units.to_dict(),
            "coordinates": self.coordinates.to_dict(),
            "indexing": self.indexing.to_dict(),
            "tolerances": self.tolerances.to_dict(),
            "solvers": self.solvers.to_dict(),
            "failures": self.failures.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


# Global singleton instance of canonical master contract
CANONICAL_CONTRACT = MasterContract()
