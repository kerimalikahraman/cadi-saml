"""
cadi_saml.analysis
==================
Finite Element Analysis (FEA), Structural Simulation, Mold Draft & Undercut Analysis,
SIMP Topology Optimization, Composites Design (CPD), KnowledgeWare Design Rules,
and Class-A Surface Continuity module for cadi_saml.
"""

from .materials import Material, MATERIALS_DB, get_material
from .solver import LinearElasticitySolver, FEMSolution
from .fea import FEAStudy, FEAResult
from .design import DimensionTolerance, ToleranceStack, DesignStudy
from .draft_analysis import analyze_draft
from .topology import TopologyOptimizer, TopologyResult, optimize_topology
from .composites import (
    CompositeMaterial,
    COMPOSITE_MATERIALS,
    Ply,
    LaminateLayup,
    add_composite_panel,
)
from .rules import (
    DesignRule,
    RuleViolation,
    HoleEdgeDistanceRule,
    SheetMetalBendRadiusRule,
    BoltSpacingRule,
    DesignRuleEngine,
    check_design_rules,
)
from .surface_continuity import check_surface_continuity

__all__ = [
    "DimensionTolerance",
    "ToleranceStack",
    "DesignStudy",
    "Material",
    "MATERIALS_DB",
    "get_material",
    "LinearElasticitySolver",
    "FEMSolution",
    "FEAStudy",
    "FEAResult",
    "analyze_draft",
    "TopologyOptimizer",
    "TopologyResult",
    "optimize_topology",
    "CompositeMaterial",
    "COMPOSITE_MATERIALS",
    "Ply",
    "LaminateLayup",
    "add_composite_panel",
    "DesignRule",
    "RuleViolation",
    "HoleEdgeDistanceRule",
    "SheetMetalBendRadiusRule",
    "BoltSpacingRule",
    "DesignRuleEngine",
    "check_design_rules",
    "check_surface_continuity",
]
