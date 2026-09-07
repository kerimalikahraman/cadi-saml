"""
cadi_saml.simulation.structural.modal

Modal vibration analysis and resonance risk assessment.
Solves the generalized eigenvalue problem [K]{phi} = omega^2 [M]{phi} for 3D solid FEA meshes,
and provides analytical natural frequency solvers for beams and plates.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Union
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ...analysis.materials import Material, get_material
from ..results import AnalysisResult, AcceptanceCriteria, ProvenanceRecord


@dataclass
class ModeShapeResult:
    mode_number: int
    frequency_hz: float
    angular_frequency_rad_s: float
    eigenvector: Optional[np.ndarray] = None  # (num_nodes, 3) normalized modal displacement


@dataclass
class ModalAnalysisResult:
    part_name: str
    num_nodes: int
    num_elements: int
    modes: List[ModeShapeResult]
    operating_frequencies_hz: List[float] = field(default_factory=list)
    resonance_warnings: List[str] = field(default_factory=list)
    is_resonance_free: bool = True

    @property
    def fundamental_frequency_hz(self) -> float:
        return self.modes[0].frequency_hz if self.modes else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "num_nodes": self.num_nodes,
            "num_elements": self.num_elements,
            "fundamental_frequency_hz": round(self.fundamental_frequency_hz, 2),
            "modes": [
                {
                    "mode": m.mode_number,
                    "frequency_hz": round(m.frequency_hz, 2),
                    "angular_freq_rad_s": round(m.angular_frequency_rad_s, 2),
                }
                for m in self.modes
            ],
            "operating_frequencies_hz": self.operating_frequencies_hz,
            "resonance_warnings": self.resonance_warnings,
            "is_resonance_free": self.is_resonance_free,
        }


def calc_cantilever_beam_natural_frequencies(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    material: Union[str, Material] = "S235JR",
    num_modes: int = 3,
) -> List[float]:
    """
    Exact analytical Euler-Bernoulli natural frequencies for a cantilever beam (fixed-free).
      omega_n = (beta_n * L)^2 * sqrt( E * I / (rho * A * L^4) )
      f_n = omega_n / (2 * pi)
    Roots: (beta_1 * L) ≈ 1.875104, (beta_2 * L) ≈ 4.694091, (beta_3 * L) ≈ 7.854757
    """
    mat = get_material(material) if isinstance(material, str) else material
    l_m = length_mm * 1e-3
    b_m = width_mm * 1e-3
    h_m = height_mm * 1e-3

    area_m2 = b_m * h_m
    # Moment of inertia about bending axis (bending in height direction)
    i_m4 = (b_m * (h_m ** 3)) / 12.0
    e_pa = mat.youngs_modulus_mpa * 1e6
    rho_kg_m3 = mat.density_kg_m3

    beta_l_roots = [1.875104, 4.694091, 7.854757, 10.99554, 14.13717]
    freqs = []
    for i in range(min(num_modes, len(beta_l_roots))):
        bl = beta_l_roots[i]
        omega = (bl ** 2) * math.sqrt((e_pa * i_m4) / (rho_kg_m3 * area_m2 * (l_m ** 4)))
        f_hz = omega / (2.0 * math.pi)
        freqs.append(f_hz)
    return freqs


def assemble_lumped_mass_matrix(
    nodes: np.ndarray,
    elements: np.ndarray,
    density_kg_m3: float,
) -> sp.dia_matrix:
    """
    Build diagonal lumped mass matrix for 4-node linear tetrahedral mesh.
    For each tetrahedron with volume V, mass = rho * V, equally distributed (1/4) to its 4 vertices.
    """
    num_nodes = len(nodes)
    nodal_masses = np.zeros(num_nodes, dtype=np.float64)

    # Element volume vectorized calculation
    # V = 1/6 * |det(v1-v4, v2-v4, v3-v4)|
    v1 = nodes[elements[:, 0]] * 1e-3  # convert mm to m
    v2 = nodes[elements[:, 1]] * 1e-3
    v3 = nodes[elements[:, 2]] * 1e-3
    v4 = nodes[elements[:, 3]] * 1e-3

    d1 = v1 - v4
    d2 = v2 - v4
    d3 = v3 - v4

    # Triple product (determinant)
    vol_elems = np.abs(np.einsum("ij,ij->i", d1, np.cross(d2, d3))) / 6.0
    elem_masses = vol_elems * density_kg_m3

    quarter_masses = elem_masses / 4.0
    for node_idx in range(4):
        np.add.at(nodal_masses, elements[:, node_idx], quarter_masses)

    # Expand to 3 DOFs per node (x, y, z translational DOFs)
    diag_m = np.repeat(nodal_masses, 3)
    # Avoid zero masses
    diag_m = np.maximum(diag_m, 1e-12)
    return sp.diags(diag_m, format="csc")


class ModalStudy:
    """
    Conducts modal extraction and resonance check for a 3D meshed solid.
    """

    def __init__(
        self,
        part_name: str,
        nodes: np.ndarray,
        elements: np.ndarray,
        material: Union[str, Material] = "S235JR",
        fixed_node_indices: Optional[Set[int]] = None,
    ):
        self.part_name = part_name
        self.nodes = np.asarray(nodes, dtype=np.float64)
        self.elements = np.asarray(elements, dtype=np.int32)
        self.material = get_material(material) if isinstance(material, str) else material
        self.fixed_nodes = set(fixed_node_indices or [])

    @classmethod
    def from_fea_study(cls, fea_study: Any) -> ModalStudy:
        """Create a ModalStudy directly from an existing FEAStudy instance."""
        if getattr(fea_study, "nodes", None) is None:
            fea_study.generate_mesh()
        return cls(
            part_name=fea_study.part_name,
            nodes=fea_study.nodes,
            elements=fea_study.elements,
            material=fea_study.material,
            fixed_node_indices=fea_study.fixed_nodes,
        )

    def solve(
        self,
        num_modes: int = 6,
        operating_rpm: Optional[List[float]] = None,
        resonance_tolerance: float = 0.15,  # ±15% band
    ) -> ModalAnalysisResult:
        """
        Solve [K]{phi} = omega^2 [M]{phi} for the lowest non-zero natural frequencies.
        """
        from ...analysis.solver import LinearElasticitySolver

        num_nodes = len(self.nodes)
        num_dofs = num_nodes * 3

        # 1. Assemble stiffness matrix K using existing LinearElasticitySolver
        fea_solver = LinearElasticitySolver(self.nodes, self.elements, self.material)
        K_global = fea_solver._assemble_stiffness_matrix()

        # 2. Assemble lumped mass matrix M
        M_global = assemble_lumped_mass_matrix(self.nodes, self.elements, self.material.density_kg_m3)

        # 3. Apply fixed Dirichlet boundary conditions (remove constrained DOFs)
        fixed_dofs = []
        for n_idx in self.fixed_nodes:
            fixed_dofs.extend([n_idx * 3, n_idx * 3 + 1, n_idx * 3 + 2])
        fixed_dofs_set = set(fixed_dofs)
        free_dofs = np.array([i for i in range(num_dofs) if i not in fixed_dofs_set], dtype=np.int32)

        if len(free_dofs) < num_modes:
            raise ValueError(f"Not enough unconstrained DOFs ({len(free_dofs)}) for {num_modes} modes.")

        K_free = K_global[free_dofs, :][:, free_dofs]
        M_free = M_global[free_dofs, :][:, free_dofs]

        # Convert K from N/mm to N/m for SI frequency consistency:
        # Since nodes are in mm, E in MPa (N/mm^2) -> K is in N/mm = 1e3 N/m
        K_free_si = K_free * 1000.0

        # Shift-invert spectral transformation around sigma = 0 to extract lowest modes
        # Solves: K * x = lambda * M * x
        eigenvalues, eigenvectors = spla.eigsh(
            A=K_free_si,
            k=num_modes,
            M=M_free,
            sigma=1.0,
            which="LM",
        )

        # Sort positive eigenvalues
        idx = np.argsort(np.real(eigenvalues))
        modes = []
        for i, m_idx in enumerate(idx):
            lam = float(np.real(eigenvalues[m_idx]))
            if lam < 0:
                lam = 0.0
            omega = math.sqrt(lam)
            f_hz = omega / (2.0 * math.pi)

            # Reconstruct full modal vector
            phi_free = np.real(eigenvectors[:, m_idx])
            phi_full = np.zeros((num_nodes, 3), dtype=np.float64)
            phi_flat = np.zeros(num_dofs, dtype=np.float64)
            phi_flat[free_dofs] = phi_free
            phi_full = phi_flat.reshape((num_nodes, 3))
            
            # Normalize mode shape
            max_amp = np.max(np.linalg.norm(phi_full, axis=1))
            if max_amp > 1e-12:
                phi_full /= max_amp

            modes.append(ModeShapeResult(
                mode_number=i + 1,
                frequency_hz=f_hz,
                angular_frequency_rad_s=omega,
                eigenvector=phi_full,
            ))

        # Check resonance with operating RPM (e.g. motor at 1500 RPM -> 25 Hz, 3000 RPM -> 50 Hz)
        op_freqs = []
        warnings = []
        is_safe = True
        if operating_rpm:
            for rpm in operating_rpm:
                f_op = rpm / 60.0
                op_freqs.append(f_op)
                for m in modes:
                    delta = abs(m.frequency_hz - f_op) / f_op if f_op > 0 else 1.0
                    if delta < resonance_tolerance:
                        is_safe = False
                        warnings.append(
                            f"RESONANCE RISK: Mode {m.mode_number} ({m.frequency_hz:.1f} Hz) is within "
                            f"{delta*100:.1f}% of operating frequency ({f_op:.1f} Hz from {rpm:.0f} RPM)."
                        )

        return ModalAnalysisResult(
            part_name=self.part_name,
            num_nodes=num_nodes,
            num_elements=len(self.elements),
            modes=modes,
            operating_frequencies_hz=op_freqs,
            resonance_warnings=warnings,
            is_resonance_free=is_safe,
        )
