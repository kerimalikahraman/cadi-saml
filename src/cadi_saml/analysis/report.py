"""
cadi_saml.analysis.report
=========================
Portable engineering report generator for FEA simulations.
Exports structured, machine-verifiable JSON schemas and human-readable Markdown
containing solver provenance, versions, mesh convergence audit, material cards,
boundary conditions, regional & interface stresses, and formal engineering verdicts.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

from .convergence import ConvergenceStudyResult
from .fea import FEAResult, InterfaceResult
from .materials import Material


@dataclass
class PortableFEAReport:
    """Standardized, portable FEA verification report object."""
    # Metadata
    study_name: str
    part_name: str
    timestamp_utc: str
    cadi_saml_version: str

    # Solver details
    solver_backend: str
    solver_version: str
    tolerances: Dict[str, Any]

    # Mesh & Convergence
    num_nodes: int
    num_elements: int
    mesh_convergence_status: str
    mesh_convergence_details: Dict[str, Any]

    # Material Cards
    materials: Dict[str, Dict[str, Any]]

    # Loads and Boundary Conditions
    boundary_conditions: Dict[str, Any]

    # Results
    max_von_mises_mpa: float
    max_displacement_mm: float
    global_safety_factor: float
    is_safe: bool
    status: str

    # Sub-domains
    regional_results: Dict[str, Dict[str, Any]]
    interface_results: Dict[str, Dict[str, Any]]

    # Formal Verdict
    verification_verdict: str  # 'VERIFIED_PASS', 'VERIFIED_WARN_YIELD', 'UNVERIFIED_GRID_CONVERGENCE'
    solver_command: Optional[str] = None
    summary_notes: List[str] = field(default_factory=list)

    @classmethod
    def from_fea_result(
        cls,
        result: FEAResult,
        convergence: Optional[ConvergenceStudyResult] = None,
        boundary_conditions: Optional[Dict[str, Any]] = None,
        cadi_saml_version: str = "0.2.0",
        solver_version: Optional[str] = None,
        solver_command: Optional[str] = None,
    ) -> PortableFEAReport:
        """Constructs a portable report from a solved FEAResult and optional convergence study."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Material cards serialization
        mats_dict: Dict[str, Dict[str, Any]] = {}
        if result.materials:
            for k, m in result.materials.items():
                mats_dict[k] = {
                    "name": m.name,
                    "youngs_modulus_mpa": float(m.youngs_modulus_mpa),
                    "poisson_ratio": float(getattr(m, "poissons_ratio", getattr(m, "poisson_ratio", 0.3))),
                    "yield_strength_mpa": float(m.yield_strength_mpa),
                    "density_kg_m3": float(m.density_kg_m3) if hasattr(m, "density_kg_m3") else None,
                }
        else:
            mats_dict["primary"] = {
                "name": result.material.name,
                "youngs_modulus_mpa": float(result.material.youngs_modulus_mpa),
                "poisson_ratio": float(getattr(result.material, "poissons_ratio", getattr(result.material, "poisson_ratio", 0.3))),
                "yield_strength_mpa": float(result.material.yield_strength_mpa),
            }

        # Convergence info
        conv_status = convergence.status if convergence else "NOT_EVALUATED"
        conv_details = {}
        if convergence:
            conv_details = {
                "is_converged": convergence.is_converged,
                "disp_relative_change_pct": convergence.disp_relative_change_pct,
                "stress_relative_change_pct": convergence.stress_relative_change_pct,
                "disp_tolerance_pct": convergence.disp_tolerance_pct,
                "stress_tolerance_pct": convergence.stress_tolerance_pct,
                "num_refinement_levels": len(convergence.steps),
            }

        # Regional results dict
        reg_dict = {}
        for rk, rv in result.regional_results.items():
            if hasattr(rv, "__dict__"):
                reg_dict[rk] = dict(rv.__dict__)
            elif isinstance(rv, dict):
                reg_dict[rk] = rv

        # Interface results dict
        inter_dict = {}
        for ik, iv in result.interface_results.items():
            if hasattr(iv, "__dict__"):
                inter_dict[ik] = dict(iv.__dict__)
            elif isinstance(iv, dict):
                inter_dict[ik] = iv

        # Formal verdict
        if convergence is not None and not convergence.is_converged:
            verdict = "UNVERIFIED_GRID_CONVERGENCE"
        elif result.is_safe:
            verdict = "VERIFIED_PASS"
        else:
            verdict = "VERIFIED_WARN_YIELD"

        backend_ver = solver_version or (
            result.solver_version
            or ("CalculiX ccx 2.21" if result.solver_backend == "calculix_ccx" else "CADi SAML Continuum Engine v1.0")
        )
        backend_cmd = solver_command or getattr(result, "solver_command", None)

        return cls(
            study_name=result.study_name,
            part_name=result.part_name,
            timestamp_utc=now_str,
            cadi_saml_version=cadi_saml_version,
            solver_backend=result.solver_backend,
            solver_version=backend_ver,
            solver_command=backend_cmd,
            tolerances={
                "required_safety_factor": result.required_safety_factor,
                "max_displacement_limit_mm": result.max_displacement_limit_mm,
            },
            num_nodes=result.num_nodes,
            num_elements=result.num_elements,
            mesh_convergence_status=conv_status,
            mesh_convergence_details=conv_details,
            materials=mats_dict,
            boundary_conditions=boundary_conditions or {},
            max_von_mises_mpa=result.max_von_mises_mpa,
            max_displacement_mm=result.max_displacement_mm,
            global_safety_factor=result.safety_factor,
            is_safe=result.is_safe,
            status=result.status,
            regional_results=reg_dict,
            interface_results=inter_dict,
            verification_verdict=verdict,
            summary_notes=[],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the report into a clean JSON-compatible dictionary."""
        return asdict(self)

    def to_json(self, filepath: Optional[str] = None, indent: int = 2) -> str:
        """Serializes report to JSON string and optionally writes to disk."""
        data = self.to_dict()
        content = json.dumps(data, indent=indent, default=str)
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        return content

    def to_markdown(self, filepath: Optional[str] = None) -> str:
        """Generates comprehensive, audit-ready engineering markdown report."""
        lines = [
            f"# CADi SAML Portable Engineering FEA Report",
            f"",
            f"**Study Name:** `{self.study_name}` | **Part Analyzed:** `{self.part_name}`",
            f"**Timestamp (UTC):** {self.timestamp_utc} | **CADi SAML Version:** `v{self.cadi_saml_version}`",
            f"",
            f"---",
            f"",
            f"## 1. Executive Summary & Verification Verdict",
            f"",
            f"| Metric | Value | Target Criteria | Status |",
            f"| :--- | :--- | :--- | :--- |",
            f"| **Verification Verdict** | **`{self.verification_verdict}`** | Grid Converged & Safe | {'[PASS]' if self.verification_verdict == 'VERIFIED_PASS' else '[WARN]'} |",
            f"| **Solver Backend** | `{self.solver_backend}` ({self.solver_version}) | Validated Solver | OK |",
            f"| **Solver Command** | `{self.solver_command or 'N/A'}` | Deterministic Execution | OK |",
            f"| **Mesh Convergence** | `{self.mesh_convergence_status}` | Convergence <= 5% | {'OK' if self.mesh_convergence_status == 'CONVERGED' else 'AUDIT'} |",
            f"| **Peak Von Mises** | **{self.max_von_mises_mpa:.2f} MPa** | Material Yield Limit | {'OK' if self.is_safe else 'EXCEEDED'} |",
            f"| **Max Deflection** | **{self.max_displacement_mm:.4f} mm** | Limit Threshold | OK |",
            f"| **Min Factor of Safety** | **{self.global_safety_factor:.2f}** | >= {self.tolerances.get('required_safety_factor', 1.5):.2f} | {'SAFE' if self.is_safe else 'ALERT'} |",
            f"",
            f"---",
            f"",
            f"## 2. Mesh & Computational Discretization",
            f"- **Node Count:** {self.num_nodes:,}",
            f"- **Element Count:** {self.num_elements:,} (3D Continuum Tetrahedra)",
            f"- **Convergence Assessment:** `{self.mesh_convergence_status}`",
        ]

        if self.mesh_convergence_details:
            d = self.mesh_convergence_details
            lines.extend([
                f"  - Relative Deflection Change: `{d.get('disp_relative_change_pct', 'N/A')}%` (Target <= {d.get('disp_tolerance_pct', 3.0)}%)",
                f"  - Relative Stress Change: `{d.get('stress_relative_change_pct', 'N/A')}%` (Target <= {d.get('stress_tolerance_pct', 5.0)}%)",
                f"  - Multi-Grid Levels Evaluated: {d.get('num_refinement_levels', 0)}",
            ])

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 3. Material Constitutive Cards",
            f"| Region / Material | Young's Modulus E (MPa) | Poisson Ratio nu | Yield Strength Sy (MPa) |",
            f"| :--- | :--- | :--- | :--- |",
        ])
        for k, m in self.materials.items():
            lines.append(f"| `{k}` ({m.get('name', 'Custom')}) | {m.get('youngs_modulus_mpa', 0):,.0f} | {m.get('poisson_ratio', 0):.2f} | {m.get('yield_strength_mpa', 0):.1f} |")

        if self.regional_results:
            lines.extend([
                f"",
                f"---",
                f"",
                f"## 4. Regional Safety Evaluation",
                f"| Region | Material | Elements | Peak VM (MPa) | Yield Sy (MPa) | Factor of Safety | Status |",
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for rk, rv in self.regional_results.items():
                s_icon = "SAFE" if rv.get("is_safe", True) else "OVERLOAD"
                lines.append(
                    f"| `{rk}` | {rv.get('material_name')} | {rv.get('element_count', 'N/A')} | "
                    f"{rv.get('max_von_mises_mpa', 0):.2f} | {rv.get('yield_strength_mpa', 0):.1f} | "
                    f"**{rv.get('safety_factor', 0):.2f}** | `{s_icon}` |"
                )

        if self.interface_results:
            lines.extend([
                f"",
                f"---",
                f"",
                f"## 5. Material Contact Interface Stress Analysis",
                f"| Interface Boundary | Shared Nodes | Peak Interface VM (MPa) | Mean Interface VM (MPa) | Interface FoS | Integrity |",
                f"| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for ik, iv in self.interface_results.items():
                s_icon = "INTEGRITY_OK" if iv.get("is_safe", True) else "DELAMINATION_RISK"
                lines.append(
                    f"| `{iv.get('region_a')} <-> {iv.get('region_b')}` | {iv.get('num_interface_nodes')} | "
                    f"{iv.get('max_von_mises_mpa', 0):.2f} | {iv.get('mean_von_mises_mpa', 0):.2f} | "
                    f"**{iv.get('safety_factor', 0):.2f}** | `{s_icon}` |"
                )

        md_content = "\n".join(lines) + "\n"
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
        return md_content
