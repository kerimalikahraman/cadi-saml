"""Sampled motion inspection and scalar transmission closure checks."""
import math
from itertools import combinations
import numpy as np
from .joints import RevoluteJoint, PrismaticJoint
from .relations import (
    BeltRelation,
    FourBarRelation,
    GearRelation,
    PlanetaryRelation,
    RackPinionRelation,
    ScrewRelation,
    SliderCrankRelation,
    SynchronizedGroupRelation,
)


def linear_relations(mechanism):
    edges, errors = [], []
    for rel in mechanism.relations:
        if isinstance(rel, (GearRelation, BeltRelation)):
            a, b, factor, kinds = rel.driver_part, rel.driven_part, rel.ratio * (-1 if rel.reverse else 1), (RevoluteJoint, RevoluteJoint)
        elif isinstance(rel, RackPinionRelation):
            a, b, factor, kinds = rel.pinion_part, rel.rack_part, math.pi / 180 * rel.pitch_radius * (-1 if rel.reverse else 1), (RevoluteJoint, PrismaticJoint)
        elif isinstance(rel, ScrewRelation):
            a, b, factor, kinds = rel.screw_part, rel.nut_part, rel.pitch_mm / 360, (RevoluteJoint, PrismaticJoint)
        elif isinstance(rel, SliderCrankRelation):
            names = (rel.crank_part, rel.conrod_part, rel.piston_part)
            if any(n not in mechanism.joints for n in names):
                errors.append('Slider-crank references missing joints')
            elif not all(isinstance(mechanism.joints[n], kind) for n, kind in zip(names, (RevoluteJoint, RevoluteJoint, PrismaticJoint))):
                errors.append('Slider-crank joint types must be revolute/revolute/prismatic')
            if not all(math.isfinite(x) for x in (rel.crank_radius, rel.conrod_length, rel.offset)) or min(rel.crank_radius, rel.conrod_length) <= 0:
                errors.append('Slider-crank lengths must be finite and positive')
            if tuple(rel.slide_axis) != (1.0, 0.0, 0.0) or rel.offset != 0:
                errors.append('Current slider-crank motion supports inline +X slides only')
            continue
        elif isinstance(rel, PlanetaryRelation):
            names = [rel.sun_part, rel.carrier_part, rel.ring_part] + list(rel.planet_parts)
            missing = [n for n in names if n not in mechanism.joints]
            if missing:
                errors.append(f"PlanetaryRelation references missing joints: {', '.join(missing)}")
            elif not all(isinstance(mechanism.joints[n], RevoluteJoint) for n in names):
                errors.append("All planetary mechanism components must have RevoluteJoint")

            if rel.z_ring != rel.z_sun + 2 * rel.z_planet:
                errors.append(
                    f"Planetary tooth count inconsistent: z_ring ({rel.z_ring}) != "
                    f"z_sun ({rel.z_sun}) + 2 * z_planet ({rel.z_planet})"
                )
            if min(rel.z_sun, rel.z_ring, rel.z_planet) <= 0:
                errors.append("Planetary tooth counts must be positive integers")

            zs, zr, zp = float(rel.z_sun), float(rel.z_ring), float(rel.z_planet)
            if rel.fixed_component == "ring" or rel.fixed_component is None:
                # Ring is fixed: sun drives carrier
                edges.append((rel.sun_part, rel.carrier_part, zs / (zs + zr)))
                planet_ratio = (zs / (zs + zr)) - (zs / zp) * (zr / (zs + zr))
                for p_part in rel.planet_parts:
                    edges.append((rel.sun_part, p_part, planet_ratio))
            elif rel.fixed_component == "carrier":
                # Carrier is fixed: sun drives ring
                edges.append((rel.sun_part, rel.ring_part, -zs / zr))
                planet_ratio = -zs / zp
                for p_part in rel.planet_parts:
                    edges.append((rel.sun_part, p_part, planet_ratio))
            elif rel.fixed_component == "sun":
                # Sun is fixed: ring drives carrier
                edges.append((rel.ring_part, rel.carrier_part, zr / (zs + zr)))
                planet_ratio = (zr / (zs + zr)) * (1.0 + zs / zp)
                for p_part in rel.planet_parts:
                    edges.append((rel.ring_part, p_part, planet_ratio))
            else:
                edges.append((rel.sun_part, rel.carrier_part, zs / (zs + zr)))
                planet_ratio = (zs / (zs + zr)) - (zs / zp) * (zr / (zs + zr))
                for p_part in rel.planet_parts:
                    edges.append((rel.sun_part, p_part, planet_ratio))
            continue
        elif isinstance(rel, SynchronizedGroupRelation):
            a = rel.driver_part
            for b in rel.driven_parts:
                ratio = rel.get_ratio_for(b) * (-1.0 if rel.reverse else 1.0)
                if not math.isfinite(ratio) or abs(ratio) < 1e-12:
                    errors.append(f'Invalid transmission factor: {a} -> {b}')
                if a not in mechanism.joints or b not in mechanism.joints:
                    errors.append(f'Missing or incompatible joints: {a} -> {b}')
                edges.append((a, b, ratio))
            continue
        else:
            errors.append(f'Unsupported relation: {type(rel).__name__}')
            continue
        if not math.isfinite(factor) or abs(factor) < 1e-12:
            errors.append(f'Invalid transmission factor: {a} -> {b}')
        if not isinstance(mechanism.joints.get(a), kinds[0]) or not isinstance(mechanism.joints.get(b), kinds[1]):
            errors.append(f'Missing or incompatible joints: {a} -> {b}')
        edges.append((a, b, factor))
    return edges, errors


def validate_mechanism(mechanism, driver_part):
    edges, errors = linear_relations(mechanism)
    if driver_part not in mechanism.joints:
        errors.append(f'Unknown driver joint: {driver_part}')
    # Check every transmission component, including disconnected loops, at a nonzero state.
    assigned = {}
    for seed in mechanism.joints:
        if seed in assigned:
            continue
        assigned[seed] = 1.0
        queue = [seed]
        while queue:
            current = queue.pop()
            for a, b, ratio in edges:
                if not math.isfinite(ratio) or abs(ratio) < 1e-12:
                    continue
                if current == a:
                    other, value = b, assigned[a] * ratio
                elif current == b:
                    other, value = a, assigned[b] / ratio
                else:
                    continue
                if other not in assigned:
                    assigned[other] = value
                    queue.append(other)
                elif not math.isclose(assigned[other], value, rel_tol=1e-8, abs_tol=1e-10):
                    errors.append(f'Inconsistent closed transmission loop at {a} -> {b}')
    reachable = {driver_part}
    links = [(a, b) for a, b, _ in edges]
    for rel in mechanism.relations:
        if isinstance(rel, SliderCrankRelation):
            links.extend([(rel.crank_part, rel.conrod_part), (rel.crank_part, rel.piston_part)])
        elif isinstance(rel, PlanetaryRelation):
            links.extend([
                (rel.sun_part, rel.carrier_part),
                (rel.carrier_part, rel.ring_part),
            ])
            for p in rel.planet_parts:
                links.append((rel.carrier_part, p))
    changed = True
    while changed:
        previous = len(reachable)
        for a, b in links:
            if a in reachable or b in reachable:
                reachable.update((a, b))
        changed = len(reachable) != previous
    return {'valid': not errors, 'errors': sorted(set(errors)),
            'disconnected_parts': sorted(set(mechanism.joints) - reachable),
            'scope': 'Scalar transmissions and inline planar slider-crank; spatial linkage closure is unsupported.'}


def solve_loop_closure(mechanism, driver_part, value=0.0):
    """Solve consistent scalar gear/belt/rack/screw loops by least squares."""
    report = validate_mechanism(mechanism, driver_part)
    if not report['valid']:
        raise ValueError('; '.join(report['errors']))
    if any(isinstance(r, SliderCrankRelation) for r in mechanism.relations):
        raise ValueError('Loop closure supports linear transmissions only')
    if not math.isfinite(value):
        raise ValueError('Driver value must be finite')
    names = [n for n in mechanism.joints if n not in report['disconnected_parts']]
    indices = {n: i for i, n in enumerate(names)}
    rows, rhs = [], []
    for a, b, factor in linear_relations(mechanism)[0]:
        if a not in indices:
            continue
        row = np.zeros(len(names))
        row[indices[b]] += 1
        row[indices[a]] -= factor
        rows.append(row)
        rhs.append(0.0)
    row = np.zeros(len(names))
    row[indices[driver_part]] = 1
    rows.append(row)
    rhs.append(value)
    solution, _, rank, _ = np.linalg.lstsq(rows, rhs, rcond=None)
    residual = float(np.linalg.norm(np.asarray(rows) @ solution - rhs))
    if rank < len(names) or residual > 1e-8 * max(1, abs(value)):
        raise ValueError('Underdetermined or inconsistent loop closure')
    return {'values': dict(zip(names, solution.tolist())), 'residual': residual,
            'disconnected_parts': report['disconnected_parts'], 'scope': 'scalar_transmissions'}


def sampled_shapes(assembly, driver_part, values):
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from ..backend.occt_backend import OCCTBackend
    values = [float(v) for v in values]
    if not values or len(values) > 10000 or not all(math.isfinite(v) for v in values):
        raise ValueError('Supply 1..10000 finite motion samples')
    mechanism = assembly._get_mechanism()
    report = validate_mechanism(mechanism, driver_part)
    if not report['valid'] or report['disconnected_parts']:
        raise ValueError(f'Invalid or disconnected mechanism: {report}')
    solids = OCCTBackend().compile(assembly.to_ir())
    if set(mechanism.joints) - set(solids):
        raise ValueError('Mechanism references parts without compiled geometry')
    for value in values:
        states = mechanism.solve(driver_part, value)
        transformed = {}
        for name, shape in solids.items():
            if name not in states:
                transformed[name] = shape
                continue
            matrix = states[name].transform_matrix
            transform = gp_Trsf()
            transform.SetValues(*matrix[:3, :4].flatten().tolist())
            transformed[name] = BRepBuilderAPI_Transform(shape, transform, True).Shape()
        yield value, transformed


def check_motion_clearances(assembly, driver_part, values, min_clearance_mm=2.0, ignore_pairs=()):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from ..validation.validation_engineer import ValidationEngineer
    if not math.isfinite(min_clearance_mm) or min_clearance_mm < 0:
        raise ValueError('Clearance must be finite and nonnegative')
    ignored = {frozenset(pair) for pair in ignore_pairs}
    minima, events, sample_count = {}, [], 0
    validator = ValidationEngineer(clash_volume_tolerance=1e-9)
    for value, solids in sampled_shapes(assembly, driver_part, values):
        sample_count += 1
        for a, b in combinations(solids, 2):
            if frozenset((a, b)) in ignored:
                continue
            distance = BRepExtrema_DistShapeShape(solids[a], solids[b])
            distance.Perform()
            if not distance.IsDone():
                raise RuntimeError(f'Distance calculation failed for {a}, {b}')
            gap = float(distance.Value())
            collision = bool(validator.check_clashes({a: solids[a], b: solids[b]})) if gap < 1e-7 else False
            status = 'COLLISION' if collision else ('CONTACT' if gap < 1e-7 else ('WARNING_PROXIMITY' if gap < min_clearance_mm else 'CLEAR'))
            record = {'first_part': a, 'second_part': b, 'driver_value': value, 'distance_mm': gap, 'status': status}
            key = (a, b)
            if key not in minima or gap < minima[key]['distance_mm'] or (collision and minima[key]['status'] != 'COLLISION' and gap <= minima[key]['distance_mm']):
                minima[key] = record
            if status != 'CLEAR':
                events.append(record)
    return {'sample_count': sample_count, 'pair_minima': list(minima.values()), 'events': events,
            'continuous': False, 'limitations': ['Events between supplied samples can be missed.']}


def get_motion_envelope(assembly, driver_part, values):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    count = 0
    for _, solids in sampled_shapes(assembly, driver_part, values):
        count += 1
        for shape in solids.values():
            BRepBndLib.Add_s(shape, box)
    return {'bounds_mm': box.Get(), 'sample_count': count, 'kind': 'sampled_assembly_aabb',
            'continuous': False, 'limitations': ['Not an exact swept volume; intermediate extrema can be missed.']}
