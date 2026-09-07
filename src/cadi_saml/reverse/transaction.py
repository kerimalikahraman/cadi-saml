"""
cadi_saml.reverse.transaction

Transactional modification and rollback system for CAD models.
Ensures that any parametric modification (e.g. hole enlargement, dimension tweak)
is validated against contract criteria before committing, with instant rollback on failure.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from ..core.assembly import Assembly


@dataclass
class TransactionSnapshot:
    step_id: int
    parameters_copy: Dict[str, Dict[str, Any]]
    description: str


@dataclass
class TransactionResult:
    committed: bool
    snapshot_id: int
    modified_parameters: Dict[str, Any]
    contract_passed: bool
    error_message: Optional[str] = None


class ReverseEngineeringTransaction:
    """
    Manages safe, atomic parametric updates on CAD models with automated rollback.
    """

    def __init__(self, assembly: Assembly):
        self.assembly = assembly
        self._history: List[TransactionSnapshot] = []
        self._current_step: int = 0
        self._record_initial_state()

    def _record_initial_state(self) -> None:
        state = {}
        for p_name, p_ref in self.assembly._parts.items():
            state[p_name] = copy.deepcopy(getattr(p_ref.node, "parameters", {}))
        self._history.append(TransactionSnapshot(
            step_id=0,
            parameters_copy=state,
            description="Initial model state",
        ))

    def apply_parametric_patch(
        self,
        part_name: str,
        param_updates: Dict[str, Any],
        description: str = "Parametric update",
        verify_contract_strict: bool = True,
    ) -> TransactionResult:
        """
        Applies a parametric modification atomically.
        If contract verification fails, the model is rolled back to its previous state.
        """
        if part_name not in self.assembly._parts:
            return TransactionResult(
                committed=False,
                snapshot_id=self._current_step,
                modified_parameters={},
                contract_passed=False,
                error_message=f"Part '{part_name}' not found in assembly.",
            )

        part_ref = self.assembly._parts[part_name]
        prev_params = copy.deepcopy(part_ref.node.parameters)

        # 1. Take snapshot before change
        self._current_step += 1
        curr_state = {}
        for name, ref in self.assembly._parts.items():
            curr_state[name] = copy.deepcopy(ref.node.parameters)
        snap = TransactionSnapshot(
            step_id=self._current_step,
            parameters_copy=curr_state,
            description=description,
        )

        # 2. Apply modifications
        for k, v in param_updates.items():
            part_ref.node.parameters[k] = v

        # Invalidate cached solid to force rebuild
        if hasattr(part_ref, "_solid"):
            part_ref._solid = None

        # 3. Verify Contract
        try:
            report = self.assembly.verify_contract(strict=verify_contract_strict, check_clash=False)
            if not report.passed and verify_contract_strict:
                # Rollback!
                part_ref.node.parameters = prev_params
                if hasattr(part_ref, "_solid"):
                    part_ref._solid = None
                return TransactionResult(
                    committed=False,
                    snapshot_id=self._current_step,
                    modified_parameters=param_updates,
                    contract_passed=False,
                    error_message=f"Contract failed: {report.summary}. Rolled back to step {self._current_step - 1}.",
                )
        except Exception as ex:
            # Rollback on execution crash
            part_ref.node.parameters = prev_params
            if hasattr(part_ref, "_solid"):
                part_ref._solid = None
            return TransactionResult(
                committed=False,
                snapshot_id=self._current_step,
                modified_parameters=param_updates,
                contract_passed=False,
                error_message=f"Verification crashed: {ex}. Rolled back.",
            )

        # Commit successful change
        self._history.append(snap)
        return TransactionResult(
            committed=True,
            snapshot_id=self._current_step,
            modified_parameters=param_updates,
            contract_passed=True,
        )

    def rollback_to_step(self, step_id: int) -> bool:
        """Restores assembly parameters to a specified historical step."""
        target_snap = None
        for snap in self._history:
            if snap.step_id == step_id:
                target_snap = snap
                break
        if not target_snap:
            return False

        for p_name, saved_params in target_snap.parameters_copy.items():
            if p_name in self.assembly._parts:
                self.assembly._parts[p_name].node.parameters = copy.deepcopy(saved_params)
                if hasattr(self.assembly._parts[p_name], "_solid"):
                    self.assembly._parts[p_name]._solid = None
        return True
