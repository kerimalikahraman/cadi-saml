"""
cadi_saml.analysis.convergence
==============================
Mesh convergence analysis engine for finite element simulations.
Performs grid refinement studies (coarse -> medium -> fine),
computes relative error decrements, monitors asymptotic behavior,
and ensures simulation models are strictly tagged as 'VERIFIED'
only after numerical mesh convergence is demonstrated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .materials import Material, get_material
from .solver import FEMSolution, LinearElasticitySolver


@dataclass
class MeshRefinementStep:
    """Results from a single discretization level."""
    level_name: str
    element_size_h: float
    num_nodes: int
    num_elements: int
    max_displacement_mm: float
    max_von_mises_mpa: float
    computational_time_sec: float = 0.0


@dataclass
class ConvergenceStudyResult:
    """Comprehensive mesh convergence study verification output."""
    study_name: str
    steps: List[MeshRefinementStep]
    disp_relative_change_pct: float
    stress_relative_change_pct: float
    disp_tolerance_pct: float
    stress_tolerance_pct: float
    is_converged: bool
    status: str  # 'CONVERGED', 'ASYMPTOTIC', 'UNCONVERGED'
    richardson_extrapolated_disp_mm: Optional[float] = None
    richardson_extrapolated_stress_mpa: Optional[float] = None

    @property
    def summary_table(self) -> str:
        icon = "[PASS]" if self.is_converged else "[FAIL]"
        header = (
            f"\n=======================================================================\n"
            f"  MESH CONVERGENCE VERIFICATION REPORT: {self.study_name}\n"
            f"=======================================================================\n"
            f"Convergence Verdict: {icon} {self.status}\n"
            f"Tolerance Targets  : Deflection <= {self.disp_tolerance_pct:.1f}% | Stress <= {self.stress_tolerance_pct:.1f}%\n"
            f"Final Step Change  : Delta Disp = {self.disp_relative_change_pct:.2f}% | Delta Stress = {self.stress_relative_change_pct:.2f}%\n"
            f"-----------------------------------------------------------------------\n"
            f"Level       h (mm)   Nodes       Elements    Max Disp (mm)  Max VM (MPa)\n"
            f"-----------------------------------------------------------------------\n"
        )
        rows = []
        for s in self.steps:
            rows.append(
                f"{s.level_name:<11} {s.element_size_h:<8.2f} {s.num_nodes:<11,d} {s.num_elements:<11,d} "
                f"{s.max_displacement_mm:<14.4f} {s.max_von_mises_mpa:<12.2f}"
            )
        footer = (
            f"-----------------------------------------------------------------------\n"
        )
        if self.richardson_extrapolated_disp_mm is not None:
            footer += (
                f"Richardson Continuum Extrapolations (h -> 0):\n"
                f"  Extrapolated Deflection: {self.richardson_extrapolated_disp_mm:.4f} mm\n"
                f"  Extrapolated Peak Stress: {self.richardson_extrapolated_stress_mpa:.2f} MPa\n"
            )
        footer += "=======================================================================\n"
        return header + "\n".join(rows) + "\n" + footer


class MeshConvergenceStudy:
    """
    Executes or evaluates multi-grid mesh refinement studies to ensure
    results are mesh-independent within acceptable engineering tolerances.
    """

    def __init__(
        self,
        study_name: str = "Grid_Convergence_Study",
        disp_tolerance_pct: float = 3.0,
        stress_tolerance_pct: float = 5.0,
    ):
        if not study_name or not isinstance(study_name, str):
            raise ValueError("study_name must be a non-empty string")
        if not np.isfinite(disp_tolerance_pct) or disp_tolerance_pct < 0:
            raise ValueError("disp_tolerance_pct must be a finite non-negative number")
        if not np.isfinite(stress_tolerance_pct) or stress_tolerance_pct < 0:
            raise ValueError("stress_tolerance_pct must be a finite non-negative number")
        self.study_name = study_name
        self.disp_tolerance_pct = disp_tolerance_pct
        self.stress_tolerance_pct = stress_tolerance_pct
        self.steps: List[MeshRefinementStep] = []

    def add_step(
        self,
        level_name: str,
        element_size_h: float,
        num_nodes: int,
        num_elements: int,
        max_displacement_mm: float,
        max_von_mises_mpa: float,
        time_sec: float = 0.0,
    ) -> MeshConvergenceStudy:
        """Appends a solved mesh resolution level to the study."""
        values = (element_size_h, max_displacement_mm, max_von_mises_mpa, time_sec)
        if not all(np.isfinite(value) for value in values):
            raise ValueError("mesh convergence values must be finite")
        if element_size_h <= 0:
            raise ValueError("element_size_h must be greater than zero")
        if num_nodes <= 0 or num_elements <= 0:
            raise ValueError("num_nodes and num_elements must be greater than zero")
        if time_sec < 0:
            raise ValueError("time_sec must be non-negative")
        if any(step.element_size_h == float(element_size_h) for step in self.steps):
            raise ValueError(f"element_size_h={element_size_h} duplicates an existing refinement step")
        self.steps.append(
            MeshRefinementStep(
                level_name=level_name,
                element_size_h=float(element_size_h),
                num_nodes=int(num_nodes),
                num_elements=int(num_elements),
                max_displacement_mm=float(max_displacement_mm),
                max_von_mises_mpa=float(max_von_mises_mpa),
                computational_time_sec=float(time_sec),
            )
        )
        return self

    def evaluate(self) -> ConvergenceStudyResult:
        """
        Evaluates convergence behavior across recorded steps.
        Requires at least 2 steps (recommended >= 3: coarse, medium, fine).
        """
        if len(self.steps) < 2:
            raise ValueError("Mesh convergence evaluation requires at least 2 refinement steps (recommended 3).")

        # Sort steps by element size descending (coarsest to finest)
        sorted_steps = sorted(self.steps, key=lambda s: s.element_size_h, reverse=True)

        penultimate = sorted_steps[-2]
        finest = sorted_steps[-1]

        # Calculate relative change between last two finest grids
        disp_fine = abs(finest.max_displacement_mm)
        if disp_fine > 1e-12:
            delta_disp_pct = abs(finest.max_displacement_mm - penultimate.max_displacement_mm) / disp_fine * 100.0
        else:
            delta_disp_pct = 0.0

        stress_fine = abs(finest.max_von_mises_mpa)
        if stress_fine > 1e-12:
            delta_stress_pct = abs(finest.max_von_mises_mpa - penultimate.max_von_mises_mpa) / stress_fine * 100.0
        else:
            delta_stress_pct = 0.0

        disp_converged = delta_disp_pct <= self.disp_tolerance_pct
        stress_converged = delta_stress_pct <= self.stress_tolerance_pct

        is_converged = disp_converged and stress_converged
        if is_converged:
            status = "CONVERGED"
        elif disp_converged:
            status = "ASYMPTOTIC"
        else:
            status = "UNCONVERGED"

        # Richardson extrapolation if >= 3 steps and roughly constant refinement ratio r ~ h1/h2
        rich_disp = None
        rich_stress = None
        if len(sorted_steps) >= 3:
            s1 = sorted_steps[-3]
            s2 = sorted_steps[-2]
            s3 = sorted_steps[-1]
            h1, h2, h3 = s1.element_size_h, s2.element_size_h, s3.element_size_h
            r21 = h1 / h2 if h2 > 0 else 1.0
            r32 = h2 / h3 if h3 > 0 else 1.0

            if abs(r21 - r32) < 0.25 and r32 > 1.1:
                # Apparent order of accuracy p ~ ln((f1 - f2)/(f2 - f3)) / ln(r)
                f1, f2, f3 = s1.max_displacement_mm, s2.max_displacement_mm, s3.max_displacement_mm
                diff23 = f2 - f3
                diff12 = f1 - f2
                if diff23 != 0 and (diff12 / diff23) > 0:
                    p = math.log(abs(diff12 / diff23)) / math.log(r32)
                    p = max(0.5, min(p, 4.0))  # Clamp order to physical boundaries
                    rich_disp = f3 + (f3 - f2) / ((r32 ** p) - 1.0)

                # Stress extrapolation
                s_f1, s_f2, s_f3 = s1.max_von_mises_mpa, s2.max_von_mises_mpa, s3.max_von_mises_mpa
                s_diff23 = s_f2 - s_f3
                s_diff12 = s_f1 - s_f2
                if s_diff23 != 0 and (s_diff12 / s_diff23) > 0:
                    p_s = math.log(abs(s_diff12 / s_diff23)) / math.log(r32)
                    p_s = max(0.5, min(p_s, 4.0))
                    rich_stress = s_f3 + (s_f3 - s_f2) / ((r32 ** p_s) - 1.0)

        return ConvergenceStudyResult(
            study_name=self.study_name,
            steps=sorted_steps,
            disp_relative_change_pct=round(delta_disp_pct, 2),
            stress_relative_change_pct=round(delta_stress_pct, 2),
            disp_tolerance_pct=self.disp_tolerance_pct,
            stress_tolerance_pct=self.stress_tolerance_pct,
            is_converged=is_converged,
            status=status,
            richardson_extrapolated_disp_mm=round(rich_disp, 4) if rich_disp is not None else None,
            richardson_extrapolated_stress_mpa=round(rich_stress, 2) if rich_stress is not None else None,
        )
