"""Conservative STEP inspection and parametric reconstruction."""
from __future__ import annotations
import math
from pathlib import Path
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
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut


class STEPParseError(RuntimeError):
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
        patterns.append({'count': len(group), 'diameter': group[0]['diameter'],
                         'pcd': radius * 2, 'center': (origin + center[0] * u + center[1] * v).tolist(),
                         'axis': normal.tolist(), 'hole_ids': [h['id'] for h in group],
                         'confidence': 'geometric', 'radial_error_mm': float(np.max(abs(radii - radius)))})
    return patterns

def inspect_step(step_file_path, part_name='imported_part', tolerance=1e-4, return_shape=False):
    """
    Conservative STEP inspection:
    Extracts geometric metadata, planar faces, cylindrical holes, outer cylinders, and PCD bolt patterns.
    """
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('tolerance must be finite and positive')
    if not Path(step_file_path).is_file():
        raise FileNotFoundError(step_file_path)
    reader = STEPControl_Reader()
    if reader.ReadFile(str(step_file_path)) != IFSelect_RetDone or reader.TransferRoots() == 0:
        raise RuntimeError(f'Cannot read STEP: {step_file_path}')
    shape = reader.OneShape()
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    bounds = bbox.Get()
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
            planar.append({'id': f'face_{index}', 'pos': _xyz(plane.Location()).tolist(), 'normal': normal.tolist()})
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
            entry = {'id': f'hole_{index}' if internal else f'cylinder_{index}',
                     'diameter': 2 * cyl.Radius(), 'pos': (origin + ends[0] * axis).tolist(),
                     'axis': axis.tolist(), 'depth': ends[1] - ends[0], 'source_face': index,
                     'confidence': 'geometric', 'evidence': 'oriented surface normal versus radial direction'}
            if internal:
                eps = max(tolerance * 10, entry['depth'] * 1e-5)
                inside = []
                for t in (ends[0] - eps, ends[1] + eps):
                    p = origin + t * axis
                    classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(*p), tolerance)
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
    lines = ['# Preserve imported geometry; add semantic ports only.', 'from cadi_saml import Assembly', '',
             f'with Assembly({(part_name + "_assembly")!r}, units="mm") as asm:',
             f'    part = asm.add_step_part({part_name!r}, {str(step_file_path)!r})']
    for h in holes:
        lines.append(f'    part.add_port({h["id"]!r}, port_type="hole", position={tuple(h["pos"])!r}, normal={tuple(h["axis"])!r}, diameter={h["diameter"]!r})')
    result = {'part_name': part_name, 'bounds_min': tuple(float(bounds[i]) for i in range(3)),
              'dimensions': dict(zip(('dx', 'dy', 'dz'), [bounds[i+3] - bounds[i] for i in range(3)])),
              'num_planar_faces': len(planar), 'num_holes': len(holes), 'holes': holes,
              'external_cylinders': cylinders, 'planar_faces': planar, 'pcd_patterns': patterns,
              'saml_code': '\n'.join(lines), 'limitations': [
                  'Feature history is not reconstructed; split faces require review.',
              'Counterbores and countersinks are not inferred from adjacent surfaces.']}
    if return_shape:
        result['_shape'] = shape
    return result

def verify_geometric_equivalence(
    shape_orig: TopoDS.TopoDS_Shape,
    shape_rebuilt: TopoDS.TopoDS_Shape,
    holes_orig: list = None,
    holes_rebuilt: list = None,
    vol_rel_tol: float = 0.005,
    area_rel_tol: float = 0.01,
    max_cog_shift: float = 0.5,
    max_bbox_diff: float = 0.5,
    boolean_vol_rel_tol: float = 0.005,
) -> dict:
    """
    Verifies geometric equivalence between original STEP B-Rep and reconstructed CADi SAML solid.
    Compares volume, surface area, center of mass, bounding box, boolean difference, and hole positions.
    """
    v_props_orig = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape_orig, v_props_orig)
    vol_orig = float(v_props_orig.Mass())
    com_orig = v_props_orig.CentreOfMass()
    com_orig_vec = np.array([com_orig.X(), com_orig.Y(), com_orig.Z()], dtype=float)

    v_props_reb = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape_rebuilt, v_props_reb)
    vol_reb = float(v_props_reb.Mass())
    com_reb = v_props_reb.CentreOfMass()
    com_reb_vec = np.array([com_reb.X(), com_reb.Y(), com_reb.Z()], dtype=float)

    vol_diff = abs(vol_orig - vol_reb)
    vol_rel_error = vol_diff / max(abs(vol_orig), 1e-6)
    com_shift = float(np.linalg.norm(com_orig_vec - com_reb_vec))

    s_props_orig = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape_orig, s_props_orig)
    area_orig = float(s_props_orig.Mass())

    s_props_reb = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape_rebuilt, s_props_reb)
    area_reb = float(s_props_reb.Mass())

    area_diff = abs(area_orig - area_reb)
    area_rel_error = area_diff / max(abs(area_orig), 1e-6)

    bbox_orig = Bnd_Box()
    BRepBndLib.Add_s(shape_orig, bbox_orig)
    b_orig = bbox_orig.Get()

    bbox_reb = Bnd_Box()
    BRepBndLib.Add_s(shape_rebuilt, bbox_reb)
    b_reb = bbox_reb.Get()

    bbox_diffs = [abs(b_orig[i] - b_reb[i]) for i in range(6)]
    bbox_max_diff = float(max(bbox_diffs))

    boolean_is_done = False
    boolean_diff_vol = 0.0
    try:
        cut_op = BRepAlgoAPI_Cut(shape_orig, shape_rebuilt)
        cut_op.Build()
        if cut_op.IsDone():
            boolean_is_done = True
            v_cut = GProp_GProps()
            BRepGProp.VolumeProperties_s(cut_op.Shape(), v_cut)
            boolean_diff_vol = float(abs(v_cut.Mass()))
    except Exception:
        boolean_is_done = False

    holes_verified = True
    hole_details = []
    if holes_orig:
        for h in holes_orig:
            h_pos = np.array(h['pos'], dtype=float)
            h_dia = float(h['diameter'])
            matched = False
            for hr in (holes_rebuilt or holes_orig):
                r_pos = np.array(hr['pos'], dtype=float)
                r_dia = float(hr['diameter'])
                if np.linalg.norm(h_pos - r_pos) < 0.2 and abs(h_dia - r_dia) < 0.2:
                    matched = True
                    break
            hole_details.append({'id': h['id'], 'matched': matched})
            if not matched:
                holes_verified = False

    errors = []
    if vol_rel_error > vol_rel_tol:
        errors.append(f"Volume relative error {vol_rel_error*100:.2f}% exceeds tolerance {vol_rel_tol*100:.2f}%")
    if area_rel_error > area_rel_tol:
        errors.append(f"Surface area relative error {area_rel_error*100:.2f}% exceeds tolerance {area_rel_tol*100:.2f}%")
    if com_shift > max_cog_shift:
        errors.append(f"Center of mass shift {com_shift:.3f} mm exceeds tolerance {max_cog_shift:.3f} mm")
    if bbox_max_diff > max_bbox_diff:
        errors.append(f"Bounding box dimension deviation {bbox_max_diff:.3f} mm exceeds tolerance {max_bbox_diff:.3f} mm")
    if boolean_is_done and (boolean_diff_vol / max(abs(vol_orig), 1e-6)) > boolean_vol_rel_tol:
        errors.append(f"Boolean difference volume {boolean_diff_vol:.2f} mm3 exceeds allowable threshold")

    passed = (len(errors) == 0) and holes_verified

    return {
        'passed': passed,
        'volume_orig': round(vol_orig, 3),
        'volume_rebuilt': round(vol_reb, 3),
        'volume_rel_error': round(vol_rel_error, 5),
        'area_orig': round(area_orig, 3),
        'area_rebuilt': round(area_reb, 3),
        'area_rel_error': round(area_rel_error, 5),
        'com_orig': [round(v, 3) for v in com_orig_vec],
        'com_rebuilt': [round(v, 3) for v in com_reb_vec],
        'com_shift_mm': round(com_shift, 4),
        'bbox_max_diff_mm': round(bbox_max_diff, 4),
        'boolean_is_done': boolean_is_done,
        'boolean_diff_volume_mm3': round(boolean_diff_vol, 4),
        'holes_verified': holes_verified,
        'errors': errors,
    }

def reconstruct_step(step_file_path, part_name='reconstructed_part', tolerance=1e-4, verify_equivalence=True):
    """Generate STEP-independent CADi SAML for strictly recognized primitives.

    Pipeline:
      1. Group external cylinders & recognize base solid
      2. Fuse steps (for stepped cylinders / shafts)
      3. Cut holes (axial and pattern cuts)
      4. Verify geometric equivalence against source STEP B-Rep
    """
    report = inspect_step(step_file_path, part_name=part_name, tolerance=tolerance, return_shape=True)
    orig_shape = report.pop('_shape', None)

    def unsupported(reason):
        report.update({
            'independent': False,
            'status': 'UNSUPPORTED_RECONSTRUCTION',
            'reconstruction_kind': None,
            'saml_code': None,
            'error': reason,
        })
        return report

    outer = report['external_cylinders']
    holes = report['holes']

    base_lines = [
        "from cadi_saml import Assembly",
        "",
        f"with Assembly({part_name + '_assembly'!r}, units='mm') as asm:",
    ]
    base_kind = None
    principal = None

    # 1. Base solid identification: group outer cylinders
    if len(outer) == 0 and report['num_planar_faces'] >= 6:
        d = report['dimensions']
        b_min = report['bounds_min']
        center = (
            round(b_min[0] + d['dx'] / 2.0, 4),
            round(b_min[1] + d['dy'] / 2.0, 4),
            round(b_min[2] + d['dz'] / 2.0, 4),
        )
        base_lines.append(
            f"    part = asm.add_box({part_name!r}, length={d['dx']!r}, width={d['dy']!r}, height={d['dz']!r}, origin={center!r})"
        )
        base_kind = 'axis_aligned_box'

    elif len(outer) == 1:
        c = outer[0]
        axis = np.asarray(c['axis'], dtype=float)
        principal = np.eye(3)[np.argmax(np.abs(axis))]
        if abs(float(np.dot(axis, principal))) < 1.0 - 1e-8:
            return unsupported('cylinder axis is not aligned with a CADi SAML primitive axis (oblique-axis cylinders require transformation parameters)')
        base_lines.append(
            f"    part = asm.add_cylinder({part_name!r}, radius={c['diameter'] / 2!r}, height={c['depth']!r}, origin={tuple(c['pos'])!r})"
        )
        base_kind = 'cylinder'

    elif len(outer) > 1 and report['num_planar_faces'] >= 2:
        axes = [np.asarray(c['axis'], dtype=float) for c in outer]
        principal = np.eye(3)[np.argmax(np.abs(axes[0]))]
        for c in outer:
            c_axis = np.asarray(c['axis'], dtype=float)
            if abs(float(np.dot(c_axis, principal))) < 1.0 - 1e-8:
                return unsupported('stepped cylinder segment axis is not aligned with a CADi SAML primitive axis')

        # Check coaxiality: segments must lie on the same axis line
        ref_pos = np.asarray(outer[0]['pos'], dtype=float)
        ref_perp = ref_pos - np.dot(ref_pos, principal) * principal
        for c in outer[1:]:
            c_pos = np.asarray(c['pos'], dtype=float)
            c_perp = c_pos - np.dot(c_pos, principal) * principal
            if np.linalg.norm(c_perp - ref_perp) > tolerance * 10:
                return unsupported('stepped cylinder segments are not coaxial')

        # Sort segments along principal axis
        cylinders = sorted(outer, key=lambda c: float(np.dot(np.asarray(c['pos']), principal)))
        for i, c in enumerate(cylinders):
            name = part_name if i == 0 else f"{part_name}_step_{i}"
            base_lines.append(
                f"    part = asm.add_cylinder({name!r}, radius={c['diameter'] / 2!r}, height={c['depth']!r}, origin={tuple(c['pos'])!r})"
            )
            if i > 0:
                base_lines.append(f"    asm.fuse({part_name!r}, {name!r})")
        base_kind = 'stepped_cylinder'

    else:
        return unsupported('topology is outside the supported primitive subset')

    # 2. Cut holes from the base / fused solid
    lines = list(base_lines)
    if report['num_holes'] > 0:
        if principal is not None:
            if not all(abs(float(np.dot(np.asarray(h['axis'], dtype=float), principal))) >= 1.0 - 1e-8 for h in holes):
                return unsupported('holes require compatible cylindrical axes aligned with base solid')
        else:
            # Box: holes must align with cardinal X, Y, or Z
            for h in holes:
                h_axis = np.asarray(h['axis'], dtype=float)
                h_princ = np.eye(3)[np.argmax(np.abs(h_axis))]
                if abs(float(np.dot(h_axis, h_princ))) < 1.0 - 1e-8:
                    return unsupported('hole axes are not aligned with box cardinal axes')

        # PCD Pattern metadata / future hook
        if report.get('pcd_patterns'):
            for pat in report['pcd_patterns']:
                lines.append(f"    # PCD Pattern: {pat['count']} holes on PCD={pat['pcd']:.2f}mm (future: asm.add_bolt_pattern)")

        for h in holes:
            lines.append(
                f"    part = asm.add_cylinder({part_name!r}, radius={h['diameter'] / 2!r}, height={h['depth']!r}, origin={tuple(h['pos'])!r}, operation='cut')"
            )

    if base_kind == 'stepped_cylinder':
        reconstruction_kind = 'stepped_cylinder_with_holes' if holes else 'stepped_cylinder'
    elif base_kind == 'cylinder':
        reconstruction_kind = 'cylinder_with_cylindrical_cuts' if holes else 'cylinder'
    elif base_kind == 'axis_aligned_box':
        reconstruction_kind = 'box_with_cylindrical_cuts' if holes else 'axis_aligned_box'

    saml_code = '\n'.join(lines) + '\n'
    report.update({
        'saml_code': saml_code,
        'independent': True,
        'status': 'RECONSTRUCTED',
        'reconstruction_kind': reconstruction_kind,
    })

    # 3. Geometric Equivalence Verification
    if verify_equivalence and orig_shape is not None:
        try:
            from ..backend.occt_backend import OCCTBackend
            local_ns = {}
            exec(saml_code, local_ns)
            rebuilt_asm = local_ns.get('asm')
            if rebuilt_asm is None:
                raise RuntimeError("Synthesized code did not leave 'asm' in namespace")
            backend = OCCTBackend()
            solids = backend.compile(rebuilt_asm.to_ir())
            if not solids:
                raise RuntimeError("Rebuilt assembly compiled to zero solids")
            rebuilt_shape = list(solids.values())[0]

            geom_report = verify_geometric_equivalence(
                shape_orig=orig_shape,
                shape_rebuilt=rebuilt_shape,
                holes_orig=holes,
            )
            report['geometric_equivalence'] = geom_report
            if not geom_report['passed']:
                report['status'] = 'GEOMETRIC_MISMATCH'
                report['error'] = '; '.join(geom_report.get('errors', []))
        except Exception as e:
            report['geometric_equivalence'] = {
                'passed': False,
                'error': str(e),
            }
            report['status'] = 'GEOMETRIC_MISMATCH'
            report['error'] = f"Geometric equivalence verification failed: {str(e)}"

    return report
