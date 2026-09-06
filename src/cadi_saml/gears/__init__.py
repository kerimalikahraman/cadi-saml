"""
CADI-SAML Analytical Gears & Mechanisms Engine.
Provides analytical involute gear geometry, center distance calculation, and continuous mesh verification.
"""

from cadi_saml.gears.involute import (
    InvoluteGearParameters,
    create_involute_spur_gear_solid,
)

__all__ = [
    "InvoluteGearParameters",
    "create_involute_spur_gear_solid",
]
