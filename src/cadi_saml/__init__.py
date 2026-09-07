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
from .reverse.standalone_generator import reverse_engineer_step_to_code, generate_standalone_python_code
from .reverse.geometry_matcher import verify_geometric_equivalence
from .reverse.transaction import ReverseEngineeringTransaction
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
    analyze_pipe_route_flow,
)
from .simulation import (
    Quantity,
    AnalysisStudy,
    AnalysisResult,
    AcceptanceCriteria,
)
from .simulation.flow import (
    analyze_pipe_flow,
    analyze_pump_requirements,
    resolve_fluid,
)
from .simulation.structural import (
    ModalStudy,
    ModalAnalysisResult,
    analyze_column_buckling,
    analyze_fatigue_life,
    calc_cantilever_beam_natural_frequencies,
)
from .simulation.coupling import (
    calc_pipe_bend_fluid_thrust,
    couple_flow_to_fea_bracket,
)

# Enterprise Parametric Kernel Extensions
from .core.error_model import (
    CADIErrorPayload,
    E_DIMENSION_CONFLICT,
    E_UNDER_CONSTRAINED,
    E_OVER_CONSTRAINED,
    E_COLLISION,
    E_DFM_VIOLATION,
    E_TOLERANCE_STACKUP,
    E_STANDARDS_MISMATCH,
    E_PATCH_CONFLICT,
)
from .spec import EngineeringSpecification
from .features import (
    Feature,
    FeatureTree,
    PadFeature,
    PocketFeature,
    HoleFeature,
    ShellFeature,
    CylinderFeature,
    ConeFeature,
    SphereFeature,
    BooleanFeature,
    FilletFeature,
    ChamferFeature,
    LinearPatternFeature,
    CircularPatternFeature,
    MirrorFeature,
)
from .sketch import (
    SketchSolver,
    SketchPoint,
    SketchLine,
    SketchCircle,
    SketchArc,
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
from .assembly_solver import (
    AssemblyMateSolver,
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
from .inspection import (
    inspect_part_geometry,
    find_faces,
    find_holes,
    measure_parts_distance,
)
from .manufacturing import (
    DFMAuditReport,
    check_hole_aspect_ratios,
    check_3d_print_overhangs,
    check_casting_draft_angles,
    audit_assembly_dfm,
)
from .tolerances import (
    calculate_iso_fit,
    ToleranceStack,
    ToleranceDimension,
)
from .gears import (
    InvoluteGearParameters,
    create_involute_spur_gear_solid,
)
from .calculations import (
    EngineeringMaterial,
    MATERIALS,
    get_material,
    calculate_shaft_diameter,
    calculate_keyway_stresses,
    calculate_bearing_l10h_life,
    calculate_bolt_preload,
    calculate_pressure_vessel_wall_thickness,
)
from .patching import (
    PatchProposal,
    preview_patch,
    apply_patch,
)
from .performance import (
    ShapeCache,
    AABB,
    SpatialIndex,
)
from .reverse.step_recognizer import STEPFeatureRecognizer

__all__ = [
    "EngineeringSpecification",
    "FeatureTree",
    "PadFeature",
    "PocketFeature",
    "HoleFeature",
    "ShellFeature",
    "CylinderFeature",
    "ConeFeature",
    "SphereFeature",
    "BooleanFeature",
    "FilletFeature",
    "ChamferFeature",
    "LinearPatternFeature",
    "CircularPatternFeature",
    "MirrorFeature",
    "SketchSolver",
    "AssemblyMateSolver",
    "CoincidentMate",
    "ConcentricMate",
    "DistanceMate",
    "GearMeshMate",
    "BeltChainMate",
    "ScrewMate",
    "DFMAuditReport",
    "audit_assembly_dfm",
    "calculate_iso_fit",
    "InvoluteGearParameters",
    "create_involute_spur_gear_solid",
    "calculate_shaft_diameter",
    "calculate_keyway_stresses",
    "calculate_bearing_l10h_life",
    "calculate_bolt_preload",
    "calculate_pressure_vessel_wall_thickness",
    "PatchProposal",
    "preview_patch",
    "apply_patch",
    "ShapeCache",
    "SpatialIndex",
    "STEPFeatureRecognizer",
    "CADIErrorPayload",
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
