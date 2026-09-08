from src.cadi_saml.simulation.flow import (
    resolve_fluid, analyze_compressible_pipe_flow,
    analyze_two_phase_flow, analyze_open_channel_flow,
    PipeNetwork
)
from src.cadi_saml.simulation.thermal import (
    analyze_pipe_heat_transfer, analyze_heat_exchanger_lmtd,
    analyze_thermal_stress, analyze_pipe_thermal_expansion
)
from src.cadi_saml.analysis.materials import get_material
from src.cadi_saml.simulation.structural.fatigue import (
    analyze_fatigue_life, analyze_miner_cumulative_damage,
    analyze_multiaxial_fatigue, MinerLoadBlock
)

# --- Test 1: Glycol su soğutma ---
eg = resolve_fluid('ethylene_glycol', 60.0, concentration_pct=50)
print(f'EG50 at 60C: rho={eg.density:.1f} mu={eg.dynamic_viscosity*1e3:.2f}mPas')

# --- Test 2: Seawater ---
sw = resolve_fluid('seawater', 20.0, salinity_ppt=35.0)
print(f'Seawater: rho={sw.density:.2f} mu={sw.dynamic_viscosity*1e3:.3f}mPas Pr={sw.prandtl_number:.2f}')

# --- Test 3: R134a ---
r134a = resolve_fluid('r134a', -10.0)
print(f'R134a -10C: rho={r134a.density:.1f} psat={r134a.vapor_pressure/1e5:.2f}bar')

# --- Test 4: Compressible flow ---
r = analyze_compressible_pipe_flow(
    inlet_pressure_bar=5.0, inlet_temperature_c=20.0,
    diameter_mm=50, length_mm=5000, inlet_mach=0.15,
    n_profile_points=5
)
print(f'Fanno: Ma_in={r.mach_inlet} Ma_out={r.mach_outlet} choked={r.is_choked}')

# --- Test 5: Two-phase ---
tp = analyze_two_phase_flow(
    diameter_mm=80, length_mm=10000,
    mass_flow_rate_kg_s=0.5, quality_x=0.1, temperature_c=100.0
)
print(f'2-phase: regime={tp.flow_regime} dp={tp.dp_total_bar:.4f} bar')

# --- Test 6: Open channel ---
oc = analyze_open_channel_flow(
    flow_rate_m3_s=0.5, slope=0.001, manning_n='concrete_smooth',
    section_type='rectangular', width_m=2.0
)
print(f'Open channel: y_n={oc.normal_depth_m:.3f}m Fr={oc.froude_number:.3f} {oc.flow_regime}')

# --- Test 7: Pipe network ---
net = PipeNetwork()
net.add_pipe('P1','A','B', diameter_mm=100, length_mm=300000)
net.add_pipe('P2','B','C', diameter_mm=80, length_mm=200000)
net.add_pipe('P3','C','A', diameter_mm=80, length_mm=250000)
net.set_node_head('A', 50.0)
sol = net.solve()
print(f'Network: converged={sol.converged} iters={sol.iterations}')

# --- Test 8: Heat transfer ---
ht = analyze_pipe_heat_transfer(
    pipe_diameter_mm=50, pipe_length_mm=3000,
    flow_rate_l_s=1.0, fluid_name='water', fluid_temperature_c=20.0,
    wall_temperature_c=80.0
)
print(f'HT: Nu={ht.nusselt:.1f} h={ht.h_convection_w_m2_k:.1f} W/m2K Q={ht.total_heat_transfer_w:.1f}W')

# --- Test 9: LMTD HX ---
hx = analyze_heat_exchanger_lmtd(
    u_overall_w_m2_k=500, area_m2=2.0,
    t_hot_in_c=90.0, t_cold_in_c=20.0,
    mass_flow_hot_kg_s=0.5, mass_flow_cold_kg_s=0.8,
    hx_type='counter_flow'
)
print(f'HX LMTD: Q={hx.q_transferred_w/1e3:.2f}kW effectiveness={hx.effectiveness:.3f}')

# --- Test 10: Thermal stress ---
ts = analyze_thermal_stress('stainless_316l', 20.0, 150.0)
print(f'Thermal stress: sigma={ts.sigma_constrained_mpa:.1f} MPa status={ts.status}')

# --- Test 11: Pipe expansion ---
pe = analyze_pipe_thermal_expansion(
    'carbon_steel', length_mm=10000, outer_diameter_mm=114.3,
    wall_thickness_mm=6.0, t_installation_c=20.0, t_operating_c=120.0,
    end_condition='fixed'
)
print(f'Pipe expansion: dL={pe.delta_length_mm:.2f}mm axial_force={pe.axial_force_n/1e3:.1f}kN')

# --- Test 12: New materials ---
m = get_material('inconel')
print(f'Material: {m.name} Sy={m.yield_strength_mpa} MPa')
cfrp = get_material('cfrp')
print(f'Material: {cfrp.name} E={cfrp.youngs_modulus_mpa/1e3:.0f}GPa rho={cfrp.density_kg_m3}kg/m3')
dmls = get_material('dmls_316')
print(f'Material: {dmls.name} Sy={dmls.yield_strength_mpa} MPa')

# --- Test 13: Multiaxial fatigue ---
mat = get_material('42CrMo4')
mf = analyze_multiaxial_fatigue('shaft', mat, 400, -100, 0, 0, 100, -100)
print(f'Multiaxial fatigue: SF={mf.goodman_safety_factor:.2f} status={mf.status}')

# --- Test 14: Miner ---
blocks = [MinerLoadBlock(300, -100, 50000), MinerLoadBlock(250, -50, 200000)]
mr = analyze_miner_cumulative_damage('axle', mat, blocks)
print(f'Miner: D={mr.total_damage_D:.4f} status={mr.status}')

print()
print('TUM TESTLER GECTI')
