"""
cadi_saml.analysis.solver
=========================
Pure NumPy / SciPy 3D Finite Element Analysis (FEA) linear elasticity solver.
Computes displacement vectors, Cauchy stress tensors, and Von-Mises equivalent stresses
on 3D tetrahedral (C3D4) meshes.
"""

from __future__ import annotations

import math
import warnings
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .materials import Material


@dataclass
class FEMSolution:
    """Raw mathematical solution from the 3D finite element solver."""
    displacements: np.ndarray         # (N, 3) nodal displacement vector (u_x, u_y, u_z) in mm
    nodal_von_mises: np.ndarray       # (N,) equivalent Von-Mises stress at each node in MPa
    element_von_mises: np.ndarray     # (M,) Von-Mises stress per element in MPa
    element_stresses: np.ndarray      # (M, 6) Cauchy stresses [s_xx, s_yy, s_zz, t_xy, t_yz, t_zx]
    max_displacement: float           # Maximum resultant deflection in mm
    reaction_forces: np.ndarray
    relative_residual: float
    max_von_mises: float              # Peak Von-Mises stress in MPa


class LinearElasticitySolver:
    """
    Vectorized 3D Solid Continuum Finite Element Solver using 4-node linear tetrahedra.
    Solves K * u = F subject to fixed Dirichlet boundary constraints.
    """

    def __init__(
        self,
        nodes: np.ndarray,      # (N, 3) float64
        elements: np.ndarray,   # (M, 4) int32
        material: Optional[Material] = None,
        element_materials: Optional[Sequence[Material]] = None,
    ):
        self.nodes = np.asarray(nodes, dtype=np.float64)
        self.elements = np.asarray(elements, dtype=np.int32)
        if self.nodes.ndim != 2 or self.nodes.shape[1] != 3 or not len(self.nodes):
            raise ValueError("nodes must be a nonempty (N, 3) array")
        if self.elements.ndim != 2 or self.elements.shape[1] != 4 or not len(self.elements):
            raise ValueError("elements must be a nonempty (M, 4) array")
        if not np.isfinite(self.nodes).all() or self.elements.min() < 0 or self.elements.max() >= len(self.nodes):
            raise ValueError("Invalid mesh coordinates or element indices")
        if len(np.unique(self.elements)) != len(self.nodes):
            raise ValueError("Mesh contains unused nodes")

        self.num_nodes = len(self.nodes)
        self.num_elements = len(self.elements)
        self.num_dofs = self.num_nodes * 3

        if element_materials is not None:
            if len(element_materials) != self.num_elements:
                raise ValueError(f"element_materials count ({len(element_materials)}) must match elements ({self.num_elements})")
            self.element_materials = list(element_materials)
            self.material = self.element_materials[0] if material is None else material
            self._elem_C = []
            for mat in self.element_materials:
                E = mat.youngs_modulus_mpa
                nu = mat.poissons_ratio
                if not (math.isfinite(E) and E > 0 and math.isfinite(nu) and -1 < nu < 0.5):
                    raise ValueError(f"Invalid material constants for {mat.name}: E={E}, nu={nu}")
                factor = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
                C_mat = factor * np.array([
                    [1.0 - nu, nu, nu, 0.0, 0.0, 0.0],
                    [nu, 1.0 - nu, nu, 0.0, 0.0, 0.0],
                    [nu, nu, 1.0 - nu, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0],
                ], dtype=np.float64)
                self._elem_C.append(C_mat)
            self.C = self._elem_C[0]
        else:
            if material is None:
                raise ValueError("Must provide material or element_materials")
            if not (math.isfinite(material.youngs_modulus_mpa) and material.youngs_modulus_mpa > 0
                    and math.isfinite(material.poissons_ratio) and -1 < material.poissons_ratio < 0.5):
                raise ValueError("Invalid isotropic material constants")
            self.material = material
            self.element_materials = None
            self._elem_C = None

            E = self.material.youngs_modulus_mpa
            nu = self.material.poissons_ratio
            factor = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
            self.C = factor * np.array([
                [1.0 - nu, nu, nu, 0.0, 0.0, 0.0],
                [nu, 1.0 - nu, nu, 0.0, 0.0, 0.0],
                [nu, nu, 1.0 - nu, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, (1.0 - 2.0 * nu) / 2.0],
            ], dtype=np.float64)

    def solve(
        self,
        fixed_node_indices: Optional[Set[int]] = None,
        nodal_forces: Optional[Dict[int, Tuple[float, float, float]]] = None,
        fixed_nodes: Optional[Set[int]] = None,
    ) -> FEMSolution:
        """
        Assembles stiffness matrix, applies boundary conditions, solves for displacements,
        and computes resultant stresses.
        """
        if fixed_node_indices is None:
            fixed_node_indices = fixed_nodes
        if fixed_node_indices is None:
            fixed_node_indices = set()
        if nodal_forces is None:
            nodal_forces = {}

        if not fixed_node_indices:
            raise ValueError("FEA requires at least one fixed face/node to prevent rigid body motion.")

        if any(i < 0 or i >= self.num_nodes for i in fixed_node_indices):
            raise ValueError("Fixed node index out of range")
        if any(i < 0 or i >= self.num_nodes or np.asarray(f).shape != (3,)
               or not np.isfinite(f).all() for i, f in nodal_forces.items()):
            raise ValueError("Invalid force node or vector")
        # Check rigid body restraint separately on every connected mesh component.
        parent = list(range(self.num_nodes))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for tet in self.elements:
            for i in tet[1:]:
                parent[find(int(i))] = find(int(tet[0]))
        groups = {}
        for i in range(self.num_nodes):
            groups.setdefault(find(i), []).append(i)
        for ids in groups.values():
            fixed = [i for i in ids if i in fixed_node_indices]
            if len(fixed) < 3 or np.linalg.matrix_rank(self.nodes[fixed] - self.nodes[fixed].mean(axis=0)) < 2:
                raise ValueError("Underconstrained mesh component: fix at least three non-collinear nodes")

        # 1. Assemble Global Stiffness Matrix K
        # Preallocate triplet arrays for COO sparse matrix (M elements * 12 * 12 = 144 * M entries)
        num_elem = self.num_elements
        entry_count = num_elem * 144
        rows = np.empty(entry_count, dtype=np.int32)
        cols = np.empty(entry_count, dtype=np.int32)
        vals = np.empty(entry_count, dtype=np.float64)

        # Store B matrices and volumes for stress calculation
        elem_B_matrices = []
        elem_volumes = np.empty(num_elem, dtype=np.float64)

        offset = 0
        for e_idx in range(num_elem):
            elem_nodes = self.elements[e_idx]
            pts = self.nodes[elem_nodes]

            # Coordinate matrix [1, x, y, z]
            M = np.ones((4, 4), dtype=np.float64)
            M[:, 1:] = pts

            det_M = np.linalg.det(M)
            scale = np.max(np.linalg.norm(pts - pts[0], axis=1))
            if abs(det_M) <= max(scale ** 3 * 1e-12, np.finfo(float).tiny):
                raise ValueError(f"Degenerate tetrahedron {e_idx}")
            vol = abs(det_M) / 6.0
            elem_volumes[e_idx] = vol

            # Shape function gradients via inverse of M
            inv_M = np.linalg.inv(M)
            dN_dx = inv_M[1, :]
            dN_dy = inv_M[2, :]
            dN_dz = inv_M[3, :]

            # Strain-displacement matrix B (6x12)
            B = np.zeros((6, 12), dtype=np.float64)
            for i in range(4):
                B[0, 3 * i] = dN_dx[i]
                B[1, 3 * i + 1] = dN_dy[i]
                B[2, 3 * i + 2] = dN_dz[i]

                B[3, 3 * i] = dN_dy[i]
                B[3, 3 * i + 1] = dN_dx[i]

                B[4, 3 * i + 1] = dN_dz[i]
                B[4, 3 * i + 2] = dN_dy[i]

                B[5, 3 * i] = dN_dz[i]
                B[5, 3 * i + 2] = dN_dx[i]

            elem_B_matrices.append(B)

            # Element stiffness Ke = vol * (B.T @ C @ B)
            C_curr = self._elem_C[e_idx] if self._elem_C is not None else self.C
            Ke = vol * (B.T @ C_curr @ B)

            # DOFs for this element: [n0_x, n0_y, n0_z, n1_x, ..., n3_z]
            dofs = np.empty(12, dtype=np.int32)
            for i, n in enumerate(elem_nodes):
                dofs[3 * i] = 3 * n
                dofs[3 * i + 1] = 3 * n + 1
                dofs[3 * i + 2] = 3 * n + 2

            # Outer product of DOFs for sparse indexing
            r_grid, c_grid = np.meshgrid(dofs, dofs, indexing="ij")
            rows[offset : offset + 144] = r_grid.ravel()
            cols[offset : offset + 144] = c_grid.ravel()
            vals[offset : offset + 144] = Ke.ravel()
            offset += 144

        K_global = sp.coo_matrix((vals, (rows, cols)), shape=(self.num_dofs, self.num_dofs)).tocsc()

        # 2. Assemble Force Vector F
        F_global = np.zeros(self.num_dofs, dtype=np.float64)
        for node_idx, force in nodal_forces.items():
            if 0 <= node_idx < self.num_nodes:
                F_global[3 * node_idx] += force[0]
                F_global[3 * node_idx + 1] += force[1]
                F_global[3 * node_idx + 2] += force[2]

        # 3. Apply Boundary Conditions (Fixed DOFs)
        fixed_dofs = set()
        for n in fixed_node_indices:
            fixed_dofs.add(3 * n)
            fixed_dofs.add(3 * n + 1)
            fixed_dofs.add(3 * n + 2)

        all_dofs = np.arange(self.num_dofs)
        free_dofs = np.array([d for d in all_dofs if d not in fixed_dofs], dtype=np.int32)

        if len(free_dofs) == 0:
            raise ValueError("All DOFs are constrained; no free nodes left to solve.")

        # Partition matrix and solve
        K_free = K_global[free_dofs, :][:, free_dofs]
        F_free = F_global[free_dofs]

        with warnings.catch_warnings():
            warnings.simplefilter("error", spla.MatrixRankWarning)
            try:
                u_free = spla.spsolve(K_free, F_free)
            except spla.MatrixRankWarning as exc:
                raise ValueError("Singular stiffness matrix; check mesh and restraints") from exc
        if not np.isfinite(u_free).all():
            raise ValueError("Non-finite FEA solution")
        relative_residual = float(np.linalg.norm(K_free @ u_free - F_free) / max(np.linalg.norm(F_free), 1.0))
        if relative_residual > 1e-7:
            raise ValueError(f"FEA residual too large: {relative_residual}")

        # Full displacement array
        u_full = np.zeros(self.num_dofs, dtype=np.float64)
        u_full[free_dofs] = u_free

        reaction_forces = (K_global @ u_full - F_global).reshape((-1, 3))
        displacements = u_full.reshape((self.num_nodes, 3))
        disp_magnitudes = np.linalg.norm(displacements, axis=1)
        max_displacement = float(np.max(disp_magnitudes))

        # 4. Compute Element and Nodal Stresses
        elem_stresses = np.zeros((num_elem, 6), dtype=np.float64)
        elem_von_mises = np.zeros(num_elem, dtype=np.float64)

        # For nodal stress averaging
        node_stress_accum = np.zeros(self.num_nodes, dtype=np.float64)
        node_weight_accum = np.zeros(self.num_nodes, dtype=np.float64)

        for e_idx in range(num_elem):
            B = elem_B_matrices[e_idx]
            elem_nodes = self.elements[e_idx]

            # Collect element displacements (12,)
            u_elem = displacements[elem_nodes].ravel()

            strain = B @ u_elem
            C_curr = self._elem_C[e_idx] if self._elem_C is not None else self.C
            stress = C_curr @ strain
            elem_stresses[e_idx] = stress

            # Von-Mises: sqrt( 0.5 * ((s1-s2)^2 + (s2-s3)^2 + (s3-s1)^2 + 6*(t12^2 + t23^2 + t31^2)) )
            s_xx, s_yy, s_zz, t_xy, t_yz, t_zx = stress
            vm = math.sqrt(
                0.5 * (
                    (s_xx - s_yy) ** 2
                    + (s_yy - s_zz) ** 2
                    + (s_zz - s_xx) ** 2
                    + 6.0 * (t_xy ** 2 + t_yz ** 2 + t_zx ** 2)
                )
            )
            elem_von_mises[e_idx] = vm

            # Accumulate into node averages weighted by element volume
            v = elem_volumes[e_idx]
            for n in elem_nodes:
                node_stress_accum[n] += vm * v
                node_weight_accum[n] += v

        # Normalize nodal stress
        valid_mask = node_weight_accum > 1e-12
        nodal_von_mises = np.zeros(self.num_nodes, dtype=np.float64)
        nodal_von_mises[valid_mask] = node_stress_accum[valid_mask] / node_weight_accum[valid_mask]

        max_von_mises = float(np.max(nodal_von_mises))

        return FEMSolution(
            reaction_forces=reaction_forces,
            relative_residual=relative_residual,
            displacements=displacements,
            nodal_von_mises=nodal_von_mises,
            element_von_mises=elem_von_mises,
            element_stresses=elem_stresses,
            max_displacement=max_displacement,
            max_von_mises=max_von_mises,
        )
