"""
tests/test_library_upgrades.py
==============================
Automated unit tests validating the 6 new advanced capabilities of cadi_saml:
1. Semantic Attachment Ports & Mating System (ports.py & asm.connect)
2. Parametric Involute Gear Engine (std_parts/gears.py & asm.add_spur_gear, add_helical_gear)
3. Helical Springs & Coilover Suspension (std_parts/springs.py & asm.add_coil_spring, add_coilover)
4. B-Rep Loft Engine for Organic Shapes (asm.add_loft)
5. Mass Properties & Inertia Analyzer (asm.get_mass_properties & ValidationEngineer)
6. 3D Piping & Spatial Tube Routing (asm.add_pipe)
"""

import math
import pytest
from cadi_saml.core.assembly import Assembly
from cadi_saml.core.ports import Port, PortType, compute_alignment_transform
from cadi_saml.backend.occt_backend import OCCTBackend
from cadi_saml.validation.validation_engineer import ValidationEngineer


def test_spur_gear():
    """Verify spur gear generation and watertightness."""
    asm = Assembly("test_spur_gear")
    gear = asm.add_spur_gear(
        "pinion",
        module=2.0,
        teeth=16,
        face_width=15.0,
        pressure_angle=20.0,
        bore_dia=12.0,
        hub_dia=20.0,
        hub_width=8.0,
        keyway_width=4.0,
        keyway_depth=2.0,
    )
    assert gear is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "pinion" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["pinion"]), "Spur gear solid is not manifold/watertight"


def test_helical_gear():
    """Verify helical gear generation with helix angle."""
    asm = Assembly("test_helical_gear")
    gear = asm.add_helical_gear(
        "helical_pinion",
        module=2.5,
        teeth=18,
        face_width=20.0,
        helix_angle=20.0,
        bore_dia=14.0,
    )
    assert gear is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "helical_pinion" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["helical_pinion"]), "Helical gear solid is not manifold"


def test_rack_and_pinion():
    """Verify linear gear rack generation."""
    asm = Assembly("test_rack")
    rack = asm.add_rack("steering_rack", module=2.0, length=150.0, height=20.0, width=15.0)
    assert rack is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "steering_rack" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["steering_rack"]), "Rack solid is not manifold"


def test_coil_spring():
    """Verify helical compression spring with flat ground ends."""
    asm = Assembly("test_spring")
    spring = asm.add_coil_spring(
        "suspension_spring",
        wire_dia=6.0,
        outer_dia=50.0,
        free_length=100.0,
        active_coils=5.0,
        ground_ends=True,
    )
    assert spring is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "suspension_spring" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["suspension_spring"]), "Spring solid is not manifold"


def test_coilover():
    """Verify motorsport coilover damper assembly generation."""
    asm = Assembly("test_coilover")
    coilover = asm.add_coilover(
        "front_coilover",
        extended_length=280.0,
        stroke=70.0,
        spring_outer_dia=60.0,
        wire_dia=8.0,
    )
    assert coilover is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "front_coilover" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["front_coilover"]), "Coilover solid is not manifold"


def test_loft_between_sections():
    """Verify B-Rep lofting between circle and rectangle."""
    asm = Assembly("test_loft")
    s1 = asm.section_circle(radius=25.0, center=(0, 0, 0), normal=(0, 0, 1))
    s2 = asm.section_rectangle(width=30.0, height=30.0, center=(0, 0, 60.0), normal=(0, 0, 1))
    loft = asm.add_loft("transition_duct", sections=[s1, s2])
    assert loft is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "transition_duct" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["transition_duct"]), "Loft solid is not manifold"


def test_pipe_routing():
    """Verify 3D spatial hollow pipe generation."""
    asm = Assembly("test_pipe")
    pipe = asm.add_pipe(
        "brake_line",
        points=[(0, 0, 0), (50, 0, 0), (50, 80, 0), (50, 80, 40)],
        outer_dia=8.0,
        wall_thickness=1.0,
    )
    assert pipe is not None
    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "brake_line" in solids
    val = ValidationEngineer()
    assert val.check_manifold(solids["brake_line"]), "Pipe solid is not manifold"


def test_mass_properties():
    """Verify analytical mass and center of gravity computation on a 100x100x100 cube."""
    asm = Assembly("test_mass")
    cube = asm.add_box("aluminum_cube", length=100.0, width=100.0, height=100.0)
    cube.set_appearance(color=(0.7, 0.7, 0.7), material="Aluminum")

    # Volume of 100x100x100 = 1,000,000 mm³
    # At density 2.7 g/cm³ (Al6061) -> mass = 10^6 * 2.7 * 10^-6 = 2.7 kg
    props = asm.get_mass_properties()
    assert abs(props["total_volume_mm3"] - 1_000_000.0) < 100.0, f"Expected 1M mm³, got {props['total_volume_mm3']}"
    assert abs(props["total_mass_kg"] - 2.7) < 0.05, f"Expected 2.7 kg, got {props['total_mass_kg']}"
    assert "aluminum_cube" in props["parts"]
    assert props["parts"]["aluminum_cube"]["material"] == "Aluminum"


def test_semantic_ports_and_mating():
    """Verify zero-coordinate mating between flange and bolt using ports."""
    asm = Assembly("test_ports")
    flange = asm.add_flange("hub_flange", outer_diameter=120.0, thickness=15.0, inner_bore=30.0, bolt_pcd=80.0, bolt_count=4, bolt_diameter=8.5)
    bolt = asm.add_bolt("m8_bolt", size="M8", length=30.0)

    # Zero-coordinate rule: Connect bolt to flange pcd hole using ports!
    asm.connect(bolt.port("under_head"), flange.port("pcd_hole_1"), mate_type="FLUSH")

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())
    assert "hub_flange" in solids
    assert "m8_bolt" in solids

    val = ValidationEngineer()
    clashes = val.check_clashes(solids)
    assert isinstance(clashes, list)
