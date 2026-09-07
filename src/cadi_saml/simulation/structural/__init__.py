"""
cadi_saml.simulation.structural

Structural dynamics, modal vibration, column stability/buckling, and fatigue life.
"""

from .modal import (
    ModeShapeResult,
    ModalAnalysisResult,
    ModalStudy,
    calc_cantilever_beam_natural_frequencies,
    assemble_lumped_mass_matrix,
)
from .buckling import (
    BucklingResult,
    analyze_column_buckling,
    END_CONDITION_K_FACTORS,
)
from .fatigue import (
    FatigueResult,
    MarinFactors,
    analyze_fatigue_life,
    calc_marin_surface_factor,
    calc_marin_size_factor,
)

__all__ = [
    "ModeShapeResult",
    "ModalAnalysisResult",
    "ModalStudy",
    "calc_cantilever_beam_natural_frequencies",
    "assemble_lumped_mass_matrix",
    "BucklingResult",
    "analyze_column_buckling",
    "END_CONDITION_K_FACTORS",
    "FatigueResult",
    "MarinFactors",
    "analyze_fatigue_life",
    "calc_marin_surface_factor",
    "calc_marin_size_factor",
]
