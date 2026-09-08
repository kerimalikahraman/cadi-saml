"""
cadi_saml.analysis.frd_reader
=============================
Parser and serializer for CalculiX .frd (Finite Element Results Data) format.
Extracts:
- Mesh nodes and 3D tetrahedral elements
- Nodal displacement vectors (U_x, U_y, U_z, U_mag)
- Cauchy stress tensor components (S_xx, S_yy, S_zz, S_xy, S_yz, S_zx)
- Derived Von Mises equivalent stresses
- Nodal reaction forces (FX, FY, FZ)
- Regional results and Factors of Safety per material zone
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from .materials import Material, get_material


@dataclass
class RegionalResult:
    """Detailed structural safety report for a specific material region."""
    region_id: str
    material_name: str
    max_von_mises_mpa: float
    max_displacement_mm: float
    yield_strength_mpa: float
    safety_factor: float
    is_safe: bool
    element_count: int
    critical_element_id: Optional[int] = None       # 1-based CalculiX element ID (from FRD/INP)
    critical_element_index: Optional[int] = None    # 0-based mesh element array index


@dataclass
class InterfaceResult:
    """Stress and structural integrity evaluation at material contact boundary."""
    region_a: str
    region_b: str
    num_interface_nodes: int
    max_von_mises_mpa: float
    mean_von_mises_mpa: float
    safety_factor: float
    is_safe: bool


@dataclass
class FRDData:
    """Raw parsed content from a CalculiX .frd file."""
    node_ids: np.ndarray             # (N,) int32
    nodes: np.ndarray                # (N, 3) float64
    elem_ids: np.ndarray             # (M,) int32
    elements: np.ndarray             # (M, 4) int32 (0-indexed into nodes)
    displacements: np.ndarray        # (N, 3) float64
    stresses: np.ndarray             # (N, 6) float64 [sxx, syy, szz, sxy, syz, szx]
    nodal_von_mises: np.ndarray      # (N,) float64
    reaction_forces: Optional[np.ndarray] = None  # (N, 3) float64
    step: int = 1
    total_steps: int = 1


def calc_von_mises(cauchy_stresses: np.ndarray) -> np.ndarray:
    """
    Computes Von Mises equivalent stress from (..., 6) Cauchy tensor [sxx, syy, szz, sxy, syz, szx].
    sigma_vm = sqrt( 0.5 * ((sxx-syy)^2 + (syy-szz)^2 + (szz-sxx)^2 + 6*(sxy^2 + syz^2 + szx^2)) )
    """
    s = np.asarray(cauchy_stresses, dtype=np.float64)
    sxx, syy, szz = s[..., 0], s[..., 1], s[..., 2]
    sxy, syz, szx = s[..., 3], s[..., 4], s[..., 5]
    diff_sq = (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
    shear_sq = 6.0 * (sxy ** 2 + syz ** 2 + szx ** 2)
    return np.sqrt(0.5 * (diff_sq + shear_sq))


import re

def _split_frd_tokens(line: str) -> List[str]:
    parts = line.strip().split()
    if not parts:
        return []
    res = []
    for p in parts:
        sub = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|[^\s]+', p)
        if sub:
            res.extend(sub)
        else:
            res.append(p)
    return res


def parse_frd(filepath: str, step: Optional[int] = None) -> FRDData:
    """
    Parses a CalculiX ASCII .frd file.
    Robustly handles:
    - Fixed-width and whitespace-delimited variants
    - Multi-step loading sequences (returns target step or latest step)
    - Integration point and element-based stress tensors (maps to nodes)
    - Partial/missing output blocks (displacements only, stress only, no reaction forces)
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"FRD results file not found: {filepath}")

    node_map: Dict[int, int] = {}
    node_ids_list: List[int] = []
    node_coords_list: List[Tuple[float, float, float]] = []

    elem_ids_list: List[int] = []
    elements_list: List[Tuple[int, int, int, int]] = []

    disp_dict: Dict[int, Tuple[float, float, float]] = {}
    stress_dict: Dict[int, List[float]] = {}
    rf_dict: Dict[int, Tuple[float, float, float]] = {}

    current_block: Optional[str] = None
    current_entity_id: Optional[int] = None
    pending_stress_vals: List[float] = []

    active_step: int = 1
    found_steps: List[int] = []
    record_this_step: bool = True

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            # Step header
            if line.startswith("    1P") or "1PSTEP" in line:
                m = re.search(r'1PSTEP\s+(\d+)', line)
                if m:
                    active_step = int(m.group(1))
                    found_steps.append(active_step)
                    if step is not None:
                        record_this_step = (active_step == step)
                    else:
                        record_this_step = True
                continue

            if not record_this_step and current_block not in ("NODES", "ELEMENTS"):
                if stripped == "-3":
                    current_block = None
                continue

            # Block header markers
            if "2C             NODES" in line or "2C NODES" in line:
                current_block = "NODES"
                continue
            elif "2C             ELEMENTS" in line or "2C ELEMENTS" in line:
                current_block = "ELEMENTS"
                continue
            elif "-4  DISP" in line:
                current_block = "DISP"
                continue
            elif "-4  STRESS" in line:
                current_block = "STRESS"
                continue
            elif "-4  FORC" in line or "-4  RF" in line:
                current_block = "FORC"
                continue
            elif line.startswith("    1C") or line.startswith("  100CL"):
                continue

            # End of block marker
            if stripped == "-3":
                if current_block == "STRESS" and current_entity_id is not None and pending_stress_vals:
                    stress_dict[current_entity_id] = pending_stress_vals
                    pending_stress_vals = []
                    current_entity_id = None
                current_block = None
                continue

            parts = _split_frd_tokens(stripped)
            if not parts:
                continue
            rec_type = parts[0]

            # 1. NODES
            if current_block == "NODES" and rec_type == "-1":
                nid = int(parts[1])
                x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                node_map[nid] = len(node_ids_list)
                node_ids_list.append(nid)
                node_coords_list.append((x, y, z))

            # 2. ELEMENTS (C3D4 tet)
            elif current_block == "ELEMENTS":
                if rec_type == "-1":
                    current_entity_id = int(parts[1])
                elif rec_type == "-2":
                    eid = current_entity_id if current_entity_id is not None else len(elem_ids_list) + 1
                    n_tags = [int(p) for p in parts[1:5]]
                    elem_ids_list.append(eid)
                    elements_list.append((node_map[n_tags[0]], node_map[n_tags[1]], node_map[n_tags[2]], node_map[n_tags[3]]))
                    current_entity_id = None

            # 3. DISPLACEMENTS (U)
            elif current_block == "DISP" and rec_type == "-1":
                nid = int(parts[1])
                ux = float(parts[2]) if len(parts) > 2 else 0.0
                uy = float(parts[3]) if len(parts) > 3 else 0.0
                uz = float(parts[4]) if len(parts) > 4 else 0.0
                disp_dict[nid] = (ux, uy, uz)

            # 4. CAUCHY STRESSES (S)
            elif current_block == "STRESS":
                if rec_type == "-1":
                    if current_entity_id is not None and pending_stress_vals:
                        stress_dict[current_entity_id] = pending_stress_vals
                    current_entity_id = int(parts[1])
                    pending_stress_vals = [float(v) for v in parts[2:]]
                elif rec_type == "-2":
                    pending_stress_vals.extend([float(v) for v in parts[1:]])
                    if len(pending_stress_vals) >= 6:
                        stress_dict[current_entity_id] = pending_stress_vals[:6]
                        pending_stress_vals = []
                        current_entity_id = None

            # 5. REACTION FORCES (FORC / RF)
            elif current_block == "FORC" and rec_type == "-1":
                nid = int(parts[1])
                fx = float(parts[2]) if len(parts) > 2 else 0.0
                fy = float(parts[3]) if len(parts) > 3 else 0.0
                fz = float(parts[4]) if len(parts) > 4 else 0.0
                rf_dict[nid] = (fx, fy, fz)

    num_nodes = len(node_ids_list)
    nodes = np.array(node_coords_list, dtype=np.float64)
    elements = np.array(elements_list, dtype=np.int32)
    node_ids = np.array(node_ids_list, dtype=np.int32)
    elem_ids = np.array(elem_ids_list, dtype=np.int32)

    # Displacements array aligned to 0..N-1 nodes
    displacements = np.zeros((num_nodes, 3), dtype=np.float64)
    for nid, d in disp_dict.items():
        if nid in node_map:
            displacements[node_map[nid]] = d

    # Stresses array aligned to 0..N-1 nodes (handles nodal & element-based stresses)
    stresses = np.zeros((num_nodes, 6), dtype=np.float64)
    elem_map = {eid: j for j, eid in enumerate(elem_ids_list)}
    node_stress_weights = np.zeros(num_nodes, dtype=np.float64)

    for entity_id, s_vals in stress_dict.items():
        s6 = [s_vals[c] if c < len(s_vals) else 0.0 for c in range(6)]
        if entity_id in node_map:
            n_idx = node_map[entity_id]
            stresses[n_idx] = s6
            node_stress_weights[n_idx] = 1.0
        elif entity_id in elem_map:
            # Map element stress to constituent nodes
            e_idx = elem_map[entity_id]
            e_nodes = elements[e_idx]
            for n_idx in e_nodes:
                stresses[n_idx] += s6
                node_stress_weights[n_idx] += 1.0

    for i in range(num_nodes):
        if node_stress_weights[i] > 1.0:
            stresses[i] /= node_stress_weights[i]

    # Reaction forces array
    rf_arr = None
    if rf_dict:
        rf_arr = np.zeros((num_nodes, 3), dtype=np.float64)
        for nid, f_vec in rf_dict.items():
            if nid in node_map:
                rf_arr[node_map[nid]] = f_vec

    nodal_vm = calc_von_mises(stresses)
    chosen_step = step if step is not None else (found_steps[-1] if found_steps else 1)
    tot_steps = max(len(found_steps), 1)

    return FRDData(
        node_ids=node_ids,
        nodes=nodes,
        elem_ids=elem_ids,
        elements=elements,
        displacements=displacements,
        stresses=stresses,
        nodal_von_mises=nodal_vm,
        reaction_forces=rf_arr,
        step=chosen_step,
        total_steps=tot_steps,
    )


def write_frd(
    filepath: str,
    nodes: np.ndarray,
    elements: np.ndarray,
    displacements: np.ndarray,
    stresses: np.ndarray,
    reaction_forces: Optional[np.ndarray] = None,
    step_num: int = 1,
) -> str:
    """
    Serializes mesh and solution arrays into standard CalculiX .frd ASCII format.
    Ensures seamless two-way interoperability.
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    num_nodes = len(nodes)
    num_elems = len(elements)

    lines = [
        "    1C                                                      1",
        "    2C             NODES",
    ]
    for i in range(num_nodes):
        nid = i + 1
        p = nodes[i]
        lines.append(f"   -1 {nid:10d} {p[0]:14.6E} {p[1]:14.6E} {p[2]:14.6E}")
    lines.append("   -3")

    lines.extend([
        "    1C                                                      1",
        "    2C             ELEMENTS",
    ])
    for j in range(num_elems):
        eid = j + 1
        e = elements[j]
        # Type 3 = C3D4 in CalculiX FRD element code
        lines.append(f"   -1 {eid:10d}         3         1         1")
        lines.append(f"   -2 {e[0]+1:10d} {e[1]+1:10d} {e[2]+1:10d} {e[3]+1:10d}")
    lines.append("   -3")

    # Displacements
    disp_mags = np.linalg.norm(displacements, axis=1)
    lines.extend([
        f"    1PSTEP                        {step_num:d}",
        "  100CL        1.00000E+00",
        "    -4  DISP        4    1",
        "    -5  NDISPX      1    1    1",
        "    -5  NDISPY      1    1    2",
        "    -5  NDISPZ      1    1    3",
        "    -5  ALL         1    1    0",
    ])
    for i in range(num_nodes):
        nid = i + 1
        u = displacements[i]
        mag = disp_mags[i]
        lines.append(f"   -1 {nid:10d} {u[0]:14.6E} {u[1]:14.6E} {u[2]:14.6E} {mag:14.6E}")
    lines.append("   -3")

    # Stresses (SXX, SYY, SZZ, SXY, SYZ, SZX)
    lines.extend([
        f"    1PSTEP                        {step_num:d}",
        "  100CL        1.00000E+00",
        "    -4  STRESS      6    1",
        "    -5  SXX         1    1    1",
        "    -5  SYY         1    1    2",
        "    -5  SZZ         1    1    3",
        "    -5  SXY         1    1    4",
        "    -5  SYZ         1    1    5",
        "    -5  SZX         1    1    6",
    ])
    for i in range(num_nodes):
        nid = i + 1
        s = stresses[i] if i < len(stresses) else np.zeros(6)
        lines.append(f"   -1 {nid:10d} {s[0]:14.6E} {s[1]:14.6E} {s[2]:14.6E} {s[3]:14.6E}")
        lines.append(f"   -2 {s[4]:14.6E} {s[5]:14.6E}")
    lines.append("   -3")

    # Reaction forces if available
    if reaction_forces is not None:
        lines.extend([
            f"    1PSTEP                        {step_num:d}",
            "  100CL        1.00000E+00",
            "    -4  FORC        3    1",
            "    -5  FX          1    1    1",
            "    -5  FY          1    1    2",
            "    -5  FZ          1    1    3",
        ])
        for i in range(num_nodes):
            rf = reaction_forces[i]
            if np.linalg.norm(rf) > 1e-6:
                lines.append(f"   -1{i+1:10d}{rf[0]:12.5E}{rf[1]:12.5E}{rf[2]:12.5E}")
        lines.append("   -3")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return os.path.abspath(filepath)


def _normalize_element_sets(
    element_sets: Optional[Dict[str, Sequence[int]]],
    num_elems: int,
    index_base: str = "auto",
) -> Dict[str, List[int]]:
    """
    Normalizes element sets to 0-based array indices [0, num_elems - 1].

    Parameters:
    - element_sets: dictionary mapping region names to element ID sequences.
    - num_elems: total element count in the mesh.
    - index_base: 'auto', 'zero', or 'one'.
      * 'one': Elements are 1-based CalculiX IDs (1 <= eid <= num_elems). Converted to eid - 1.
      * 'zero': Elements are 0-based array indices (0 <= eid < num_elems). Preserved as is.
      * 'auto': Disambiguates between 1-based and 0-based conventions.
                Strictly rejects mixed-base sets or out-of-bounds IDs with ValueError.

    Raises:
    - ValueError: If index_base is invalid.
    - ValueError: If any element ID is out of bounds for the detected or specified base.
    - ValueError: If conflicting / mixed 0-based and 1-based element indices are detected.
    """
    if not element_sets or num_elems <= 0:
        return {}

    if index_base not in ("auto", "zero", "one"):
        raise ValueError(f"Invalid index_base '{index_base}'. Expected 'auto', 'zero', or 'one'.")

    # Collect and validate all IDs across sets
    all_raw_ids: List[int] = []
    for name, eids in element_sets.items():
        if not eids:
            continue
        for x in eids:
            try:
                val = int(x)
            except (TypeError, ValueError):
                raise ValueError(f"Non-integer element ID {x!r} found in element set '{name}'.")
            all_raw_ids.append(val)

    if not all_raw_ids:
        return {name: [] for name in element_sets}

    min_val = min(all_raw_ids)
    max_val = max(all_raw_ids)

    # Any ID strictly negative or strictly greater than num_elems is universally invalid
    if min_val < 0:
        bad_id = min_val
        bad_set = [k for k, v in element_sets.items() if bad_id in [int(x) for x in v]][0]
        raise ValueError(f"Negative element ID {bad_id} in set '{bad_set}' is invalid.")

    if max_val > num_elems:
        bad_id = max_val
        bad_set = [k for k, v in element_sets.items() if bad_id in [int(x) for x in v]][0]
        raise ValueError(f"Element ID {bad_id} in set '{bad_set}' exceeds mesh element count {num_elems}.")

    has_zero = any(eid == 0 for eid in all_raw_ids)
    has_num_elems = any(eid == num_elems for eid in all_raw_ids)

    # Disambiguate or enforce base
    if index_base == "auto":
        # Mixed-base contradiction: ID 0 (0-based) and ID num_elems (1-based) both present
        if has_zero and has_num_elems:
            raise ValueError(
                f"Conflicting / mixed element index base detected across element sets: "
                f"Element ID 0 (0-based) and Element ID {num_elems} (1-based for mesh with {num_elems} elements) "
                f"cannot co-exist. Explicitly specify index_base='zero' or index_base='one'."
            )

        # Check for mixed conventions across individual sets
        set_has_zero = {k: any(int(x) == 0 for x in v) for k, v in element_sets.items() if len(v) > 0}
        if any(set_has_zero.values()):
            # At least one set has 0 -> all sets must be valid 0-based (< num_elems)
            for k, v in element_sets.items():
                for x in v:
                    if int(x) >= num_elems:
                        raise ValueError(
                            f"Mixed element indexing detected: element set contains index 0 while set '{k}' "
                            f"contains element ID {x} >= num_elems ({num_elems})."
                        )
            effective_base = "zero"
        else:
            # Standard CalculiX: none have 0 -> treat as 1-based
            effective_base = "one"
    else:
        effective_base = index_base

    # Perform strict normalization according to effective_base
    norm_sets: Dict[str, List[int]] = {}
    for name, eids in element_sets.items():
        converted: List[int] = []
        for raw_eid in eids:
            eid = int(raw_eid)
            if effective_base == "one":
                if eid < 1 or eid > num_elems:
                    raise ValueError(
                        f"Element ID {eid} in set '{name}' is out of bounds for 1-based indexing "
                        f"(valid range: 1..{num_elems})."
                    )
                converted.append(eid - 1)
            elif effective_base == "zero":
                if eid < 0 or eid >= num_elems:
                    raise ValueError(
                        f"Element index {eid} in set '{name}' is out of bounds for 0-based indexing "
                        f"(valid range: 0..{num_elems - 1})."
                    )
                converted.append(eid)
        norm_sets[name] = converted

    return norm_sets


def _to_0based_element_indices(indices: Any, num_elems: int, index_base: str = "auto") -> List[int]:
    """Helper converting a single sequence of element IDs to 0-based array indices."""
    if not indices or num_elems <= 0:
        return []
    sets = {"_": indices}
    norm = _normalize_element_sets(sets, num_elems, index_base=index_base)
    return norm.get("_", [])


def frd_to_fea_result(
    frd_path: str,
    materials: Optional[Dict[str, Material]] = None,
    element_sets: Optional[Dict[str, List[int]]] = None,
    study_name: str = "CalculiX_Study",
    part_name: str = "model",
    required_safety_factor: float = 1.5,
    solver_backend: str = "builtin",
    index_base: str = "auto",
    solver_version: Optional[str] = None,
    solver_command: Optional[str] = None,
) -> Any:
    """
    Converts a parsed .frd file into a fully populated CADi SAML FEAResult object,
    evaluating regional Von Mises stresses and local Factors of Safety per material region.
    """
    from .fea import FEAResult

    data = parse_frd(frd_path)
    max_vm = float(np.max(data.nodal_von_mises)) if len(data.nodal_von_mises) else 0.0
    disp_mags = np.linalg.norm(data.displacements, axis=1)
    max_disp = float(np.max(disp_mags)) if len(disp_mags) else 0.0

    materials_dict = materials or {"default": get_material("S235JR")}
    primary_mat = list(materials_dict.values())[0]

    # Evaluate regional results
    regional_results: Dict[str, RegionalResult] = {}
    num_elems = len(data.elements)
    elem_mat_ids = np.zeros(num_elems, dtype=np.int32)

    # Element-level stress approx from nodes
    elem_vm = np.zeros(num_elems, dtype=np.float64)
    for j, e in enumerate(data.elements):
        elem_vm[j] = np.mean(data.nodal_von_mises[e])

    # Normalize element sets to safe 0-based indices
    norm_element_sets = _normalize_element_sets(element_sets, num_elems, index_base=index_base)

    if norm_element_sets and len(materials_dict) > 1:
        mat_keys = list(materials_dict.keys())
        for m_idx, (set_name, valid_eids) in enumerate(norm_element_sets.items()):
            mat = materials_dict.get(set_name, primary_mat)
            for eid_idx in valid_eids:
                elem_mat_ids[eid_idx] = m_idx

            if valid_eids:
                reg_vm = float(np.max(elem_vm[valid_eids]))
                crit_idx = valid_eids[int(np.argmax(elem_vm[valid_eids]))]
                # critical_element_id reported as 1-based CalculiX element ID for engineering audit
                crit_elem_id = int(data.elem_ids[crit_idx]) if (data.elem_ids is not None and crit_idx < len(data.elem_ids)) else (crit_idx + 1)
                # Map element nodes for max disp
                reg_node_indices = np.unique(data.elements[valid_eids].ravel())
                reg_disp = float(np.max(disp_mags[reg_node_indices])) if len(reg_node_indices) else 0.0
                sy = float(mat.yield_strength_mpa)
                fos = sy / max(reg_vm, 1e-4)
                is_safe = fos >= required_safety_factor

                regional_results[set_name] = RegionalResult(
                    region_id=set_name,
                    material_name=mat.name,
                    max_von_mises_mpa=round(reg_vm, 2),
                    max_displacement_mm=round(reg_disp, 4),
                    yield_strength_mpa=round(sy, 1),
                    safety_factor=round(fos, 2),
                    is_safe=is_safe,
                    element_count=len(valid_eids),
                    critical_element_id=crit_elem_id,
                    critical_element_index=int(crit_idx),
                )
    else:
        sy = float(primary_mat.yield_strength_mpa)
        fos = sy / max(max_vm, 1e-4)
        is_safe = fos >= required_safety_factor
        crit_all_idx = int(np.argmax(elem_vm)) if num_elems > 0 else 0
        crit_all_id = int(data.elem_ids[crit_all_idx]) if (data.elem_ids is not None and crit_all_idx < len(data.elem_ids)) else (crit_all_idx + 1)
        regional_results["global"] = RegionalResult(
            region_id="global",
            material_name=primary_mat.name,
            max_von_mises_mpa=round(max_vm, 2),
            max_displacement_mm=round(max_disp, 4),
            yield_strength_mpa=round(sy, 1),
            safety_factor=round(fos, 2),
            is_safe=is_safe,
            element_count=num_elems,
            critical_element_id=crit_all_id,
            critical_element_index=crit_all_idx,
        )

    # Evaluate interface results across adjacent material regions
    interface_results: Dict[str, InterfaceResult] = {}
    if norm_element_sets and len(materials_dict) > 1:
        region_keys = list(norm_element_sets.keys())
        for i in range(len(region_keys)):
            for j in range(i + 1, len(region_keys)):
                r_a = region_keys[i]
                r_b = region_keys[j]
                elems_a = norm_element_sets[r_a]
                elems_b = norm_element_sets[r_b]
                if not elems_a or not elems_b:
                    continue
                nodes_a = set(data.elements[elems_a].ravel())
                nodes_b = set(data.elements[elems_b].ravel())
                inter_nodes = sorted(list(nodes_a.intersection(nodes_b)))
                if inter_nodes:
                    inter_vm = data.nodal_von_mises[inter_nodes]
                    max_inter_vm = float(np.max(inter_vm))
                    mean_inter_vm = float(np.mean(inter_vm))
                    mat_a = materials_dict.get(r_a, primary_mat)
                    mat_b = materials_dict.get(r_b, primary_mat)
                    min_sy = min(float(mat_a.yield_strength_mpa), float(mat_b.yield_strength_mpa))
                    inter_fos = min_sy / max(max_inter_vm, 1e-4)
                    inter_safe = inter_fos >= required_safety_factor
                    pair_key = f"{r_a}__{r_b}"
                    interface_results[pair_key] = InterfaceResult(
                        region_a=r_a,
                        region_b=r_b,
                        num_interface_nodes=len(inter_nodes),
                        max_von_mises_mpa=round(max_inter_vm, 2),
                        mean_von_mises_mpa=round(mean_inter_vm, 2),
                        safety_factor=round(inter_fos, 2),
                        is_safe=inter_safe,
                    )

    min_fos = min(r.safety_factor for r in regional_results.values())
    all_safe = all(r.is_safe for r in regional_results.values())
    if interface_results:
        all_safe = all_safe and all(ir.is_safe for ir in interface_results.values())
    status = "ACCEPTABLE" if all_safe else "YIELD_EXCEEDED"

    result = FEAResult(
        study_name=study_name,
        part_name=part_name,
        material=primary_mat,
        num_nodes=len(data.nodes),
        num_elements=num_elems,
        max_von_mises_mpa=round(max_vm, 2),
        max_displacement_mm=round(max_disp, 4),
        yield_strength_mpa=round(primary_mat.yield_strength_mpa, 1),
        safety_factor=round(min_fos, 2),
        is_safe=all_safe,
        status=status,
        nodal_displacements=data.displacements,
        nodal_von_mises=data.nodal_von_mises,
        nodes=data.nodes,
        elements=data.elements,
        required_safety_factor=required_safety_factor,
        solver_backend=solver_backend,
        solver_version=solver_version,
        solver_command=solver_command,
        materials=materials_dict,
        regional_results=regional_results,
        interface_results=interface_results,
        element_material_ids=elem_mat_ids,
        reaction_forces=data.reaction_forces,
    )

    return result


normalize_element_sets = _normalize_element_sets
