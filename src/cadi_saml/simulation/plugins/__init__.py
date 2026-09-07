"""
cadi_saml.simulation.plugins

External solver plugins and simulation exporter interfaces:
- OpenFOAM CFD case generation (controlDict, fvSchemes, blockMesh)
- CalculiX FEA .inp input deck generation
"""

from .openfoam import OpenFOAMCaseExporter
from .calculix import CalculiXInputExporter

__all__ = [
    "OpenFOAMCaseExporter",
    "CalculiXInputExporter",
]
