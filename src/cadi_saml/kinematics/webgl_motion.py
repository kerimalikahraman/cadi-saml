"""
cadi_saml.kinematics.webgl_motion
=================================
Interactive 3D WebGL motion animation exporter for mechanical assemblies.
Powered by Three.js with hardware-accelerated PBR lighting, OrbitControls,
sub-millimeter kinematic transmission, and live telemetry scrubbing.
"""

from __future__ import annotations

import json
import math
import os
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape

from .joints import PrismaticJoint, RevoluteJoint

if TYPE_CHECKING:
    from ..core.assembly import Assembly
    from .motion_solver import KinematicMechanism


PART_COLOR_PALETTE = [
    [0.92, 0.65, 0.18],  # Industrial Brass / Bronze
    [0.22, 0.65, 0.95],  # Electric Anodized Blue
    [0.85, 0.25, 0.35],  # Anodized Crimson Red
    [0.20, 0.82, 0.55],  # Precision Emerald
    [0.70, 0.74, 0.82],  # Polished Billet Aluminum
    [0.98, 0.48, 0.15],  # High-Visibility Amber
    [0.65, 0.35, 0.92],  # Metallic Purple
]


def _extract_part_mesh(shape: TopoDS_Shape, deflection: float = 0.5) -> Tuple[List[List[float]], List[int]]:
    """Tessellates an OpenCASCADE shape into flat vertices and index list."""
    try:
        BRepMesh_IncrementalMesh(shape, deflection)
    except Exception:
        pass

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    vertices: List[List[float]] = []
    indices: List[int] = []
    offset = 0

    while exp.More():
        # OCP exposes the downcast as Face_s; TopoDS.Face is unavailable in
        # newer bindings and breaks motion export at runtime.
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation:
            trsf = loc.Transformation()
            num_nodes = triangulation.NbNodes()
            for i in range(1, num_nodes + 1):
                p = triangulation.Node(i).Transformed(trsf)
                vertices.append([round(p.X(), 4), round(p.Y(), 4), round(p.Z(), 4)])

            is_reversed = (face.Orientation() == TopAbs_REVERSED)
            num_tri = triangulation.NbTriangles()
            for i in range(1, num_tri + 1):
                t = triangulation.Triangle(i)
                i1, i2, i3 = t.Get()
                if is_reversed:
                    indices.extend([offset + i1 - 1, offset + i3 - 1, offset + i2 - 1])
                else:
                    indices.extend([offset + i1 - 1, offset + i2 - 1, offset + i3 - 1])
            offset += num_nodes
        exp.Next()

    return vertices, indices


HTML_MOTION_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CADi Motion: __ASSEMBLY_TITLE__</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #080c14;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    overflow: hidden;
    color: #f8fafc;
    user-select: none;
  }
  #canvas3d {
    width: 100vw;
    height: 100vh;
    display: block;
    position: absolute;
    top: 0;
    left: 0;
  }

  /* Glassmorphism Panels */
  .panel {
    position: absolute;
    background: rgba(15, 23, 42, 0.82);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.55);
    z-index: 10;
  }

  /* Top Info Card */
  .info-card {
    top: 24px;
    left: 24px;
    padding: 18px 22px;
    min-width: 360px;
    max-width: 440px;
  }
  .info-card h1 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #38bdf8;
    display: flex;
    align-items: center;
    gap: 10px;
    letter-spacing: -0.01em;
  }
  .info-card h1 span.badge-cadi {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    background: rgba(56, 189, 248, 0.18);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.4);
    padding: 2px 7px;
    border-radius: 6px;
    letter-spacing: 0.05em;
  }
  .info-card .subtitle {
    font-size: 0.78rem;
    color: #94a3b8;
    margin-top: 4px;
    margin-bottom: 14px;
  }

  .telemetry-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75rem;
    margin-top: 6px;
  }
  .telemetry-table th {
    text-align: left;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.65rem;
    letter-spacing: 0.05em;
    padding: 6px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }
  .telemetry-table td {
    padding: 7px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-variant-numeric: tabular-nums;
  }
  .telemetry-table tr:last-child td {
    border-bottom: none;
  }
  .part-badge {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
    box-shadow: 0 0 6px currentColor;
  }
  .tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
  }
  .tag.revolute { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
  .tag.prismatic { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
  .tag.fixed { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

  /* Controls Deck */
  .controls-deck {
    bottom: 24px;
    left: 24px;
    padding: 16px 22px;
    min-width: 380px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .btn-cluster {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .btn {
    background: #1e293b;
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.14);
    padding: 7px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .btn:hover {
    background: #334155;
    border-color: #38bdf8;
    color: #ffffff;
    transform: translateY(-1px);
  }
  .btn.primary {
    background: #0284c7;
    border-color: #38bdf8;
    color: #ffffff;
    box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4);
  }
  .btn.primary:hover {
    background: #0369a1;
  }
  .btn.active {
    background: rgba(56, 189, 248, 0.25);
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .control-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.78rem;
    color: #cbd5e1;
    gap: 12px;
  }
  .control-row label {
    min-width: 100px;
    font-weight: 500;
  }
  .control-row input[type="range"] {
    flex: 1;
    cursor: pointer;
    accent-color: #38bdf8;
    height: 6px;
    background: #1e293b;
    border-radius: 3px;
  }
  .value-display {
    min-width: 60px;
    text-align: right;
    font-weight: 700;
    color: #38bdf8;
    font-variant-numeric: tabular-nums;
  }

  /* Help Pill */
  .help-pill {
    position: absolute;
    bottom: 24px;
    right: 24px;
    padding: 10px 18px;
    background: rgba(15, 23, 42, 0.75);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 30px;
    font-size: 0.74rem;
    color: #94a3b8;
    display: flex;
    gap: 14px;
    align-items: center;
  }
  .help-pill span strong {
    color: #f1f5f9;
  }

  /* Status Indicator */
  .pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 8px #22c55e;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
  }
</style>
<!-- Three.js + OrbitControls (CDN) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <canvas id="canvas3d"></canvas>

  <!-- Telemetry HUD -->
  <div class="panel info-card">
    <h1>
      <div class="pulse-dot"></div>
      __ASSEMBLY_TITLE__
      <span class="badge-cadi">CADi Kinematics</span>
    </h1>
    <div class="subtitle">Multi-Body Dynamic Simulation & Gear Transmission</div>
    <table class="telemetry-table">
      <thead>
        <tr>
          <th>Part</th>
          <th>Joint</th>
          <th>Ratio</th>
          <th>Position / Angle</th>
          <th>Velocity</th>
        </tr>
      </thead>
      <tbody id="telemetryBody"></tbody>
    </table>
  </div>

  <!-- Interactive Controls Deck -->
  <div class="panel controls-deck">
    <div class="btn-cluster">
      <button class="btn primary" id="playBtn">▶ Run Motor</button>
      <button class="btn" id="revBtn" title="Reverse Motor Direction">⇄ Reverse</button>
      <button class="btn" id="wireBtn">Wireframe</button>
      <button class="btn" id="resetCamBtn">Reset View</button>
    </div>
    
    <div class="control-row">
      <label for="angleSlider">Driver Angle:</label>
      <input type="range" id="angleSlider" min="0" max="360" step="1" value="0">
      <span class="value-display" id="angleVal">0.0°</span>
    </div>

    <div class="control-row">
      <label for="speedSlider">Motor Speed:</label>
      <input type="range" id="speedSlider" min="5" max="150" step="5" value="30">
      <span class="value-display" id="speedVal">30 RPM</span>
    </div>

    <div class="control-row">
      <label for="explodeSlider">Exploded View:</label>
      <input type="range" id="explodeSlider" min="0" max="100" step="1" value="0">
      <span class="value-display" id="explodeVal">0%</span>
    </div>
  </div>

  <div class="help-pill">
    <span>🖱️ <strong>Left Click</strong>: Rotate</span>
    <span>•</span>
    <span>🖱️ <strong>Right Click</strong>: Pan</span>
    <span>•</span>
    <span>⚙️ <strong>Scroll</strong>: Zoom</span>
  </div>

<script>
const SCENE_DATA = __SCENE_DATA_JSON__;

// ---------------------------------------------------------------------------
// Three.js Scene, Camera, Renderer Setup
// ---------------------------------------------------------------------------
const canvas = document.getElementById("canvas3d");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080c14);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.5, 5000);
const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;

const controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.screenSpacePanning = true;

// ---------------------------------------------------------------------------
// Engineering Studio Lighting
// ---------------------------------------------------------------------------
const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1e293b, 0.65);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.25);
keyLight.position.set(150, 200, 250);
keyLight.castShadow = true;
keyLight.shadow.mapSize.width = 2048;
keyLight.shadow.mapSize.height = 2048;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.45);
fillLight.position.set(-150, -100, 150);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.35);
rimLight.position.set(0, -200, -100);
scene.add(rimLight);

// Subtle Ground Grid
const gridHelper = new THREE.GridHelper(300, 30, 0x1e293b, 0x0f172a);
gridHelper.position.y = 0;
gridHelper.rotation.x = Math.PI / 2; // Lie on XY plane if Z is up
scene.add(gridHelper);

// ---------------------------------------------------------------------------
// Build CAD Part Meshes & Hierarchy
// ---------------------------------------------------------------------------
const loadedParts = [];
const overallBox = new THREE.Box3();

for (let p of SCENE_DATA.parts) {
  // Convert vertices & index into BufferGeometry
  const geom = new THREE.BufferGeometry();
  const flatPositions = new Float32Array(p.vertices.length * 3);
  for (let i = 0; i < p.vertices.length; i++) {
    flatPositions[i * 3 + 0] = p.vertices[i][0];
    flatPositions[i * 3 + 1] = p.vertices[i][1];
    flatPositions[i * 3 + 2] = p.vertices[i][2];
  }
  geom.setAttribute('position', new THREE.BufferAttribute(flatPositions, 3));
  geom.setIndex(p.indices);
  geom.computeVertexNormals();

  // Material with premium metallic look
  const r = p.color[0], g = p.color[1], b = p.color[2];
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(r, g, b),
    metalness: 0.55,
    roughness: 0.32,
    envMapIntensity: 1.0,
    side: THREE.DoubleSide,
    shadowSide: THREE.DoubleSide,
  });

  const wireMat = new THREE.LineBasicMaterial({
    color: 0x0f172a,
    transparent: true,
    opacity: 0.45,
  });

  const ox = p.joint.origin[0];
  const oy = p.joint.origin[1];
  const oz = p.joint.origin[2];

  let pivotGroup = new THREE.Group();
  let mesh;
  let edges;

  if (p.joint.type === "revolute") {
    // Crucial for exact pivot:
    // 1. Shift the geometry by -origin so that (0,0,0) of this geometry is its exact rotation axis
    geom.translate(-ox, -oy, -oz);
    mesh = new THREE.Mesh(geom, material);
    edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25), wireMat);
    mesh.add(edges);

    // 2. Position the pivot group at the world origin (ox, oy, oz)
    pivotGroup.position.set(ox, oy, oz);
    pivotGroup.add(mesh);
    scene.add(pivotGroup);

  } else if (p.joint.type === "prismatic") {
    geom.translate(-ox, -oy, -oz);
    mesh = new THREE.Mesh(geom, material);
    edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25), wireMat);
    mesh.add(edges);

    pivotGroup.position.set(ox, oy, oz);
    pivotGroup.add(mesh);
    scene.add(pivotGroup);

  } else {
    // Fixed base part (e.g. chassis)
    mesh = new THREE.Mesh(geom, material);
    edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25), wireMat);
    mesh.add(edges);
    pivotGroup.add(mesh);
    scene.add(pivotGroup);
  }

  // Bounding box for camera centering
  const partBox = new THREE.Box3().setFromObject(pivotGroup);
  overallBox.union(partBox);

  // Parse axis vector
  const axisVec = new THREE.Vector3(p.joint.axis[0], p.joint.axis[1], p.joint.axis[2]).normalize();
  if (axisVec.lengthSq() < 0.001) axisVec.set(0, 0, 1);

  loadedParts.push({
    name: p.name,
    color: p.color,
    joint: p.joint,
    factor: p.factor,
    pivot: pivotGroup,
    mesh: mesh,
    edges: edges,
    material: material,
    axis: axisVec,
    origOrigin: [ox, oy, oz],
    initialAngle: (p.joint.initial_angle || 0.0) * Math.PI / 180.0,
    initialDisp: p.joint.initial_disp || 0.0,
  });
}

// Center camera on assembly
const center = overallBox.getCenter(new THREE.Vector3());
const size = overallBox.getSize(new THREE.Vector3());
const maxDim = Math.max(size.x, size.y, size.z, 50.0);

camera.position.set(center.x + maxDim * 1.3, center.y - maxDim * 1.8, center.z + maxDim * 1.4);
camera.lookAt(center);
controls.target.copy(center);
controls.update();

// Reposition ground grid under the assembly
gridHelper.position.set(center.x, center.y, overallBox.min.z - 1.0);

// ---------------------------------------------------------------------------
// Telemetry Table Population
// ---------------------------------------------------------------------------
const tbody = document.getElementById("telemetryBody");
for (let p of loadedParts) {
  const tr = document.createElement("tr");
  const hex = ((1 << 24) + (Math.round(p.color[0]*255) << 16) + (Math.round(p.color[1]*255) << 8) + Math.round(p.color[2]*255)).toString(16).slice(1);
  const tagClass = p.joint.type === "revolute" ? "revolute" : p.joint.type === "prismatic" ? "prismatic" : "fixed";

  tr.innerHTML = `
    <td>
      <span class="part-badge" style="color: #${hex}; background: #${hex}"></span>
      <strong style="color: #f1f5f9">${p.name}</strong>
    </td>
    <td><span class="tag ${tagClass}">${p.joint.type}</span></td>
    <td style="color: #38bdf8; font-weight: 600">${p.factor !== 0 ? (p.factor > 0 ? "+" : "") + p.factor.toFixed(2) + "x" : "—"}</td>
    <td id="pos_${p.name}" style="color: #e2e8f0; font-weight: 600">0.0°</td>
    <td id="vel_${p.name}" style="color: #94a3b8">0.0 RPM</td>
  `;
  tbody.appendChild(tr);
}

// ---------------------------------------------------------------------------
// Animation & Dynamic Simulation Loop
// ---------------------------------------------------------------------------
let isPlaying = false;
let motorDirection = 1.0;
let driverAngleDeg = 0.0;
let speedRPM = 30.0;
let explodePercent = 0.0;
let isWireframe = false;

function updateKinematics() {
  const driverAngleRad = (driverAngleDeg * motorDirection) * Math.PI / 180.0;
  const normAngle = ((driverAngleDeg * motorDirection) % 360 + 360) % 360;

  for (let p of loadedParts) {
    // Exploded View displacement offset
    const explodeOffsetZ = (explodePercent / 100.0) * (
      p.name.includes("pinion") ? 45.0 :
      p.name.includes("wheel") ? 30.0 :
      p.name.includes("shaft") ? 60.0 :
      p.name.includes("conrod") ? 25.0 :
      p.name.includes("piston") ? 15.0 : 0.0
    );

    const traj = (SCENE_DATA.trajectories && SCENE_DATA.trajectories[p.name]) ? SCENE_DATA.trajectories[p.name] : null;

    if (traj && traj.length > 0) {
      const idx0 = Math.floor(normAngle) % traj.length;
      const idx1 = (idx0 + 1) % traj.length;
      const frac = normAngle - Math.floor(normAngle);

      const pt0 = traj[idx0];
      const pt1 = traj[idx1];

      const posX = pt0.pos[0] + (pt1.pos[0] - pt0.pos[0]) * frac;
      const posY = pt0.pos[1] + (pt1.pos[1] - pt0.pos[1]) * frac;
      const posZ = pt0.pos[2] + (pt1.pos[2] - pt0.pos[2]) * frac;

      let a0 = pt0.angle_deg;
      let a1 = pt1.angle_deg;
      let diff = a1 - a0;
      if (diff > 180) diff -= 360;
      if (diff < -180) diff += 360;
      const curAngleDeg = (p.joint.initial_angle || 0.0) + (a0 + diff * frac);
      const curAngleRad = curAngleDeg * Math.PI / 180.0;

      p.pivot.quaternion.setFromAxisAngle(p.axis, curAngleRad);
      p.pivot.position.set(posX, posY, posZ + explodeOffsetZ);

      // Telemetry update
      const cellPos = document.getElementById("pos_" + p.name);
      if (cellPos) {
        if (p.joint.type === "prismatic" || (p.factor === 0 && pt0.translation_mm !== 0)) {
          cellPos.textContent = (pt0.translation_mm + (pt1.translation_mm - pt0.translation_mm) * frac).toFixed(2) + " mm";
        } else {
          cellPos.textContent = ((curAngleDeg % 360 + 360) % 360).toFixed(1) + "°";
        }
      }

      const cellVel = document.getElementById("vel_" + p.name);
      if (cellVel) {
        cellVel.textContent = (speedRPM * Math.max(0.1, Math.abs(p.factor))).toFixed(1) + (p.joint.type === "prismatic" ? " mm/s" : " RPM");
      }

    } else if (p.joint.type === "revolute") {
      const currentAngle = p.initialAngle + (driverAngleRad * p.factor);
      p.pivot.quaternion.setFromAxisAngle(p.axis, currentAngle);
      p.pivot.position.set(p.origOrigin[0], p.origOrigin[1], p.origOrigin[2] + explodeOffsetZ);

      // Telemetry update
      const degValue = ((currentAngle * 180.0 / Math.PI) % 360.0);
      const normalizedDeg = degValue < 0 ? degValue + 360.0 : degValue;
      const cellPos = document.getElementById("pos_" + p.name);
      if (cellPos) cellPos.textContent = normalizedDeg.toFixed(1) + "°";

      const cellVel = document.getElementById("vel_" + p.name);
      if (cellVel) cellVel.textContent = (speedRPM * Math.abs(p.factor)).toFixed(1) + " RPM";

    } else if (p.joint.type === "prismatic") {
      const disp = p.initialDisp + (driverAngleRad * p.factor);
      p.pivot.position.set(
        p.origOrigin[0] + p.axis.x * disp,
        p.origOrigin[1] + p.axis.y * disp,
        p.origOrigin[2] + p.axis.z * disp + explodeOffsetZ
      );

      const cellPos = document.getElementById("pos_" + p.name);
      if (cellPos) cellPos.textContent = disp.toFixed(2) + " mm";

      const cellVel = document.getElementById("vel_" + p.name);
      if (cellVel) cellVel.textContent = (speedRPM * p.factor * 0.1).toFixed(1) + " mm/s";

    } else {
      p.pivot.position.set(p.origOrigin[0], p.origOrigin[1], p.origOrigin[2]);
    }
  }
}

let lastTime = performance.now();
function animate(currentTime) {
  requestAnimationFrame(animate);

  const dt = (currentTime - lastTime) / 1000.0;
  lastTime = currentTime;

  if (isPlaying) {
    // 1 RPM = 360 deg / 60 sec = 6.0 deg/sec
    driverAngleDeg += speedRPM * 6.0 * dt;
    const sliderVal = (driverAngleDeg % 360.0 + 360.0) % 360.0;
    document.getElementById("angleSlider").value = Math.round(sliderVal);
    document.getElementById("angleVal").textContent = sliderVal.toFixed(1) + "°";
  }

  updateKinematics();
  controls.update();
  renderer.render(scene, camera);
}
requestAnimationFrame(animate);

// ---------------------------------------------------------------------------
// UI Interactions & Event Handlers
// ---------------------------------------------------------------------------
const playBtn = document.getElementById("playBtn");
playBtn.addEventListener("click", () => {
  isPlaying = !isPlaying;
  playBtn.textContent = isPlaying ? "⏸ Pause" : "▶ Run Motor";
  playBtn.classList.toggle("primary", !isPlaying);
  playBtn.classList.toggle("active", isPlaying);
});

const revBtn = document.getElementById("revBtn");
revBtn.addEventListener("click", () => {
  motorDirection *= -1.0;
  revBtn.classList.toggle("active", motorDirection < 0);
});

const angleSlider = document.getElementById("angleSlider");
const angleVal = document.getElementById("angleVal");
angleSlider.addEventListener("input", (e) => {
  driverAngleDeg = parseFloat(e.target.value);
  angleVal.textContent = driverAngleDeg.toFixed(1) + "°";
  if (isPlaying) {
    isPlaying = false;
    playBtn.textContent = "▶ Run Motor";
    playBtn.classList.add("primary");
    playBtn.classList.remove("active");
  }
  updateKinematics();
});

const speedSlider = document.getElementById("speedSlider");
const speedVal = document.getElementById("speedVal");
speedSlider.addEventListener("input", (e) => {
  speedRPM = parseFloat(e.target.value);
  speedVal.textContent = speedRPM.toFixed(0) + " RPM";
});

const explodeSlider = document.getElementById("explodeSlider");
const explodeVal = document.getElementById("explodeVal");
explodeSlider.addEventListener("input", (e) => {
  explodePercent = parseFloat(e.target.value);
  explodeVal.textContent = explodePercent.toFixed(0) + "%";
  updateKinematics();
});

const wireBtn = document.getElementById("wireBtn");
wireBtn.addEventListener("click", () => {
  isWireframe = !isWireframe;
  wireBtn.classList.toggle("active", isWireframe);
  for (let p of loadedParts) {
    p.material.wireframe = isWireframe;
    if (p.edges) p.edges.visible = !isWireframe;
  }
});

const resetCamBtn = document.getElementById("resetCamBtn");
resetCamBtn.addEventListener("click", () => {
  camera.position.set(center.x + maxDim * 1.3, center.y - maxDim * 1.8, center.z + maxDim * 1.4);
  controls.target.copy(center);
  controls.update();
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
</script>
</body>
</html>
"""


def export_motion_html(
    assembly: Assembly,
    mechanism: KinematicMechanism,
    filepath: str,
    title: Optional[str] = None,
    driver_part: Optional[str] = None,
) -> str:
    """
    Compiles assembly solid parts and kinematic relations into an interactive 3D WebGL motion HTML file.
    Uses Three.js with hardware accelerated PBR materials and precise local pivot rotation.
    """
    out_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    from ..backend.occt_backend import OCCTBackend

    backend = OCCTBackend()
    solids = backend.compile(assembly.to_ir())

    if not mechanism.joints:
        raise ValueError("Mechanism has no joints defined. Use asm.add_revolute_joint(...) first.")

    # Determine driver part
    if driver_part is None:
        driver_part = next(iter(mechanism.joints.keys()))

    # Solve unit motion to get transmission factors
    unit_states = mechanism.solve(driver_part, driver_value=1.0)

    parts_data = []
    color_idx = 0

    for part_name, shape in solids.items():
        verts, indices = _extract_part_mesh(shape, deflection=0.5)
        if not verts or not indices:
            continue

        joint = mechanism.joints.get(part_name)

        if joint is not None:
            joint_info = {
                "type": "revolute" if isinstance(joint, RevoluteJoint) else "prismatic",
                "origin": list(joint.origin),
                "axis": list(joint.axis),
                "initial_angle": getattr(joint, "initial_angle_deg", 0.0),
                "initial_disp": getattr(joint, "initial_disp_mm", 0.0),
            }
            state = unit_states.get(part_name)
            if isinstance(joint, RevoluteJoint):
                factor = state.angle_deg if state else 1.0
            else:
                factor = state.translation_mm if state else 1.0
        else:
            # Fixed part
            joint_info = {
                "type": "fixed",
                "origin": [0.0, 0.0, 0.0],
                "axis": [0.0, 0.0, 1.0],
                "initial_angle": 0.0,
                "initial_disp": 0.0,
            }
            factor = 0.0

        # Custom color or palette
        part_ref = assembly._parts.get(part_name)
        if part_ref and getattr(part_ref.node, "color", None):
            color = list(part_ref.node.color)
        else:
            color = PART_COLOR_PALETTE[color_idx % len(PART_COLOR_PALETTE)]
            color_idx += 1

        parts_data.append({
            "name": part_name,
            "vertices": verts,
            "indices": indices,
            "color": color,
            "joint": joint_info,
            "factor": round(factor, 4),
        })

    trajectories = {}
    try:
        trajectories = mechanism.solve_trajectory(driver_part, start_deg=0.0, end_deg=360.0, step_deg=1.0)
    except Exception:
        pass

    scene_data = {
        "parts": parts_data,
        "driver_part": driver_part,
        "trajectories": trajectories,
    }

    doc_title = title or assembly.name.replace("_", " ").upper()
    html = HTML_MOTION_TEMPLATE
    html = html.replace("__ASSEMBLY_TITLE__", doc_title)
    html = html.replace("__SCENE_DATA_JSON__", json.dumps(scene_data))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return out_path
