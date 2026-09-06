"""
cadi_saml.core.assembly_exports
================================
Export pipelines for STEP AP242/AP214, STL meshes, glTF WebGL assets,
Bill of Materials (BOM), and visual validation snapshots.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


def export_step_file(assembly: Any, file_path: Union[str, Path], schema: str = "AP242") -> str:
    """Exports assembly solids to standard STEP CAD file."""
    from ..backend.occt_backend import OCCTBackend
    backend = OCCTBackend()
    backend.compile(assembly.to_ir())
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    backend.export_step(assembly.to_ir(), str(p))
    return str(p)


def export_stl_file(assembly: Any, file_path: Union[str, Path], linear_deflection: float = 0.1) -> str:
    """Exports assembly solids to triangulated STL mesh file."""
    from ..backend.occt_backend import OCCTBackend
    backend = OCCTBackend()
    backend.compile(assembly.to_ir())
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    backend.export_stl(assembly.to_ir(), str(p), linear_deflection=linear_deflection)
    return str(p)


def generate_bom_report(assembly: Any) -> Dict[str, Any]:
    """Generates structured Bill of Materials for the assembly."""
    parts = getattr(assembly, "_parts", {})
    bom_items = []
    for name, ref in parts.items():
        node = getattr(ref, "node", None)
        bom_items.append({
            "name": name,
            "part_type": getattr(node, "part_type", "unknown"),
            "shape": getattr(node, "shape", "unknown"),
            "material": getattr(node, "material", "Steel"),
            "color": getattr(node, "color", (0.5, 0.5, 0.5)),
            "parameters": getattr(ref, "parameters", {}),
        })
    return {
        "assembly_name": getattr(assembly, "name", "Assembly"),
        "total_parts": len(bom_items),
        "items": bom_items,
    }
