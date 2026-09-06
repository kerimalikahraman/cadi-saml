"""
cadi_saml.standards
===================
Authoritative mechanical engineering standard catalogs (DIN, ISO, EN).
"""

from .catalogs import (
    CATALOG_REGISTRY,
    DIN_115_COUPLINGS,
    DIN_1025_1_IPE,
    DIN_6885_1_KEYWAYS,
    DIN_6935_SHEET_METAL,
    ISO_965_1_THREADS,
    ISO_4200_PIPING,
    ISO_7005_1_FLANGES,
    find_standard_by_source_ref,
    lookup_catalog,
    validate_catalog_parameter,
)

__all__ = [
    "CATALOG_REGISTRY",
    "DIN_1025_1_IPE",
    "ISO_7005_1_FLANGES",
    "DIN_6885_1_KEYWAYS",
    "ISO_4200_PIPING",
    "ISO_965_1_THREADS",
    "DIN_115_COUPLINGS",
    "DIN_6935_SHEET_METAL",
    "lookup_catalog",
    "validate_catalog_parameter",
    "find_standard_by_source_ref",
]
