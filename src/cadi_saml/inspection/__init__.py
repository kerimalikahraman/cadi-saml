"""
CADI-SAML Geometry Query & Introspection Package.
Provides tools to inspect faces, holes, dimensions, and distances on CAD models.
"""

from cadi_saml.inspection.query_api import (
    inspect_part_geometry,
    find_faces,
    find_holes,
    measure_parts_distance,
)

__all__ = [
    "inspect_part_geometry",
    "find_faces",
    "find_holes",
    "measure_parts_distance",
]
