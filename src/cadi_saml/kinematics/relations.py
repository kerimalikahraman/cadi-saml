"""
cadi_saml.kinematics.relations
==============================
Mechanical mate and kinematic transmission relations between assembly parts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


from typing import Dict, List, Optional, Tuple


class RelationType(str, Enum):
    GEAR = "gear"
    RACK_PINION = "rack_pinion"
    BELT = "belt"
    SCREW = "screw"
    SLIDER_CRANK = "slider_crank"
    FOUR_BAR = "four_bar"
    PLANETARY = "planetary"


@dataclass
class GearRelation:
    """
    Gear mate relation coupling two rotational gears.
    Driven angle: theta_driven = (-1 if reverse else 1) * theta_driver * ratio
    where ratio = teeth_driver / teeth_driven.
    """
    driver_part: str
    driven_part: str
    ratio: float = 1.0
    reverse: bool = True
    relation_type: RelationType = RelationType.GEAR


@dataclass
class RackPinionRelation:
    """
    Couples rotational pinion movement to linear rack translation.
    Delta x_rack = Delta theta_pinion (radians) * pitch_radius.
    """
    pinion_part: str
    rack_part: str
    pitch_radius: float
    reverse: bool = False
    relation_type: RelationType = RelationType.RACK_PINION


@dataclass
class BeltRelation:
    """
    Belt / chain drive coupling two pulleys or sprockets.
    Both pulleys rotate in the same direction unless crossed.
    """
    driver_part: str
    driven_part: str
    ratio: float = 1.0
    reverse: bool = False
    relation_type: RelationType = RelationType.BELT


@dataclass
class ScrewRelation:
    """
    Screw mate coupling rotational lead screw motion to linear nut translation.
    Delta z_nut = Delta theta_screw (degrees) * (pitch_mm / 360.0).
    """
    screw_part: str
    nut_part: str
    pitch_mm: float
    relation_type: RelationType = RelationType.SCREW


@dataclass
class SliderCrankRelation:
    """
    Planar slider-crank mechanism coupling rotating crank to oscillating conrod and reciprocating piston.
    - crank_part: Rotating crank arm / disc
    - conrod_part: Oscillating connecting rod link
    - piston_part: Reciprocating slider / piston
    - crank_radius: Distance R between crankshaft center and crankpin center (mm)
    - conrod_length: Distance L between crankpin center and wristpin center (mm)
    - crank_center: (x, y, z) rotation center of the crankshaft
    - slide_axis: (dx, dy, dz) normalized linear sliding direction vector (default: (1, 0, 0))
    - offset: Perpendicular offset from crank center to slide line (mm, default 0.0 for inline engine)
    """
    crank_part: str
    conrod_part: str
    piston_part: str
    crank_radius: float
    conrod_length: float
    crank_center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    slide_axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    offset: float = 0.0
    relation_type: RelationType = RelationType.SLIDER_CRANK

    def solve_for_crank_angle(self, crank_angle_deg: float) -> Tuple[float, float, Tuple[float, float, float]]:
        """
        Calculates (piston_disp_mm, conrod_angle_deg, conrod_origin_xyz) for a given crank angle.
        Returns:
            piston_disp: linear displacement of piston along slide axis
            conrod_angle: rotation angle of connecting rod in degrees
            conrod_origin: 3D position of the crankpin (pivot of connecting rod)
        """
        theta = math.radians(crank_angle_deg)
        R = self.crank_radius
        L = self.conrod_length
        x0, y0, z0 = self.crank_center

        # Crankpin position in XY plane around crank center
        x_pin = x0 + R * math.cos(theta)
        y_pin = y0 + R * math.sin(theta)
        z_pin = z0

        # Offset distance perpendicular to slide line (inline: offset=0)
        dy = (y_pin - y0) - self.offset
        if L <= 0 or abs(dy) > L:
            raise ValueError('Slider-crank pose is unreachable')
        sin_phi = -dy / L
        sin_phi = max(-1.0, min(1.0, sin_phi))
        phi = math.asin(sin_phi)

        # Piston displacement along slide axis (from crank center)
        # x_piston = R*cos(theta) + sqrt(L^2 - dy^2)
        x_piston = (x_pin - x0) + math.sqrt(max(0.0, L * L - dy * dy))

        return x_piston, math.degrees(phi), (x_pin, y_pin, z_pin)


@dataclass
class FourBarRelation:
    """
    Planar 4-bar linkage (ground link 1, crank link 2, coupler link 3, rocker link 4).
    """
    ground_part: str
    crank_part: str
    coupler_part: str
    rocker_part: str
    link_lengths: Tuple[float, float, float, float]  # (L1_ground, L2_crank, L3_coupler, L4_rocker)
    ground_pivots: Tuple[Tuple[float, float, float], Tuple[float, float, float]]  # (P1_crank_pivot, P4_rocker_pivot)
    relation_type: RelationType = RelationType.FOUR_BAR


@dataclass
class PlanetaryRelation:
    """
    Epicyclic / planetary gear kinematic relation governed by the Willis equation:
        z_s * omega_s + z_r * omega_r - (z_s + z_r) * omega_c = 0
        omega_p = omega_c - (z_s / z_p) * (omega_s - omega_c)

    Parameters:
        sun_part: Name of the central sun gear part
        carrier_part: Name of the planet carrier part
        ring_part: Name of the outer annular ring gear part
        planet_parts: List of planet gear part names
        z_sun: Tooth count of sun gear (z_s)
        z_ring: Tooth count of ring gear (z_r)
        z_planet: Tooth count of planet gears (z_p)
        fixed_component: Grounded component ("ring", "carrier", "sun", or None)
        relation_type: RelationType = RelationType.PLANETARY
    """
    sun_part: str
    carrier_part: str
    ring_part: str
    planet_parts: List[str]
    z_sun: int
    z_ring: int
    z_planet: int
    fixed_component: Optional[str] = "ring"
    relation_type: RelationType = RelationType.PLANETARY

    @property
    def stage_ratio(self) -> float:
        """
        Calculates the primary reduction / transmission ratio based on the fixed component.
        If ring is fixed (standard reducer): ratio = (z_s + z_r) / z_s = 1 + z_r / z_s.
        If carrier is fixed (solar): ratio = - z_r / z_s.
        If sun is fixed: ratio = (z_s + z_r) / z_r.
        """
        zs, zr = float(self.z_sun), float(self.z_ring)
        if self.fixed_component == "ring":
            return (zs + zr) / zs
        elif self.fixed_component == "carrier":
            return -zr / zs
        elif self.fixed_component == "sun":
            return (zs + zr) / zr
        return (zs + zr) / zs

    def solve_speeds(
        self,
        omega_sun: Optional[float] = None,
        omega_carrier: Optional[float] = None,
        omega_ring: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Solves angular velocities (e.g. deg/s or deg displacement) for all components:
        sun, carrier, ring, and each planet gear using the Willis equation.
        """
        zs, zr, zp = float(self.z_sun), float(self.z_ring), float(self.z_planet)

        # Apply boundary conditions from fixed component
        if self.fixed_component == "ring" and omega_ring is None:
            omega_ring = 0.0
        elif self.fixed_component == "carrier" and omega_carrier is None:
            omega_carrier = 0.0
        elif self.fixed_component == "sun" and omega_sun is None:
            omega_sun = 0.0

        # Willis equation: zs * ws + zr * wr = (zs + zr) * wc
        if omega_sun is not None and omega_ring is not None and omega_carrier is None:
            omega_carrier = (zs * omega_sun + zr * omega_ring) / (zs + zr)
        elif omega_sun is not None and omega_carrier is not None and omega_ring is None:
            omega_ring = ((zs + zr) * omega_carrier - zs * omega_sun) / zr
        elif omega_carrier is not None and omega_ring is not None and omega_sun is None:
            omega_sun = ((zs + zr) * omega_carrier - zr * omega_ring) / zs
        elif omega_sun is not None and omega_carrier is None and omega_ring is None:
            if self.fixed_component == "ring":
                omega_ring = 0.0
                omega_carrier = (zs * omega_sun) / (zs + zr)
            elif self.fixed_component == "carrier":
                omega_carrier = 0.0
                omega_ring = -(zs / zr) * omega_sun
            else:
                omega_carrier = (zs * omega_sun) / (zs + zr)
                omega_ring = 0.0
        elif omega_carrier is not None and omega_sun is None and omega_ring is None:
            if self.fixed_component == "ring":
                omega_ring = 0.0
                omega_sun = ((zs + zr) * omega_carrier) / zs
            elif self.fixed_component == "sun":
                omega_sun = 0.0
                omega_ring = ((zs + zr) * omega_carrier) / zr
            else:
                omega_sun = ((zs + zr) * omega_carrier) / zs
                omega_ring = 0.0
        elif omega_ring is not None and omega_sun is None and omega_carrier is None:
            if self.fixed_component == "sun":
                omega_sun = 0.0
                omega_carrier = (zr * omega_ring) / (zs + zr)
            elif self.fixed_component == "carrier":
                omega_carrier = 0.0
                omega_sun = -(zr / zs) * omega_ring
            else:
                omega_sun = 0.0
                omega_carrier = (zr * omega_ring) / (zs + zr)

        if omega_sun is None:
            omega_sun = 0.0
        if omega_carrier is None:
            omega_carrier = 0.0
        if omega_ring is None:
            omega_ring = 0.0

        # Planet gear rotational velocity relative to carrier pin
        omega_planet = omega_carrier - (zs / zp) * (omega_sun - omega_carrier)

        res = {
            self.sun_part: omega_sun,
            self.carrier_part: omega_carrier,
            self.ring_part: omega_ring,
        }
        for p in self.planet_parts:
            res[p] = omega_planet

        return res
