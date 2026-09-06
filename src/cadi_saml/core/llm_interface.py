"""Machine-readable discovery, compact state queries, and transactional patches."""
from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
import hashlib
import inspect as pyinspect
import json
import math
from typing import Any, Dict, get_args, get_origin


SCHEMA_OVERRIDES = {
    "connect": {
        "category": "assembly",
        "constraints": {"mate_type": {"enum": ["FLUSH", "COINCIDENT", "COAXIAL", "CONCENTRIC", "DISTANCE", "ALIGN_HOLES"]}},
    },
    "add_bolted_joint": {
        "category": "macro",
        "constraints": {"thread": {"pattern": "^M[0-9]+$"}, "grip_length": {"exclusive_minimum": 0, "unit": "mm"}},
    },
    "add_gear_pair": {
        "category": "macro",
        "constraints": {"module": {"exclusive_minimum": 0, "unit": "mm"}, "pinion_teeth": {"minimum": 1}, "gear_teeth": {"minimum": 1}},
    },
}

for _name in ("add_mounting_bracket", "add_profile_frame", "add_motor_mount",
              "add_bearing_support", "add_shaft_stack"):
    SCHEMA_OVERRIDES.setdefault(_name, {})["category"] = "macro"
for _name in ("add_counterbore", "add_countersink", "add_keyway",
              "add_retaining_ring_groove", "add_pocket", "add_rib"):
    SCHEMA_OVERRIDES.setdefault(_name, {})["category"] = "feature"

_UNITS = {
    "angle": "deg", "angle_deg": "deg", "start_angle": "deg", "helix_angle": "deg",
    "length": "mm", "width": "mm", "height": "mm", "radius": "mm", "diameter": "mm",
    "distance": "mm", "offset": "mm", "thickness": "mm", "depth": "mm", "pcd": "mm",
    "force_vector": "N", "pressure_mpa": "MPa", "density": "kg/m3",
}


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and type(value).__module__ == "enum":
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _type_schema(annotation):
    if annotation is pyinspect.Parameter.empty:
        return {"type": "any"}
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is not None:
        return {"type": str(origin).replace("typing.", ""), "args": [_type_schema(a) for a in args]}
    return {"type": getattr(annotation, "__name__", str(annotation).replace("typing.", ""))}


def _unit_for(name):
    lower = name.lower()
    for token, unit in _UNITS.items():
        if lower == token or lower.endswith("_" + token) or token in lower:
            return unit
    return None


def describe_callable(owner, name):
    if name.startswith("_") or not hasattr(owner, name) or not callable(getattr(owner, name)):
        raise KeyError(f"Unknown public capability: {name}")
    fn = getattr(owner, name)
    signature = pyinspect.signature(fn)
    override = SCHEMA_OVERRIDES.get(name, {})
    constraints = override.get("constraints", {})
    parameters = {}
    for param_name, param in signature.parameters.items():
        if param_name == "self":
            continue
        entry = _type_schema(param.annotation)
        entry["required"] = param.default is pyinspect.Parameter.empty
        if param.default is not pyinspect.Parameter.empty:
            entry["default"] = _jsonable(param.default)
        unit = _unit_for(param_name)
        if unit:
            entry["unit"] = unit
        entry.update(constraints.get(param_name, {}))
        parameters[param_name] = entry
    doc = pyinspect.getdoc(fn) or ""
    summary = doc.splitlines()[0] if doc else ""
    return {
        "name": name,
        "category": override.get("category", "method"),
        "summary": summary,
        "description": summary,
        "parameters": parameters,
        "returns": _type_schema(signature.return_annotation),
        "signature": str(signature),
        "source": "runtime_signature",
    }


def capability_catalog(owner):
    prefixes = ("add_", "export_", "check_", "get_", "set_", "solve_", "validate_", "describe", "inspect", "preview_")
    names = sorted(name for name in dir(owner) if not name.startswith("_") and name.startswith(prefixes) and callable(getattr(owner, name)))
    capabilities = {name: describe_callable(owner, name) for name in names}
    return {"schema_version": "1.0", "capabilities": capabilities,
            "assembly_macros": [name for name, schema in capabilities.items() if schema["category"] == "macro"],
            "features": [name for name, schema in capabilities.items() if schema["category"] == "feature"]}


def _fingerprint(ir):
    return hashlib.sha256(repr(ir).encode("utf-8")).hexdigest()


def _change_value(ir, key, value):
    tokens = key.split(".")
    if len(tokens) < 2 or tokens[0] not in ir.parts:
        raise KeyError(f"Patch path must start with an existing part: {key}")
    part = ir.parts[tokens[0]]
    attr = tokens[1]
    if attr in ("name", "ports", "holes", "fillets", "chamfers"):
        raise ValueError(f"Patch path is protected: {key}")
    if attr == "parameters":
        target, remaining = part.parameters, tokens[2:]
    elif len(tokens) == 2 and attr in ("color", "material", "draft_angle"):
        setattr(part, attr, value)
        return
    elif len(tokens) == 2 and attr in part.parameters:
        target, remaining = part.parameters, [attr]
    else:
        raise KeyError(f"Unknown patch path: {key}")
    if not remaining:
        raise ValueError(f"Patch path must identify one value: {key}")
    for token in remaining[:-1]:
        if not isinstance(target, dict) or token not in target:
            raise KeyError(f"Unknown patch path: {key}")
        target = target[token]
    leaf = remaining[-1]
    if not isinstance(target, dict) or leaf not in target:
        raise KeyError(f"Unknown patch path: {key}")
    old = target[leaf]
    if isinstance(old, bool) and not isinstance(value, bool):
        raise TypeError(f"Expected bool for {key}")
    if isinstance(old, (int, float)) and not isinstance(old, bool):
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise TypeError(f"Expected finite number for {key}")
    target[leaf] = value


from cadi_saml.patching.patch_engine import PatchProposal as CanonicalPatchProposal


class PatchProposal(CanonicalPatchProposal):
    """A conflict-detecting patch that cannot mutate its source until commit()."""
    def __init__(self, assembly, diff: Dict[str, Any]):
        super().__init__(assembly, diff)


def structured_diagnostics(raw):
    issues = []
    for part in raw.get("manifold_failures", []):
        issues.append({"code": "NON_MANIFOLD", "severity": "error", "parts": [part],
                       "message": f"Part {part!r} is not watertight.",
                       "repair_options": [{"action": "heal_shape", "target": part}, {"action": "inspect_features", "target": part}]})
    for clash in raw.get("clashes", []):
        a, b = clash.get("first_part"), clash.get("second_part")
        issues.append({"code": "VOLUMETRIC_CLASH", "severity": "error", "parts": [a, b],
                       "actual": {"intersection_volume_mm3": clash.get("volume_mm3")},
                       "message": clash.get("description") or f"{a!r} and {b!r} intersect.",
                       "repair_options": [{"action": "adjust_mate_offset", "parts": [a, b]},
                                          {"action": "add_clearance_feature", "parts": [a, b]}]})
    return {"status": "PASS" if not issues else "FAIL", "issues": issues,
            "summary": {"issue_count": len(issues), "error_count": sum(i["severity"] == "error" for i in issues)}}
