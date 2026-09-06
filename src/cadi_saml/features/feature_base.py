"""
Base Parametric Feature and DAG Node Architecture for CADI-SAML.
Supports dependency tracking, dirty-state propagation, and deterministic recomputation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Union
import uuid
from cadi_saml.core.error_model import CADIErrorPayload, E_FEATURE_FAILURE


class Feature(ABC):
    """
    Abstract Base Class for all parametric B-Rep features.
    Maintains inputs, parent solid relation, upstream dependencies,
    dirty state, and recomputation logic.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional["Feature"] = None,
        inputs: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ):
        self.id: str = str(uuid.uuid4())[:8]
        self.name: str = name or f"{self.__class__.__name__}_{self.id}"
        self.parent: Optional["Feature"] = parent
        self.inputs: Dict[str, Any] = inputs.copy() if inputs else {}
        self.provenance: Dict[str, Any] = provenance.copy() if provenance else {}

        self.dependencies: List["Feature"] = []
        self.dependents: List["Feature"] = []

        self._dirty: bool = True
        self._cached_shape: Any = None
        self._last_error: Optional[CADIErrorPayload] = None

        if self.parent is not None:
            self.add_dependency(self.parent)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self, cascade: bool = True) -> None:
        """Mark feature dirty and recursively invalidate downstream dependents."""
        self._dirty = True
        self._cached_shape = None
        if cascade:
            for dep in self.dependents:
                if not dep.is_dirty:
                    dep.mark_dirty(cascade=True)

    def add_dependency(self, upstream_feature: "Feature") -> None:
        """Link an upstream feature that this feature depends on."""
        if upstream_feature not in self.dependencies:
            self.dependencies.append(upstream_feature)
        if self not in upstream_feature.dependents:
            upstream_feature.dependents.append(self)

    def update_input(self, param_name: str, value: Any) -> None:
        """Update a parametric input value, triggering dirty invalidation if modified."""
        if self.inputs.get(param_name) != value:
            self.inputs[param_name] = value
            self.mark_dirty(cascade=True)

    def get_input(self, param_name: str, default: Any = None) -> Any:
        return self.inputs.get(param_name, default)

    @abstractmethod
    def _execute(self, parent_shape: Any, context: Dict[str, Any]) -> Any:
        """Concrete feature computation in OpenCASCADE. Returns TopoDS_Shape."""
        pass

    def recompute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Recompute feature if dirty. Automatically ensures dependencies are clean first.
        """
        if not self._dirty and self._cached_shape is not None:
            return self._cached_shape

        ctx = context or {}

        # 1. Resolve parent shape
        parent_shape = None
        if self.parent is not None:
            parent_shape = self.parent.recompute(ctx)

        # 2. Recompute upstream dependencies
        for dep in self.dependencies:
            if dep != self.parent:
                dep.recompute(ctx)

        # 3. Execute self
        try:
            self._cached_shape = self._execute(parent_shape, ctx)
            self._dirty = False
            self._last_error = None
            return self._cached_shape
        except Exception as ex:
            err = CADIErrorPayload(
                code=E_FEATURE_FAILURE,
                path=f"features.{self.name}",
                provided=self.inputs,
                expected="Valid B-Rep geometry construction",
                message=f"Feature '{self.name}' failed to recompute: {str(ex)}",
                suggested_fix="Verify input dimensions and parent topological boundary",
                related_parts=[self.name],
            )
            self._last_error = err
            raise RuntimeError(str(err)) from ex

    def to_dict(self) -> Dict[str, Any]:
        """Serialize feature metadata and parameters for inspection."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.__class__.__name__,
            "parent": self.parent.name if self.parent else None,
            "inputs": self.inputs,
            "dependencies": [d.name for d in self.dependencies],
            "dirty": self._dirty,
            "provenance": self.provenance,
        }
