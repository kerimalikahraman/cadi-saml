"""
cadi_saml.core.impact

Parametric Dependency and Impact Analysis Engine:
- Traces variable, expression, and dimension dependencies across the Assembly DAG
- Predicts geometric, structural, and cost impacts before committing parameter changes
- Identifies affected parts, features, broken constraints, and out-of-date simulations
- Generates structured ImpactReport for automated workflows and LLM decision-making
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, Any
import numpy as np

from ..systems.dfm import DFMAnalyzer


@dataclass
class ParameterDelta:
    """Details of a proposed parameter modification."""
    parameter_name: str
    current_value: Any
    proposed_value: Any


@dataclass
class ImpactReport:
    """Detailed report on the downstream effects of a parameter change."""
    parameter: str
    current_value: Any
    proposed_value: Any
    dependent_variables: List[str] = field(default_factory=list)
    affected_parts: List[str] = field(default_factory=list)
    affected_features: List[str] = field(default_factory=list)
    broken_constraints: List[str] = field(default_factory=list)
    outdated_analyses: List[str] = field(default_factory=list)
    volume_delta_mm3: float = 0.0
    mass_delta_kg: float = 0.0
    cost_delta_usd: float = 0.0
    can_auto_commit: bool = True
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "dependent_variables": self.dependent_variables,
            "affected_parts": self.affected_parts,
            "affected_features": self.affected_features,
            "broken_constraints": self.broken_constraints,
            "outdated_analyses": self.outdated_analyses,
            "volume_delta_mm3": round(self.volume_delta_mm3, 2),
            "mass_delta_kg": round(self.mass_delta_kg, 4),
            "cost_delta_usd": round(self.cost_delta_usd, 2),
            "can_auto_commit": self.can_auto_commit,
            "warnings": self.warnings,
        }


class DependencyImpactAnalyzer:
    """
    Evaluates the structural DAG and geometry graph to forecast the consequences
    of a proposed parameter update.
    """

    def __init__(self, assembly: Any):
        self.assembly = assembly

    def preview_parameter_change(
        self,
        parameter_name: str,
        new_value: Any,
    ) -> ImpactReport:
        """
        Calculates all downstream ripple effects if `parameter_name` were updated to `new_value`.
        Does not mutate the actual assembly state.
        """
        asm = self.assembly
        variables = getattr(asm, "_variables", {})
        
        current_val = variables.get(parameter_name, None)
        if current_val is None:
            # Check part parameters
            for pname, pref in asm._parts.items():
                if parameter_name in pref._node.parameters:
                    current_val = pref._node.parameters[parameter_name]
                    break

        # 1. Dependency Graph (DAG) traversal
        dep_vars: Set[str] = set()
        affected_parts: Set[str] = set()
        affected_features: Set[str] = set()

        from .assembly import SafeEvaluator
        dag = SafeEvaluator.build_dependency_dag(variables)
        # Find all nodes that depend on parameter_name (reverse lookup)
        to_visit = [parameter_name]
        visited = set()
        while to_visit:
            curr = to_visit.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            for var, deps in dag.items():
                if curr in deps and var not in dep_vars:
                    dep_vars.add(var)
                    to_visit.append(var)

        # 2. Identify affected parts
        all_changed_vars = dep_vars.union({parameter_name})
        for pname, pref in asm._parts.items():
            node = pref._node
            for param_val in node.parameters.values():
                if isinstance(param_val, str):
                    for cv in all_changed_vars:
                        if cv in param_val:
                            affected_parts.add(pname)
                            break
            # Also check direct parameter name match
            if parameter_name in node.parameters:
                affected_parts.add(pname)

            # Check holes & features
            for h in getattr(node, "holes", []):
                affected_features.add(f"{pname}.hole.{h.name}")
                affected_parts.add(pname)

        # 3. Predict out-of-date analyses
        outdated: List[str] = []
        if getattr(asm, "_last_flow_result", None) is not None:
            outdated.append("pipe_flow_simulation")
        if getattr(asm, "_last_fea_result", None) is not None or any("load" in p.lower() or "dia" in p.lower() for p in all_changed_vars):
            outdated.append("structural_fea_and_modal")
        outdated.append("post_build_contract_verification")

        # 4. Volume & Mass delta estimation
        # Rough estimation based on first order sensitivity
        vol_delta = 0.0
        warnings = []
        broken_constraints = []

        if isinstance(current_val, (int, float)) and isinstance(new_value, (int, float)):
            ratio = float(new_value) / max(1e-4, float(current_val))
            if ratio <= 0.0:
                broken_constraints.append(f"Non-positive parameter value {new_value} violates geometric manifold constraints.")
            elif ratio > 3.0 or ratio < 0.2:
                warnings.append(f"Large parameter change ({ratio:.1f}x) may cause severe geometric topology changes.")

            # Estimate volume difference
            vol_delta = (ratio - 1.0) * 15000.0  # approximate delta in mm3

        density_kg_mm3 = 2.7e-6  # Aluminum reference
        mass_delta_kg = vol_delta * density_kg_mm3
        cost_delta_usd = (mass_delta_kg * 6.5) + (abs(vol_delta / 1000.0) / 100.0 * 1.5)

        can_auto_commit = len(broken_constraints) == 0

        return ImpactReport(
            parameter=parameter_name,
            current_value=current_val,
            proposed_value=new_value,
            dependent_variables=sorted(list(dep_vars)),
            affected_parts=sorted(list(affected_parts)),
            affected_features=sorted(list(affected_features)),
            broken_constraints=broken_constraints,
            outdated_analyses=outdated,
            volume_delta_mm3=vol_delta,
            mass_delta_kg=mass_delta_kg,
            cost_delta_usd=cost_delta_usd,
            can_auto_commit=can_auto_commit,
            warnings=warnings,
        )
