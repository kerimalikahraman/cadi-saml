"""
cadi_saml.simulation.load_cases

Boundary conditions, flow inputs, and wall characteristics.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
from .units import Quantity, ensure_quantity


# Standard pipe absolute surface roughness values (meters)
# Sources: Moody (1944), Crane Technical Paper 410
STANDARD_ROUGHNESS: Dict[str, float] = {
    "drawn_tubing": 1.5e-6,        # Copper, brass, plastic, glass
    "pvc": 1.5e-6,
    "plastic": 1.5e-6,
    "copper": 1.5e-6,
    "commercial_steel": 4.5e-5,   # Carbon steel, new
    "stainless_steel": 1.5e-5,    # Clean stainless steel
    "wrought_iron": 4.5e-5,
    "galvanized_iron": 1.5e-4,
    "cast_iron": 2.6e-4,
    "concrete": 1.0e-3,
    "corroded_steel": 1.0e-3,
}


@dataclass
class FlowBoundaryCondition:
    """Boundary conditions for internal fluid flow."""
    flow_rate: Optional[Quantity] = None      # Volume flow rate (e.g. L/s or m3/s)
    velocity: Optional[Quantity] = None       # Inlet velocity (m/s)
    inlet_pressure: Optional[Quantity] = None # Bar or Pa
    outlet_pressure: Optional[Quantity] = None
    temperature: Quantity = Quantity(value=20.0, unit="C", dimension="temperature")

    @classmethod
    def from_flow_rate_l_s(cls, q_l_s: float, temp_c: float = 20.0) -> FlowBoundaryCondition:
        return cls(
            flow_rate=Quantity(value=q_l_s, unit="l/s", dimension="flow_rate"),
            temperature=Quantity(value=temp_c, unit="C", dimension="temperature")
        )

    @classmethod
    def from_velocity_m_s(cls, v_m_s: float, temp_c: float = 20.0) -> FlowBoundaryCondition:
        return cls(
            velocity=Quantity(value=v_m_s, unit="m/s", dimension="velocity"),
            temperature=Quantity(value=temp_c, unit="C", dimension="temperature")
        )
