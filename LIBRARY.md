# CADi SAML — Semantic Assembly Modeling Language for Python

Engineering validation, sampled motion inspection, tolerance stackups and bounded
parametric design search are documented in [ENGINEERING_UPGRADE.md](ENGINEERING_UPGRADE.md).

[![PyPI Version](https://img.shields.io/pypi/v/cadi_saml.svg)](https://pypi.org/project/cadi_saml/)
[![Python Versions](https://img.shields.io/pypi/pyversions/cadi_saml.svg)](https://pypi.org/project/cadi_saml/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Deterministic, Zero-Coordinate, LLM-Native CAD & Kinematics Engine built on OpenCASCADE (OCCT)**

`cadi_saml` is a high-level Python CAD library purpose-built for AI/LLM code generation and mechanical engineering automation. Instead of thousands of lines of fragile coordinate transformations, `cadi_saml` enables declarative modeling — using semantic ports, kinematic joint mates, cascading parametric formulas, and monolithic mechanical assemblies — while an industrial-grade OpenCASCADE core generates watertight B-Rep solids, 2D ISO drawings, and interactive 3D WebGL motion simulations.

---

## ⚡ Quick Installation

```bash
pip install cadi_saml
```

*Note: For full B-Rep solid kernel compilation, ensure an OpenCASCADE Python binding (such as `cadquery-ocp` / `OCP`) is available in your Python environment.*

---

## 🚀 Key Features

### 1. Planar Linkages & Reciprocating Engines
Model authentic monolithic crankshafts, connecting rods, pistons, and engine frames with coupled non-linear kinematics:

```python
from cadi_saml import Assembly, OCCTBackend

with Assembly("Planar_Crank_Slider", units="mm", material="Steel4140") as asm:
    # 1. Engine Bedplate Frame with Main Bearing Stand & 36mm Cylinder Bore
    frame = asm.add_engine_frame(
        "engine_frame",
        base_length=250.0,
        base_width=90.0,
        cylinder_bore_dia=36.0,
        origin=(0.0, 0.0, 0.0)
    )

    # 2. Monolithic Counterweighted Crankshaft (R=30mm)
    crank = asm.add_crankshaft(
        "crankshaft",
        crank_radius=30.0,
        disc_radius=44.0,
        origin=(0.0, 0.0, 17.0)
    )

    # 3. Forged Connecting Rod (L=90mm)
    conrod = asm.add_connecting_rod(
        "connecting_rod",
        length=90.0,
        origin=(30.0, 0.0, 27.0)
    )

    # 4. Horizontal Slider Piston with Ring Grooves & Wristpin
    piston = asm.add_slider_piston(
        "slider_piston",
        diameter=34.0,
        length=42.0,
        origin=(120.0, 0.0, 32.0)
    )

    # Define Kinematic Joints
    asm.add_revolute_joint("crankshaft", origin=(0.0, 0.0, 17.0), axis=(0.0, 0.0, 1.0))
    asm.add_revolute_joint("connecting_rod", origin=(30.0, 0.0, 27.0), axis=(0.0, 0.0, 1.0))
    asm.add_prismatic_joint("slider_piston", origin=(120.0, 0.0, 32.0), axis=(1.0, 0.0, 0.0))

    # Coupled Planar Slider-Crank Motion Coupler
    asm.add_slider_crank_relation(
        crank_part="crankshaft",
        conrod_part="connecting_rod",
        piston_part="slider_piston",
        crank_radius=30.0,
        conrod_length=90.0,
        crank_center=(0.0, 0.0, 17.0),
        slide_axis=(1.0, 0.0, 0.0)
    )

    # Solve forward kinematics at 90° crank rotation
    states = asm.solve_motion("crankshaft", value=90.0)
    print(f"Piston Position: {states['slider_piston'].translation_mm:.2f} mm")

    # Generate interactive 3D WebGL motion animation
    asm.export_motion_html("planar_mechanism.html", driver_part="crankshaft")
```

---

### 2. Involute Spur & Helical Gear Transmissions
High-precision gear modeling with standard modules, pitch circles, keyways, and automatic center-distance speed ratios:

```python
with Assembly("GearReductionStage", units="mm") as asm:
    # Driving Pinion (m=2.5 mm, z=20)
    pinion = asm.add_spur_gear("pinion", module=2.5, teeth=20, face_width=25.0, bore_dia=16.0, origin=(0, 0, 0))

    # Driven Wheel (m=2.5 mm, z=40) at Center Distance a = 75 mm
    wheel = asm.add_spur_gear("wheel", module=2.5, teeth=40, face_width=25.0, bore_dia=25.0, origin=(75.0, 0, 0))

    # Kinematic Transmission Mate (i = 20 / 40 = 0.5)
    asm.add_revolute_joint("pinion", origin=(0, 0, 0), axis=(0, 0, 1))
    asm.add_revolute_joint("wheel", origin=(75.0, 0, 0), axis=(0, 0, 1))
    asm.add_gear_relation("pinion", "wheel", ratio=0.5, reverse=True)
```

---

### 3. Sheet Metal with DIN 6935 K-Factor Bend Deduction
Generate folded sheet metal parts with exact industrial bend allowances and flat pattern calculation:

```python
with Assembly("SheetMetalEnclosure", units="mm") as asm:
    bracket = asm.add_sheet_metal_bracket(
        name="chassis_mount",
        bracket_type="U",
        width=50.0,
        length1=60.0,
        length2=40.0,
        thickness=2.0,
        k_factor=0.44,
        hole_diameter=6.5
    )
```

---

### 4. Motorsport Running Gear & High-Performance Suspension
Formula Student and GT3 racing standard parts library:

```python
with Assembly("MotorsportCorner", units="mm") as asm:
    rotor = asm.add_brake_rotor("ventilated_rotor", outer_diameter=240.0)
    caliper = asm.add_brake_caliper("caliper", length=140.0)
    nut = asm.add_centerlock_nut("wheel_nut", size="M30")
    coilover = asm.add_coilover("suspension_damper", extended_length=320.0, stroke=80.0, wire_dia=10.0)
    rod_end = asm.add_heim_joint("heim_joint", thread_size="M10")
```

---

### 5. Standard Hardware & Modular Profiles
Single-line insertion of off-the-shelf industrial parts:

```python
# Aluminum Extrusion Profiles
rail = asm.add_profile("rail_x", profile_type="2040", length=300.0)

# Stepper Motors
motor = asm.add_motor("z_stepper", frame="NEMA17", body_length=40.0)

# Bearings & Fasteners
bearing = asm.add_bearing("shaft_bearing", standard="SKF", code="608ZZ")
bolt = asm.add_bolt("clamp_bolt", size="M6", length=25.0)
```

---

### 6. Organic Modeling & NACA Aerodynamics
Exact C2-continuous aerodynamic NACA 4-digit airfoil lofts:

```python
with Assembly("AerodynamicWing", units="mm") as asm:
    root = asm.section_naca(code="2412", chord=160.0, center=(0, 0, 0))
    tip = asm.section_naca(code="0012", chord=100.0, center=(0, 250.0, 30.0))
    wing = asm.add_loft("fsae_rear_wing", sections=[root, tip])
```

---

### 7. Automated 2D ISO Engineering Drawings
Export multi-view engineering technical drawings with OpenCASCADE Hidden Line Removal (HLR):

```python
asm.export_drawing(
    filepath="technical_drawing.svg",
    sheet_size="A4",
    title="PLANAR CRANK-SLIDER MECHANISM",
    material="Steel4140"
)
```

---

### 8. Geometry Validation & Physical Properties
Full B-Rep manifold verification, clash detection, and GProp physical mass properties:

```python
from cadi_saml import ValidationEngineer

validator = ValidationEngineer()
validator.check_manifold(solid)       # Is it a watertight manifold 3D solid?
clashes = validator.check_clashes(solids) # Are components colliding?

# Physical mass & center of gravity calculation
mass_props = asm.get_mass_properties()
print(f"Total Mass: {mass_props['total_mass_kg']:.3f} kg")
print(f"Center of Gravity: {mass_props['center_of_gravity']}")
```

---

### 9. Automated Engineering Bill of Materials (BOM)
Extract hierarchical BOM reports, aggregate quantities of linear/radial pattern instances and fasteners, and export to Markdown, CSV, JSON, or interactive HTML:

```python
# Export to Markdown table, CSV, JSON, or styled HTML
md_table = asm.generate_bom(format="markdown")
asm.generate_bom(format="csv", filepath="assembly_bom.csv")
asm.generate_bom(format="html", filepath="assembly_bom.html")

# Access programmatic data
bom = asm.generate_bom(format="raw")
print(f"Total Mass: {bom.total_mass_kg:.3f} kg | Total Parts: {bom.total_parts_count}")
```

---

### 10. Standard Seals & Shaft Couplings Library
Declarative insertion of elastomer seals (O-Rings, DIN 3760 radial shaft seals) and mechanical shaft couplings (Flexible Jaw, DIN 115 Rigid Flange, Oldham):

```python
# Elastomer Seals
oring = asm.add_seal("motor_oring", seal_type="oring", inner_dia=25.0, cross_section=3.0)
oil_seal = asm.add_seal("crank_seal", seal_type="radial_shaft_seal", shaft_dia=20.0, outer_dia=35.0, width=7.0)

# Shaft Couplings with dual input/output bore ports
jaw_cpl = asm.add_coupling("jaw_coupling", coupling_type="flexible_jaw", shaft1_dia=14.0, shaft2_dia=16.0, outer_dia=55.0, length=66.0)
flange_cpl = asm.add_coupling("rigid_coupling", coupling_type="rigid_flange", shaft1_dia=20.0, shaft2_dia=25.0, outer_dia=80.0, length=70.0)
```

---

### 11. Batch Parametric Variant Export Pipeline
Simultaneously generate multiple parameter variations, verify B-Rep manifold validity, and export `.step`, `.stl`, `.svg`, and `.html` with summary manifest:

```python
variants = [
    {"name": "shaft_short", "radius": 10.0, "length": 50.0},
    {"name": "shaft_heavy", "radius": 20.0, "length": 150.0},
]
report = asm.batch_export(variants, output_dir="./variants", formats=["step", "stl", "svg"])
print(f"Compiled {report.successful_count}/{report.total_variants} variants in {report.total_elapsed_seconds:.2f}s")
```

---

### 12. Constraint & Degree-of-Freedom (DOF) Debugger
Audit assembly degree-of-freedom states, identify floating/unanchored parts, find unconnected semantic ports, and generate interactive traffic-light HTML reports:

```python
diag_report = asm.debug_constraints(html_filepath="constraint_audit.html")
print(f"Fully Constrained: {diag_report.fully_constrained_count}, Floating: {diag_report.floating_count}")
```

---

### 13. Strict LLM Mode, Provenance & Post-Build Engineering Contract
Enforces zero hallucinated geometry. When an LLM provides missing, unknown, or contradictory parameters, macros raise structured `CADISpecificationError` rather than silently making arbitrary geometric assumptions:

```python
from cadi_saml import CADISpecificationError

# 1. Provenance tracking for every dimension
bracket = asm.add_box("bracket", 120.0, 60.0, 15.0)
bracket.track_provenance("length", source="llm_json", source_ref="payload.dimensions.length_mm", confidence=1.0)

# 2. Automated Post-Build Contract Verification
# Stages: compile -> manifold -> dimensions -> interference -> kinematics -> STEP AP214 roundtrip
report = asm.verify_contract(test_step_roundtrip=True, check_clash=True)
assert report.passed
print(f"Verified {report.total_parts_verified} parts, total volume: {report.total_volume_mm3:.2f} mm³")
```

---

### 14. Epicyclic Planetary Kinematics (Willis Equation) & Involute Ring Gears
True epicyclic kinematics governing planetary gear trains via the fundamental Willis equation ($\frac{\omega_s - \omega_c}{\omega_r - \omega_c} = -\frac{Z_r}{Z_s}$) coupled with analytical internal involute tooth profile generation:

```python
# 1. Internal Ring Gear with Involute Teeth & PCD Flange Holes
ring = asm.add_internal_gear("ring_gear", module=2.0, teeth=48, face_width=20.0, rim_thickness=12.0)

# 2. Willis Epicyclic Kinematic Relation
asm.add_planetary_relation(
    sun_part="sun",
    carrier_part="carrier",
    ring_part="ring_gear",
    planet_parts=["planet_1", "planet_2", "planet_3"],
    fixed_component="ring",
)
```

---

## 📦 Multi-Format Export Support

| Format | Extension | Target |
|---|---|---|
| **STEP** | `.step`, `.stp` | SolidWorks, Siemens NX, CATIA, Fusion 360, FreeCAD |
| **IGES** | `.igs`, `.iges` | Legacy CAM / CNC Machining |
| **STL** | `.stl` | 3D Printing (SLA / SLS / FDM) |
| **GLTF** | `.gltf`, `.glb` | Three.js, Blender, Unreal Engine, Web 3D |
| **SVG** | `.svg` | ISO 2D Engineering Drawings with Title Block |
| **HTML** | `.html` | Standalone interactive 3D WebGL Motion Player |

---

## 📄 License
MIT License. Developed by the CADi Team.
