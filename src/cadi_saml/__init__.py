"""
cadi-saml: Deterministic, LLM-friendly CAD Modeling and Assembly Engine.
Built natively on OpenCASCADE (OCCT).
"""

from .core.assembly import Assembly, PartReference, SafeEvaluator, CircularDependencyError
from .core.exceptions import CADISpecificationError
from .core.ports import PortStatus, StalePortError, OverConstrainedError, ConstraintStatus
from .core.sketch import Sketch
from .core.sheet_metal import SheetMetalBuilder, BendDefinition, FlatPatternResult
from .core.bom import BOMReport, BOMItem, extract_assembly_bom
from .core.batch import BatchExportPipeline, BatchReport, VariantExportResult
from .std_parts.fasteners import Fastener
from .std_parts.bearings import Bearing
from .std_parts.nuts import Nut
from .std_parts.washers import Washer
from .std_parts.profiles import Profile
from .std_parts.motors import Motor
from .std_parts.motorsport import Motorsport
from .std_parts.seals import Seal
from .std_parts.couplings import Coupling
from .ir.nodes import AssemblyIR, CrossSection, ExportFormat, MateType, PatternType, UnitSystem, ProvenanceRecord
from .ir.parser import SAMLParser
from .backend.occt_backend import OCCTBackend
from .reverse.step_importer import STEPReverseEngineer
from .validation.validation_engineer import ValidationEngineer, ClashReport
from .validation.contract import PostBuildContract, ContractReport, ContractStageResult
from .analysis.design import ToleranceStack, DimensionTolerance, DesignStudy
from .analysis.fea import FEAStudy, FEAResult
from .analysis.materials import Material, MATERIALS_DB, get_material
from .analysis.draft_analysis import analyze_draft
from .analysis.topology import TopologyOptimizer, TopologyResult, optimize_topology
from .analysis.composites import (
    CompositeMaterial,
    COMPOSITE_MATERIALS,
    Ply,
    LaminateLayup,
    add_composite_panel,
)
from .analysis.rules import (
    DesignRule,
    RuleViolation,
    HoleEdgeDistanceRule,
    SheetMetalBendRadiusRule,
    BoltSpacingRule,
    DesignRuleEngine,
    check_design_rules,
)
from .analysis.surface_continuity import check_surface_continuity
from .drafting.drawing import DrawingSheet
from .drafting.projection import HLRViewExtractor, ProjectorView
from .kinematics.joints import RevoluteJoint, PrismaticJoint
from .kinematics.relations import GearRelation, RackPinionRelation, BeltRelation, ScrewRelation, PlanetaryRelation
from .kinematics.motion_solver import KinematicMechanism, KinematicState
from .kinematics.debugger import ConstraintDebugger, ConstraintDebugReport, PartConstraintDiagnostic
from .kinematics.swept_envelope import compute_swept_envelope, check_dynamic_clearance
from .macros import (
    add_bolted_joint,
    add_mounting_bracket,
    add_profile_frame,
    add_motor_mount,
    add_bearing_support,
    add_gear_pair,
    add_shaft_stack,
    add_shaft_keyway,
    add_circlip_groove,
    lookup_din_6885,
    lookup_din_471,
    add_gusset,
    add_end_cap,
    add_planetary_stage,
    solve_planetary_teeth,
    add_disk_cam,
    evaluate_motion_law,
    add_threaded_hole,
    lookup_metric_thread,
    METRIC_THREADS,
    add_pipe_route,
    PIPE_SCHEDULES,
)

__all__ = [
    "ToleranceStack",
    "DimensionTolerance",
    "DesignStudy",
    "Assembly",
    "PartReference",
    "SafeEvaluator",
    "CircularDependencyError",
    "PortStatus",
    "StalePortError",
    "OverConstrainedError",
    "ConstraintStatus",
    "Sketch",
    "SheetMetalBuilder",
    "BendDefinition",
    "FlatPatternResult",
    "CrossSection",
    "PatternType",
    "Fastener",
    "Bearing",
    "Nut",
    "Washer",
    "Profile",
    "Motor",
    "Motorsport",
    "AssemblyIR",
    "MateType",
    "UnitSystem",
    "ExportFormat",
    "SAMLParser",
    "OCCTBackend",
    "STEPReverseEngineer",
    "ValidationEngineer",
    "ClashReport",
    "FEAStudy",
    "FEAResult",
    "Material",
    "MATERIALS_DB",
    "get_material",
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
    "DrawingSheet",
    "HLRViewExtractor",
    "ProjectorView",
    "RevoluteJoint",
    "PrismaticJoint",
    "CADISpecificationError",
    "ProvenanceRecord",
    "PostBuildContract",
    "ContractReport",
    "GearRelation",
    "RackPinionRelation",
    "BeltRelation",
    "ScrewRelation",
    "PlanetaryRelation",
    "KinematicMechanism",
    "KinematicState",
    "BOMReport",
    "BOMItem",
    "extract_assembly_bom",
    "Seal",
    "Coupling",
    "BatchExportPipeline",
    "BatchReport",
    "VariantExportResult",
    "ConstraintDebugger",
    "ConstraintDebugReport",
    "PartConstraintDiagnostic",
    "compute_swept_envelope",
    "check_dynamic_clearance",
    "add_bolted_joint",
    "add_mounting_bracket",
    "add_profile_frame",
    "add_motor_mount",
    "add_bearing_support",
    "add_gear_pair",
    "add_shaft_stack",
    "add_shaft_keyway",
    "add_circlip_groove",
    "lookup_din_6885",
    "lookup_din_471",
    "add_gusset",
    "add_end_cap",
    "add_planetary_stage",
    "solve_planetary_teeth",
    "add_disk_cam",
    "evaluate_motion_law",
    "add_threaded_hole",
    "lookup_metric_thread",
    "METRIC_THREADS",
    "add_pipe_route",
    "PIPE_SCHEDULES",
    "__version__",
]

__version__ = "0.6.0"
