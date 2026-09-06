"""
cadi_saml.analysis.fea
=====================
High-level Finite Element Analysis (FEA) study and reporting engine for cadi_saml.
Seamlessly connects OpenCASCADE B-Rep solids to Gmsh tetrahedral mesher,
runs 3D linear elasticity structural analysis, and generates engineering analysis reports.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import OCP.STEPControl as STEPControl
import OCP.TopoDS as TopoDS
import OCP.BRepGProp as BRepGProp
import OCP.GProp as GProp
import gmsh

from .materials import Material, get_material
from .solver import FEMSolution, LinearElasticitySolver


@dataclass
class FEAResult:
    """Linear elastic analysis result; acceptance applies only to configured criteria."""
    study_name: str
    part_name: str
    material: Material
    num_nodes: int
    num_elements: int
    max_von_mises_mpa: float
    max_displacement_mm: float
    yield_strength_mpa: float
    safety_factor: float
    is_safe: bool
    status: str
    nodal_displacements: np.ndarray = field(repr=False)
    nodal_von_mises: np.ndarray = field(repr=False)
    nodes: Optional[np.ndarray] = field(default=None, repr=False)
    elements: Optional[np.ndarray] = field(default=None, repr=False)
    raw_solution: Optional[FEMSolution] = field(default=None, repr=False)

    required_safety_factor: float = 1.5
    max_displacement_limit_mm: Optional[float] = None
    solution_valid: bool = True
    criteria_passed: Dict[str, bool] = field(default_factory=dict)

    @property
    def summary_report(self) -> str:
        """Structured engineering validation report."""
        status_icon = "[PASS]" if self.is_safe else "[WARN]"
        return (
            f"\n=======================================================\n"
            f"  CADi FEA STRUCTURAL SIMULATION REPORT\n"
            f"=======================================================\n"
            f"Study Name       : {self.study_name}\n"
            f"Part Analyzed    : {self.part_name}\n"
            f"Material         : {self.material.name} (E={self.material.youngs_modulus_mpa:,.0f} MPa, Sy={self.yield_strength_mpa:.1f} MPa)\n"
            f"Mesh Statistics  : {self.num_nodes:,} Nodes | {self.num_elements:,} 3D Tetrahedral Elements\n"
            f"-------------------------------------------------------\n"
            f"Peak Von-Mises   : {self.max_von_mises_mpa:.2f} MPa\n"
            f"Max Deflection   : {self.max_displacement_mm:.4f} mm\n"
            f"Factor of Safety : {self.safety_factor:.2f} (Target: >= {self.required_safety_factor:.2f})\n"
            f"Status           : {status_icon} {self.status}\n"
            f"=======================================================\n"
        )

    def export_vtk(self, filepath: str) -> str:
        """
        Exports the 3D mesh with displacement and Von-Mises stress fields to standard VTK format
        for visualization in ParaView, PyVista, or Blender.
        """
        from .visualization import export_vtk
        return export_vtk(self, filepath)

    def export_html(self, filepath: str, deformation_scale: float = 10.0) -> str:
        """
        Generates a standalone, self-contained interactive 3D WebGL HTML simulation report.
        Allows rotating, zooming, real-time deformation scaling, and inspecting stress contours.
        """
        from .visualization import export_interactive_html
        return export_interactive_html(self, filepath, deformation_scale=deformation_scale)


class FEAStudy:
    """
    Finite Element Analysis Study configuration for a specific CAD solid part.
    Handles meshing, boundary conditions (fixing faces), load application, and solving.
    """

    def __init__(
        self,
        part_name: str,
        solid_shape: Optional[TopoDS.TopoDS_Shape] = None,
        material: Union[str, Material] = "S235JR",
        study_name: Optional[str] = None,
        mesh_size: Optional[float] = None,
        required_safety_factor: float = 1.5,
        max_displacement_mm: Optional[float] = None,
    ):
        self.part_name = part_name
        self.solid_shape = solid_shape
        self.study_name = study_name or f"FEA_{part_name}"
        self.material = material if isinstance(material, Material) else get_material(material)
        self.mesh_size = mesh_size
        if not math.isfinite(required_safety_factor) or required_safety_factor <= 0:
            raise ValueError("required_safety_factor must be finite and positive")
        if max_displacement_mm is not None and (not math.isfinite(max_displacement_mm) or max_displacement_mm <= 0):
            raise ValueError("max_displacement_mm must be finite and positive")
        if mesh_size is not None and (not math.isfinite(mesh_size) or mesh_size <= 0):
            raise ValueError("mesh_size must be finite and positive")
        self.required_safety_factor = required_safety_factor
        self.max_displacement_limit_mm = max_displacement_mm

        self._fixed_faces: List[Union[str, Callable[[float, float, float], bool]]] = []
        self._forces: List[Dict[str, Any]] = []

        # Mesh data
        self.nodes: Optional[np.ndarray] = None
        self.elements: Optional[np.ndarray] = None

    def set_shape(self, shape: TopoDS.TopoDS_Shape) -> FEAStudy:
        """Assign or update the OpenCASCADE solid shape to analyze."""
        self.solid_shape = shape
        self.nodes = self.elements = None
        return self

    def fix_face(
        self,
        face_selector: Union[str, Callable[[float, float, float], bool]],
    ) -> FEAStudy:
        """
        Fix all degrees of freedom (u_x = u_y = u_z = 0) on the designated boundary face.
        Selectors:
        - 'x_min' or 'left'
        - 'x_max' or 'right'
        - 'y_min' or 'front'
        - 'y_max' or 'back'
        - 'z_min' or 'bottom'
        - 'z_max' or 'top'
        - Callable: func(x, y, z) -> bool
        """
        self._fixed_faces.append(face_selector)
        return self

    def apply_force(
        self,
        face: Union[str, Callable[[float, float, float], bool]],
        force_vector: Tuple[float, float, float],
    ) -> FEAStudy:
        """
        Applies a resultant force vector (Fx, Fy, Fz) in Newtons,
        distributed equally across all surface nodes on the designated face.
        """
        if len(force_vector) != 3 or not np.isfinite(force_vector).all():
            raise ValueError("Force must contain three finite components")
        self._forces.append({
            "type": "force",
            "face": face,
            "vector": (float(force_vector[0]), float(force_vector[1]), float(force_vector[2])),
        })
        return self

    def apply_pressure(
        self,
        face: str,
        pressure_mpa: float,
    ) -> FEAStudy:
        """
        Applies a normal pressure in MPa (N/mm^2) over the designated boundary face.
        """
        if not math.isfinite(pressure_mpa):
            raise ValueError("Pressure must be finite")
        self._forces.append({
            "type": "pressure",
            "face": face,
            "pressure": float(pressure_mpa),
        })
        return self

    # ---------------------------------------------------------------------------
    # Automatic 3D Meshing via Gmsh OCC Bridge
    # ---------------------------------------------------------------------------

    def generate_mesh(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates a 3D linear tetrahedral mesh (C3D4) directly from the OpenCASCADE solid shape.
        """
        if self.solid_shape is None or self.solid_shape.IsNull():
            raise ValueError(f"Cannot mesh part '{self.part_name}': Solid shape is None or Null.")

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tf:
            step_path = tf.name

        try:
            # 1. Export solid to temporary STEP for Gmsh OCC
            writer = STEPControl.STEPControl_Writer()
            writer.Transfer(self.solid_shape, STEPControl.STEPControl_StepModelType.STEPControl_AsIs)
            writer.Write(step_path)

            # 2. Run Gmsh
            gmsh.initialize()
            gmsh.option.setNumber("General.Terminal", 0)  # Silence console output
            gmsh.model.add(f"cad_fea_{self.part_name}")
            gmsh.model.occ.importShapes(step_path)
            gmsh.model.occ.synchronize()

            # Automatic characteristic mesh sizing if not provided
            if self.mesh_size is not None and self.mesh_size > 0:
                gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(self.mesh_size))
                gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(self.mesh_size) * 0.25)
            else:
                # Estimate from bounding box: ~15 elements across largest dimension
                bbox = gmsh.model.getBoundingBox(-1, -1)
                dx = bbox[3] - bbox[0]
                dy = bbox[4] - bbox[1]
                dz = bbox[5] - bbox[2]
                max_dim = max(dx, dy, dz, 10.0)
                auto_size = max(max_dim / 15.0, 1.0)
                gmsh.option.setNumber("Mesh.CharacteristicLengthMax", auto_size)

            gmsh.model.mesh.generate(3)

            node_tags, coords, _ = gmsh.model.mesh.getNodes()
            coords = np.asarray(coords, dtype=np.float64).reshape((-1, 3))
            tag_to_idx = {tag: i for i, tag in enumerate(node_tags)}

            elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=3)

            raw_tets = []
            for t_idx, el_type in enumerate(elem_types):
                if el_type == 4:  # 4-node linear tetrahedron
                    raw_tets = elem_node_tags[t_idx].reshape((-1, 4))
                    break

            if len(raw_tets) == 0:
                raise RuntimeError(f"Gmsh failed to generate 3D tetrahedral elements for '{self.part_name}'.")

            # Remap tags to consecutive 0..N-1 node indices
            elements = np.empty(raw_tets.shape, dtype=np.int32)
            for i in range(len(raw_tets)):
                for j in range(4):
                    elements[i, j] = tag_to_idx[raw_tets[i, j]]

            self.nodes = coords
            self.elements = elements

            return coords, elements

        finally:
            try:
                gmsh.finalize()
            except Exception:
                pass
            if os.path.exists(step_path):
                try:
                    os.remove(step_path)
                except Exception:
                    pass

    # ---------------------------------------------------------------------------
    # Boundary Node Identification
    # ---------------------------------------------------------------------------

    def _get_matching_nodes(
        self,
        selector: Union[str, Callable[[float, float, float], bool]],
        tol_factor: float = 1e-8,
    ) -> List[int]:
        """Finds all mesh node indices satisfying the spatial face selector."""
        if self.nodes is None:
            return []

        pts = self.nodes
        if callable(selector):
            matched = [i for i, (x, y, z) in enumerate(pts) if selector(x, y, z)]
            return matched

        xmin, ymin, zmin = np.min(pts, axis=0)
        xmax, ymax, zmax = np.max(pts, axis=0)
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        tol = max(tol_factor * max(dx, dy, dz), 1e-7)

        sel = str(selector).strip().lower()

        if sel in ("x_min", "left"):
            return np.where(np.abs(pts[:, 0] - xmin) <= tol)[0].tolist()
        elif sel in ("x_max", "right"):
            return np.where(np.abs(pts[:, 0] - xmax) <= tol)[0].tolist()
        elif sel in ("y_min", "front"):
            return np.where(np.abs(pts[:, 1] - ymin) <= tol)[0].tolist()
        elif sel in ("y_max", "back"):
            return np.where(np.abs(pts[:, 1] - ymax) <= tol)[0].tolist()
        elif sel in ("z_min", "bottom", "all_bottom"):
            return np.where(np.abs(pts[:, 2] - zmin) <= tol)[0].tolist()
        elif sel in ("z_max", "top", "all_top"):
            return np.where(np.abs(pts[:, 2] - zmax) <= tol)[0].tolist()
        else:
            # Fallback: check if selector matches any coordinate
            return []

    # ---------------------------------------------------------------------------
    # Solution Engine
    # ---------------------------------------------------------------------------

    def _boundary_triangles(self):
        """Oriented external tetrahedral facets, including cavity surfaces."""
        faces = {}
        for tet in self.elements:
            for opposite in range(4):
                ids = [int(tet[j]) for j in range(4) if j != opposite]
                key = tuple(sorted(ids))
                if key in faces:
                    count, _ = faces[key]
                    faces[key] = (count + 1, None)
                    continue
                xyz = self.nodes[ids]
                area_vector = np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0]) / 2
                if np.dot(area_vector, self.nodes[tet[opposite]] - xyz[0]) > 0:
                    area_vector = -area_vector
                faces[key] = (1, (ids, area_vector))
        if any(count > 2 for count, _ in faces.values()):
            raise ValueError("Non-manifold tetrahedral mesh")
        return [face for count, face in faces.values() if count == 1]

    def preview_boundary_conditions(self):
        """Return resolved mesh nodes and loads without solving or inventing restraints."""
        if not self._fixed_faces:
            raise ValueError("No restraints specified; call fix_face explicitly")
        if not self._forces:
            raise ValueError("No loads specified")
        if self.nodes is None or self.elements is None:
            self.generate_mesh()
        fixed = set()
        for selector in self._fixed_faces:
            matching = self._get_matching_nodes(selector)
            if not matching:
                raise ValueError(f"Restraint selector matched no nodes: {selector!r}")
            fixed.update(matching)
        forces = np.zeros_like(self.nodes, dtype=float)
        loads = []
        for item in self._forces:
            selected = self._get_matching_nodes(item['face'])
            if not selected:
                raise ValueError(f"Load selector matched no nodes: {item['face']!r}")
            load = np.zeros_like(forces)
            area = None
            if item['type'] == 'force':
                load[selected] = np.asarray(item['vector']) / len(selected)
            else:
                chosen = set(selected)
                area = 0.0
                for ids, vector in self._boundary_triangles():
                    if set(ids).issubset(chosen):
                        area += float(np.linalg.norm(vector))
                        load[ids] += -item['pressure'] * vector / 3
                if area <= 0:
                    raise ValueError("Pressure selector matched no boundary triangles")
            forces += load
            loads.append({'selector': repr(item['face']), 'node_count': len(selected),
                          'area_mm2': area, 'resultant_n': load.sum(axis=0).tolist()})
        if not np.isfinite(forces).all() or not np.any(forces):
            raise ValueError("Resolved loads are zero or non-finite")
        return {'fixed_nodes': sorted(fixed), 'nodal_forces': forces,
                'loads': loads, 'resultant_n': forces.sum(axis=0).tolist()}

    def solve(self) -> FEAResult:
        """Solve validated linear elasticity; is_safe means configured criteria passed."""
        preview = self.preview_boundary_conditions()
        fixed_indices = set(preview['fixed_nodes'])
        nodal_forces = {i: tuple(f) for i, f in enumerate(preview['nodal_forces']) if np.any(f)}

        # Run linear elasticity solver
        solver = LinearElasticitySolver(self.nodes, self.elements, self.material)
        sol = solver.solve(fixed_indices, nodal_forces)

        # Evaluate safety factor
        peak_stress = sol.max_von_mises
        sy = self.material.yield_strength_mpa
        fos = sy / peak_stress if peak_stress > 0 else math.inf
        criteria = {'safety_factor': bool(fos >= self.required_safety_factor)}
        if self.max_displacement_limit_mm is not None:
            criteria['displacement'] = bool(sol.max_displacement <= self.max_displacement_limit_mm)
        is_safe = all(criteria.values())
        status = 'PASS' if is_safe else ('WARNING_YIELD' if not criteria['safety_factor'] else 'WARNING_DISPLACEMENT')

        return FEAResult(
            study_name=self.study_name,
            part_name=self.part_name,
            material=self.material,
            num_nodes=len(self.nodes),
            num_elements=len(self.elements),
            max_von_mises_mpa=round(peak_stress, 2),
            max_displacement_mm=round(sol.max_displacement, 4),
            yield_strength_mpa=sy,
            safety_factor=round(fos, 2),
            is_safe=is_safe,
            status=status,
            nodal_displacements=sol.displacements,
            nodal_von_mises=sol.nodal_von_mises,
            nodes=self.nodes,
            elements=self.elements,
            raw_solution=sol,
            required_safety_factor=self.required_safety_factor,
            max_displacement_limit_mm=self.max_displacement_limit_mm,
            criteria_passed=criteria,
        )
