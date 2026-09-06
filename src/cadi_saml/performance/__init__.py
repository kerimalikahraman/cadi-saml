"""
CADI-SAML Large Assembly Performance Package.
Provides content-addressable shape caching and broad-phase spatial AABB collision indexing.
"""

from cadi_saml.performance.cache import (
    ShapeCache,
    AABB,
    SpatialIndex,
)

__all__ = [
    "ShapeCache",
    "AABB",
    "SpatialIndex",
]
