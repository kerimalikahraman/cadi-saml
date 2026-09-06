"""
CADI-SAML Model Patch & Repair Package.
Provides atomic preview and application of parameter diffs for interactive agent editing.
"""

from cadi_saml.patching.patch_engine import (
    PatchProposal,
    preview_patch,
)

__all__ = [
    "PatchProposal",
    "preview_patch",
]
