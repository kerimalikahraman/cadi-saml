"""
tests/test_v5_macros.py
=======================
Automated verification suite for cadi_saml v0.5.0 advanced assembly macros,
machine design detailing features, LLM introspection, and manufacturing outputs.
"""

import sys
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import cadi_saml
from cadi_saml import Assembly, OCCTBackend, ValidationEngineer

def test_v5_macros():
    print("=" * 70)
    print(f"RUNNING CADI_SAML {cadi_saml.__version__} MACRO & FEATURE VERIFICATION SUITE")
    print("=" * 70)
    
    val = ValidationEngineer()
    backend = OCCTBackend()

    # -------------------------------------------------------------------------
    # TEST 1: Bolted Joint Macro (ISO 4014 / DIN 912)
    # -------------------------------------------------------------------------
    print("\n--> [TEST 1] add_bolted_joint()...")
    with Assembly("TestBoltedJoint", units="mm") as asm:
        # Clamped plates
        asm.add_box("plate1", 80, 80, 12, origin=(0, 0, 0))
        asm.add_box("plate2", 80, 80, 12, origin=(0, 0, 12))
        
        # Bolted Joint Macro
        joint_rep = asm.add_bolted_joint(
            name="clamp_joint",
            thread="M10",
            bolt_type="hex_head",
            with_washer_head=True,
            with_washer_nut=True,
            with_nut=True,
            grip_length=24.0,
        )
        
    assert joint_rep["engagement_check_passed"] is True, "Thread engagement check failed!"
    assert joint_rep["selected_bolt_length_mm"] >= 35, "Bolt length selection invalid!"
    solids = backend.compile(asm.to_ir())
    print(f"    Joint: {joint_rep['standard_designation']} (Selected Length: {joint_rep['selected_bolt_length_mm']}mm)")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 2: Mounting Bracket & Gusset Macro
    # -------------------------------------------------------------------------
    print("\n--> [TEST 2] add_mounting_bracket()...")
    with Assembly("TestBracket", units="mm") as asm:
        b_rep = asm.add_mounting_bracket(
            name="chassis_bracket",
            bracket_type="L",
            width=50.0,
            length1=75.0,
            length2=65.0,
            thickness=4.0,
            with_gusset=True,
        )
    solids = backend.compile(asm.to_ir())
    print(f"    Bracket Type: {b_rep['type']} | Gusset: {b_rep['gusset_reinforced']}")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 3: Profile Frame Macro & Cut-List
    # -------------------------------------------------------------------------
    print("\n--> [TEST 3] add_profile_frame()...")
    with Assembly("TestFrame", units="mm") as asm:
        frame_rep = asm.add_profile_frame(
            name="cart_frame",
            profile_type="4040",
            length_x=600.0,
            width_y=400.0,
            height_z=500.0,
        )
    cut_list = frame_rep["cut_list"]
    assert len(cut_list) == 3, "Cut list should contain 3 distinct cut groups!"
    assert frame_rep["total_profile_length_meters"] > 0.0, "Linear meters must be calculated!"
    solids = backend.compile(asm.to_ir())
    print(f"    Frame Envelope: {frame_rep['envelope_dimensions_mm']}")
    print(f"    Total Profile Needed: {frame_rep['total_profile_length_meters']} m across {len(cut_list)} cuts")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 4: Gear Pair with Kinematic Center Distance
    # -------------------------------------------------------------------------
    print("\n--> [TEST 4] add_gear_pair()...")
    with Assembly("TestGearPair", units="mm") as asm:
        gp_rep = asm.add_gear_pair(
            name="speed_reducer",
            pinion_teeth=18,
            gear_teeth=54,
            module=2.5,
            face_width=25.0,
        )
    assert gp_rep["reduction_ratio"] == 3.0, "Gear ratio must be 3.0!"
    assert abs(gp_rep["center_distance_mm"] - 90.0) < 0.001, "Center distance m*(z1+z2)/2 must equal 90.0mm!"
    solids = backend.compile(asm.to_ir())
    print(f"    Ratio: {gp_rep['reduction_ratio']} | Center Distance: {gp_rep['center_distance_mm']}mm")
    print(f"    Kinematic Mesh Relation: {gp_rep['kinematic_relation_established']}")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 5: Bearing Support Housing Unit
    # -------------------------------------------------------------------------
    print("\n--> [TEST 5] add_bearing_support()...")
    with Assembly("TestBearingSupport", units="mm") as asm:
        bs_rep = asm.add_bearing_support(
            name="drive_pillow_block",
            shaft_dia=25.0,
            housing_type="pillow_block",
            bearing_series="6205",
        )
    solids = backend.compile(asm.to_ir())
    print(f"    Housing: {bs_rep['housing_type']} for {bs_rep['bearing_designation']}")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 6: Stepped Shaft Stack
    # -------------------------------------------------------------------------
    print("\n--> [TEST 6] add_shaft_stack()...")
    with Assembly("TestShaftStack", units="mm") as asm:
        steps = [(20.0, 30.0), (25.0, 45.0), (30.0, 60.0), (25.0, 40.0)]
        stack_rep = asm.add_shaft_stack(
            name="main_spindle",
            shaft_name="spindle_shaft",
            steps=steps,
            stack_elements=[
                {"step_index": 1, "type": "bearing", "name": "front_bearing"},
                {"step_index": 2, "type": "gear", "teeth": 24, "name": "drive_gear"},
            ]
        )
    solids = backend.compile(asm.to_ir())
    print(f"    Shaft Steps: {stack_rep['step_count']} | Total Length: {stack_rep['total_shaft_length_mm']}mm")
    print(f"    Mounted Elements: {len(stack_rep['elements_mounted'])}")
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 7: Mechanical Detailing Features (Keyway, Counterbore, Groove)
    # -------------------------------------------------------------------------
    print("\n--> [TEST 7] Machine Detailing Features...")
    with Assembly("TestFeatures", units="mm") as asm:
        shaft = asm.add_cylinder("jack_shaft", radius=15.0, height=100.0)
        # Add keyway and retaining ring groove via PartReference fluent methods
        shaft.add_keyway(width=8.0, depth=4.0, length=40.0, shaft_dia=30.0)
        shaft.add_retaining_ring_groove(shaft_dia=30.0, groove_dia=28.0, width=1.3, position_z=85.0)
        
        # Plate with counterbore & pocket
        block = asm.add_box("tool_block", 100, 100, 30)
        block.add_counterbore(cbore_dia=15.0, cbore_depth=8.0, hole_dia=9.0, origin=(25.0, 25.0, 30.0))
        block.add_pocket(length=40.0, width=40.0, depth=12.0, origin=(50.0, 50.0, 18.0))
        
    solids = backend.compile(asm.to_ir())
    print(f"    Compiled Solids: {len(solids)} | Watertight: {all(val.check_manifold(s) for s in solids.values())}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    # -------------------------------------------------------------------------
    # TEST 8: LLM Introspection & Manufacturing Outputs (BOM, Cut-List)
    # -------------------------------------------------------------------------
    print("\n--> [TEST 8] LLM Introspection & BOM Export...")
    caps = asm.list_capabilities()
    assert "add_bolted_joint" in caps["assembly_macros"], "add_bolted_joint must be in capabilities!"
    assert "add_gear_pair" in caps["assembly_macros"], "add_gear_pair must be in capabilities!"
    
    desc = asm.describe_macro("add_bolted_joint")
    assert "thread" in desc["parameters"], "Macro descriptor must describe parameters!"
    
    bom = asm.export_bom()
    assert len(bom) > 0, "BOM should not be empty!"
    
    cut_list = asm.export_cut_list()
    val_report = asm.generate_validation_report()
    
    print(f"    Capabilities Catalog: {len(caps['assembly_macros'])} macros, {len(caps['features'])} features")
    print(f"    Describe Macro (add_bolted_joint): {desc['description']}")
    print(f"    BOM Items Count: {len(bom)} | Total Parts: {sum(i['quantity'] for i in bom)}")
    print(f"    Validation Report Status: {val_report['status']}")
    assert solids and all(val.check_manifold(shape) for shape in solids.values())
    print("    PASSED!")

    print("\n" + "=" * 70)
    print("ALL 8 VERIFICATION TESTS PASSED SUCCESSFULLY! (cadi_saml v0.5.0)")
    print("=" * 70)

if __name__ == "__main__":
    test_v5_macros()
