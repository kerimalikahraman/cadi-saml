"""
Comprehensive tests for Universal Aesthetic & Organic CAD Modeling:
- Ergonomic Computer Mouse Body (Multi-section C2 Loft + Shelling)
- Aerodynamic Car Bumper / Wing Spoiler (Spline Sweep / Loft)
- High-Performance Sport Wheel Rim (Revolve Rim + Aerodynamic Spoke + 10x Polar Pattern)
"""

import os
import sys
import math
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
)


def test_ergonomic_mouse():
    """
    Test 1: Ergonomic Computer Mouse Body
    Uses 3 elliptical cross-sections with smooth C2 lofting,
    then hollows it out via Shelling with 2mm wall thickness.
    """
    asm = Assembly(name="ErgonomicMouse")

    # 3 planar sections along Z:
    # 1. Nose / Front: small rounded ellipse (Z=0, rx=20, ry=12)
    s_front = asm.section_ellipse(rx=20.0, ry=12.0, center=(0.0, -35.0, 0.0))
    # 2. Palm rest (crest): wider, taller ellipse (Z=16, rx=32, ry=20)
    s_mid = asm.section_ellipse(rx=32.0, ry=20.0, center=(0.0, 0.0, 16.0))
    # 3. Rear heel: smooth slope back to base (Z=4, rx=28, ry=15)
    s_rear = asm.section_ellipse(rx=28.0, ry=15.0, center=(0.0, 35.0, 4.0))

    mouse = asm.add_loft("mouse_shell", sections=[s_front, s_mid, s_rear], ruled=False)
    mouse.shell(thickness=2.0, open_face="bottom")

    backend = OCCTBackend()
    out_dir = str(Path(__file__).parent.parent / "output")
    os.makedirs(out_dir, exist_ok=True)

    out_step = os.path.join(out_dir, "ergonomic_mouse.step")
    out_stl = os.path.join(out_dir, "ergonomic_mouse.stl")
    backend.export_step(asm.to_ir(), out_step)
    backend.export_stl(asm.to_ir(), out_stl)

    assert os.path.exists(out_step)
    assert os.path.getsize(out_step) > 2000
    print("  -> Ergonomic Mouse STEP & STL created in library/output:", out_step)


def test_aerodynamic_wing():
    """
    Test 2: Aerodynamic High-Performance GT Wing / Spoiler
    Uses mathematically exact NACA 2412 airfoil (C2-continuous NURBS B-Spline).
    Swept along curved 700mm wingspan trajectory with aerodynamic camber arch.
    Includes aerodynamic endplates on both wingtips.
    """
    asm = Assembly(name="AerodynamicWing")

    # Mathematically smooth C2-continuous NACA 2412 airfoil
    sec = asm.section_naca(code="2412", chord=180.0, points_count=40)

    # Curved spine path along vehicle width (Y from -350 to +350 with 35mm aerodynamic arch)
    path = [
        (0.0, -350.0, 0.0),
        (0.0, 0.0, 35.0),
        (0.0, 350.0, 0.0),
    ]

    asm.add_sweep("wing_blade", section=sec, path_points=path)

    # Aerodynamic Endplates precisely mounted on both wingtips (Left Y=-350, Right Y=+350)
    # 220mm long (X from -20 to 200), 8mm thick (Y), 110mm tall (Z from -55 to 55)
    left_plate = asm.add_box("left_endplate", length=220.0, width=8.0, height=110.0, origin=(90.0, -350.0, 0.0))
    left_plate.add_fillet(radius=3.0, edges="all")

    right_plate = asm.add_box("right_endplate", length=220.0, width=8.0, height=110.0, origin=(90.0, 350.0, 0.0))
    right_plate.add_fillet(radius=3.0, edges="all")

    backend = OCCTBackend()
    out_dir = str(Path(__file__).parent.parent / "output")
    out_step = os.path.join(out_dir, "aerodynamic_wing.step")
    out_stl = os.path.join(out_dir, "aerodynamic_wing.stl")
    backend.export_step(asm.to_ir(), out_step)
    backend.export_stl(asm.to_ir(), out_stl)

    assert os.path.exists(out_step)
    assert os.path.getsize(out_step) > 2000
    print("  -> Aerodynamic NACA Wing STEP & STL created in library/output:", out_step)


def test_oz_style_sport_wheel():
    """
    Test 3: High-Performance Sport Wheel (OZ Superturismo WRC / GT Style)
    - Revolved rim barrel (18 inch = R~230mm) with drop center lip
    - Center hub (R=52, 40mm thick) with center bore
    - 15 Slender, fine-spoke aerodynamically sculpted spokes (high spoke count)
    - Substantial Z-thickness (35-44mm) so they are physically rigid and never paper-thin
    - Deep concave slope (Z=+18mm at hub down to Z=-25mm at rim)
    - 15x Circular Pattern
    """
    asm = Assembly(name="OZ_SportWheel")

    # 1. Filleted Rim Barrel Profile: smooth transition radii at lips, bead seat, and drop center
    rim_points = [
        (218.0, -100.0),
        (238.0, -100.0),
        (242.0, -96.0),   # Front outer lip smooth radius
        (242.0, -88.0),
        (235.0, -85.0),   # Smooth radius into front bead seat
        (230.0, -80.0),
        (226.0, -30.0),
        (224.0, 0.0),     # Continuous drop center curve
        (226.0, 30.0),
        (230.0, 80.0),
        (235.0, 85.0),    # Smooth radius into rear bead seat
        (242.0, 88.0),
        (242.0, 96.0),    # Rear outer lip smooth radius
        (238.0, 100.0),
        (218.0, 100.0),
        (215.0, 90.0),
        (214.0, 0.0),     # Inner barrel wall
        (215.0, -90.0),
    ]
    asm.add_revolve("rim_barrel", profile_points=rim_points, angle=360.0)

    # 2. Center hub (R=52, thickness=42) with filleted top edge and 5x112 PCD lug holes
    hub = asm.add_cylinder("center_hub", radius=52.0, height=42.0)
    # Smooth 3mm radius on outer rim edge of center hub
    hub.add_fillet(radius=3.0, edges="all_top")
    # Center bore hole (dia 66.6mm -> r=33.3)
    hub.add_hole("center_bore", diameter=66.6, depth=42.0, position=(0.0, 0.0))

    # 5 Lug nut bolt holes (PCD 5x112: radius=56mm, dia=12mm at 72° intervals)
    for i in range(5):
        ang_rad = i * (2.0 * math.pi / 5.0)
        lx = 56.0 * math.cos(ang_rad)
        ly = 56.0 * math.sin(ang_rad)
        hub.add_hole(f"lug_hole_{i+1}", diameter=12.0, depth=25.0, position=(lx, ly), face="top")

    # 3. Ultra-Slender 10-Spoke Design (Fine, lightweight racing look with deep 3D concavity)
    # Extends along X (from hub R=52 to rim R=220).
    # Normal is (1.0, 0.0, 0.0) in YZ plane:
    #   rx = Z-depth/thickness (generous, 26-40mm, deep structural rigidity)
    #   ry = Y-width (ultra-slender 6-12mm, sleek fine-spoke look)
    #
    # Section 1: Flared root embedded into hub (Z-depth=40mm, Y-width=12mm, Z=18)
    s_root = asm.section_ellipse(rx=20.0, ry=6.0, center=(50.0, 0.0, 18.0), normal=(1.0, 0.0, 0.0))
    # Section 2: Slender neck (Z-depth=32mm, Y-width=8mm, Z=10)
    s_neck = asm.section_ellipse(rx=16.0, ry=4.0, center=(85.0, 0.0, 10.0), normal=(1.0, 0.0, 0.0))
    # Section 3: Fine mid blade with concave slope (Z-depth=26mm, Y-width=6mm, Z=-8)
    s_mid  = asm.section_ellipse(rx=13.0, ry=3.0, center=(150.0, 0.0, -8.0), normal=(1.0, 0.0, 0.0))
    # Section 4: Flared tip blending into rim drop center (Z-depth=34mm, Y-width=10mm, Z=-25)
    s_tip  = asm.section_ellipse(rx=17.0, ry=5.0, center=(220.0, 0.0, -25.0), normal=(1.0, 0.0, 0.0))

    spoke = asm.add_loft("spoke", sections=[s_root, s_neck, s_mid, s_tip], ruled=False)

    # 4. 10x Circular Pattern (10 Slender Spokes)
    asm.pattern_circular(target_part="spoke", count=10, center=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

    backend = OCCTBackend()
    solids = backend.compile(asm.to_ir())

    # Should contain rim_barrel, center_hub, spoke + 9 pattern instances = 12 parts
    assert len(solids) == 12
    assert "spoke_pattern_9" in solids

    out_dir = str(Path(__file__).parent.parent / "output")
    out_step = os.path.join(out_dir, "oz_sport_wheel.step")
    out_stl = os.path.join(out_dir, "oz_sport_wheel.stl")
    backend.export_step(asm.to_ir(), out_step)
    backend.export_stl(asm.to_ir(), out_stl)

    assert os.path.exists(out_step)
    assert os.path.getsize(out_step) > 20000
    print("  -> OZ Racing 10-Spoke Slender Wheel STEP & STL created in library/output:", out_step)


if __name__ == "__main__":
    print("=== Running cadi-saml Universal Aesthetic Modeling Tests ===")
    print("[1/3] Testing Ergonomic Mouse (Loft + Shelling)...")
    test_ergonomic_mouse()
    print("  -> Mouse OK")

    print("[2/3] Testing Aerodynamic Wing/Spoiler (Sweep)...")
    test_aerodynamic_wing()
    print("  -> Wing OK")

    print("[3/3] Testing OZ Racing Sport Wheel (Revolve + Loft + 10x Circular Pattern)...")
    test_oz_style_sport_wheel()
    print("  -> Sport Wheel OK")

    print("\n>>> ALL AESTHETIC MODELING TESTS PASSED SUCCESSFULLY! <<<")
