"""
cadi_saml.backend.compiler
===========================
Assembly IR compilation driver and spatial transformation resolver.
Translates abstract graph nodes and kinematic constraints into evaluated B-Rep solids.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class AssemblyCompiler:
    """Orchestrates traversal of Assembly IR and invokes geometric backend primitives."""

    def __init__(self, backend: Optional[Any] = None):
        if backend is None:
            from .occt_backend import OCCTBackend
            self.backend = OCCTBackend()
        else:
            self.backend = backend

    def compile(self, ir_assembly: Any) -> Dict[str, Any]:
        """Compiles the Assembly IR into a mapping of part_name -> TopoDS_Shape."""
        return self.backend.compile(ir_assembly)

    def get_part_transforms(self, ir_assembly: Any) -> Dict[str, Tuple[float, float, float]]:
        """Resolves global translation coordinates for every part."""
        transforms = {}
        for p_name, part_node in ir_assembly.parts.items():
            orig = part_node.parameters.get("origin", (0.0, 0.0, 0.0))
            transforms[p_name] = (float(orig[0]), float(orig[1]), float(orig[2]))
        return transforms
