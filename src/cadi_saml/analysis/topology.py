"""
cadi_saml.analysis.topology
===========================
2D Plane-Stress SIMP Topology Optimization Engine.
Implements the SIMP (Solid Isotropic Material with Penalization) algorithm
with sensitivity filtering and Optimality Criteria (OC) update scheme.
Solves for minimum structural compliance (maximum stiffness) under volume constraints,
and transforms the resulting optimal density field into tangible lightweight 3D CAD features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


def _element_stiffness_matrix_2d(youngs_modulus: float = 1.0, nu: float = 0.3) -> np.ndarray:
    """Analytical 8x8 element stiffness matrix for 4-node plane stress quadrilateral."""
    k = np.zeros(8)
    k[0] = 1.0 / 2.0 - nu / 6.0
    k[1] = 1.0 / 8.0 + nu / 8.0
    k[2] = -1.0 / 4.0 - nu / 12.0
    k[3] = -1.0 / 8.0 + 3.0 * nu / 8.0
    k[4] = -1.0 / 4.0 + nu / 12.0
    k[5] = -1.0 / 8.0 - nu / 8.0
    k[6] = nu / 6.0
    k[7] = 1.0 / 8.0 - 3.0 * nu / 8.0

    ke = (
        youngs_modulus
        / (1.0 - nu**2)
        * np.array(
            [
                [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
                [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
                [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
                [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
                [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
                [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
                [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
                [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
            ]
        )
    )
    return ke


@dataclass
class TopologyResult:
    """Outcome of a SIMP topology optimization run."""
    nelx: int
    nely: int
    volfrac: float
    penal: float
    rmin: float
    iterations: int
    final_compliance: float
    volume_achieved: float
    density_grid: np.ndarray  # Shape (nely, nelx)
    void_boxes: List[Tuple[float, float, float, float]]  # (x_min, y_min, x_max, y_max)
    length_mm: float
    height_mm: float
    thickness_mm: float

    def summary(self) -> str:
        return (
            f"SIMP Topology Optimization Results:\n"
            f"  Mesh Grid: {self.nelx} x {self.nely} ({self.nelx * self.nely} elements)\n"
            f"  Target Volume Fraction: {self.volfrac:.1%}\n"
            f"  Achieved Volume Fraction: {self.volume_achieved:.1%}\n"
            f"  Mass Reduction: {(1.0 - self.volume_achieved) * 100:.1f}%\n"
            f"  Final Compliance (Strain Energy): {self.final_compliance:.4e}\n"
            f"  Iterations: {self.iterations}\n"
            f"  Lightweight Voids Extracted: {len(self.void_boxes)}"
        )


class TopologyOptimizer:
    """
    SIMP Topology Optimizer for lightweight structural synthesis.
    """

    def __init__(
        self,
        nelx: int = 40,
        nely: int = 20,
        volfrac: float = 0.5,
        penal: float = 3.0,
        rmin: float = 1.5,
        length_mm: float = 100.0,
        height_mm: float = 50.0,
        thickness_mm: float = 10.0,
        problem_type: str = "cantilever",
    ):
        self.nelx = int(nelx)
        self.nely = int(nely)
        self.volfrac = float(volfrac)
        self.penal = float(penal)
        self.rmin = float(rmin)
        self.length = float(length_mm)
        self.height = float(height_mm)
        self.thickness = float(thickness_mm)
        self.problem_type = problem_type.lower()

    def solve(self, max_iter: int = 35, tol: float = 0.01) -> TopologyResult:
        """Runs the iterative SIMP density optimization."""
        nelx, nely = self.nelx, self.nely
        volfrac = self.volfrac
        penal = self.penal
        rmin = self.rmin
        E_min = 1e-9
        E_0 = 1.0

        ke = _element_stiffness_matrix_2d(youngs_modulus=E_0, nu=0.3)

        # Build DOF mapping
        nodenrs = np.arange((nelx + 1) * (nely + 1)).reshape((nelx + 1, nely + 1)).T
        edofVec = (2 * nodenrs[0:-1, 0:-1] + 2).reshape((nelx * nely, 1), order="F")
        edofMat = np.tile(edofVec, (1, 8)) + np.tile(
            np.array(
                [
                    0,
                    1,
                    2 * nely + 2,
                    2 * nely + 3,
                    2 * nely,
                    2 * nely + 1,
                    -2,
                    -1,
                ]
            ),
            (nelx * nely, 1),
        )

        iK = np.kron(edofMat, np.ones((8, 1))).flatten()
        jK = np.kron(edofMat, np.ones((1, 8))).flatten()

        # Mesh-independent filter weights
        nfilter = int(nelx * nely * ((2 * (math.ceil(rmin) - 1) + 1) ** 2))
        iH = np.zeros(nfilter)
        jH = np.zeros(nfilter)
        sH = np.zeros(nfilter)
        cc = 0
        for i in range(nelx):
            for j in range(nely):
                row = i * nely + j
                kk1 = int(max(i - (math.ceil(rmin) - 1), 0))
                kk2 = int(min(i + math.ceil(rmin), nelx))
                ll1 = int(max(j - (math.ceil(rmin) - 1), 0))
                ll2 = int(min(j + math.ceil(rmin), nely))
                for k in range(kk1, kk2):
                    for l in range(ll1, ll2):
                        col = k * nely + l
                        fac = rmin - math.sqrt((i - k) ** 2 + (j - l) ** 2)
                        iH[cc] = row
                        jH[cc] = col
                        sH[cc] = max(0.0, fac)
                        cc += 1

        iH = iH[:cc]
        jH = jH[:cc]
        sH = sH[:cc]
        H = sp.coo_matrix((sH, (iH, jH)), shape=(nelx * nely, nelx * nely)).tocsc()
        Hs = np.array(H.sum(1)).flatten()

        # Load & Boundary Conditions
        total_dof = 2 * (nelx + 1) * (nely + 1)
        F = np.zeros((total_dof, 1))
        
        if self.problem_type == "cantilever":
            # Cantilever: Fixed at left end (x = 0), point load at center-right
            fixed_nodes = np.arange(0, 2 * (nely + 1))
            load_dof = 2 * (nelx * (nely + 1) + nely // 2) + 1
            F[load_dof, 0] = -1.0
        elif self.problem_type == "mbb":
            # MBB beam (half symmetric): Left edge fixed horizontally, bottom-right fixed vertically
            fixed_nodes = np.union1d(
                np.arange(0, 2 * (nely + 1), 2),  # x = 0 fixed in x
                np.array([2 * (nelx + 1) * (nely + 1) - 1]),  # bottom-right in y
            )
            load_dof = 1  # Top-left vertical load
            F[load_dof, 0] = -1.0
        else:
            # Default to cantilever
            fixed_nodes = np.arange(0, 2 * (nely + 1))
            load_dof = 2 * (nelx * (nely + 1) + nely // 2) + 1
            F[load_dof, 0] = -1.0

        all_dof = np.arange(total_dof)
        free_dof = np.setdiff1d(all_dof, fixed_nodes)

        # Initial density distribution
        x = np.ones((nely, nelx)) * volfrac
        xPhys = x.copy()

        change = 1.0
        iteration = 0
        final_compliance = 0.0

        # Optimization loop
        while change > tol and iteration < max_iter:
            iteration += 1

            # FE Analysis
            sK = ((ke.flatten()[np.newaxis, :] * (E_min + (xPhys.flatten(order="F") ** penal) * (E_0 - E_min))[:, np.newaxis]).flatten())
            K = sp.coo_matrix((sK, (iK, jK)), shape=(total_dof, total_dof)).tocsc()
            K_free = K[free_dof, :][:, free_dof]

            U = np.zeros((total_dof, 1))
            U[free_dof, 0] = spla.spsolve(K_free, F[free_dof, 0])

            # Objective & Sensitivities
            U_1d = U.flatten()
            Ue = U_1d[edofMat]
            ce = np.sum((Ue @ ke) * Ue, axis=1)
            c = np.sum((E_min + (xPhys.flatten(order="F") ** penal) * (E_0 - E_min)) * ce)
            final_compliance = float(c)

            dc = -penal * (E_0 - E_min) * (xPhys.flatten(order="F") ** (penal - 1)) * ce
            dv = np.ones(nelx * nely)

            # Sensitivity filter
            dc = np.array(H @ (xPhys.flatten(order="F") * dc) / Hs / np.maximum(1e-3, xPhys.flatten(order="F"))).flatten()
            dv = np.array(H @ dv / Hs).flatten()

            # Optimality Criteria (OC) Update
            l1, l2 = 0.0, 1e9
            move = 0.2
            xnew = np.zeros(nelx * nely)
            x_flat = x.flatten(order="F")

            while (l2 - l1) / (l1 + l2 + 1e-12) > 1e-3:
                lmid = 0.5 * (l2 + l1)
                Be = -dc / dv / lmid
                x_candidate = np.maximum(
                    0.0,
                    np.maximum(
                        x_flat - move,
                        np.minimum(
                            1.0,
                            np.minimum(x_flat + move, x_flat * np.sqrt(np.maximum(1e-10, Be))),
                        ),
                    ),
                )
                xPhys_candidate = np.array(H @ x_candidate / Hs).flatten()
                if np.sum(xPhys_candidate) > volfrac * nelx * nely:
                    l1 = lmid
                else:
                    l2 = lmid
                xnew = x_candidate

            change = np.max(np.abs(xnew - x_flat))
            x = xnew.reshape((nely, nelx), order="F")
            xPhys = np.array(H @ xnew / Hs).reshape((nely, nelx), order="F")

        # Extract void regions (connected regions below density threshold 0.25)
        void_boxes = self._extract_void_regions(xPhys)

        return TopologyResult(
            nelx=nelx,
            nely=nely,
            volfrac=volfrac,
            penal=penal,
            rmin=rmin,
            iterations=iteration,
            final_compliance=final_compliance,
            volume_achieved=float(np.mean(xPhys)),
            density_grid=xPhys,
            void_boxes=void_boxes,
            length_mm=self.length,
            height_mm=self.height,
            thickness_mm=self.thickness,
        )

    def _extract_void_regions(
        self, density: np.ndarray, threshold: float = 0.25
    ) -> List[Tuple[float, float, float, float]]:
        """Identifies large contiguous void areas to convert to CAD cutting boxes."""
        nely, nelx = density.shape
        dx = self.length / nelx
        dy = self.height / nely

        void_mask = density < threshold
        void_boxes: List[Tuple[float, float, float, float]] = []

        # Find connected low-density blocks (simple rectangular aggregation)
        visited = np.zeros_like(void_mask, dtype=bool)

        for j in range(1, nely - 1):
            for i in range(1, nelx - 1):
                if void_mask[j, i] and not visited[j, i]:
                    # Grow rectangle
                    i_end = i
                    while i_end < nelx - 1 and void_mask[j, i_end] and not visited[j, i_end]:
                        i_end += 1
                    j_end = j
                    while j_end < nely - 1 and np.all(void_mask[j_end, i:i_end]) and not np.any(visited[j_end, i:i_end]):
                        j_end += 1

                    if (i_end - i) >= 3 and (j_end - j) >= 2:
                        visited[j:j_end, i:i_end] = True
                        x_min = i * dx
                        x_max = i_end * dx
                        y_min = j * dy
                        y_max = j_end * dy
                        void_boxes.append((round(x_min, 2), round(y_min, 2), round(x_max, 2), round(y_max, 2)))

        return void_boxes


def optimize_topology(
    assembly: Optional["Assembly"] = None,
    part_name: str = "topology_bracket",
    length_mm: float = 120.0,
    height_mm: float = 60.0,
    thickness_mm: float = 15.0,
    target_volume_fraction: float = 0.45,
    problem_type: str = "cantilever",
    nelx: int = 30,
    nely: int = 15,
    material: str = "Aluminum6061",
) -> Dict[str, Any]:
    """
    Convenience function: Solves SIMP topology optimization and generates
    the resulting lightweighted 3D CAD part with cutouts in the assembly.
    """
    optimizer = TopologyOptimizer(
        nelx=nelx,
        nely=nely,
        volfrac=target_volume_fraction,
        length_mm=length_mm,
        height_mm=height_mm,
        thickness_mm=thickness_mm,
        problem_type=problem_type,
    )
    result = optimizer.solve()

    created_part = None
    if assembly is not None:
        # Create base solid block
        assembly.add_box(
            name=part_name,
            length=length_mm,
            width=height_mm,
            height=thickness_mm,
            origin=(0.0, 0.0, 0.0),
        )
        created_part = assembly._parts[part_name]
        created_part.set_appearance(color=(0.3, 0.6, 0.8), material=material)

        # Cut extracted void regions
        for idx, (xmin, ymin, xmax, ymax) in enumerate(result.void_boxes):
            void_cutter = f"{part_name}_void_{idx+1}"
            w = xmax - xmin
            h = ymax - ymin
            assembly.add_box(
                name=void_cutter,
                length=w,
                width=h,
                height=thickness_mm + 10.0,
                origin=(xmin, ymin, -5.0),
            )
            assembly.cut(part_name, void_cutter, keep_tool=False)

    return {
        "part_name": part_name,
        "length_mm": length_mm,
        "height_mm": height_mm,
        "thickness_mm": thickness_mm,
        "target_volume_fraction": target_volume_fraction,
        "achieved_volume_fraction": round(result.volume_achieved, 3),
        "mass_reduction_percent": round((1.0 - result.volume_achieved) * 100, 1),
        "iterations": result.iterations,
        "final_compliance": result.final_compliance,
        "void_regions_cut": len(result.void_boxes),
        "summary": result.summary(),
    }
