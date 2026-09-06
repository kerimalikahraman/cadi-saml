"""
cadi_saml.core.ports
====================
Semantic attachment ports and constraint-based mating mathematics.
Eliminates arbitrary Cartesian (x, y, z) positioning in assemblies
by enabling ports to attach coaxially, flush, or offset using deterministic
rigid body transformation matrices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any

import OCP.gp as gp

class PortStatus(str, Enum):
    VALID = "VALID"            # Fully aligned with current solid geometry
    STALE = "STALE"            # Invalidated by downstream geometric operations (fillet, cut, etc.)
    REBOUND = "REBOUND"        # Automatically re-projected to modified adjacent surface

class StalePortError(Exception):
    """Raised when an assembly operation targets a port invalidated by geometry modification."""
    pass

class OverConstrainedError(Exception):
    """Raised when multiple mate constraints produce contradictory transformations (inconsistent degrees of freedom)."""
    pass

class ConstraintStatus(str, Enum):
    FULLY_CONSTRAINED = "FULLY_CONSTRAINED"     # 0 DOFs remaining (rigidly locked)
    UNDER_CONSTRAINED = "UNDER_CONSTRAINED"     # >0 DOFs remaining (free rotation/translation)
    OVER_CONSTRAINED = "OVER_CONSTRAINED"       # Contradictory/conflicting constraints

class PortType(str, Enum):
    HOLE = "hole"              # Cylindrical hole center with axis
    SHAFT = "shaft"            # Cylindrical shaft center with axis
    FLANGE = "flange"          # Planar mating face with surface normal
    PLANE = "plane"            # General planar face
    AXIS = "axis"              # Axis line
    POINT = "point"            # Reference 3D point

@dataclass
class Port:
    """A semantic connection port on a CAD component."""
    name: str
    origin: Tuple[float, float, float]          # (x, y, z) in part local coordinates
    direction: Tuple[float, float, float]       # Normal vector or axis vector (dx, dy, dz)
    port_type: PortType = PortType.HOLE
    parent_part: Optional[str] = None           # Name of parent PartNode
    status: PortStatus = PortStatus.VALID       # Geometric validity status
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize direction vector
        dx, dy, dz = self.direction
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length > 1e-9:
            self.direction = (dx / length, dy / length, dz / length)
        else:
            self.direction = (0.0, 0.0, 1.0)

    @property
    def gp_pnt(self) -> gp.gp_Pnt:
        x, y, z = self.origin
        return gp.gp_Pnt(float(x), float(y), float(z))

    @property
    def gp_dir(self) -> gp.gp_Dir:
        dx, dy, dz = self.direction
        return gp.gp_Dir(float(dx), float(dy), float(dz))

    @property
    def gp_ax1(self) -> gp.gp_Ax1:
        return gp.gp_Ax1(self.gp_pnt, self.gp_dir)

    def compute_alignment_transform(
        self,
        target_port: Port,
        mate_type: str = "coaxial",
        offset: float = 0.0,
        flip_direction: bool = True,
    ) -> gp.gp_Trsf:
        """
        Computes the rigid body transformation (gp_Trsf) that moves THIS port
        (and its parent part) so that it aligns with target_port.
        
        Args:
            target_port: The fixed port on the target part to connect to.
            mate_type: 'coaxial', 'flush', 'coincident', 'offset'
            offset: Axial offset distance along target direction (mm).
            flip_direction: If True (default for flush/face mates), makes normals oppose each other.
        """
        tr = gp.gp_Trsf()

        # Step 1: Calculate rotation matrix to align direction vectors
        v_src = self.gp_dir
        v_dst = target_port.gp_dir

        if flip_direction:
            v_dst = v_dst.Reversed()

        dot = v_src.Dot(v_dst)

        if dot < -0.999999:
            # Vectors are exactly opposite -> rotate 180 deg around any perpendicular axis
            perp = gp.gp_Dir(1.0, 0.0, 0.0)
            if abs(v_src.X()) > 0.9:
                perp = gp.gp_Dir(0.0, 1.0, 0.0)
            rot_axis = v_src.Crossed(perp)
            ax = gp.gp_Ax1(self.gp_pnt, rot_axis)
            tr.SetRotation(ax, math.pi)
        elif dot > 0.999999:
            # Vectors already aligned -> no rotation needed
            pass
        else:
            # General rotation
            rot_axis = v_src.Crossed(v_dst)
            angle = math.acos(max(-1.0, min(1.0, dot)))
            ax = gp.gp_Ax1(self.gp_pnt, rot_axis)
            tr.SetRotation(ax, angle)

        # Step 2: Apply rotation to our origin point
        p_rotated = self.gp_pnt.Transformed(tr)

        # Step 3: Compute translation to match target origin (+ offset)
        target_p = target_port.gp_pnt
        if abs(offset) > 1e-9:
            t_dir = target_port.gp_dir
            target_p = gp.gp_Pnt(
                target_p.X() + t_dir.X() * offset,
                target_p.Y() + t_dir.Y() * offset,
                target_p.Z() + t_dir.Z() * offset,
            )

        translation_vec = gp.gp_Vec(p_rotated, target_p)

        # Step 4: Final composite transform
        tr_trans = gp.gp_Trsf()
        tr_trans.SetTranslation(translation_vec)

        final_tr = tr_trans.Multiplied(tr)
        return final_tr


def compute_alignment_transform(
    source_port: Port,
    target_port: Port,
    mate_type: str = "coaxial",
    offset: float = 0.0,
    flip_direction: bool = True,
) -> gp.gp_Trsf:
    """Convenience functional interface to compute rigid transformation aligning source_port to target_port."""
    return source_port.compute_alignment_transform(
        target_port=target_port,
        mate_type=mate_type,
        offset=offset,
        flip_direction=flip_direction,
    )

