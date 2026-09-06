"""
CADI-SAML Manufacturing & DFM Package.
Provides automated manufacturability auditing across machining, additive, sheet metal, and casting.
"""

from cadi_saml.manufacturing.dfm_checker import (
    DFMAuditReport,
    check_hole_aspect_ratios,
    check_3d_print_overhangs,
    check_casting_draft_angles,
    audit_assembly_dfm,
)

__all__ = [
    "DFMAuditReport",
    "check_hole_aspect_ratios",
    "check_3d_print_overhangs",
    "check_casting_draft_angles",
    "audit_assembly_dfm",
]
