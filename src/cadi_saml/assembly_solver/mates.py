"""
3D Assembly Mates and Mechanical Kinematic Constraints for CADI-SAML.
Supports standard geometric mates and advanced mechanical couples (GearMesh, BeltChain, Screw, Planetary).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import math


class AssemblyMate(ABC):
    """Abstract Base Class for all 3D assembly mates."""

    def __init__(self, name: str, part_a: str, part_b: str):
        if not part_a or not part_b or part_a == part_b:
            raise ValueError("assembly mate requires two distinct non-empty parts")
        self.name = name
        self.part_a = part_a
        self.part_b = part_b

    @abstractmethod
    def constrained_dof(self) -> int:
        """Returns number of relative DOFs removed between part_a and part_b."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class CoincidentMate(AssemblyMate):
    """Enforces planar or point coincidence between two parts (removes 3 DOFs)."""

    def __init__(self, part_a: str, part_b: str, face_a: Optional[str] = None, face_b: Optional[str] = None):
        super().__init__(f"Coincident({part_a}, {part_b})", part_a, part_b)
        self.face_a = face_a
        self.face_b = face_b

    def constrained_dof(self) -> int:
        return 3

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "coincident", "part_a": self.part_a, "part_b": self.part_b, "face_a": self.face_a, "face_b": self.face_b}


class ConcentricMate(AssemblyMate):
    """Aligns rotational axes of two cylindrical features (removes 4 DOFs: 2 trans, 2 rot)."""

    def __init__(self, part_a: str, part_b: str, axis_a: Optional[str] = None, axis_b: Optional[str] = None):
        super().__init__(f"Concentric({part_a}, {part_b})", part_a, part_b)
        self.axis_a = axis_a
        self.axis_b = axis_b

    def constrained_dof(self) -> int:
        return 4

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "concentric", "part_a": self.part_a, "part_b": self.part_b, "axis_a": self.axis_a, "axis_b": self.axis_b}


class DistanceMate(AssemblyMate):
    """Maintains a specified distance between two planar faces (removes 1 DOF)."""

    def __init__(self, part_a: str, part_b: str, distance: float):
        if not math.isfinite(distance) or distance < 0:
            raise ValueError("distance must be a finite non-negative number")
        super().__init__(f"Distance({part_a}, {part_b}) = {distance}", part_a, part_b)
        self.distance = float(distance)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "distance", "part_a": self.part_a, "part_b": self.part_b, "distance": self.distance}


class AngleMate(AssemblyMate):
    """Maintains a specified angular orientation between two faces or vectors (removes 1 DOF)."""

    def __init__(self, part_a: str, part_b: str, angle_deg: float):
        super().__init__(f"Angle({part_a}, {part_b}) = {angle_deg}", part_a, part_b)
        self.angle_deg = float(angle_deg)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "angle", "part_a": self.part_a, "part_b": self.part_b, "angle_deg": self.angle_deg}


class ParallelMate(AssemblyMate):
    """Enforces parallelism between two direction vectors or planes (removes 2 rotational DOFs)."""

    def __init__(self, part_a: str, part_b: str):
        super().__init__(f"Parallel({part_a}, {part_b})", part_a, part_b)

    def constrained_dof(self) -> int:
        return 2

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "parallel", "part_a": self.part_a, "part_b": self.part_b}


class PerpendicularMate(AssemblyMate):
    """Enforces orthogonality between two directions or planes (removes 1 rotational DOF)."""

    def __init__(self, part_a: str, part_b: str):
        super().__init__(f"Perpendicular({part_a}, {part_b})", part_a, part_b)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "perpendicular", "part_a": self.part_a, "part_b": self.part_b}


class TangentMate(AssemblyMate):
    """Enforces cylindrical surface tangency to a planar surface (removes 1 DOF)."""

    def __init__(self, part_a: str, part_b: str):
        super().__init__(f"Tangent({part_a}, {part_b})", part_a, part_b)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "tangent", "part_a": self.part_a, "part_b": self.part_b}


class GearMeshMate(AssemblyMate):
    """Couples rotation of two gears according to gear ratio: theta_b = - (z_a / z_b) * theta_a."""

    def __init__(self, gear_a: str, gear_b: str, ratio: float, backlash: float = 0.05):
        if not math.isfinite(ratio) or ratio == 0:
            raise ValueError("gear ratio must be finite and non-zero")
        if not math.isfinite(backlash) or backlash < 0:
            raise ValueError("backlash must be finite and non-negative")
        super().__init__(f"GearMesh({gear_a}, {gear_b}, ratio={ratio})", gear_a, gear_b)
        self.ratio = float(ratio)
        self.backlash = float(backlash)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "gear_mesh", "gear_a": self.part_a, "gear_b": self.part_b, "ratio": self.ratio, "backlash": self.backlash}


class BeltChainMate(AssemblyMate):
    """Couples angular velocities of two sprockets or pulleys connected by a belt or chain."""

    def __init__(self, sprocket_a: str, sprocket_b: str, ratio: float = 1.0, center_distance: Optional[float] = None):
        super().__init__(f"BeltChain({sprocket_a}, {sprocket_b})", sprocket_a, sprocket_b)
        self.ratio = float(ratio)
        self.center_distance = float(center_distance) if center_distance is not None else None

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "belt_chain", "sprocket_a": self.part_a, "sprocket_b": self.part_b, "ratio": self.ratio, "center_distance": self.center_distance}


class ScrewMate(AssemblyMate):
    """Couples linear translation along Z with rotation around Z according to thread pitch."""

    def __init__(self, bolt: str, nut: str, pitch_mm: float):
        super().__init__(f"Screw({bolt}, {nut}, pitch={pitch_mm})", bolt, nut)
        self.pitch_mm = float(pitch_mm)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "screw", "bolt": self.part_a, "nut": self.part_b, "pitch_mm": self.pitch_mm}


class RackAndPinionMate(AssemblyMate):
    """Couples pinion angular rotation with linear motion of a rack."""

    def __init__(self, pinion: str, rack: str, pitch_diameter: float):
        super().__init__(f"RackAndPinion({pinion}, {rack})", pinion, rack)
        self.pitch_diameter = float(pitch_diameter)

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "rack_and_pinion", "pinion": self.part_a, "rack": self.part_b, "pitch_diameter": self.pitch_diameter}


class LimitMate(AssemblyMate):
    """Constrains motion within a specified minimum and maximum bounding range."""

    def __init__(self, part_a: str, part_b: str, min_val: float, max_val: float, motion_type: str = "distance"):
        if not math.isfinite(min_val) or not math.isfinite(max_val) or min_val > max_val:
            raise ValueError("limit mate requires finite min_val <= max_val")
        super().__init__(f"LimitMate({part_a}, {part_b})", part_a, part_b)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.motion_type = motion_type

    def constrained_dof(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "limit_mate", "part_a": self.part_a, "part_b": self.part_b, "min": self.min_val, "max": self.max_val, "motion": self.motion_type}
