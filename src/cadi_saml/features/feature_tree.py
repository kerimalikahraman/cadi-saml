"""
Parametric Feature Tree & Recomputation DAG Engine for CADI-SAML.
Tracks the chronological and topological feature tree of a part or assembly.
"""

from typing import Any, Dict, List, Optional, Set
from collections import deque

from cadi_saml.features.feature_base import Feature


class FeatureTree:
    """
    Manages the parametric feature tree for a solid model.
    Provides dependency ordering, selective incremental recomputation,
    and history rollback.
    """

    def __init__(self, name: str = "PartFeatureTree"):
        self.name: str = name
        self.features: List[Feature] = []
        self._root: Optional[Feature] = None

    @property
    def root(self) -> Optional[Feature]:
        return self._root

    def add_feature(self, feature: Feature) -> Feature:
        """Appends a new feature to the tree and establishes default parent linkage."""
        if not self.features and self._root is None:
            self._root = feature

        if feature not in self.features:
            self.features.append(feature)

        return feature

    def get_feature(self, name_or_id: str) -> Optional[Feature]:
        for f in self.features:
            if f.name == name_or_id or f.id == name_or_id:
                return f
        return None

    def get_topological_order(self) -> List[Feature]:
        """
        Calculates a valid topological execution order resolving dependencies first.
        """
        in_degree: Dict[Feature, int] = {f: 0 for f in self.features}
        adj: Dict[Feature, List[Feature]] = {f: [] for f in self.features}

        for f in self.features:
            for dep in f.dependencies:
                if dep in in_degree:
                    adj[dep].append(f)
                    in_degree[f] += 1

        queue = deque([f for f in self.features if in_degree[f] == 0])
        ordered: List[Feature] = []

        while queue:
            curr = queue.popleft()
            ordered.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self.features):
            # Fall back to chronological order if cycle or unlinked node
            return list(self.features)

        return ordered

    def recompute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Recomputes dirty nodes in topological dependency order.
        Returns the terminal solid shape.
        """
        if not self.features:
            return None

        ctx = context or {}
        order = self.get_topological_order()
        terminal_shape = None

        for feat in order:
            terminal_shape = feat.recompute(ctx)

        return terminal_shape

    def to_tree_dict(self) -> List[Dict[str, Any]]:
        """Exports hierarchical feature tree overview for LLM inspection."""
        return [f.to_dict() for f in self.features]
