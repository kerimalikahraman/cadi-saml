"""
cadi_saml.analysis.visualization
================================
Visualization exporters for FEA structural simulation results:
1. VTK (Unstructured Grid ASCII) for ParaView, Blender, and PyVista.
2. Self-contained 3D WebGL HTML interactive viewer with real-time deformation scaling,
   Von-Mises rainbow stress contours, orbit controls, and engineering report card.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from typing import TYPE_CHECKING, List, Tuple

import numpy as np

if TYPE_CHECKING:
    from .fea import FEAResult


def export_vtk(result: FEAResult, filepath: str) -> str:
    """
    Exports the 3D FEA mesh, displacement field, and Von-Mises stress to standard VTK (v3.0) format.
    Fully compatible with ParaView, PyVista, MeshLab, and Blender.
    """
    out_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    nodes = result.nodes if result.nodes is not None else result.raw_solution.nodes
    elements = result.elements if result.elements is not None else result.raw_solution.elements
    displacements = result.nodal_displacements
    nodal_stresses = result.nodal_von_mises
    element_von_mises = (
        result.raw_solution.element_von_mises
        if result.raw_solution is not None
        else []
    )
    num_nodes = len(nodes)
    num_elements = len(elements)

    with open(out_path, "w", encoding="utf-8") as f:
        # Header
        f.write("# vtk DataFile Version 3.0\n")
        f.write(f"CADi FEA Result - {result.study_name} ({result.material.name})\n")
        f.write("ASCII\n")
        f.write("DATASET UNSTRUCTURED_GRID\n")

        # Points
        f.write(f"POINTS {num_nodes} float\n")
        for p in nodes:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")

        # Cells (Tetrahedra: 4 nodes per cell)
        f.write(f"CELLS {num_elements} {num_elements * 5}\n")
        for elem in elements:
            f.write(f"4 {elem[0]} {elem[1]} {elem[2]} {elem[3]}\n")

        # Cell Types (10 = VTK_TETRA)
        f.write(f"CELL_TYPES {num_elements}\n")
        for _ in range(num_elements):
            f.write("10\n")

        # Point Data: Von-Mises Stress & Displacements
        f.write(f"POINT_DATA {num_nodes}\n")
        f.write("SCALARS Von_Mises_Stress_MPa float 1\n")
        f.write("LOOKUP_TABLE default\n")
        for s in nodal_stresses:
            f.write(f"{s:.4f}\n")

        f.write("VECTORS Displacement_mm float\n")
        for u in displacements:
            f.write(f"{u[0]:.6f} {u[1]:.6f} {u[2]:.6f}\n")

        # Cell Data: Element Von-Mises Stress
        if len(element_von_mises) == num_elements:
            f.write(f"CELL_DATA {num_elements}\n")
            f.write("SCALARS Element_Von_Mises_MPa float 1\n")
            f.write("LOOKUP_TABLE default\n")
            for es in element_von_mises:
                f.write(f"{es:.4f}\n")

    return out_path


def _jet_colormap(t: float) -> Tuple[float, float, float]:
    """Smooth rainbow colormap: Blue -> Cyan -> Green -> Yellow -> Red."""
    t = max(0.0, min(1.0, float(t)))
    if t < 0.25:
        f = t / 0.25
        return (0.0, f, 1.0)
    elif t < 0.5:
        f = (t - 0.25) / 0.25
        return (0.0, 1.0, 1.0 - f)
    elif t < 0.75:
        f = (t - 0.5) / 0.25
        return (f, 1.0, 0.0)
    else:
        f = (t - 0.75) / 0.25
        return (1.0, 1.0 - f, 0.0)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CADi FEA: __STUDY_NAME__</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; color: #f8fafc; }
  #canvas3d { width: 100vw; height: 100vh; display: block; }
  
  .card {
    position: absolute;
    top: 20px;
    left: 20px;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 18px 22px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    min-width: 320px;
  }
  .card h2 { font-size: 1.1rem; font-weight: 700; color: #38bdf8; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
  .card .sub { font-size: 0.8rem; color: #94a3b8; margin-bottom: 12px; }
  .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
  .stat-box { background: rgba(30, 41, 59, 0.7); border-radius: 8px; padding: 8px 10px; border: 1px solid rgba(255, 255, 255, 0.05); }
  .stat-box .label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; }
  .stat-box .val { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; }
  
  .badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
  }
  .badge.pass { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }
  .badge.fail { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }

  .controls-card {
    position: absolute;
    bottom: 25px;
    left: 20px;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 14px 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .slider-row { display: flex; align-items: center; gap: 12px; font-size: 0.85rem; color: #cbd5e1; }
  .slider-row input[type="range"] { width: 140px; cursor: pointer; accent-color: #38bdf8; }
  .btn-row { display: flex; gap: 8px; }
  .btn {
    background: #1e293b;
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 600;
    transition: all 0.2s;
  }
  .btn:hover { background: #334155; border-color: #38bdf8; }

  .legend {
    position: absolute;
    top: 25px;
    right: 25px;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .legend-bar {
    width: 16px;
    height: 180px;
    border-radius: 4px;
    background: linear-gradient(to bottom, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff);
  }
  .legend-labels {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 180px;
    font-size: 0.75rem;
    font-weight: 600;
    color: #cbd5e1;
  }
</style>
</head>
<body>
  <canvas id="canvas3d"></canvas>

  <div class="card">
    <h2>⚡ __STUDY_NAME__</h2>
    <div class="sub">Part: <b>__PART_NAME__</b> | Material: <b>__MATERIAL_NAME__</b></div>
    <div class="stat-grid">
      <div class="stat-box">
        <div class="label">Peak Stress</div>
        <div class="val">__PEAK_STRESS__ <span style="font-size:0.75rem;color:#94a3b8">MPa</span></div>
      </div>
      <div class="stat-box">
        <div class="label">Max Deflection</div>
        <div class="val">__MAX_DEFLECTION__ <span style="font-size:0.75rem;color:#94a3b8">mm</span></div>
      </div>
      <div class="stat-box">
        <div class="label">Yield Limit (Sy)</div>
        <div class="val">__YIELD_STRENGTH__ <span style="font-size:0.75rem;color:#94a3b8">MPa</span></div>
      </div>
      <div class="stat-box">
        <div class="label">Safety Factor</div>
        <div class="val">__SAFETY_FACTOR__</div>
      </div>
    </div>
    <div>
      <span class="badge __STATUS_CLASS__">__STATUS_TEXT__</span>
    </div>
  </div>

  <div class="controls-card">
    <div class="slider-row">
      <span>Deform Scale:</span>
      <input type="range" id="scaleSlider" min="0" max="50" step="1" value="__DEF_SCALE__">
      <span id="scaleVal" style="font-weight:700;color:#38bdf8;min-width:35px">__DEF_SCALE__x</span>
    </div>
    <div class="btn-row">
      <button class="btn" id="wireBtn">Toggle Wireframe</button>
      <button class="btn" id="resetBtn">Reset Camera</button>
    </div>
  </div>

  <div class="legend">
    <div class="legend-bar"></div>
    <div class="legend-labels">
      <span>__PEAK_STRESS__ MPa (Max)</span>
      <span>__LEGEND_75__</span>
      <span>__LEGEND_50__</span>
      <span>__LEGEND_25__</span>
      <span>0.0 MPa (Min)</span>
    </div>
  </div>

<script>
const DATA = __MODEL_DATA_JSON__;

const canvas = document.getElementById("canvas3d");
const gl = canvas.getContext("webgl", { antialias: true, alpha: false });
if (!gl) { alert("WebGL not supported"); }

const vsSource = `
  attribute vec3 aPosition;
  attribute vec3 aColor;
  attribute vec3 aNormal;
  uniform mat4 uMatrix;
  uniform vec3 uLightDir;
  varying vec3 vColor;
  void main() {
    gl_Position = uMatrix * vec4(aPosition, 1.0);
    float diff = max(dot(aNormal, uLightDir), 0.0);
    float ambient = 0.35;
    vColor = aColor * (ambient + 0.65 * diff);
  }
`;

const fsSource = `
  precision mediump float;
  varying vec3 vColor;
  void main() {
    gl_FragColor = vec4(vColor, 1.0);
  }
`;

function createShader(gl, type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source);
  gl.compileShader(s);
  return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, createShader(gl, gl.VERTEX_SHADER, vsSource));
gl.attachShader(prog, createShader(gl, gl.FRAGMENT_SHADER, fsSource));
gl.linkProgram(prog);
gl.useProgram(prog);

const aPosLoc = gl.getAttribLocation(prog, "aPosition");
const aColLoc = gl.getAttribLocation(prog, "aColor");
const aNormLoc = gl.getAttribLocation(prog, "aNormal");
const uMatLoc = gl.getUniformLocation(prog, "uMatrix");
const uLightLoc = gl.getUniformLocation(prog, "uLightDir");

let defScale = DATA.default_scale;
let wireframe = false;

let maxR = 10.0;
for (let p of DATA.nodes) {
  let r = Math.hypot(p[0], p[1], p[2]);
  if (r > maxR) maxR = r;
}

let camDist = maxR * 2.6;
let rotX = -0.45;
let rotY = 0.65;
let panX = 0, panY = 0;

function buildMeshBuffers(scale) {
  const posArray = [];
  const colArray = [];
  const normArray = [];

  for (let tri of DATA.triangles) {
    const i0 = tri[0], i1 = tri[1], i2 = tri[2];
    const p0 = [DATA.nodes[i0][0] + DATA.displacements[i0][0] * scale, DATA.nodes[i0][1] + DATA.displacements[i0][1] * scale, DATA.nodes[i0][2] + DATA.displacements[i0][2] * scale];
    const p1 = [DATA.nodes[i1][0] + DATA.displacements[i1][0] * scale, DATA.nodes[i1][1] + DATA.displacements[i1][1] * scale, DATA.nodes[i1][2] + DATA.displacements[i1][2] * scale];
    const p2 = [DATA.nodes[i2][0] + DATA.displacements[i2][0] * scale, DATA.nodes[i2][1] + DATA.displacements[i2][1] * scale, DATA.nodes[i2][2] + DATA.displacements[i2][2] * scale];

    const vA = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]];
    const vB = [p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]];
    let nx = vA[1] * vB[2] - vA[2] * vB[1];
    let ny = vA[2] * vB[0] - vA[0] * vB[2];
    let nz = vA[0] * vB[1] - vA[1] * vB[0];
    const len = Math.hypot(nx, ny, nz) || 1.0;
    nx /= len; ny /= len; nz /= len;

    for (let idx of [i0, i1, i2]) {
      let p = idx === i0 ? p0 : (idx === i1 ? p1 : p2);
      posArray.push(p[0], p[1], p[2]);
      colArray.push(DATA.colors[idx][0], DATA.colors[idx][1], DATA.colors[idx][2]);
      normArray.push(nx, ny, nz);
    }
  }

  const posBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(posArray), gl.STATIC_DRAW);

  const colBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, colBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(colArray), gl.STATIC_DRAW);

  const normBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(normArray), gl.STATIC_DRAW);

  return { posBuf, colBuf, normBuf, count: posArray.length / 3 };
}

let meshBuffers = buildMeshBuffers(defScale);

function render() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0.06, 0.09, 0.16, 1.0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

  const aspect = canvas.width / canvas.height;
  const fov = 45 * Math.PI / 180;
  const f = 1.0 / Math.tan(fov / 2);
  const near = 0.1, far = maxR * 20.0;
  const proj = [
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) / (near - far), -1,
    0, 0, (2 * far * near) / (near - far), 0
  ];

  const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
  
  const mvp = new Float32Array(16);
  const r00 = cosY, r01 = sinX * sinY, r02 = -cosX * sinY;
  const r10 = 0,    r11 = cosX,        r12 = sinX;
  const r20 = sinY, r21 = -sinX * cosY, r22 = cosX * cosY;

  mvp[0] = proj[0] * r00;
  mvp[1] = proj[5] * r01;
  mvp[2] = proj[10] * r02;
  mvp[3] = -r02;

  mvp[4] = proj[0] * r10;
  mvp[5] = proj[5] * r11;
  mvp[6] = proj[10] * r12;
  mvp[7] = -r12;

  mvp[8] = proj[0] * r20;
  mvp[9] = proj[5] * r21;
  mvp[10] = proj[10] * r22;
  mvp[11] = -r22;

  mvp[12] = proj[0] * panX;
  mvp[13] = proj[5] * panY;
  mvp[14] = proj[10] * (-camDist) + proj[14];
  mvp[15] = camDist;

  gl.uniformMatrix4fv(uMatLoc, false, mvp);
  gl.uniform3f(uLightLoc, 0.577, 0.577, 0.577);

  gl.bindBuffer(gl.ARRAY_BUFFER, meshBuffers.posBuf);
  gl.vertexAttribPointer(aPosLoc, 3, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(aPosLoc);

  gl.bindBuffer(gl.ARRAY_BUFFER, meshBuffers.colBuf);
  gl.vertexAttribPointer(aColLoc, 3, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(aColLoc);

  gl.bindBuffer(gl.ARRAY_BUFFER, meshBuffers.normBuf);
  gl.vertexAttribPointer(aNormLoc, 3, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(aNormLoc);

  const drawMode = wireframe ? gl.LINE_LOOP : gl.TRIANGLES;
  gl.drawArrays(drawMode, 0, meshBuffers.count);
}

window.addEventListener("resize", render);

let isDown = false, isRight = false, lastX = 0, lastY = 0;
canvas.addEventListener("mousedown", e => {
  isDown = true;
  isRight = e.button === 2;
  lastX = e.clientX;
  lastY = e.clientY;
});
window.addEventListener("mouseup", () => isDown = false);
canvas.addEventListener("contextmenu", e => e.preventDefault());
canvas.addEventListener("mousemove", e => {
  if (!isDown) return;
  const dx = e.clientX - lastX;
  const dy = e.clientY - lastY;
  lastX = e.clientX;
  lastY = e.clientY;

  if (isRight) {
    panX += dx * 0.05 * (camDist / maxR);
    panY -= dy * 0.05 * (camDist / maxR);
  } else {
    rotY += dx * 0.01;
    rotX += dy * 0.01;
  }
  render();
});
canvas.addEventListener("wheel", e => {
  camDist *= e.deltaY > 0 ? 1.08 : 0.92;
  render();
});

const slider = document.getElementById("scaleSlider");
const scaleVal = document.getElementById("scaleVal");
slider.addEventListener("input", e => {
  defScale = parseFloat(e.target.value);
  scaleVal.textContent = defScale.toFixed(0) + "x";
  meshBuffers = buildMeshBuffers(defScale);
  render();
});

document.getElementById("wireBtn").addEventListener("click", () => {
  wireframe = !wireframe;
  render();
});

document.getElementById("resetBtn").addEventListener("click", () => {
  camDist = maxR * 2.6;
  rotX = -0.45; rotY = 0.65;
  panX = 0; panY = 0;
  render();
});

render();
</script>
</body>
</html>
"""


def export_interactive_html(
    result: FEAResult,
    filepath: str,
    deformation_scale: float = 10.0,
) -> str:
    """
    Generates a 100% self-contained, standalone 3D WebGL HTML simulation viewer.
    """
    out_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    nodes = result.nodes if result.nodes is not None else result.raw_solution.nodes
    elements = result.elements if result.elements is not None else result.raw_solution.elements
    displacements = result.nodal_displacements
    nodal_stresses = result.nodal_von_mises

    # Extract boundary triangles
    face_counts = Counter()
    face_orientations = {}
    for e in elements:
        faces = [
            (e[0], e[1], e[2]),
            (e[0], e[2], e[3]),
            (e[0], e[3], e[1]),
            (e[1], e[3], e[2]),
        ]
        for f in faces:
            sf = tuple(sorted(f))
            face_counts[sf] += 1
            face_orientations[sf] = f

    boundary_triangles = [
        face_orientations[sf] for sf, count in face_counts.items() if count == 1
    ]

    max_stress = max(0.001, float(result.max_von_mises_mpa))
    colors = []
    for s in nodal_stresses:
        t = s / max_stress
        r, g, b = _jet_colormap(t)
        colors.append([round(r, 3), round(g, 3), round(b, 3)])

    center = np.mean(nodes, axis=0)
    centered_nodes = (nodes - center).tolist()
    disp_list = displacements.tolist()
    tri_list = [[int(idx) for idx in tri] for tri in boundary_triangles]

    model_data = {
        "nodes": centered_nodes,
        "displacements": disp_list,
        "triangles": tri_list,
        "colors": colors,
        "max_stress": max_stress,
        "yield_strength": result.yield_strength_mpa,
        "safety_factor": result.safety_factor,
        "is_safe": result.is_safe,
        "max_displacement": result.max_displacement_mm,
        "default_scale": deformation_scale,
    }

    status_class = "pass" if result.is_safe else "fail"
    status_text = "PASS (Safe)" if result.is_safe else "WARNING: YIELD EXCEEDED"

    html = HTML_TEMPLATE
    html = html.replace("__STUDY_NAME__", str(result.study_name))
    html = html.replace("__PART_NAME__", str(result.part_name))
    html = html.replace("__MATERIAL_NAME__", str(result.material.name))
    html = html.replace("__PEAK_STRESS__", f"{result.max_von_mises_mpa:.1f}")
    html = html.replace("__MAX_DEFLECTION__", f"{result.max_displacement_mm:.3f}")
    html = html.replace("__YIELD_STRENGTH__", f"{result.yield_strength_mpa:.1f}")
    html = html.replace("__SAFETY_FACTOR__", f"{result.safety_factor:.2f}")
    html = html.replace("__STATUS_CLASS__", status_class)
    html = html.replace("__STATUS_TEXT__", status_text)
    html = html.replace("__DEF_SCALE__", f"{deformation_scale:.0f}")
    html = html.replace("__LEGEND_75__", f"{result.max_von_mises_mpa * 0.75:.1f}")
    html = html.replace("__LEGEND_50__", f"{result.max_von_mises_mpa * 0.50:.1f}")
    html = html.replace("__LEGEND_25__", f"{result.max_von_mises_mpa * 0.25:.1f}")
    html = html.replace("__MODEL_DATA_JSON__", json.dumps(model_data))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return out_path


def export_image(
    result: FEAResult,
    filepath: str,
    deformation_scale: float = 10.0,
    dpi: int = 150,
) -> str:
    """
    Renders high-resolution 2D/3D PNG static image of the FEA simulation results:
    - 3D deformed surface mesh colored by Von Mises stress contour heatmap
    - Colorbar with MPa stress gradient
    - Engineering summary card with regional safety factors and material breakdown
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    out_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    nodes = result.nodes if result.nodes is not None else result.raw_solution.nodes
    elements = result.elements if result.elements is not None else result.raw_solution.elements
    displacements = result.nodal_displacements
    nodal_stresses = result.nodal_von_mises

    # Extract boundary surface triangles
    face_counts = Counter()
    face_orientations = {}
    for e in elements:
        faces = [
            (e[0], e[1], e[2]),
            (e[0], e[2], e[3]),
            (e[0], e[3], e[1]),
            (e[1], e[3], e[2]),
        ]
        for f in faces:
            sf = tuple(sorted(f))
            face_counts[sf] += 1
            face_orientations[sf] = f

    boundary_triangles = [
        face_orientations[sf] for sf, count in face_counts.items() if count == 1
    ]

    # Deformed coordinates
    def_nodes = nodes + displacements * float(deformation_scale)

    fig = plt.figure(figsize=(13, 6), dpi=dpi, facecolor="#0f172a")
    ax = fig.add_subplot(1, 2, 1, projection="3d", facecolor="#0f172a")

    # Build 3D polygons
    max_stress = max(0.01, float(result.max_von_mises_mpa))
    norm = Normalize(vmin=0.0, vmax=max_stress)
    cmap = plt.cm.turbo

    tri_polys = []
    face_colors = []
    for tri in boundary_triangles:
        tri_pts = def_nodes[list(tri)]
        tri_polys.append(tri_pts)
        mean_s = float(np.mean(nodal_stresses[list(tri)]))
        face_colors.append(cmap(norm(mean_s)))

    mesh_col = Poly3DCollection(tri_polys, facecolors=face_colors, edgecolors="#1e293b", linewidths=0.2, alpha=0.95)
    ax.add_collection3d(mesh_col)

    # Set axes limits
    all_pts = def_nodes
    min_b = np.min(all_pts, axis=0)
    max_b = np.max(all_pts, axis=0)
    mid = 0.5 * (min_b + max_b)
    max_span = 0.5 * max(max_b - min_b)
    ax.set_xlim(mid[0] - max_span, mid[0] + max_span)
    ax.set_ylim(mid[1] - max_span, mid[1] + max_span)
    ax.set_zlim(mid[2] - max_span, mid[2] + max_span)

    ax.set_title(f"{result.study_name} - Von Mises Stress", color="#38bdf8", fontsize=11, fontweight="bold", pad=8)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor("#334155")
    ax.yaxis.pane.set_edgecolor("#334155")
    ax.zaxis.pane.set_edgecolor("#334155")

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.1)
    cb.set_label("Von Mises Stress (MPa)", color="#f1f5f9", fontsize=9, fontweight="bold")
    cb.ax.tick_params(colors="#f1f5f9", labelsize=8)

    # Panel 2: Summary Card and Regional Breakdown
    ax_info = fig.add_subplot(1, 2, 2, facecolor="#0f172a")
    ax_info.axis("off")

    status_color = "#34d399" if result.is_safe else "#f87171"
    status_text = "PASSED (Safe)" if result.is_safe else "YIELD EXCEEDED"

    lines_text = [
        f"Study: {result.study_name}",
        f"Part: {result.part_name}",
        f"Mesh: {result.num_nodes:,} Nodes | {result.num_elements:,} Elements",
        "-" * 42,
        f"Peak Stress       : {result.max_von_mises_mpa:.2f} MPa",
        f"Max Deflection    : {result.max_displacement_mm:.4f} mm",
        f"Target Safety FoS : >= {result.required_safety_factor:.2f}",
        f"Overall Safety FoS: {result.safety_factor:.2f}",
        f"Status            : {status_text}",
        "=" * 42,
    ]

    regional_res = getattr(result, "regional_results", None)
    if regional_res:
        lines_text.append("MATERIAL REGIONS BREAKDOWN:")
        for r_id, reg in regional_res.items():
            r_icon = "[PASS]" if reg.is_safe else "[CRIT]"
            lines_text.append(f"• {reg.region_id} ({reg.material_name}):")
            lines_text.append(f"   Peak: {reg.max_von_mises_mpa:.1f} MPa | Sy: {reg.yield_strength_mpa:.1f} MPa | FoS: {reg.safety_factor:.2f} {r_icon}")
    else:
        lines_text.append(f"Material: {result.material.name} (Sy={result.yield_strength_mpa:.1f} MPa)")

    info_str = "\n".join(lines_text)
    ax_info.text(
        0.05, 0.95, info_str,
        transform=ax_info.transAxes,
        fontsize=9,
        fontfamily="monospace",
        color="#f8fafc",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.8", facecolor="#1e293b", edgecolor="#334155", linewidth=1.5),
    )

    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return out_path

