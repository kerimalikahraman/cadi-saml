"""
cadi_saml.analysis
==================
Finite Element Analysis (FEA) and Structural Simulation module for cadi_saml.
"""

from .materials import Material, MATERIALS_DB, get_material
from .solver import LinearElasticitySolver, FEMSolution
from .fea import FEAStudy, FEAResult, InterfaceResult, GmshNotAvailableError
from .design import DimensionTolerance, ToleranceStack, DesignStudy
from .calculix_adapter import CalculiXModel, MaterialRegion
from .calculix_runner import CalculiXRunner
from .frd_reader import (
    parse_frd,
    write_frd,
    frd_to_fea_result,
    RegionalResult,
    FRDData,
    calc_von_mises,
    _normalize_element_sets,
    normalize_element_sets,
)
from .visualization import export_image, export_vtk, export_interactive_html
from .benchmark import (
    compute_analytical_cantilever,
    generate_structured_beam_mesh,
    BenchmarkValidator,
    BenchmarkComparisonResult,
    AnalyticalBeamResult,
)
from .convergence import (
    MeshConvergenceStudy,
    MeshRefinementStep,
    ConvergenceStudyResult,
)
from .report import PortableFEAReport

__all__ = [
    "DimensionTolerance", "ToleranceStack", "DesignStudy",
    "Material",
    "MATERIALS_DB",
    "get_material",
    "LinearElasticitySolver",
    "FEMSolution",
    "FEAStudy",
    "FEAResult",
    "InterfaceResult",
    "GmshNotAvailableError",
    "CalculiXModel",
    "MaterialRegion",
    "CalculiXRunner",
    "parse_frd",
    "write_frd",
    "frd_to_fea_result",
    "RegionalResult",
    "FRDData",
    "calc_von_mises",
    "_normalize_element_sets",
    "normalize_element_sets",
    "export_image",
    "export_vtk",
    "export_interactive_html",
    "compute_analytical_cantilever",
    "generate_structured_beam_mesh",
    "BenchmarkValidator",
    "BenchmarkComparisonResult",
    "AnalyticalBeamResult",
    "MeshConvergenceStudy",
    "MeshRefinementStep",
    "ConvergenceStudyResult",
    "PortableFEAReport",
]
