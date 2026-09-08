"""
scripts/generate_iris_nozzle_demo.py
====================================
Generates investor-grade demonstration assets for Jet Engine Variable Exhaust Nozzle:
1. AP214 standard STEP model (output/iris_nozzle_12petal_mechanism.step)
2. Interactive 3D WebGL HTML demo with Three.js (output/iris_nozzle_interactive_demo.html)
   Features live opening angle scrubbing, thrust vectoring (pitch/yaw), exhaust plume,
   and aerodynamic telemetry.
"""

import json
import math
import os
import sys

# Ensure library is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cadi_saml import build_variable_exhaust_nozzle, OCCTBackend
from cadi_saml.kinematics.webgl_motion import _extract_part_mesh


HTML_IRIS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CADi Jet Engine: 12-Petal Variable Exhaust Nozzle</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-main: #060911;
    --panel-bg: rgba(13, 20, 36, 0.82);
    --panel-border: rgba(56, 189, 248, 0.22);
    --accent-cyan: #38bdf8;
    --accent-amber: #f59e0b;
    --accent-crimson: #ef4444;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-dim: #64748b;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg-main);
    font-family: 'Inter', -apple-system, sans-serif;
    overflow: hidden;
    color: var(--text-primary);
    user-select: none;
    width: 100vw;
    height: 100vh;
  }

  #canvas3d {
    width: 100vw;
    height: 100vh;
    display: block;
    position: absolute;
    top: 0;
    left: 0;
    z-index: 1;
  }

  /* Glassmorphic Panels */
  .panel {
    position: absolute;
    background: var(--panel-bg);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    box-shadow: 0 20px 48px rgba(0, 0, 0, 0.65);
    z-index: 10;
    transition: all 0.25s ease;
  }

  /* Header / Telemetry HUD */
  .header-card {
    top: 24px;
    left: 24px;
    padding: 20px 24px;
    width: 420px;
  }

  .header-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }

  .header-title h1 {
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #ffffff 0%, #38bdf8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .badge-tag {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: rgba(56, 189, 248, 0.15);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    padding: 3px 8px;
    border-radius: 6px;
  }

  .header-desc {
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin-bottom: 16px;
  }

  /* Metric Cards Grid */
  .metrics-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .metric-item {
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 10px 12px;
  }

  .metric-label {
    font-size: 0.66rem;
    color: var(--text-dim);
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }

  .metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.15rem;
    font-weight: 700;
    color: #38bdf8;
  }

  .metric-unit {
    font-size: 0.72rem;
    color: var(--text-secondary);
    font-weight: 400;
    margin-left: 2px;
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
    padding: 8px 12px;
    background: rgba(56, 189, 248, 0.08);
    border-radius: 8px;
    border: 1px solid rgba(56, 189, 248, 0.2);
    font-size: 0.74rem;
    font-weight: 600;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
    animation: pulseDot 2s infinite ease-in-out;
  }

  @keyframes pulseDot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.6; }
  }

  /* Controls Panel */
  .controls-panel {
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    padding: 18px 28px;
    display: flex;
    align-items: center;
    gap: 28px;
    max-width: 92vw;
  }

  .ctrl-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 170px;
  }

  .ctrl-header {
    display: flex;
    justify-content: space-between;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .ctrl-val {
    font-family: 'JetBrains Mono', monospace;
    color: var(--accent-cyan);
    font-weight: 700;
  }

  input[type="range"] {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 5px;
    background: rgba(255, 255, 255, 0.12);
    border-radius: 4px;
    outline: none;
    transition: background 0.2s;
  }

  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #38bdf8;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.7);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  input[type="range"]::-webkit-slider-thumb:hover {
    transform: scale(1.2);
    background: #ffffff;
  }

  .btn {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: var(--text-primary);
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .btn:hover {
    background: rgba(56, 189, 248, 0.18);
    border-color: rgba(56, 189, 248, 0.45);
    color: #38bdf8;
  }

  .btn.active {
    background: #0284c7;
    border-color: #38bdf8;
    color: #ffffff;
    box-shadow: 0 0 16px rgba(56, 189, 248, 0.4);
  }

  /* Quick View Actions Panel (Top Right) */
  .actions-panel {
    top: 24px;
    right: 24px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .hint-badge {
    position: absolute;
    bottom: 24px;
    right: 24px;
    font-size: 0.7rem;
    color: var(--text-dim);
    z-index: 10;
  }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>

<canvas id="canvas3d"></canvas>

<!-- Top Left: Aerodynamic Telemetry Card -->
<div class="panel header-card">
  <div class="header-title">
    <h1>VARIABLE EXHAUST NOZZLE</h1>
    <span class="badge-tag">12-PETAL IRIS</span>
  </div>
  <p class="header-desc">
    Synchronized 12-segment convergent-divergent supersonic nozzle. Rigid-body rotation around local tangent hinge axes with synchronized throttle & 2-axis thrust vectoring.
  </p>

  <div class="metrics-grid">
    <div class="metric-item">
      <div class="metric-label">Throat Dia (D8)</div>
      <div class="metric-value" id="valD8">320.0<span class="metric-unit">mm</span></div>
    </div>
    <div class="metric-item">
      <div class="metric-label">Throat Area (A8)</div>
      <div class="metric-value" id="valA8">804.2<span class="metric-unit">cm²</span></div>
    </div>
    <div class="metric-item">
      <div class="metric-label">Expansion Ratio (ε)</div>
      <div class="metric-value" id="valExp">1.00<span class="metric-unit"></span></div>
    </div>
    <div class="metric-item">
      <div class="metric-label">Thrust Vector</div>
      <div class="metric-value" id="valVec">0.0<span class="metric-unit">°</span></div>
    </div>
  </div>

  <div class="status-indicator">
    <div class="status-dot"></div>
    <span id="txtStatus">CRUISE DESIGN CONFIGURATION</span>
  </div>
</div>

<!-- Top Right: View Controls -->
<div class="panel actions-panel">
  <button class="btn" id="btnPlume">🔥 Afterburner Plume</button>
  <button class="btn" id="btnWire">🌐 Wireframe</button>
  <button class="btn" id="btnReset">🎯 Reset View</button>
</div>

<!-- Bottom Center: Main Interactive Actuators -->
<div class="panel controls-panel">
  <button class="btn active" id="btnAuto">⏸ Auto Cycle</button>

  <div class="ctrl-group">
    <div class="ctrl-header">
      <span>NOZZLE OPENING</span>
      <span class="ctrl-val" id="dispOpening">+10.0°</span>
    </div>
    <input type="range" id="sliderOpening" min="-6" max="24" step="0.2" value="10">
  </div>

  <div class="ctrl-group">
    <div class="ctrl-header">
      <span>GIMBAL PITCH</span>
      <span class="ctrl-val" id="dispPitch">0.0°</span>
    </div>
    <input type="range" id="sliderPitch" min="-20" max="20" step="0.5" value="0">
  </div>

  <div class="ctrl-group">
    <div class="ctrl-header">
      <span>GIMBAL YAW</span>
      <span class="ctrl-val" id="dispYaw">0.0°</span>
    </div>
    <input type="range" id="sliderYaw" min="-20" max="20" step="0.5" value="0">
  </div>
</div>

<div class="hint-badge">CADi SAML Kernel • Left Click: Rotate • Right Click: Pan • Scroll: Zoom</div>

<script>
const SCENE_PARTS = __SCENE_DATA_JSON__;

const canvas = document.getElementById("canvas3d");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.shadowMap.enabled = true;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x060911);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 5000);
camera.position.set(380, -420, 320);

const controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.target.set(0, 0, 60);

// Lighting Rig
const ambientLight = new THREE.AmbientLight(0xffffff, 0.45);
scene.add(ambientLight);

const mainKeyLight = new THREE.DirectionalLight(0xfff7ed, 1.4);
mainKeyLight.position.set(400, 300, 500);
scene.add(mainKeyLight);

const blueFillLight = new THREE.DirectionalLight(0x38bdf8, 0.9);
blueFillLight.position.set(-400, -300, 200);
scene.add(blueFillLight);

const rimLight = new THREE.DirectionalLight(0xf59e0b, 0.8);
rimLight.position.set(0, -400, -300);
scene.add(rimLight);

// Master Gimbal Vectoring Assembly Group
const nozzleGimbalGroup = new THREE.Group();
scene.add(nozzleGimbalGroup);

// Exhaust Flame Plume Group
const plumeGroup = new THREE.Group();
nozzleGimbalGroup.add(plumeGroup);

// Create Cone Flame Mesh
const flameGeom = new THREE.ConeGeometry(80, 280, 32, 1, true);
flameGeom.rotateX(-Math.PI / 2);
flameGeom.translate(0, 0, 200);
const flameMat = new THREE.MeshBasicMaterial({
  color: 0x38bdf8,
  transparent: true,
  opacity: 0.55,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
});
const flameMesh = new THREE.Mesh(flameGeom, flameMat);
plumeGroup.add(flameMesh);

// Shock Diamond Discs
for (let s = 1; s <= 4; s++) {
  const shockGeom = new THREE.RingGeometry(2, 28 - s * 4, 24);
  const shockMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.75 - s * 0.12,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });
  const shockMesh = new THREE.Mesh(shockGeom, shockMat);
  shockMesh.position.set(0, 0, 110 + s * 38);
  plumeGroup.add(shockMesh);
}
plumeGroup.visible = true;

// Build Meshes and Hinged Petal Pivots
const loadedParts = [];
const petalPivots = [];

const wireMat = new THREE.LineBasicMaterial({
  color: 0x0f172a,
  transparent: true,
  opacity: 0.45,
});

for (const p of SCENE_PARTS) {
  const geom = new THREE.BufferGeometry();
  const flatVerts = [];
  for (const v of p.vertices) flatVerts.push(v[0], v[1], v[2]);
  geom.setAttribute("position", new THREE.Float32BufferAttribute(flatVerts, 3));
  geom.setIndex(p.indices);
  geom.computeVertexNormals();

  const isPetal = p.name.startsWith("petal_");
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(p.color[0], p.color[1], p.color[2]),
    metalness: isPetal ? 0.75 : 0.4,
    roughness: isPetal ? 0.25 : 0.45,
  });

  const mesh = new THREE.Mesh(geom, material);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25), wireMat);
  mesh.add(edges);

  if (p.joint && p.joint.type === "revolute" && isPetal) {
    // Petal local hinge pivot
    const ox = p.joint.origin[0];
    const oy = p.joint.origin[1];
    const oz = p.joint.origin[2];

    geom.translate(-ox, -oy, -oz);
    const pivot = new THREE.Group();
    pivot.position.set(ox, oy, oz);
    pivot.add(mesh);
    nozzleGimbalGroup.add(pivot);

    const axis = new THREE.Vector3(p.joint.axis[0], p.joint.axis[1], p.joint.axis[2]).normalize();

    petalPivots.push({
      name: p.name,
      pivot: pivot,
      mesh: mesh,
      edges: edges,
      material: material,
      axis: axis,
      initialAngle: (p.joint.initial_angle || 10.0) * Math.PI / 180.0,
    });
  } else {
    // Static casing or ring
    nozzleGimbalGroup.add(mesh);
    loadedParts.push({ mesh, edges, material });
  }
}

// Telemetry & Control Elements
const valD8 = document.getElementById("valD8");
const valA8 = document.getElementById("valA8");
const valExp = document.getElementById("valExp");
const valVec = document.getElementById("valVec");
const txtStatus = document.getElementById("txtStatus");

const sliderOpening = document.getElementById("sliderOpening");
const dispOpening = document.getElementById("dispOpening");
const sliderPitch = document.getElementById("sliderPitch");
const dispPitch = document.getElementById("dispPitch");
const sliderYaw = document.getElementById("sliderYaw");
const dispYaw = document.getElementById("dispYaw");

const btnAuto = document.getElementById("btnAuto");
const btnPlume = document.getElementById("btnPlume");
const btnWire = document.getElementById("btnWire");
const btnReset = document.getElementById("btnReset");

let isAuto = true;
let isWireframe = false;
let openingAngle = 10.0;
let pitchAngle = 0.0;
let yawAngle = 0.0;
let autoTimer = 0.0;

const BASE_RADIUS = 160.0;
const PETAL_LENGTH = 130.0;

function updateNozzle() {
  // Update 12 Petals around local hinge axes
  const deltaAngleRad = (openingAngle - 10.0) * Math.PI / 180.0;

  for (const p of petalPivots) {
    const curAngle = p.initialAngle + deltaAngleRad;
    p.pivot.quaternion.setFromAxisAngle(p.axis, curAngle);
  }

  // Update Thrust Vectoring Gimbal Tilt
  const pitchRad = pitchAngle * Math.PI / 180.0;
  const yawRad = yawAngle * Math.PI / 180.0;
  nozzleGimbalGroup.rotation.x = pitchRad;
  nozzleGimbalGroup.rotation.y = yawRad;

  // Aerodynamic Telemetry Calculations
  const rExit = BASE_RADIUS + PETAL_LENGTH * Math.sin(openingAngle * Math.PI / 180.0);
  const d8 = 2.0 * rExit;
  const a8 = (0.5 * 12 * Math.pow(rExit, 2) * Math.sin(2.0 * Math.PI / 12)) / 100.0; // cm^2
  const aInlet = (Math.PI * Math.pow(BASE_RADIUS, 2)) / 100.0; // cm^2
  const expRatio = a8 / aInlet;
  const vecMag = Math.sqrt(pitchAngle * pitchAngle + yawAngle * yawAngle);

  valD8.innerHTML = d8.toFixed(1) + '<span class="metric-unit">mm</span>';
  valA8.innerHTML = a8.toFixed(1) + '<span class="metric-unit">cm²</span>';
  valExp.innerHTML = expRatio.toFixed(2);
  valVec.innerHTML = vecMag.toFixed(1) + '<span class="metric-unit">°</span>';

  dispOpening.textContent = (openingAngle >= 0 ? "+" : "") + openingAngle.toFixed(1) + "°";
  dispPitch.textContent = (pitchAngle >= 0 ? "+" : "") + pitchAngle.toFixed(1) + "°";
  dispYaw.textContent = (yawAngle >= 0 ? "+" : "") + yawAngle.toFixed(1) + "°";

  if (openingAngle < 0) {
    txtStatus.textContent = "CONVERGENT SUB-CRITICAL THROAT";
  } else if (openingAngle < 15) {
    txtStatus.textContent = "CRUISE OPTIMIZED EXPANSION";
  } else {
    txtStatus.textContent = "AFTERBURNER DIVERGENT MAXIMUM THRUST";
  }

  // Update Flame scale according to throat area
  const flameScale = 0.7 + (openingAngle + 6) / 30.0;
  flameMesh.scale.set(flameScale, flameScale, flameScale * 1.1);
  flameMesh.material.opacity = 0.4 + (openingAngle + 6) * 0.015;
}

sliderOpening.addEventListener("input", (e) => {
  openingAngle = parseFloat(e.target.value);
  isAuto = false;
  btnAuto.classList.remove("active");
  btnAuto.textContent = "▶ Auto Cycle";
  updateNozzle();
});

sliderPitch.addEventListener("input", (e) => {
  pitchAngle = parseFloat(e.target.value);
  updateNozzle();
});

sliderYaw.addEventListener("input", (e) => {
  yawAngle = parseFloat(e.target.value);
  updateNozzle();
});

btnAuto.addEventListener("click", () => {
  isAuto = !isAuto;
  btnAuto.classList.toggle("active", isAuto);
  btnAuto.textContent = isAuto ? "⏸ Auto Cycle" : "▶ Auto Cycle";
});

btnPlume.addEventListener("click", () => {
  plumeGroup.visible = !plumeGroup.visible;
  btnPlume.classList.toggle("active", plumeGroup.visible);
});

btnWire.addEventListener("click", () => {
  isWireframe = !isWireframe;
  btnWire.classList.toggle("active", isWireframe);
  for (const p of petalPivots) {
    p.material.wireframe = isWireframe;
    p.edges.visible = !isWireframe;
  }
  for (const p of loadedParts) {
    p.material.wireframe = isWireframe;
    p.edges.visible = !isWireframe;
  }
});

btnReset.addEventListener("click", () => {
  camera.position.set(380, -420, 320);
  controls.target.set(0, 0, 60);
  controls.update();
  pitchAngle = 0;
  yawAngle = 0;
  sliderPitch.value = 0;
  sliderYaw.value = 0;
  updateNozzle();
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

updateNozzle();

// Animation Loop
let lastTime = performance.now();
function animate(currentTime) {
  requestAnimationFrame(animate);
  const dt = (currentTime - lastTime) / 1000.0;
  lastTime = currentTime;

  if (isAuto) {
    autoTimer += dt * 0.9;
    // Harmonic opening/closing between -4 deg and +22 deg
    openingAngle = 9.0 + 13.0 * Math.sin(autoTimer);
    sliderOpening.value = openingAngle;

    // Gentle thrust vectoring wobble
    pitchAngle = 6.0 * Math.sin(autoTimer * 0.7);
    yawAngle = 5.0 * Math.cos(autoTimer * 0.5);
    sliderPitch.value = pitchAngle;
    sliderYaw.value = yawAngle;

    updateNozzle();
  }

  controls.update();
  renderer.render(scene, camera);
}
requestAnimationFrame(animate);
</script>
</body>
</html>
"""


def main():
    print("[1/3] Building Variable Exhaust Nozzle assembly...")
    asm, mech = build_variable_exhaust_nozzle(
        num_petals=12,
        base_radius=160.0,
        petal_length=130.0,
        nominal_opening_deg=10.0,
    )

    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
    os.makedirs(out_dir, exist_ok=True)

    backend = OCCTBackend()
    print("[2/3] Compiling B-Rep and exporting AP214 STEP...")
    step_path = os.path.join(out_dir, "iris_nozzle_12petal_mechanism.step")
    backend.export_step(asm.to_ir(), step_path)
    print(f"      -> STEP saved: {step_path} ({os.path.getsize(step_path)} bytes)")

    print("[3/3] Tessellating meshes and generating interactive 3D WebGL HTML...")
    solids = backend.compile(asm.to_ir())
    parts_data = []

    for name, shape in solids.items():
        verts, indices = _extract_part_mesh(shape, deflection=0.4)
        if not verts or not indices:
            continue

        part_ref = asm._parts.get(name)
        color = [0.75, 0.78, 0.82]
        if part_ref and getattr(part_ref.node, "color", None):
            color = list(part_ref.node.color)

        joint = asm._get_mechanism().joints.get(name)
        joint_info = None
        if joint:
            joint_info = {
                "type": "revolute",
                "origin": list(joint.origin),
                "axis": list(joint.axis),
                "initial_angle": getattr(joint, "initial_angle_deg", 10.0),
            }

        parts_data.append({
            "name": name,
            "vertices": verts,
            "indices": indices,
            "color": color,
            "joint": joint_info,
        })

    html_content = HTML_IRIS_TEMPLATE.replace("__SCENE_DATA_JSON__", json.dumps(parts_data))
    html_path = os.path.join(out_dir, "iris_nozzle_interactive_demo.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"      -> HTML saved: {html_path} ({os.path.getsize(html_path)} bytes)")
    print("\n[SUCCESS] Successfully generated Jet Engine Iris Nozzle demonstration assets!")


if __name__ == "__main__":
    main()
