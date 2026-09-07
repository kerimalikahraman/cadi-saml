"""
cadi_saml.reverse.inspection

Conservative STEP inspection:
Analyzes raw B-Rep geometry without recutting or generating fake assemblies.
Extracts planar faces, inner holes, outer cylinders, PCD bolt patterns, and bounding box.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_IN
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt, gp_Vec


class STEPParseError(RuntimeError):
    """Raised when a STEP file cannot be parsed, transferred, or contains invalid geometry."""
    pass


def _xyz(p):
    return np.array([p.X(), p.Y(), p.Z()], dtype=float)


def _pcd_patterns(holes, tolerance):
    groups = []
    for hole in holes:
        axis, pos = np.array(hole['axis']), np.array(hole['pos'])
        for group in groups:
            ref = group[0]
            if (abs(hole['diameter'] - ref['diameter']) <= tolerance
                    and abs(np.dot(axis, ref['axis'])) > 1 - 1e-8
                    and abs(np.dot(pos - ref['pos'], axis)) <= tolerance):
                group.append(hole)
                break
        else:
            groups.append([hole])
    patterns = []
    for group in groups:
        if len(group) < 3:
            continue
        normal = np.array(group[0]['axis'])
        seed = np.eye(3)[np.argmin(abs(normal))]
        u = np.cross(normal, seed)
        u /= np.linalg.norm(u)
        v = np.cross(normal, u)
        origin = np.array(group[0]['pos'])
        xyz = np.array([h['pos'] for h in group])
        xy = np.column_stack(((xyz - origin) @ u, (xyz - origin) @ v))
        A = np.column_stack((2 * xy, np.ones(len(xy))))
        fit, _, rank, _ = np.linalg.lstsq(A, np.sum(xy ** 2, axis=1), rcond=None)
        if rank < 3:
            continue
        center = fit[:2]
        radii = np.linalg.norm(xy - center, axis=1)
        radius = float(radii.mean())
        if radius <= tolerance or np.max(abs(radii - radius)) > tolerance:
            continue
        angles = np.sort(np.mod(np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0]), 2 * math.pi))
        gaps = np.diff(np.r_[angles, angles[0] + 2 * math.pi])
        if np.max(abs(gaps - 2 * math.pi / len(group))) * radius > tolerance:
            continue
        patterns.append({
            'count': len(group),
            'diameter': group[0]['diameter'],
            'pcd': radius * 2,
            'center': (origin + center[0] * u + center[1] * v).tolist(),
            'axis': normal.tolist(),
            'hole_ids': [h['id'] for h in group],
            'confidence': 'geometric',
            'radial_error_mm': float(np.max(abs(radii - radius))),
        })
    return patterns


def inspect_step(
    step_file_path: str,
    part_name: str = 'inspected_part',
    tolerance: float = 1e-4,
    strict: bool = True,
) -> Dict[str, Any]:
    """
    Pure inspection API for STEP files.
    Extracts geometric metadata, surfaces, cylindrical holes, and bolt patterns.
    Does NOT generate code or modify models.
    """
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('tolerance must be finite and positive')

    p = Path(step_file_path)
    if not p.is_file():
        err_msg = f"STEP file not found: {step_file_path}"
        if strict:
            raise FileNotFoundError(err_msg)
        return {"status": "PARSE_ERROR", "error": err_msg}

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_file_path))
    if status != IFSelect_RetDone:
        err_msg = f"Cannot read STEP (IFSelect error status {status}): {step_file_path}"
        if strict:
            raise STEPParseError(err_msg)
        return {"status": "PARSE_ERROR", "error": err_msg}

    if reader.TransferRoots() == 0:
        err_msg = f"Cannot transfer roots for STEP: {step_file_path}"
        if strict:
            raise STEPParseError(err_msg)
        return {"status": "PARSE_ERROR", "error": err_msg}

    shape = reader.OneShape()
    if shape is None or shape.IsNull():
        err_msg = f"STEP file contains no valid solid geometry: {step_file_path}"
        if strict:
            raise STEPParseError(err_msg)
        return {"status": "PARSE_ERROR", "error": err_msg}

    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    bounds = bbox.Get()
    dx = float(bounds[3] - bounds[0])
    dy = float(bounds[4] - bounds[1])
    dz = float(bounds[5] - bounds[2])

    planar, holes, cylinders = [], [], []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    index = 0

    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        kind = adaptor.GetType()

        if kind == GeomAbs_Plane:
            plane = adaptor.Plane()
            normal = _xyz(plane.Axis().Direction())
            if face.Orientation() == TopAbs_REVERSED:
                normal = -normal
            planar.append({
                'id': f'face_{index}',
                'pos': _xyz(plane.Location()).tolist(),
                'normal': normal.tolist(),
            })

        elif kind == GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            axis = _xyz(cyl.Axis().Direction())
            origin = _xyz(cyl.Location())
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
            point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
            adaptor.D1((u0 + u1) / 2, (v0 + v1) / 2, point, du, dv)
            outward = np.cross(_xyz(du), _xyz(dv))
            if face.Orientation() == TopAbs_REVERSED:
                outward = -outward
            radial = _xyz(point) - origin
            radial -= np.dot(radial, axis) * axis
            internal = np.dot(outward, radial) < 0
            a = _xyz(adaptor.Value((u0 + u1) / 2, v0))
            b = _xyz(adaptor.Value((u0 + u1) / 2, v1))
            ends = sorted([float(np.dot(a - origin, axis)), float(np.dot(b - origin, axis))])
            
            entry = {
                'id': f'hole_{index}' if internal else f'cylinder_{index}',
                'diameter': round(2 * cyl.Radius(), 3),
                'pos': (origin + ends[0] * axis).tolist(),
                'axis': axis.tolist(),
                'depth': round(ends[1] - ends[0], 3),
                'source_face': index,
                'confidence': 'geometric',
                'evidence': 'oriented surface normal versus radial direction',
            }

            if internal:
                eps = max(tolerance * 10, entry['depth'] * 1e-5)
                inside = []
                for t in (ends[0] - eps, ends[1] + eps):
                    p_test = origin + t * axis
                    classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(*p_test), tolerance)
                    inside.append(classifier.State() == TopAbs_IN)
                entry['kind'] = 'blind' if sum(inside) == 1 else ('through' if not any(inside) else 'enclosed_cavity')
                if abs((u1 - u0) - 2 * math.pi) > 1e-5:
                    entry['kind'] = 'partial_cylindrical_cavity'
                    entry['confidence'] = 'provisional'
                holes.append(entry)
            else:
                cylinders.append(entry)

        index += 1
        exp.Next()

    patterns = _pcd_patterns([h for h in holes if h['confidence'] == 'geometric'], tolerance)

    return {
        'status': 'INSPECTED',
        'part_name': part_name,
        'dimensions': {'dx': round(dx, 3), 'dy': round(dy, 3), 'dz': round(dz, 3)},
        'bounding_box': [round(v, 3) for v in bounds],
        'num_planar_faces': len(planar),
        'num_holes': len(holes),
        'num_external_cylinders': len(cylinders),
        'holes': holes,
        'external_cylinders': cylinders,
        'planar_faces': planar,
        'pcd_patterns': patterns,
        'limitations': [
            'Inspection only: geometric features are identified but not compiled into a parametric model.',
            'Use reconstruct_step() to synthesize standalone CADi SAML code.',
        ],
    }
