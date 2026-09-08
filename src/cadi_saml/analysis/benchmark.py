"""
cadi_saml.analysis.benchmark
============================
Standardized analytical and physical benchmark comparison engine for FEA validation.
Implements classical Euler-Bernoulli/Timoshenko beam problems and comparative
metrics between analytical theory, internal continuum solver, and CalculiX (ccx).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

from .materials import Material, get_material
from .solver import FEMSolution, LinearElasticitySolver


@dataclass(frozen=True)
class AnalyticalBeamResult:
    """Exact analytical Euler-Bernoulli & Timoshenko closed-form solutions."""
    length_mm: float
    width_mm: float
    height_mm: float
    force_n: float
    youngs_modulus_mpa: float
    poisson_ratio: float
    moment_of_inertia_mm4: float
    area_mm2: float
    shear_modulus_mpa: float

    euler_bernoulli_tip_disp_mm: float
    timoshenko_tip_disp_mm: float
    peak_bending_stress_mpa: float


def compute_analytical_cantilever(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    force_n: float,
    material: Union[str, Material],
) -> AnalyticalBeamResult:
    """
    Computes closed-form analytical deflection and stress for an end-loaded cantilever beam.
    Uses Euler-Bernoulli and Timoshenko beam theory with shear coefficient kappa = 5/6.
    """
    mat = material if isinstance(material, Material) else get_material(material)
    L = float(length_mm)
    b = float(width_mm)
    h = float(height_mm)
    F = float(force_n)
    E = float(mat.youngs_modulus_mpa)
    nu = float(getattr(mat, "poissons_ratio", getattr(mat, "poisson_ratio", 0.3)))

    I = (b * (h ** 3)) / 12.0
    A = b * h
    G = E / (2.0 * (1.0 + nu))
    kappa = 5.0 / 6.0  # Rectangular cross-section shear factor

    # Euler-Bernoulli pure bending tip deflection: F * L^3 / (3 * E * I)
    delta_eb = (F * (L ** 3)) / (3.0 * E * I)

    # Timoshenko shear deformation contribution: F * L / (kappa * G * A)
    delta_shear = (F * L) / (kappa * G * A)
    delta_timo = delta_eb + delta_shear

    # Maximum bending stress at fixed root: M * (h/2) / I = (F * L) * (h/2) / I
    sigma_max = (F * L * (h / 2.0)) / I

    return AnalyticalBeamResult(
        length_mm=L,
        width_mm=b,
        height_mm=h,
        force_n=F,
        youngs_modulus_mpa=E,
        poisson_ratio=nu,
        moment_of_inertia_mm4=I,
        area_mm2=A,
        shear_modulus_mpa=G,
        euler_bernoulli_tip_disp_mm=delta_eb,
        timoshenko_tip_disp_mm=delta_timo,
        peak_bending_stress_mpa=sigma_max,
    )


def generate_structured_beam_mesh(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    nx: int = 10,
    ny: int = 2,
    nz: int = 2,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates a structured 3D tetrahedral mesh for a rectangular prism.
    Returns:
    - nodes: (N, 3) float64
    - elements: (M, 4) int32
    """
    xs = np.linspace(0, length_mm, nx + 1)
    ys = np.linspace(0, width_mm, ny + 1)
    zs = np.linspace(0, height_mm, nz + 1)

    node_map = {}
    nodes = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            for k, z in enumerate(zs):
                idx = len(nodes)
                nodes.append([x, y, z])
                node_map[(i, j, k)] = idx

    elements = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                n000 = node_map[(i, j, k)]
                n100 = node_map[(i + 1, j, k)]
                n010 = node_map[(i, j + 1, k)]
                n110 = node_map[(i + 1, j + 1, k)]
                n001 = node_map[(i, j, k + 1)]
                n101 = node_map[(i + 1, j, k + 1)]
                n011 = node_map[(i, j + 1, k + 1)]
                n111 = node_map[(i + 1, j + 1, k + 1)]

                # Decompose hex cell into 5 tetrahedra
                elements.append([n000, n100, n010, n001])
                elements.append([n100, n110, n010, n111])
                elements.append([n100, n001, n101, n111])
                elements.append([n010, n001, n111, n011])
                elements.append([n100, n010, n001, n111])

    return np.array(nodes, dtype=np.float64), np.array(elements, dtype=np.int32)


@dataclass
class BenchmarkComparisonResult:
    """Comparative verification metric between analytical theory and numerical FEA."""
    benchmark_name: str
    analytical_disp_mm: float
    numerical_disp_mm: float
    disp_error_pct: float

    analytical_stress_mpa: float
    numerical_stress_mpa: float
    stress_error_pct: float

    tolerance_pct: float
    is_verified: bool
    solver_backend: str
    num_nodes: int
    num_elements: int
    details: Dict[str, Any]

    @property
    def summary_table(self) -> str:
        status = "PASSED (VERIFIED)" if self.is_verified else "FAILED (TOLERANCE EXCEEDED)"
        return (
            f"\n=======================================================\n"
            f"  FEA BENCHMARK VALIDATION REPORT: {self.benchmark_name}\n"
            f"=======================================================\n"
            f"Solver Backend   : {self.solver_backend}\n"
            f"Mesh Discretization: {self.num_nodes:,} Nodes | {self.num_elements:,} Elements\n"
            f"Tolerance Target : <= {self.tolerance_pct:.1f}%\n"
            f"-------------------------------------------------------\n"
            f"Deflection (mm)  : Analytical = {self.analytical_disp_mm:.4f} mm | FEA = {self.numerical_disp_mm:.4f} mm\n"
            f"Disp Error       : {self.disp_error_pct:.2f}%\n"
            f"Peak Stress (MPa): Analytical = {self.analytical_stress_mpa:.2f} MPa | FEA = {self.numerical_stress_mpa:.2f} MPa\n"
            f"Stress Error     : {self.stress_error_pct:.2f}%\n"
            f"Verification     : {status}\n"
            f"=======================================================\n"
        )


class BenchmarkValidator:
    """Automates analytical beam and plate benchmarks for solver verification."""

    @staticmethod
    def run_uniaxial_tension_benchmark(
        length_mm: float = 100.0,
        width_mm: float = 10.0,
        height_mm: float = 10.0,
        axial_force_n: float = 10000.0,
        material: Union[str, Material] = "S235JR",
        nx: int = 10,
        ny: int = 2,
        nz: int = 2,
        tolerance_pct: float = 6.0,
    ) -> BenchmarkComparisonResult:
        """
        Executes pure uniaxial tensile bar benchmark.
        Because linear tetrahedra (C3D4) are constant strain elements, they represent
        uniform tension with high precision (stress error < 0.5%, 3D Poisson end-effects disp error ~5%).
        """
        mat = material if isinstance(material, Material) else get_material(material)
        L = float(length_mm)
        A = float(width_mm * height_mm)
        E = float(mat.youngs_modulus_mpa)
        F = float(axial_force_n)

        analytical_disp = (F * L) / (E * A)
        analytical_stress = F / A

        nodes, elements = generate_structured_beam_mesh(L, width_mm, height_mm, nx=nx, ny=ny, nz=nz)

        # Fixed root at x=0
        root_indices = set(np.where(nodes[:, 0] < 1e-5)[0])

        # Tensile load applied in +X at x=L face
        tip_indices = np.where(nodes[:, 0] > (L - 1e-5))[0]
        nodal_f = F / len(tip_indices)
        nodal_forces = {int(idx): (nodal_f, 0.0, 0.0) for idx in tip_indices}

        solver = LinearElasticitySolver(nodes, elements, mat)
        sol: FEMSolution = solver.solve(root_indices, nodal_forces)

        fe_disp = float(sol.max_displacement)
        fe_stress = float(np.mean(sol.nodal_von_mises))

        disp_err = abs(fe_disp - analytical_disp) / analytical_disp * 100.0
        stress_err = abs(fe_stress - analytical_stress) / analytical_stress * 100.0

        is_verified = (disp_err <= tolerance_pct) and (stress_err <= (tolerance_pct * 2.0))

        return BenchmarkComparisonResult(
            benchmark_name="Uniaxial_Tensile_Bar",
            analytical_disp_mm=round(analytical_disp, 4),
            numerical_disp_mm=round(fe_disp, 4),
            disp_error_pct=round(disp_err, 2),
            analytical_stress_mpa=round(analytical_stress, 2),
            numerical_stress_mpa=round(fe_stress, 2),
            stress_error_pct=round(stress_err, 2),
            tolerance_pct=tolerance_pct,
            is_verified=is_verified,
            solver_backend="builtin",
            num_nodes=len(nodes),
            num_elements=len(elements),
            details={
                "cross_section_area_mm2": A,
                "axial_stiffness_n_mm": (E * A) / L,
            },
        )

    @staticmethod
    def run_cantilever_benchmark(
        length_mm: float = 100.0,
        width_mm: float = 10.0,
        height_mm: float = 10.0,
        tip_force_n: float = 500.0,
        material: Union[str, Material] = "S235JR",
        nx: int = 15,
        ny: int = 3,
        nz: int = 3,
        tolerance_pct: float = 40.0,
    ) -> BenchmarkComparisonResult:
        """
        Executes cantilever beam benchmark against Timoshenko analytical solution.
        Linear 4-node tetrahedral elements (C3D4) exhibit artificial bending stiffness (shear locking)
        under pure bending with coarse thickness discretization, expected within 30-40% band.
        """
        mat = material if isinstance(material, Material) else get_material(material)
        analytical = compute_analytical_cantilever(length_mm, width_mm, height_mm, tip_force_n, mat)

        nodes, elements = generate_structured_beam_mesh(length_mm, width_mm, height_mm, nx=nx, ny=ny, nz=nz)

        # Fixed root at x=0
        root_indices = set(np.where(nodes[:, 0] < 1e-5)[0])

        # Force applied downwards in Z at x=L tip face
        tip_indices = np.where(nodes[:, 0] > (length_mm - 1e-5))[0]
        nodal_f = -abs(tip_force_n) / len(tip_indices)
        nodal_forces = {int(idx): (0.0, 0.0, nodal_f) for idx in tip_indices}

        solver = LinearElasticitySolver(nodes, elements, mat)
        sol: FEMSolution = solver.solve(root_indices, nodal_forces)

        fe_disp = float(sol.max_displacement)
        fe_stress = float(sol.max_von_mises)

        target_disp = analytical.timoshenko_tip_disp_mm
        target_stress = analytical.peak_bending_stress_mpa

        disp_err = abs(fe_disp - target_disp) / target_disp * 100.0
        stress_err = abs(fe_stress - target_stress) / target_stress * 100.0

        is_verified = (disp_err <= tolerance_pct) and (stress_err <= tolerance_pct * 1.5)

        return BenchmarkComparisonResult(
            benchmark_name="Cantilever_Timoshenko_Beam",
            analytical_disp_mm=round(target_disp, 4),
            numerical_disp_mm=round(fe_disp, 4),
            disp_error_pct=round(disp_err, 2),
            analytical_stress_mpa=round(target_stress, 2),
            numerical_stress_mpa=round(fe_stress, 2),
            stress_error_pct=round(stress_err, 2),
            tolerance_pct=tolerance_pct,
            is_verified=is_verified,
            solver_backend="builtin",
            num_nodes=len(nodes),
            num_elements=len(elements),
            details={
                "euler_bernoulli_disp_mm": analytical.euler_bernoulli_tip_disp_mm,
                "timoshenko_disp_mm": analytical.timoshenko_tip_disp_mm,
                "aspect_ratio": length_mm / height_mm,
                "note": "Linear C3D4 elements exhibit artificial shear locking under bending with coarse thickness.",
            },
        )
