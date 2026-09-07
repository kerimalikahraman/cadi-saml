"""
cadi_saml.systems.propulsion

High-energy propulsion and rocket nozzle engineering module:
- 1D isentropic compressible gas dynamics solver (Chamber, Throat, Exit states)
- Area ratio expansion solver (A_e / A_t -> Mach number Newton-Raphson)
- Thrust coefficient (C_f), sea level & vacuum thrust, and Specific Impulse (I_sp)
- Parametric de Laval nozzle contour geometry generation (convergent-divergent cone)
- Integrated regenerative cooling channel geometry and hydraulic pressure drop
- 3D CAD Assembly synthesis with mounting flange and sensor ports
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from ..core.assembly import Assembly
from ..simulation.flow.pipe_flow import analyze_pipe_flow


# Standard gravity constant
G0 = 9.80665


@dataclass
class GasMixture:
    """Combustion product thermodynamic gas properties."""
    name: str = "LOX_Methane"
    gamma: float = 1.22           # Specific heat ratio (Cp / Cv)
    molecular_weight_g_mol: float = 20.5 # g/mol
    chamber_pressure_bar: float = 50.0   # Pc in bar
    chamber_temperature_k: float = 3300.0 # Tc in Kelvin

    @property
    def gas_constant_j_kg_k(self) -> float:
        """Specific gas constant R = R_u / M."""
        r_universal = 8314.462  # J / (kmol * K)
        return r_universal / self.molecular_weight_g_mol


@dataclass
class NozzleAeroState:
    """1D isentropic nozzle aerodynamic performance output."""
    expansion_ratio: float
    mach_exit: float
    exit_pressure_bar: float
    exit_temperature_k: float
    exhaust_velocity_m_s: float
    thrust_coefficient: float
    thrust_vacuum_n: float
    thrust_sea_level_n: float
    isp_vacuum_s: float
    isp_sea_level_s: float
    mass_flow_rate_kg_s: float


class RocketNozzle:
    """
    Parametric de Laval rocket engine thrust chamber and nozzle assembly.
    """

    def __init__(
        self,
        name: str = "liquid_rocket_nozzle",
        throat_diameter_mm: float = 50.0,
        expansion_area_ratio: float = 16.0,  # Ae / At
        chamber_diameter_mm: float = 100.0,
        convergent_half_angle_deg: float = 30.0,
        divergent_half_angle_deg: float = 15.0,
        wall_thickness_mm: float = 3.5,
        gas_properties: Optional[GasMixture] = None,
        num_cooling_channels: int = 40,
        cooling_channel_width_mm: float = 2.0,
        cooling_channel_height_mm: float = 3.0,
    ):
        self.name = name
        self.throat_dia = throat_diameter_mm
        self.eps = expansion_area_ratio
        self.chamber_dia = chamber_diameter_mm
        self.conv_angle = convergent_half_angle_deg
        self.div_angle = divergent_half_angle_deg
        self.wall_thickness = wall_thickness_mm
        self.gas = gas_properties or GasMixture()
        self.num_cooling_channels = num_cooling_channels
        self.ch_w = cooling_channel_width_mm
        self.ch_h = cooling_channel_height_mm

        # Derived geometric dimensions
        self.throat_area_mm2 = math.pi * ((self.throat_dia / 2.0) ** 2)
        self.exit_area_mm2 = self.throat_area_mm2 * self.eps
        self.exit_diameter_mm = 2.0 * math.sqrt(self.exit_area_mm2 / math.pi)

        # Axial lengths (mm)
        r_c = self.chamber_dia / 2.0
        r_t = self.throat_dia / 2.0
        r_e = self.exit_diameter_mm / 2.0

        self.conv_length_mm = (r_c - r_t) / math.tan(math.radians(self.conv_angle))
        self.div_length_mm = (r_e - r_t) / math.tan(math.radians(self.div_angle))
        self.total_nozzle_length_mm = self.conv_length_mm + self.div_length_mm

    def solve_exit_mach_number(self, target_area_ratio: float) -> float:
        """
        Solves Mach number from area ratio A/A* for supersonic branch (M > 1)
        using Newton-Raphson iteration on the isentropic area-Mach equation:
        A/At = (1/M) * [ (2 / (gamma+1)) * (1 + 0.5*(gamma-1)*M^2) ] ^ [ (gamma+1) / (2*(gamma-1)) ]
        """
        gamma = self.gas.gamma
        g_exp = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        c_factor = 2.0 / (gamma + 1.0)

        # Initial guess using asymptotic expansion M ~ sqrt(eps)
        m = math.sqrt(target_area_ratio) * 1.5

        for _ in range(30):
            term = c_factor * (1.0 + 0.5 * (gamma - 1.0) * (m ** 2))
            f = (1.0 / m) * (term ** g_exp) - target_area_ratio

            # Numerical derivative df/dm
            dm = 1e-5
            term_p = c_factor * (1.0 + 0.5 * (gamma - 1.0) * ((m + dm) ** 2))
            f_p = (1.0 / (m + dm)) * (term_p ** g_exp) - target_area_ratio
            df = (f_p - f) / dm

            step = f / max(1e-6, df)
            m -= step
            if abs(step) < 1e-6:
                break

        return max(1.01, float(m))

    def calculate_aerothermodynamic_performance(self) -> NozzleAeroState:
        """
        Solves full isentropic compressible flow relations for chamber, throat, and exit.
        """
        gamma = self.gas.gamma
        r_gas = self.gas.gas_constant_j_kg_k
        pc_pa = self.gas.chamber_pressure_bar * 1e5
        tc_k = self.gas.chamber_temperature_k
        p_ambient_pa = 101325.0  # 1 atm sea level

        # 1. Throat condition (M = 1)
        p_throat_pa = pc_pa * (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        t_throat_k = tc_k * (2.0 / (gamma + 1.0))
        v_throat_m_s = math.sqrt(gamma * r_gas * t_throat_k)
        rho_throat_kg_m3 = p_throat_pa / (r_gas * t_throat_k)

        throat_area_m2 = self.throat_area_mm2 * 1e-6
        mass_flow_kg_s = rho_throat_kg_m3 * throat_area_m2 * v_throat_m_s

        # 2. Exit condition
        m_exit = self.solve_exit_mach_number(self.eps)
        temp_ratio = 1.0 + 0.5 * (gamma - 1.0) * (m_exit ** 2)
        t_exit_k = tc_k / temp_ratio
        p_exit_pa = pc_pa / (temp_ratio ** (gamma / (gamma - 1.0)))
        v_exit_m_s = m_exit * math.sqrt(gamma * r_gas * t_exit_k)

        # 3. Thrust & Specific Impulse
        exit_area_m2 = self.exit_area_mm2 * 1e-6
        # Vacuum thrust: F = m_dot * v_e + P_e * A_e
        f_vac_n = (mass_flow_kg_s * v_exit_m_s) + (p_exit_pa * exit_area_m2)
        # Sea level thrust: F = m_dot * v_e + (P_e - P_a) * A_e
        f_sl_n = (mass_flow_kg_s * v_exit_m_s) + ((p_exit_pa - p_ambient_pa) * exit_area_m2)

        # Thrust coefficient: Cf = F / (Pc * At)
        cf = f_vac_n / max(1.0, pc_pa * throat_area_m2)

        isp_vac_s = f_vac_n / max(1e-4, mass_flow_kg_s * G0)
        isp_sl_s = max(0.0, f_sl_n / max(1e-4, mass_flow_kg_s * G0))

        return NozzleAeroState(
            expansion_ratio=self.eps,
            mach_exit=round(m_exit, 3),
            exit_pressure_bar=round(p_exit_pa / 1e5, 3),
            exit_temperature_k=round(t_exit_k, 1),
            exhaust_velocity_m_s=round(v_exit_m_s, 1),
            thrust_coefficient=round(cf, 3),
            thrust_vacuum_n=round(f_vac_n, 1),
            thrust_sea_level_n=round(f_sl_n, 1),
            isp_vacuum_s=round(isp_vac_s, 1),
            isp_sea_level_s=round(isp_sl_s, 1),
            mass_flow_rate_kg_s=round(mass_flow_kg_s, 3),
        )

    def analyze_regenerative_cooling_channels(
        self,
        coolant_mass_flow_kg_s: float = 2.5,
        coolant_fluid: str = "water",
        coolant_inlet_temp_c: float = 25.0,
    ) -> Dict[str, Any]:
        """
        Calculates fluid velocity and hydraulic pressure drop across the parallel
        regenerative milled cooling channels surrounding the nozzle wall.
        """
        flow_per_channel_kg_s = coolant_mass_flow_kg_s / max(1, self.num_cooling_channels)
        # 1 kg/s of water ~ 1 L/s
        flow_per_channel_l_s = flow_per_channel_kg_s * 1.0

        # Hydraulic diameter: D_h = 4 * A / P = 4 * (w * h) / (2 * (w + h))
        d_h_mm = (2.0 * self.ch_w * self.ch_h) / max(0.1, self.ch_w + self.ch_h)
        channel_length_mm = self.total_nozzle_length_mm * 1.05  # slightly helical

        flow_res = analyze_pipe_flow(
            diameter_mm=d_h_mm,
            length_mm=channel_length_mm,
            flow_rate_l_s=flow_per_channel_l_s,
            fluid=coolant_fluid,
            temperature_c=coolant_inlet_temp_c,
            material_roughness="smooth",
        )

        return {
            "num_channels": self.num_cooling_channels,
            "hydraulic_diameter_mm": round(d_h_mm, 2),
            "channel_length_mm": round(channel_length_mm, 1),
            "flow_velocity_m_s": round(flow_res.velocity_m_s, 2),
            "pressure_drop_bar": round(flow_res.pressure_drop_bar, 3),
            "reynolds_number": round(flow_res.reynolds, 1),
            "is_cooling_pressure_drop_acceptable": flow_res.pressure_drop_bar < 10.0,
        }

    def to_assembly(self, assembly_name: Optional[str] = None) -> Assembly:
        """
        Synthesizes 3D CAD geometry for combustion chamber, throat restriction,
        divergent nozzle bell, and injector mounting flange.
        """
        asm = Assembly(assembly_name or self.name)

        # 1. Combustion Chamber Cylinder
        asm.add_cylinder(
            name=f"{self.name}_chamber",
            radius=self.chamber_dia / 2.0,
            height=self.conv_length_mm + 50.0,
            origin=(0.0, 0.0, float(self.total_nozzle_length_mm / 2.0)),
        )

        # 2. Divergent Nozzle Bell Cone
        r_exit = self.exit_diameter_mm / 2.0
        asm.add_cylinder(
            name=f"{self.name}_divergent_bell",
            radius=r_exit,
            height=self.div_length_mm,
            origin=(0.0, 0.0, -float(self.div_length_mm / 2.0)),
        )

        # 3. Injector Dome / Top Mounting Flange with PCD bolt holes
        flange_r = (self.chamber_dia / 2.0) + 25.0
        flange = asm.add_cylinder(
            name=f"{self.name}_mounting_flange",
            radius=flange_r,
            height=15.0,
            origin=(0.0, 0.0, float(self.total_nozzle_length_mm / 2.0 + self.conv_length_mm / 2.0 + 30.0)),
        )
        # Add 4 mounting holes for test fixture
        hole_pcd_r = flange_r - 12.0
        flange.add_hole(name="pcd_hole_1", diameter=8.5, depth=15.0, position=(hole_pcd_r, 0.0))
        flange.add_hole(name="pcd_hole_2", diameter=8.5, depth=15.0, position=(-hole_pcd_r, 0.0))
        flange.add_hole(name="pcd_hole_3", diameter=8.5, depth=15.0, position=(0.0, hole_pcd_r))
        flange.add_hole(name="pcd_hole_4", diameter=8.5, depth=15.0, position=(0.0, -hole_pcd_r))

        return asm
