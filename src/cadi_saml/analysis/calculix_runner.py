"""
cadi_saml.analysis.calculix_runner
==================================
Automated CalculiX FEA execution pipeline:
1. Writes standard .inp deck from CalculiXModel.
2. Runs external CalculiX solver (ccx / ccx.exe) if available.
3. Fallback: If ccx is not installed on the system, executes the verified
   multi-material C3D4 linear elasticity solver to compute the solution,
   writes a standard CalculiX .frd results file, and reads it through frd_reader.
4. Returns rich FEAResult with regional stresses, deformations, and safety factors.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from .calculix_adapter import CalculiXModel
from .fea import FEAResult
from .frd_reader import frd_to_fea_result, write_frd, _normalize_element_sets
from .solver import LinearElasticitySolver


class CalculiXRunner:
    """
    Orchestrates CalculiX input generation, solver execution, and results ingestion.
    """

    def __init__(
        self,
        model_or_executable: Optional[Union[CalculiXModel, str]] = None,
        executable: Optional[str] = None,
        timeout_seconds: float = 120.0,
        prefer_builtin_fallback: bool = True,
        model: Optional[CalculiXModel] = None,
    ):
        if isinstance(model_or_executable, CalculiXModel):
            self.model = model_or_executable
            exe = executable
        elif isinstance(model_or_executable, str):
            self.model = model
            exe = model_or_executable
        else:
            self.model = model
            exe = executable

        self.executable = exe or self._find_ccx_binary()
        self.timeout = timeout_seconds
        self.prefer_builtin_fallback = prefer_builtin_fallback

    @staticmethod
    def _find_ccx_binary() -> Optional[str]:
        """Locates CalculiX ccx binary from environment or PATH."""
        env_exe = os.environ.get("CCX_BINARY") or os.environ.get("CALCULIX_EXE")
        if env_exe and os.path.isfile(env_exe) and os.access(env_exe, os.X_OK):
            return env_exe

        for name in ("ccx", "ccx.exe", "calculix", "ccx_2.21", "ccx_2.20"):
            found = shutil.which(name)
            if found:
                return found
        return None

    def run(
        self,
        model: Optional[CalculiXModel] = None,
        work_dir: Optional[str] = None,
        job_name: Optional[str] = None,
        study_name: Optional[str] = None,
        required_safety_factor: float = 1.5,
    ) -> FEAResult:
        """
        Executes end-to-end FEA study:
        .inp generation -> ccx solve -> .frd parsing -> FEAResult.
        """
        target_model = model or self.model
        if target_model is None:
            raise ValueError("CalculiXModel must be provided either in constructor or in run().")

        actual_job = job_name or study_name or getattr(target_model, "name", "cad_analysis")
        actual_study = study_name or actual_job

        cleanup_dir = False
        if work_dir is None:
            work_dir = tempfile.mkdtemp(prefix="calculix_run_")
            cleanup_dir = True
        else:
            os.makedirs(work_dir, exist_ok=True)

        inp_path = os.path.join(work_dir, f"{actual_job}.inp")
        frd_path = os.path.join(work_dir, f"{actual_job}.frd")

        try:
            # 1. Generate .inp deck
            inp_content = target_model.to_inp()
            with open(inp_path, "w", encoding="utf-8") as f:
                f.write(inp_content)

            # 2. Run solver (ccx binary or built-in multi-material engine)
            exe = self.executable
            can_run_exe = (exe is not None) and (
                shutil.which(exe) is not None or os.path.isfile(exe) or not self.prefer_builtin_fallback
            )
            solver_ver = "CADi SAML Continuum Engine v1.0"
            solver_cmd = "builtin_linear_elasticity_solver"
            if can_run_exe and exe is not None:
                cmd = [exe, actual_job]
                proc = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"CalculiX execution failed (exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}")

                if not os.path.isfile(frd_path):
                    raise RuntimeError(f"CalculiX finished but did not produce output file {frd_path}:\n{proc.stdout}")

                backend_used = "calculix_ccx"
                solver_cmd = " ".join(cmd)
                solver_ver = "CalculiX ccx"
                for line in (proc.stdout or "").splitlines()[:5]:
                    if "CalculiX" in line:
                        solver_ver = line.strip()
                        break

            else:
                if not self.prefer_builtin_fallback:
                    raise RuntimeError(
                        "CalculiX binary ('ccx') was not found on PATH or via CCX_BINARY environment variable."
                    )
                # Fallback: Solve using built-in multi-material continuum engine and write real .frd
                self._solve_builtin_and_write_frd(target_model, frd_path)
                backend_used = "builtin"

            # 3. Read .frd and build FEAResult
            result = frd_to_fea_result(
                frd_path=frd_path,
                materials=target_model.materials,
                element_sets=target_model.element_sets,
                study_name=actual_study,
                part_name=actual_job,
                required_safety_factor=required_safety_factor,
                solver_backend=backend_used,
                index_base=getattr(target_model, "index_base", "one"),
                solver_version=solver_ver,
                solver_command=solver_cmd,
            )
            return result

        finally:
            if cleanup_dir and os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

    def _solve_builtin_and_write_frd(self, model: CalculiXModel, frd_path: str) -> None:
        """
        Solves multi-material elasticity using LinearElasticitySolver and serializes .frd file.
        """
        # Extract 0-based node and element arrays
        node_map = {int(n[0]): i for i, n in enumerate(model.nodes)}
        num_nodes = len(model.nodes)
        nodes_arr = np.array([[float(n[1]), float(n[2]), float(n[3])] for n in model.nodes], dtype=np.float64)

        num_elems = len(model.elements)
        elements_arr = np.zeros((num_elems, 4), dtype=np.int32)
        for j, e in enumerate(model.elements):
            elements_arr[j] = [node_map[int(x)] for x in e[1:5]]

        # Map each element to its Material using the standardized normalization function
        elem_materials: List[Any] = []
        if len(model.materials) > 1 and model.element_sets:
            norm_sets = _normalize_element_sets(
                model.element_sets,
                num_elems=num_elems,
                index_base=getattr(model, "index_base", "auto"),
            )
            mat_by_idx: Dict[int, Any] = {}
            for set_name, indices in norm_sets.items():
                mat = model.materials[set_name]
                for idx in indices:
                    mat_by_idx[idx] = mat
            for j in range(num_elems):
                elem_materials.append(mat_by_idx[j])
        else:
            default_mat = list(model.materials.values())[0]
            elem_materials = [default_mat] * num_elems

        solver = LinearElasticitySolver(
            nodes=nodes_arr,
            elements=elements_arr,
            element_materials=elem_materials,
        )

        fixed_indices = {node_map[int(nid)] for nid in model.fixed_nodes if int(nid) in node_map}
        forces_dict = {
            node_map[int(nid)]: f_vec for nid, f_vec in model.nodal_forces.items() if int(nid) in node_map
        }

        sol = solver.solve(fixed_node_indices=fixed_indices, nodal_forces=forces_dict)

        # Reconstruct nodal Cauchy stresses from element Cauchy stresses
        nodal_stresses = np.zeros((num_nodes, 6), dtype=np.float64)
        node_weights = np.zeros(num_nodes, dtype=np.float64)
        for j, elem_nodes in enumerate(elements_arr):
            for n_idx in elem_nodes:
                nodal_stresses[n_idx] += sol.element_stresses[j]
                node_weights[n_idx] += 1.0
        for i in range(num_nodes):
            if node_weights[i] > 0:
                nodal_stresses[i] /= node_weights[i]

        write_frd(
            filepath=frd_path,
            nodes=nodes_arr,
            elements=elements_arr,
            displacements=sol.displacements,
            stresses=nodal_stresses,
            reaction_forces=sol.reaction_forces,
        )
