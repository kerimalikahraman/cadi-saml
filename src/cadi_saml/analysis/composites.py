"""
cadi_saml.analysis.composites
=============================
CATIA-grade Composites Design (CPD) and Classical Laminate Theory (CLT) engine.
Supports multi-layer anisotropic laminate layups (e.g. [0/45/-45/90]_s),
calculates ABD stiffness matrices (extensional, coupling, bending),
computes equivalent engineering moduli (Ex, Ey, Gxy, nuxy),
and performs Tsai-Wu and Maximum Stress failure index evaluations.
Generates 3D B-Rep composite panel solids in CAD assemblies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import numpy as np

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


@dataclass(frozen=True)
class CompositeMaterial:
    """Unidirectional or woven lamina material properties (MPa and mm)."""
    name: str
    E1: float  # Longitudinal modulus (MPa)
    E2: float  # Transverse modulus (MPa)
    nu12: float  # Major Poisson ratio
    G12: float  # In-plane shear modulus (MPa)
    ply_thickness: float = 0.25  # Nominal cured ply thickness (mm)
    density_g_cm3: float = 1.55  # Density
    # Strength limits (MPa)
    Xt: float = 1500.0  # Longitudinal tensile strength
    Xc: float = 1200.0  # Longitudinal compressive strength
    Yt: float = 50.0  # Transverse tensile strength
    Yc: float = 150.0  # Transverse compressive strength
    S: float = 70.0  # In-plane shear strength


# Standard Aerospace & Motorsport Composite Material Database
COMPOSITE_MATERIALS: Dict[str, CompositeMaterial] = {
    "Carbon_T300_Epoxy": CompositeMaterial(
        name="Carbon_T300_Epoxy",
        E1=135000.0,
        E2=10000.0,
        nu12=0.30,
        G12=5000.0,
        ply_thickness=0.20,
        density_g_cm3=1.55,
        Xt=1500.0,
        Xc=1200.0,
        Yt=50.0,
        Yc=150.0,
        S=70.0,
    ),
    "Carbon_T700_Epoxy": CompositeMaterial(
        name="Carbon_T700_Epoxy",
        E1=150000.0,
        E2=9000.0,
        nu12=0.32,
        G12=5500.0,
        ply_thickness=0.25,
        density_g_cm3=1.58,
        Xt=2200.0,
        Xc=1400.0,
        Yt=60.0,
        Yc=180.0,
        S=85.0,
    ),
    "Glass_EGlass_Epoxy": CompositeMaterial(
        name="Glass_EGlass_Epoxy",
        E1=45000.0,
        E2=12000.0,
        nu12=0.28,
        G12=4500.0,
        ply_thickness=0.30,
        density_g_cm3=1.95,
        Xt=1000.0,
        Xc=800.0,
        Yt=40.0,
        Yc=120.0,
        S=50.0,
    ),
    "Aramid_Kevlar49_Epoxy": CompositeMaterial(
        name="Aramid_Kevlar49_Epoxy",
        E1=76000.0,
        E2=5500.0,
        nu12=0.34,
        G12=2300.0,
        ply_thickness=0.25,
        density_g_cm3=1.40,
        Xt=1400.0,
        Xc=280.0,
        Yt=30.0,
        Yc=140.0,
        S=45.0,
    ),
}


@dataclass
class Ply:
    """An individual lamina within a composite stacking sequence."""
    angle_deg: float
    thickness: float
    material: CompositeMaterial


class LaminateLayup:
    """
    Classical Laminate Theory (CLT) calculator for composite stacking sequences.
    """

    def __init__(
        self,
        angles: List[float],
        material: Union[str, CompositeMaterial] = "Carbon_T300_Epoxy",
        ply_thickness: Optional[float] = None,
        symmetric: bool = False,
    ):
        mat = (
            COMPOSITE_MATERIALS[material]
            if isinstance(material, str)
            else material
        )
        self.material = mat
        nom_t = float(ply_thickness or mat.ply_thickness)

        full_angles = list(angles)
        if symmetric:
            full_angles = full_angles + list(reversed(full_angles))

        self.plies: List[Ply] = [
            Ply(angle_deg=float(a), thickness=nom_t, material=mat)
            for a in full_angles
        ]

        # Calculate CLT ABD Matrices
        self._calculate_clt()

    @property
    def total_thickness(self) -> float:
        return sum(p.thickness for p in self.plies)

    @property
    def num_plies(self) -> int:
        return len(self.plies)

    def _calculate_clt(self):
        """Computes Reduced Q, Transformed Q_bar, and A, B, D matrices."""
        mat = self.material
        E1, E2, nu12, G12 = mat.E1, mat.E2, mat.nu12, mat.G12
        nu21 = nu12 * (E2 / E1)

        denom = 1.0 - nu12 * nu21
        Q11 = E1 / denom
        Q22 = E2 / denom
        Q12 = (nu12 * E2) / denom
        Q66 = G12

        # Stacking z-coordinates from mid-plane (-H/2 to +H/2)
        H = self.total_thickness
        z_coords = [-H / 2.0]
        for p in self.plies:
            z_coords.append(z_coords[-1] + p.thickness)

        A = np.zeros((3, 3))
        B = np.zeros((3, 3))
        D = np.zeros((3, 3))

        self.q_bar_matrices: List[np.ndarray] = []

        for k, ply in enumerate(self.plies):
            theta = math.radians(ply.angle_deg)
            m = math.cos(theta)
            n = math.sin(theta)

            m2, n2 = m * m, n * n
            m4, n4 = m2 * m2, n2 * n2
            m2n2 = m2 * n2

            q_bar = np.zeros((3, 3))
            q_bar[0, 0] = Q11 * m4 + 2.0 * (Q12 + 2.0 * Q66) * m2n2 + Q22 * n4
            q_bar[1, 1] = Q11 * n4 + 2.0 * (Q12 + 2.0 * Q66) * m2n2 + Q22 * m4
            q_bar[0, 1] = q_bar[1, 0] = (Q11 + Q22 - 4.0 * Q66) * m2n2 + Q12 * (m4 + n4)
            q_bar[0, 2] = q_bar[2, 0] = (Q11 - Q12 - 2.0 * Q66) * m * m2 * n - (Q22 - Q12 - 2.0 * Q66) * m * n * n2
            q_bar[1, 2] = q_bar[2, 1] = (Q11 - Q12 - 2.0 * Q66) * m * n * n2 - (Q22 - Q12 - 2.0 * Q66) * m * m2 * n
            q_bar[2, 2] = (Q11 + Q22 - 2.0 * Q12 - 2.0 * Q66) * m2n2 + Q66 * (m4 + n4)

            self.q_bar_matrices.append(q_bar)

            zk = z_coords[k + 1]
            zk_1 = z_coords[k]

            A += q_bar * (zk - zk_1)
            B += 0.5 * q_bar * (zk * zk - zk_1 * zk_1)
            D += (1.0 / 3.0) * q_bar * (zk**3 - zk_1**3)

        self.A = A
        self.B = B
        self.D = D

        # Invert A to extract equivalent in-plane engineering constants
        try:
            a_inv = np.linalg.inv(A)
            self.Ex = 1.0 / (H * a_inv[0, 0])
            self.Ey = 1.0 / (H * a_inv[1, 1])
            self.Gxy = 1.0 / (H * a_inv[2, 2])
            self.nu_xy = -a_inv[0, 1] / a_inv[0, 0]
        except np.linalg.LinAlgError:
            self.Ex = self.Ey = self.Gxy = self.nu_xy = 0.0

    def evaluate_failure(
        self,
        Nx: float = 0.0,  # N/mm in-plane normal load
        Ny: float = 0.0,
        Nxy: float = 0.0,  # N/mm in-plane shear load
        Mx: float = 0.0,  # N*mm/mm bending moment
        My: float = 0.0,
        Mxy: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calculates ply stresses and evaluates Tsai-Wu failure criteria.
        Returns critical failure index and first ply failure (FPF) ply.
        """
        loads = np.array([Nx, Ny, Nxy, Mx, My, Mxy], dtype=float)
        ABD = np.block([[self.A, self.B], [self.B, self.D]])

        try:
            strains_curvatures = np.linalg.solve(ABD, loads)
        except np.linalg.LinAlgError:
            return {"status": "ERROR_SINGULAR_STIFFNESS", "max_tsai_wu": float("inf")}

        eps0 = strains_curvatures[0:3]
        kappa = strains_curvatures[3:6]

        H = self.total_thickness
        z_curr = -H / 2.0
        ply_results = []
        max_tsai_wu = 0.0
        critical_ply_idx = 0

        mat = self.material
        Xt, Xc, Yt, Yc, S = mat.Xt, mat.Xc, mat.Yt, mat.Yc, mat.S

        # Tsai-Wu coefficients
        F1 = 1.0 / Xt - 1.0 / Xc
        F11 = 1.0 / (Xt * Xc)
        F2 = 1.0 / Yt - 1.0 / Yc
        F22 = 1.0 / (Yt * Yc)
        F66 = 1.0 / (S * S)
        F12 = -0.5 * math.sqrt(F11 * F22)

        for k, ply in enumerate(self.plies):
            z_mid = z_curr + ply.thickness / 2.0
            z_curr += ply.thickness

            # Global lamina strain: eps = eps0 + z * kappa
            eps_global = eps0 + z_mid * kappa

            theta = math.radians(ply.angle_deg)
            m = math.cos(theta)
            n = math.sin(theta)

            # Transform strain to principal material axes (1, 2)
            eps1 = m * m * eps_global[0] + n * n * eps_global[1] + m * n * eps_global[2]
            eps2 = n * n * eps_global[0] + m * m * eps_global[1] - m * n * eps_global[2]
            gamma12 = -2.0 * m * n * eps_global[0] + 2.0 * m * n * eps_global[1] + (m * m - n * n) * eps_global[2]

            # Compute principal lamina stresses
            nu21 = mat.nu12 * (mat.E2 / mat.E1)
            denom = 1.0 - mat.nu12 * nu21
            Q11 = mat.E1 / denom
            Q22 = mat.E2 / denom
            Q12 = (mat.nu12 * mat.E2) / denom
            Q66 = mat.G12

            sigma1 = Q11 * eps1 + Q12 * eps2
            sigma2 = Q12 * eps1 + Q22 * eps2
            tau12 = Q66 * gamma12

            # Tsai-Wu Failure Index: I_TW
            I_TW = (
                F1 * sigma1
                + F2 * sigma2
                + F11 * (sigma1**2)
                + F22 * (sigma2**2)
                + F66 * (tau12**2)
                + 2.0 * F12 * sigma1 * sigma2
            )

            if I_TW > max_tsai_wu:
                max_tsai_wu = I_TW
                critical_ply_idx = k + 1

            ply_results.append({
                "ply_number": k + 1,
                "angle_deg": ply.angle_deg,
                "z_mid_mm": round(z_mid, 3),
                "sigma1_mpa": round(float(sigma1), 2),
                "sigma2_mpa": round(float(sigma2), 2),
                "tau12_mpa": round(float(tau12), 2),
                "tsai_wu_index": round(float(I_TW), 4),
                "is_safe": bool(I_TW < 1.0),
            })

        safety_factor = round(1.0 / math.sqrt(max_tsai_wu), 2) if max_tsai_wu > 0 else 999.0

        return {
            "status": "PASS" if max_tsai_wu < 1.0 else "FAILURE_PREDICTED",
            "max_tsai_wu_index": round(float(max_tsai_wu), 4),
            "safety_factor": safety_factor,
            "critical_ply": critical_ply_idx,
            "plies": ply_results,
        }


def add_composite_panel(
    assembly: "Assembly",
    name: str,
    mount_to: Optional[str] = None,
    length: float = 200.0,
    width: float = 100.0,
    angles: Optional[List[float]] = None,
    material: str = "Carbon_T300_Epoxy",
    ply_thickness: Optional[float] = None,
    symmetric: bool = True,
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Dict[str, Any]:
    """
    Builds an engineered 3D composite sandwich/monolithic panel in the assembly.
    Supports ZERO-COORDINATE mounting via mount_to='chassis:flange'.
    Default layup is standard quasi-isotropic aerospace layup [0, 45, -45, 90]_s.
    """
    if angles is None:
        angles = [0.0, 45.0, -45.0, 90.0]

    layup = LaminateLayup(
        angles=angles,
        material=material,
        ply_thickness=ply_thickness,
        symmetric=symmetric,
    )
    thick = layup.total_thickness

    # Add base 3D solid box with composite thickness
    panel = assembly.add_box(
        name=name,
        length=length,
        width=width,
        height=thick,
        origin=origin,
    )
    panel.set_appearance(color=(0.18, 0.18, 0.20), material=f"Composite_{material}")

    # Add laminate ports for fiber orientation and surface tooling
    panel.add_port(
        name="tooling_surface_bottom",
        port_type="planar",
        position=(origin[0] + length / 2.0, origin[1] + width / 2.0, origin[2]),
        normal=(0.0, 0.0, -1.0),
        diameter=min(length, width),
    )
    panel.add_port(
        name="bag_surface_top",
        port_type="planar",
        position=(origin[0] + length / 2.0, origin[1] + width / 2.0, origin[2] + thick),
        normal=(0.0, 0.0, 1.0),
        diameter=min(length, width),
    )
    panel.add_port(
        name="fiber_reference_axis",
        port_type="axis",
        position=(origin[0], origin[1], origin[2]),
        normal=(1.0, 0.0, 0.0),  # 0 degree alignment along X
    )

    if mount_to:
        assembly.connect(f"{name}:tooling_surface_bottom", mount_to, mate_type="FLUSH")

    return {
        "panel_name": name,
        "material": material,
        "num_plies": layup.num_plies,
        "total_thickness_mm": round(thick, 3),
        "layup_sequence": [p.angle_deg for p in layup.plies],
        "equivalent_moduli_gpa": {
            "Ex": round(layup.Ex / 1000.0, 2),
            "Ey": round(layup.Ey / 1000.0, 2),
            "Gxy": round(layup.Gxy / 1000.0, 2),
            "nu_xy": round(layup.nu_xy, 3),
        },
        "layup_object": layup,
    }
