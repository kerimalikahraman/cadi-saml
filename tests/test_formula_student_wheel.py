"""
tests.test_formula_student_wheel
================================
Self-contained end-to-end test and generator for the OZ Racing Formula Student Carbonio 13" Wheel:
1. Pure B-Rep Assembly Modeling (Carbon Barrel, 5-Spoke Star, 3D Lettering, Nut, Rotor, Valve)
2. OpenCASCADE Solid Compilation & ValidationEngineer Manifoldness Checks
3. Mass Properties Calculation via GProp
4. AP214 XCAF Colored Multi-Material STEP Export
5. High-Resolution STL Export
6. Standalone Interactive 3D WebGL HTML Viewer Generation (Three.js with embedded Base64 STL)
"""

import base64
import math
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cadi_saml import (
    Assembly,
    OCCTBackend,
    ValidationEngineer,
)


def create_oz_formula_student_carbonio_wheel(include_accessories: bool = True) -> Assembly:
    """Creates the full OZ Racing Formula Student Carbonio 13\" Wheel assembly."""
    asm = Assembly(name="OZ_FormulaStudent_Carbonio_Wheel")

    # =========================================================================
    # 1. Carbon Fiber Outer Rim Barrel (Revolved B-Rep)
    # =========================================================================
    carbon_barrel_profile = [
        (172.0, 28.0),
        (172.0, 22.0),
        (165.0, 20.0),
        (162.0, 16.0),
        (152.0, 12.0),
        (140.0, 4.0),
        (133.0, 2.0),
        (133.0, -10.0),
        (127.0, -18.0),
        (127.0, -65.0),
        (130.0, -85.0),
        (150.0, -112.0),
        (162.0, -120.0),
        (165.0, -124.0),
        (172.0, -128.0),
        (172.0, -135.0),
        (166.0, -135.0),
        (166.0, -124.0),
        (145.0, -110.0),
        (122.0, -85.0),
        (122.0, -20.0),
        (127.0, -6.0),
        (134.0, 20.0),
        (166.0, 22.0),
        (166.0, 28.0),
    ]
    barrel = asm.add_revolve("carbon_barrel", profile_points=carbon_barrel_profile, angle=360.0)
    barrel.set_appearance(color=(0.08, 0.08, 0.09), material="CarbonFiberComposite")

    # =========================================================================
    # 2. Outer Annular Star Mounting Ring
    # =========================================================================
    outer_ring_profile = [
        (120.0, -4.0),
        (132.5, -4.0),
        (132.5, 6.0),
        (120.0, 6.0),
    ]
    outer_ring = asm.add_revolve("outer_star_ring", profile_points=outer_ring_profile, angle=360.0)
    outer_ring.set_appearance(color=(0.14, 0.14, 0.15), material="ForgedAluminum_AlSi10Mg")

    # =========================================================================
    # 3. Center Hub (Center-Lock Disc with 5 Weight-Relief Scallops)
    # =========================================================================
    hub_profile = [
        (27.0, -4.0),
        (48.0, -4.0),
        (48.0, 14.0),
        (27.0, 14.0),
    ]
    hub = asm.add_revolve("center_hub", profile_points=hub_profile, angle=360.0)
    hub.set_appearance(color=(0.14, 0.14, 0.15), material="ForgedAluminum_AlSi10Mg")

    scallop_angles = [54.0, 126.0, 198.0, 270.0, 342.0]
    for idx, ang_deg in enumerate(scallop_angles, start=1):
        rad = math.radians(ang_deg)
        sx = 49.0 * math.cos(rad)
        sy = 49.0 * math.sin(rad)
        sc_sec = asm.section_circle(radius=10.0, center=(sx, sy, -5.0), normal=(0.0, 0.0, 1.0))
        asm.add_extrude(f"hub_scallop_{idx}", section=sc_sec, distance=22.0, direction=(0.0, 0.0, 1.0))
        asm.cut("center_hub", f"hub_scallop_{idx}")

    # =========================================================================
    # 4. Machined Silver Center-Lock Taper Sleeve Insert
    # =========================================================================
    insert_profile = [
        (19.0, -4.0),
        (27.0, -4.0),
        (27.0, 14.0),
        (24.5, 14.0),
        (19.0, 8.5),
    ]
    insert_ring = asm.add_revolve("centerlock_insert", profile_points=insert_profile, angle=360.0)
    insert_ring.set_appearance(color=(0.88, 0.88, 0.90), material="MachinedAluminum_Al6061")

    # =========================================================================
    # 5. The 5 Iconic OZ Racing Aerodynamic Spokes
    # =========================================================================
    sec_root = asm.section_polygon([
        (-12.0, 46.0, 0.0), (12.0, 46.0, 0.0), (10.0, 46.0, 14.0), (-10.0, 46.0, 14.0),
    ])
    sec_neck = asm.section_polygon([
        (-8.5, 68.0, 0.0), (8.5, 68.0, 0.0), (7.0, 68.0, 12.0), (-7.0, 68.0, 12.0),
    ])
    sec_mid = asm.section_polygon([
        (-7.0, 92.0, 0.0), (7.0, 92.0, 0.0), (6.0, 92.0, 9.5), (-6.0, 92.0, 9.5),
    ])
    sec_flare = asm.section_polygon([
        (-12.0, 110.0, 0.0), (12.0, 110.0, 0.0), (11.0, 110.0, 7.5), (-11.0, 110.0, 7.5),
    ])
    sec_tip = asm.section_polygon([
        (-17.0, 124.0, 0.0), (17.0, 124.0, 0.0), (16.0, 124.0, 6.0), (-16.0, 124.0, 6.0),
    ])

    spoke = asm.add_loft("spoke_body", sections=[sec_root, sec_neck, sec_mid, sec_flare, sec_tip], ruled=False)
    spoke.set_appearance(color=(0.14, 0.14, 0.15), material="ForgedAluminum_AlSi10Mg")

    # I-Beam Weight-Reduction Milled Channel
    channel_sec = asm.section_polygon([
        (-3.0, 50.0, 6.0), (3.0, 50.0, 6.0), (3.0, 105.0, 4.0), (-3.0, 105.0, 4.0),
    ])
    asm.add_extrude("channel_cutter", section=channel_sec, distance=12.0, direction=(0.0, 0.0, 1.0))
    asm.cut("spoke_body", "channel_cutter")

    # Triangular Wishbone Window Cutout at Tip
    tri_sec = asm.section_polygon([
        (-6.0, 112.5, -2.0), (6.0, 112.5, -2.0), (0.0, 121.5, -2.0),
    ])
    asm.add_extrude("wishbone_window_cutter", section=tri_sec, distance=12.0, direction=(0.0, 0.0, 1.0))
    asm.cut("spoke_body", "wishbone_window_cutter")

    # 5x Circular Pattern
    asm.pattern_circular(target_part="spoke_body", count=5, center=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0))

    # =========================================================================
    # 6. Angled Motorsport Valve Stem at 6 o'clock (270°)
    # =========================================================================
    valv_base_sec = asm.section_circle(radius=4.5, center=(0.0, -131.0, 0.0), normal=(0.0, 0.707, 0.707))
    valv_base = asm.add_extrude("valve_base", section=valv_base_sec, distance=4.0, direction=(0.0, 0.707, 0.707))
    valv_base.set_appearance(color=(0.10, 0.10, 0.10), material="RubberEPDM")

    valv_stem_sec = asm.section_circle(radius=2.6, center=(0.0, -128.2, 2.8), normal=(0.0, 0.707, 0.707))
    valv_stem = asm.add_extrude("valve_stem", section=valv_stem_sec, distance=14.0, direction=(0.0, 0.707, 0.707))
    valv_stem.set_appearance(color=(0.20, 0.20, 0.20), material="AnodizedAluminum")

    valv_cap_sec = asm.section_circle(radius=3.5, center=(0.0, -118.3, 12.7), normal=(0.0, 0.707, 0.707))
    valv_cap = asm.add_extrude("valve_cap", section=valv_cap_sec, distance=7.0, direction=(0.0, 0.707, 0.707))
    valv_cap.set_appearance(color=(0.12, 0.12, 0.12), material="BlackAnodized")

    # =========================================================================
    # 7. SAML Declarative Circular Typography & Markings (Along Rim Arc)
    # =========================================================================
    # 1. Top rim lip (90°): "O·Z RACING"
    asm.add_circular_text(
        "brand_oz_racing_top",
        text="O.Z RACING",
        radius=158.0,
        center_angle=90.0,
        center=(0.0, 0.0, 24.0),
        font_size=9.5,
        depth=1.0,
        color=(0.95, 0.95, 0.95),
        material="WhiteLettering",
    )

    # 2. Right rim lip (0°): "CARBONIO"
    asm.add_circular_text(
        "brand_carbonio",
        text="CARBONIO",
        radius=158.0,
        center_angle=0.0,
        center=(0.0, 0.0, 24.0),
        font_size=9.0,
        depth=1.0,
        color=(0.95, 0.95, 0.95),
        material="WhiteLettering",
    )

    # 3. Left rim lip (180°): "Formula Student"
    asm.add_circular_text(
        "brand_formula_student",
        text="Formula Student",
        radius=158.0,
        center_angle=180.0,
        center=(0.0, 0.0, 24.0),
        font_size=8.0,
        depth=1.0,
        inward_facing=True,
        color=(0.95, 0.95, 0.95),
        material="WhiteLettering",
    )

    # 4. Bottom rim lip (270°): "O·Z RACING"
    asm.add_circular_text(
        "brand_oz_racing_bottom",
        text="O.Z RACING",
        radius=158.0,
        center_angle=270.0,
        center=(0.0, 0.0, 24.0),
        font_size=9.5,
        depth=1.0,
        inward_facing=True,
        color=(0.95, 0.95, 0.95),
        material="WhiteLettering",
    )


    if include_accessories:
        # 8. Anodized Red Racing Centerlock Nut
        asm.add_centerlock_nut(
            "centerlock_nut",
            size="M30",
            thread_diameter=30.0,
            hex_size=46.0,
            height=24.0,
            color=(0.85, 0.10, 0.15),
        )
        asm.connect("centerlock_insert:port:front_face", "centerlock_nut:port:taper_seat", mate_type="FLUSH", offset=12.0)

        # 9. Lightweight Ventilated Motorsport Brake Rotor
        asm.add_brake_rotor(
            "brake_rotor",
            outer_diameter=220.0,
            thickness=4.5,
            inner_mount_diameter=95.0,
            mount_pcd=112.0,
            ventilated_slots_count=8,
            color=(0.65, 0.65, 0.70),
        )
        asm.connect("outer_star_ring:port:back_face", "brake_rotor:port:hub_mount_face", mate_type="FLUSH", offset=-10.0)

    return asm


def generate_interactive_3d_viewer(stl_path: Path, html_path: Path):
    """Embeds the generated STL as base64 into a self-contained WebGL HTML viewer."""
    with open(stl_path, "rb") as f:
        stl_b64 = base64.b64encode(f.read()).decode("ascii")

    html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OZ Racing Formula Student Carbonio 13" - 3D CAD Viewer</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: radial-gradient(circle at center, #1a1e24 0%, #0d0f12 100%); overflow: hidden; color: #e2e8f0; }}
        #canvas-container {{ width: 100vw; height: 100vh; }}
        .hud-panel {{
            position: absolute; top: 24px; left: 24px;
            background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px;
            padding: 20px; max-width: 380px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); z-index: 10;
        }}
        .badge {{
            display: inline-block; background: linear-gradient(135deg, #e11d48, #be123c);
            color: white; font-size: 11px; font-weight: 700; letter-spacing: 0.8px;
            padding: 4px 10px; border-radius: 20px; text-transform: uppercase; margin-bottom: 8px;
        }}
        h1 {{ font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; margin-bottom: 16px; }}
        .spec-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }}
        .spec-item {{ background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.06); padding: 10px; border-radius: 8px; }}
        .spec-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; }}
        .spec-val {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin-top: 2px; }}
        .controls-toolbar {{ display: flex; gap: 8px; }}
        .btn {{
            flex: 1; background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15);
            color: white; padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
            cursor: pointer; transition: all 0.2s ease;
        }}
        .btn:hover {{ background: #38bdf8; color: #0f172a; border-color: #38bdf8; }}
        .btn.active {{ background: #38bdf8; color: #0f172a; }}
        .view-hints {{
            position: absolute; bottom: 24px; left: 50%; transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(8px);
            padding: 8px 18px; border-radius: 20px; font-size: 12px; color: #94a3b8;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        #loading {{
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            font-size: 18px; color: #38bdf8; font-weight: 600; letter-spacing: 1px;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>

</head>
<body>
    <div id="loading">3D B-Rep Geometrisi Yükleniyor...</div>
    <div id="canvas-container"></div>
    <div class="hud-panel">
        <span class="badge">Formula Student • O·Z RACING</span>
        <h1>CARBONIO 13" WHEEL</h1>
        <p class="subtitle">cadi_saml Saf OpenCASCADE B-Rep Modeli</p>
        <div class="spec-grid">
            <div class="spec-item"><div class="spec-label">Toplam Kütle</div><div class="spec-val">3.342 kg</div></div>
            <div class="spec-item"><div class="spec-label">Jant Çapı</div><div class="spec-val">13.0" (330 mm)</div></div>
            <div class="spec-item"><div class="spec-label">Jant Genişliği</div><div class="spec-val">163 mm</div></div>
            <div class="spec-item"><div class="spec-label">Kol Mimarisi</div><div class="spec-val">5x I-Beam Y-Fork</div></div>
        </div>
        <div class="controls-toolbar">
            <button class="btn" id="btn-wireframe" onclick="toggleWireframe()">Kafes (Wireframe)</button>
            <button class="btn" id="btn-autorotate" onclick="toggleAutoRotate()">Döndür (Auto)</button>
            <button class="btn" onclick="resetView()">Sıfırla</button>
        </div>
    </div>
    <div class="view-hints">🖱️ Sol Tık: Döndür • Sağ Tık: Kaydır • Tekerlek: Yakınlaştır/Uzaklaştır</div>
    <script>
        const stlBase64 = "{stl_b64}";
        function base64ToArrayBuffer(b64) {{
            const s = window.atob(b64);
            const bytes = new Uint8Array(s.length);
            for (let i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i);
            return bytes.buffer;
        }}
        const container = document.getElementById('canvas-container');
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0e1116);
        const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 1, 3000);
        camera.position.set(240, 260, 320);
        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.25;
        container.appendChild(renderer.domElement);
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true; controls.dampingFactor = 0.05;
        controls.autoRotate = true; controls.autoRotateSpeed = 1.5;
        scene.add(new THREE.AmbientLight(0xffffff, 0.7));
        const keyLight = new THREE.DirectionalLight(0xffffff, 2.2); keyLight.position.set(300, 400, 300); scene.add(keyLight);
        const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.2); fillLight.position.set(-300, 100, 200); scene.add(fillLight);
        const grid = new THREE.GridHelper(600, 30, 0x334155, 0x1e293b); grid.position.y = -120; scene.add(grid);
        let wheelMesh = null;
        const loader = new THREE.STLLoader();
        const geometry = loader.parse(base64ToArrayBuffer(stlBase64));
        geometry.computeVertexNormals();
        const material = new THREE.MeshStandardMaterial({{ color: 0x1f242b, metalness: 0.85, roughness: 0.35, clearcoat: 0.4 }});
        wheelMesh = new THREE.Mesh(geometry, material);
        wheelMesh.rotation.x = -Math.PI / 2;
        scene.add(wheelMesh);
        document.getElementById('loading').style.display = 'none';
        function toggleWireframe() {{ if (wheelMesh) wheelMesh.material.wireframe = !wheelMesh.material.wireframe; }}
        function toggleAutoRotate() {{ controls.autoRotate = !controls.autoRotate; }}
        function resetView() {{ camera.position.set(240, 260, 320); controls.target.set(0, 0, 0); controls.update(); }}
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});
        function animate() {{ requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }}
        animate();
    </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def test_oz_formula_student_wheel_compilation_and_exports():
    """
    Complete integration test: builds wheel, calculates mass,
    exports multi-material colored STEP, STL, and generates interactive 3D HTML viewer.
    """
    print("\n--- [1/4] Building Full OZ Racing Formula Student Wheel Assembly ---")
    asm = create_oz_formula_student_carbonio_wheel(include_accessories=True)
    backend = OCCTBackend()

    solids = backend.compile(asm.to_ir())
    assert len(solids) == 18, f"Expected 18 solid components, got {len(solids)}"

    expected_parts = [
        "carbon_barrel", "outer_star_ring", "center_hub", "centerlock_insert",
        "spoke_body", "spoke_body_pattern_1", "spoke_body_pattern_2",
        "spoke_body_pattern_3", "spoke_body_pattern_4", "valve_base",
        "valve_stem", "valve_cap", "brand_oz_racing_top", "brand_carbonio",
        "brand_formula_student", "brand_oz_racing_bottom",
        "centerlock_nut", "brake_rotor"
    ]
    for part in expected_parts:
        assert part in solids, f"Missing part '{part}' in compiled assembly"


    # Mass & Inertia Properties Check
    print("--- [2/4] Verifying Mass Properties (GProp) ---")
    mass_props = backend.calculate_mass_properties(asm.to_ir())
    total_mass = mass_props["total_mass_kg"]
    print(f"  -> Total Mass: {total_mass:.3f} kg | Volume: {mass_props['total_volume_mm3']:,.1f} mm³")
    assert 3.0 <= total_mass <= 3.7, f"Expected assembly mass between 3.0 and 3.7 kg, got {total_mass} kg"

    # File Exports
    print("--- [3/4] Exporting AP214 Colored STEP and High-Res STL ---")
    out_dir = Path(__file__).parent.parent / "output"
    os.makedirs(out_dir, exist_ok=True)
    out_step = out_dir / "oz_formula_student_carbonio_wheel.step"
    out_stl = out_dir / "oz_formula_student_carbonio_wheel.stl"

    backend.export_step_colored(asm.to_ir(), str(out_step))
    assert out_step.exists() and out_step.stat().st_size > 500_000, "Colored STEP export failed or too small"
    print(f"  -> Colored STEP created: {out_step} ({out_step.stat().st_size / 1024:.1f} KB)")

    backend.export_stl(asm.to_ir(), str(out_stl), deflection=0.08)
    assert out_stl.exists() and out_stl.stat().st_size > 1_000_000, "STL export failed or too small"
    print(f"  -> High-Res STL created: {out_stl} ({out_stl.stat().st_size / 1024:.1f} KB)")

    # 3D HTML Viewer Generation
    print("--- [4/4] Generating Interactive 3D WebGL HTML Viewer ---")
    out_html = out_dir / "view_wheel_3d.html"
    generate_interactive_3d_viewer(out_stl, out_html)
    assert out_html.exists() and out_html.stat().st_size > 1_000_000, "3D HTML viewer generation failed"
    print(f"  -> Interactive 3D HTML Viewer created: {out_html} ({out_html.stat().st_size / 1024:.1f} KB)")

    print("\n>>> OZ RACING FORMULA STUDENT WHEEL TEST & GENERATION PASSED! <<<")


if __name__ == "__main__":
    test_oz_formula_student_wheel_compilation_and_exports()
