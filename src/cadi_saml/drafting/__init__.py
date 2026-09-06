"""
cadi_saml.drafting
==================
Automated 2D technical drawing and drafting engine built on OpenCASCADE HLR (Hidden Line Removal).
Produces standard engineering drawings (orthographic projections, isometric view, hidden dashed lines,
title blocks/antet) in vector SVG format.
"""

from .projection import HLRViewExtractor, ProjectorView
from .drawing import DrawingSheet

__all__ = [
    "HLRViewExtractor",
    "ProjectorView",
    "DrawingSheet",
]
