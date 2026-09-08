"""
cadi_saml.ir.nodes
==================
Intermediate Representation (IR) node definitions for cadi-saml.
Pure Python dataclasses, 100% deterministic, no external CAD dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class MateType(str, Enum):
    FLUSH = "FLUSH"                 # Faces aligned coincident with matching normals
    COINCIDENT = "COINCIDENT"       # Faces touch with opposing normals
    CONCENTRIC = "CONCENTRIC"       # Cylindrical/circular axes are colinear
    COAXIAL = "COAXIAL"             # Alias for concentric
    ALIGN_HOLES = "ALIGN_HOLES"     # Centers of two cylindrical holes aligned
    DISTANCE = "DISTANCE"           # Fixed offset along normal
    ANGLE = "ANGLE"                 # Fixed relative angle between planar faces
    ATTACH = "ATTACH"               # Port-to-port rigid connection


class UnitSystem(str, Enum):
    MM = "mm"
    INCH = "inch"
    M = "m"


class ExportFormat(str, Enum):
    STEP = "STEP"
    STL = "STL"
    DXF = "DXF"
    GLTF = "GLTF"


@dataclass
class MetadataNode:
    """Mandatory metadata required for any industrial CAD export."""
    name: str
    units: UnitSystem = UnitSystem.MM
    tolerance_standard: str = "ISO 2768-m"
    material: Optional[str] = None
    export_formats: List[ExportFormat] = field(default_factory=lambda: [ExportFormat.STEP])
    version: str = "1.0.0"

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.name or not self.name.strip():
            errors.append("Metadata 'name' is required.")
        if not self.tolerance_standard:
            errors.append("Metadata 'tolerance_standard' is required.")
        return errors


@dataclass
class PortNode:
    """Semantic anchor port for connection points (prevents topological naming hallucination)."""
    name: str
    port_type: str = "face"         # 'face', 'axis', 'hole', 'origin'
    relative_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    diameter: Optional[float] = None
    status: str = "VALID"           # 'VALID', 'STALE', 'REBOUND'


@dataclass
class HoleNode:
    """Parametric cylindrical hole in a solid body."""
    name: str
    diameter: float
    depth: float                    # Depth of hole, or <= 0 for through-hole
    position: Tuple[float, float] = (0.0, 0.0)  # (X, Y) relative to face origin
    face_alias: str = "top"         # Face where the hole is bored ("top", "bottom", etc.)


@dataclass
class FilletNode:
    """Round edges with a specific radius."""
    radius: float
    edge_selector: str = "all_top"  # 'all_top', 'all_bottom', 'all'


@dataclass
class ChamferNode:
    """Chamfer/bevel edges with a specific distance."""
    distance: float
    edge_selector: str = "all_top"  # 'all_top', 'all_bottom', 'all'


@dataclass
class CrossSection:
    """A planar 2D/3D profile section for lofting or sweeping."""
    shape: str                                   # 'circle', 'ellipse', 'rectangle', 'polygon', 'spline'
    parameters: Dict[str, Any] = field(default_factory=dict)
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)

    @property
    def points(self) -> List[Any]:
        return self.parameters.get("points", [])

    def add_holes(self, holes: List[Dict[str, Any]]) -> CrossSection:
        self.parameters.setdefault("holes", []).extend(holes)
        return self

    def to_ir(self) -> CrossSection:
        return self


@dataclass
class ShellNode:
    """Hollow out a solid leaving a thin uniform wall thickness."""
    thickness: float
    open_face: Optional[str] = "bottom"          # 'bottom', 'top', None


class PatternType(str, Enum):
    CIRCULAR = "CIRCULAR"
    LINEAR = "LINEAR"


@dataclass
class PatternNode:
    """Circular or linear array of a part."""
    target_part: str
    pattern_type: PatternType
    count: int
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    angle: float = 360.0                         # Total span angle for circular
    spacing: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (dx, dy, dz) step for linear
    create_instances: bool = False
    prefix: Optional[str] = None


@dataclass
class MirrorNode:
    """Mirror operation creating a symmetric part across a plane."""
    name: str
    source_part: str
    plane: str = "XZ"                           # 'XY', 'XZ', 'YZ', or 'CUSTOM'
    point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    keep_original: bool = True


class BooleanOpType(str, Enum):
    CUT = "CUT"
    FUSE = "FUSE"
    INTERSECT = "INTERSECT"


@dataclass
class BooleanNode:
    """Boolean operation between two parts in the assembly."""
    op_type: BooleanOpType
    target_part: str
    tool_part: str
    keep_tool: bool = False


@dataclass
class ProvenanceRecord:
    """
    Structured provenance record tracing the exact origin and validation of an engineering parameter.
    
    Fields:
    - parameter: Name of the parameter (e.g. "outer_diameter", "wall_thickness")
    - source: Origin source ("llm_json", "catalog", "calculated", "user", "user_explicit")
    - source_ref: JSON path (e.g. "specs.dimensions.outer_diameter") or standard number (e.g. "DIN 6885")
    - original_value: Raw input value as extracted from source
    - effective_value: Value actually assigned and utilized in CAD modeling
    - unit: Physical unit ("mm", "deg", "mm3", etc., default "mm")
    - transformation: Type of conversion applied ("exact", "rounding", "catalog_lookup", "calculated")
    - confidence: Confidence score between 0.0 and 1.0
    - details: Optional supplementary metadata
    """
    parameter: str
    source: str = "user"
    source_ref: Optional[str] = None
    original_value: Any = None
    effective_value: Any = None
    unit: str = "mm"
    transformation: str = "exact"
    confidence: float = 1.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "source": self.source,
            "source_ref": self.source_ref,
            "original_value": self.original_value,
            "effective_value": self.effective_value,
            "unit": self.unit,
            "transformation": self.transformation,
            "confidence": self.confidence,
            "details": self.details,
            "value": self.effective_value,  # backward compatibility
        }


@dataclass
class PartNode:
    """A geometric part definition."""
    name: str
    part_type: str                  # 'primitive', 'standard', 'custom', 'step_file', 'loft', 'sweep', 'revolve'
    shape: Optional[str] = None     # 'box', 'cylinder', 'cone', 'sphere', 'torus', 'loft', 'sweep', 'revolve', etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    source_file: Optional[str] = None
    ports: Dict[str, PortNode] = field(default_factory=dict)
    holes: List[HoleNode] = field(default_factory=list)
    fillets: List[FilletNode] = field(default_factory=list)
    chamfers: List[ChamferNode] = field(default_factory=list)
    shell: Optional[ShellNode] = None
    sections: List[CrossSection] = field(default_factory=list)
    path_points: List[Tuple[float, float, float]] = field(default_factory=list)
    color: Optional[Tuple[float, float, float]] = None       # RGB (0.0 - 1.0)
    material: Optional[str] = None
    draft_angle: Optional[Dict[str, Any]] = None             # Casting / molding draft angle parameters
    source_part: Optional[str] = None                         # Master part name if this part is a linked instance or mirror
    instance_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    instance_rotation: Optional[Dict[str, Any]] = None        # {'axis': (ax,ay,az), 'angle_deg': float, 'center': (cx,cy,cz)}
    spec_provenance: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Parameter provenance trace

    def track_provenance(
        self,
        parameter: str,
        source: str = "user",
        source_ref: Optional[str] = None,
        confidence: Optional[float] = None,
        original_value: Any = None,
        effective_value: Any = None,
        unit: str = "mm",
        transformation: str = "exact",
        details: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        """
        Record the engineering origin of a parameter (e.g. user prompt, standard table, formula).
        Ensures strict provenance without hallucinated parameters.
        """
        eff_val = effective_value if effective_value is not None else self.parameters.get(parameter)
        orig_val = original_value if original_value is not None else eff_val
        conf = float(confidence) if confidence is not None else 1.0
        rec = ProvenanceRecord(
            parameter=parameter,
            source=source,
            source_ref=source_ref,
            original_value=orig_val,
            effective_value=eff_val,
            unit=unit,
            transformation=transformation,
            confidence=conf,
            details=details or {},
        )
        self.spec_provenance[parameter] = rec.to_dict()
        return rec


    def add_port(self, port: PortNode) -> None:
        self.ports[port.name] = port

    def add_hole(self, hole: HoleNode) -> None:
        self.holes.append(hole)

    def add_fillet(self, fillet: FilletNode) -> None:
        self.fillets.append(fillet)

    def add_chamfer(self, chamfer: ChamferNode) -> None:
        self.chamfers.append(chamfer)

    def set_shell(self, shell: ShellNode) -> None:
        self.shell = shell

    def get_port(self, name: str) -> Optional[PortNode]:
        return self.ports.get(name)


@dataclass
class MateNode:
    """A spatial relationship constraint between two parts or their ports/faces."""
    mate_type: MateType
    first_part: str = ""
    second_part: str = ""
    first_selector: Optional[str] = None   # e.g., 'top', 'h1', 'shaft_port'
    second_selector: Optional[str] = None  # e.g., 'bottom', 'hub_port'
    offset: float = 0.0
    angle: float = 0.0
    part_a: Optional[str] = None
    part_b: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.part_a and not self.first_part:
            self.first_part = self.part_a
        elif self.first_part and not self.part_a:
            self.part_a = self.first_part

        if self.part_b and not self.second_part:
            self.second_part = self.part_b
        elif self.second_part and not self.part_b:
            self.part_b = self.second_part

        if self.parameters and "offset" in self.parameters and self.offset == 0.0:
            self.offset = float(self.parameters["offset"])


@dataclass
class AssemblyIR:
    """Complete in-memory representation of an assembly before backend compilation."""
    metadata: MetadataNode
    parts: Dict[str, PartNode] = field(default_factory=dict)
    mates: List[MateNode] = field(default_factory=list)
    boolean_ops: List[BooleanNode] = field(default_factory=list)
    patterns: List[PatternNode] = field(default_factory=list)
    mirrors: List[MirrorNode] = field(default_factory=list)
    parameters: Dict[str, float] = field(default_factory=dict)

    def add_part(self, part: PartNode) -> None:
        self.parts[part.name] = part

    def add_mate(self, mate: MateNode) -> None:
        self.mates.append(mate)

    def add_boolean_op(self, op: BooleanNode) -> None:
        self.boolean_ops.append(op)

    def add_pattern(self, pattern: PatternNode) -> None:
        self.patterns.append(pattern)

    def add_mirror(self, mirror: MirrorNode) -> None:
        self.mirrors.append(mirror)

    def set_param(self, name: str, value: float) -> None:
        self.parameters[name] = float(value)

    def validate(self) -> List[str]:
        errors = self.metadata.validate()
        for mate in self.mates:
            if mate.first_part not in self.parts:
                errors.append(f"Mate references unknown first_part: '{mate.first_part}'")
            if mate.second_part not in self.parts:
                errors.append(f"Mate references unknown second_part: '{mate.second_part}'")
        return errors
