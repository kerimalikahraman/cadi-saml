"""
cadi_saml.kinematics.joints
===========================
Kinematic joint definitions for mechanical assemblies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class JointType(str, Enum):
    REVOLUTE = "revolute"       # 1 rotational DOF
    PRISMATIC = "prismatic"     # 1 translational sliding DOF


@dataclass
class RevoluteJoint:
    """Rotational joint defining an axis of rotation for a specific part."""
    name: str
    part_name: str
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    initial_angle_deg: float = 0.0

    def __post_init__(self):
        # Normalize axis vector
        ax, ay, az = self.axis
        mag = math.hypot(ax, ay, az)
        if not math.isfinite(mag) or mag <= 0 or not all(math.isfinite(x) for x in self.origin):
            raise ValueError('Joint axis must be finite and nonzero; origin must be finite')
        self.axis = (ax / mag, ay / mag, az / mag)


@dataclass
class PrismaticJoint:
    """Translational sliding joint defining a linear movement axis for a part."""
    name: str
    part_name: str
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    initial_disp_mm: float = 0.0

    def __post_init__(self):
        # Normalize axis vector
        ax, ay, az = self.axis
        mag = math.hypot(ax, ay, az)
        if not math.isfinite(mag) or mag <= 0 or not all(math.isfinite(x) for x in self.origin):
            raise ValueError('Joint axis must be finite and nonzero; origin must be finite')
        self.axis = (ax / mag, ay / mag, az / mag)
