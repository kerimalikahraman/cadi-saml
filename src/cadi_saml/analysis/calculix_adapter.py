"""Small, deterministic CalculiX input adapter with multi-material support.

Translates mesh geometry, material regions, element sets, and loads into
standard CalculiX/Abaqus .inp decks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

from .materials import Material, get_material
from .frd_reader import _normalize_element_sets


@dataclass
class BoundaryCondition:
    """CalculiX Dirichlet boundary condition with explicit DOF range and value."""
    target: Union[str, int]
    start_dof: int = 1
    end_dof: int = 3
    value: float = 0.0


@dataclass
class MaterialRegion:
    """Designates a geometric region, element set, or volume partition with distinct material properties."""
    name: str
    material: Union[str, Material]
    element_ids: Sequence[int] = field(default_factory=tuple)
    selector: Optional[Callable[[float, float, float], bool]] = None
    fiber_direction: Optional[Tuple[float, float, float]] = None

    def __post_init__(self):
        if not isinstance(self.material, Material):
            self.material = get_material(str(self.material))
        if self.fiber_direction is not None:
            raise NotImplementedError(
                "Orthotropic material with fiber_direction is not yet supported. "
                "Current release supports isotropic multi-material regions."
            )


class CalculiXModel:
    """
    Finite element model representation for CalculiX export and execution.
    Supports heterogeneous multi-material regions, node sets, boundary conditions, and loads.
    """

    def __init__(
        self,
        *args,
        nodes: Optional[Any] = None,
        elements: Optional[Any] = None,
        materials: Optional[Dict[str, Material]] = None,
        element_sets: Optional[Dict[str, Sequence[int]]] = None,
        fixed_nodes: Optional[Sequence[int]] = None,
        nodal_forces: Optional[Mapping[int, Tuple[float, float, float]]] = None,
        index_base: str = "one",
    ):
        name: Optional[str] = None
        raw_nodes = nodes
        raw_elems = elements

        if len(args) == 3:
            name, raw_nodes, raw_elems = args
        elif len(args) == 2:
            raw_nodes, raw_elems = args
        elif len(args) == 1:
            if isinstance(args[0], str):
                name = args[0]
            else:
                raw_nodes = args[0]

        self.name = name or "CalculiXModel"
        self.index_base = str(index_base).lower()
        if self.index_base not in ("one", "zero", "auto"):
            raise ValueError(f"Invalid index_base '{index_base}'. Expected 'one', 'zero', or 'auto'.")

        # Normalize nodes to list of (id, x, y, z)
        self.nodes: List[Tuple[int, float, float, float]] = []
        if raw_nodes is not None:
            raw_arr = np.asarray(raw_nodes)
            if raw_arr.ndim == 2 and raw_arr.shape[1] == 3:
                self.nodes = [
                    (i + 1, float(p[0]), float(p[1]), float(p[2]))
                    for i, p in enumerate(raw_arr)
                ]
            else:
                self.nodes = list(raw_nodes)

        # Normalize elements to list of (id, n1, n2, n3, n4)
        self.elements: List[Tuple[int, int, int, int, int]] = []
        if raw_elems is not None:
            elem_arr = np.asarray(raw_elems)
            if elem_arr.ndim == 2 and elem_arr.shape[1] == 4:
                # 0-indexed nodes -> convert to 1-based node IDs
                self.elements = [
                    (j + 1, int(e[0]) + 1, int(e[1]) + 1, int(e[2]) + 1, int(e[3]) + 1)
                    for j, e in enumerate(elem_arr)
                ]
            else:
                self.elements = list(raw_elems)

        self.materials: Dict[str, Material] = dict(materials or {})
        self.element_sets: Dict[str, Sequence[int]] = dict(element_sets or {})
        self.node_sets: Dict[str, Sequence[int]] = {}
        self.boundary_conditions: List[BoundaryCondition] = []
        self.fixed_nodes: List[int] = list(fixed_nodes or [])
        self.nodal_forces: Dict[int, Tuple[float, float, float]] = dict(nodal_forces or {})
        self._pending_selectors: Dict[str, Callable[[float, float, float], bool]] = {}

    def add_material(self, name: str, material: Union[str, Material]) -> None:
        """Register a material definition by name."""
        self.materials[str(name)] = material if isinstance(material, Material) else get_material(str(material))

    def add_material_region(
        self,
        name_or_region: Union[str, MaterialRegion],
        material: Optional[Union[str, Material]] = None,
        element_ids: Optional[Sequence[int]] = None,
        selector: Optional[Callable[[float, float, float], bool]] = None,
    ) -> None:
        """Adds a material region and associates it with element sets or spatial selector."""
        if isinstance(name_or_region, MaterialRegion):
            reg = name_or_region
            name = reg.name
            mat = reg.material if isinstance(reg.material, Material) else get_material(str(reg.material))
            self.materials[str(name)] = mat
            if reg.element_ids:
                self.element_sets[str(name)] = [int(eid) for eid in reg.element_ids]
            elif reg.selector is not None:
                self._pending_selectors[str(name)] = reg.selector
                self.element_sets[str(name)] = self._filter_elements_by_selector(reg.selector)
        else:
            name = str(name_or_region)
            if material is None:
                raise ValueError("material must be specified when adding material region by name")
            mat = material if isinstance(material, Material) else get_material(str(material))
            self.materials[name] = mat

            if element_ids is not None:
                self.element_sets[name] = [int(eid) for eid in element_ids]
            elif selector is not None:
                self._pending_selectors[name] = selector
                self.element_sets[name] = self._filter_elements_by_selector(selector)

    def assign_element_sets(self) -> None:
        """Re-evaluates any pending spatial selectors to populate element sets."""
        for name, sel in self._pending_selectors.items():
            self.element_sets[name] = self._filter_elements_by_selector(sel)

    def add_node_set(self, name: str, node_ids: Sequence[int]) -> None:
        """Add a named node set (1-based node IDs or 0-based node IDs auto-converted)."""
        if not node_ids:
            self.node_sets[str(name)] = []
            return
        is_zero_based = (min(node_ids) == 0)
        norm_ids = [int(n) + 1 if is_zero_based else int(n) for n in node_ids]
        self.node_sets[str(name)] = norm_ids

    def add_boundary_condition(
        self,
        node_set_or_id: Union[str, int],
        start_dof: int = 1,
        end_dof: int = 3,
        value: float = 0.0,
    ) -> None:
        """Add Dirichlet boundary condition with explicit DOF range and optional displacement value."""
        if not (1 <= start_dof <= 6 and 1 <= end_dof <= 6 and start_dof <= end_dof):
            raise ValueError(f"Invalid DOF range: {start_dof} to {end_dof}")

        if isinstance(node_set_or_id, int):
            nid = node_set_or_id + 1 if node_set_or_id == 0 else node_set_or_id
            target: Union[str, int] = nid
            self.fixed_nodes.append(nid)
        else:
            target = str(node_set_or_id)
            nids = self.node_sets.get(target, [])
            self.fixed_nodes.extend(nids)

        self.boundary_conditions.append(
            BoundaryCondition(target=target, start_dof=start_dof, end_dof=end_dof, value=value)
        )

    def add_nodal_load(self, node_id: int, dof: int, value: float) -> None:
        """Apply a point load to a node in DOF 1 (X), 2 (Y), or 3 (Z)."""
        nid = int(node_id) + 1 if int(node_id) == 0 else int(node_id)
        current = list(self.nodal_forces.get(nid, (0.0, 0.0, 0.0)))
        current[dof - 1] += float(value)
        self.nodal_forces[nid] = (current[0], current[1], current[2])

    def _filter_elements_by_selector(self, selector: Callable[[float, float, float], bool]) -> List[int]:
        """Identifies element IDs whose centroid satisfies the spatial selector."""
        node_coords = {int(n[0]): (float(n[1]), float(n[2]), float(n[3])) for n in self.nodes}
        matching_eids = []
        for j, elem in enumerate(self.elements):
            eid = int(elem[0])
            n_ids = [int(x) for x in elem[1:5]]
            pts = [node_coords[nid] for nid in n_ids if nid in node_coords]
            if len(pts) == 4:
                cx = sum(p[0] for p in pts) / 4.0
                cy = sum(p[1] for p in pts) / 4.0
                cz = sum(p[2] for p in pts) / 4.0
                if selector(cx, cy, cz):
                    if self.index_base == "zero":
                        matching_eids.append(j)
                    else:
                        matching_eids.append(eid)
        return matching_eids

    def validate_multi_material(self) -> bool:
        """Ensures all mesh elements are assigned to valid, non-overlapping material regions."""
        if not self.elements:
            return True
        num_elems = len(self.elements)
        if self.element_sets or len(self.materials) > 1:
            for set_name in self.element_sets.keys():
                if set_name not in self.materials:
                    raise ValueError(f"Element set '{set_name}' does not correspond to any defined material.")

            norm_sets = _normalize_element_sets(
                self.element_sets,
                num_elems=num_elems,
                index_base=self.index_base,
            )

            all_indices = set(range(num_elems))
            assigned_indices: set = set()
            for set_name, indices in norm_sets.items():
                if not indices:
                    raise ValueError(f"Element set '{set_name}' is empty.")
                overlap = assigned_indices.intersection(set(indices))
                if overlap:
                    sample_eids = [i + 1 for i in sorted(list(overlap))[:5]]
                    raise ValueError(
                        f"Overlapping material regions detected: {len(overlap)} elements in region '{set_name}' "
                        f"were already assigned to another material region (sample eids: {sample_eids})."
                    )
                assigned_indices.update(indices)

            unassigned = all_indices - assigned_indices
            if unassigned:
                sample_unassigned = [i + 1 for i in sorted(list(unassigned))[:5]]
                raise ValueError(
                    f"Not all elements assigned: {len(unassigned)} elements have no material assignment "
                    f"(sample unassigned eids: {sample_unassigned})."
                )
        return True

    def to_inp(self) -> str:
        if not self.nodes or not self.elements:
            raise ValueError("CalculiX model requires nodes and tetrahedral elements")
        if not self.materials:
            raise ValueError("At least one material region is required")

        self.validate_multi_material()

        num_elems = len(self.elements)
        norm_sets = _normalize_element_sets(
            self.element_sets,
            num_elems=num_elems,
            index_base=self.index_base,
        ) if self.element_sets else {}

        lines = ["*HEADING", "CADi SAML CalculiX export", "*NODE"]
        lines += [f"{i}, {x:.12g}, {y:.12g}, {z:.12g}" for i, x, y, z in self.nodes]
        lines.append("*ELEMENT, TYPE=C3D4, ELSET=ALL_ELEMENTS")
        lines += [f"{i}, {n1}, {n2}, {n3}, {n4}" for i, n1, n2, n3, n4 in self.elements]

        # Element sets (CalculiX requires 1-based IDs on .inp cards)
        for name, indices in norm_sets.items():
            lines.append(f"*ELSET, ELSET={name}")
            # Format in chunks of 16 IDs per line for standard card readability
            id_strs = [str(int(i) + 1) for i in indices]
            for c_start in range(0, len(id_strs), 16):
                lines.append(", ".join(id_strs[c_start : c_start + 16]))

        # Solid sections and materials
        for name, mat in self.materials.items():
            elset = name if name in self.element_sets else "ALL_ELEMENTS"
            lines += [
                f"*SOLID SECTION, ELSET={elset}, MATERIAL={name}",
                ",",
                f"*MATERIAL, NAME={name}",
                "*ELASTIC",
                f"{mat.youngs_modulus_mpa:.12g}, {mat.poissons_ratio:.12g}",
                "*DENSITY",
                f"{mat.density_kg_m3:.12g}",
            ]

        if self.boundary_conditions:
            lines.append("*BOUNDARY")
            for bc in self.boundary_conditions:
                if bc.value != 0.0:
                    lines.append(f"{bc.target}, {bc.start_dof}, {bc.end_dof}, {bc.value:.12g}")
                elif bc.start_dof == bc.end_dof:
                    lines.append(f"{bc.target}, {bc.start_dof}")
                else:
                    lines.append(f"{bc.target}, {bc.start_dof}, {bc.end_dof}")
        elif self.fixed_nodes:
            unique_fixed = sorted(set(int(i) for i in self.fixed_nodes))
            lines += ["*BOUNDARY"] + [f"{i}, 1, 3" for i in unique_fixed]

        if self.nodal_forces:
            lines.append("*CLOAD")
            for i, force in self.nodal_forces.items():
                if len(force) != 3:
                    raise ValueError("Nodal force must have three components")
                lines += [f"{int(i)}, {dof}, {float(force[dof-1]):.12g}" for dof in (1, 2, 3) if float(force[dof-1]) != 0.0]

        lines += ["*STEP", "*STATIC", "1., 1., 1e-05, 1.", "*NODE FILE", "U", "*EL FILE", "S", "*END STEP"]
        return "\n".join(lines) + "\n"
