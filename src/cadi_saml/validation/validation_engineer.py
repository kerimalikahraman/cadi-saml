"""
cadi_saml.validation.validation_engineer
========================================
Mechanical validation engine for CAD assemblies.
Checks manifoldness, detects clashes (intersections), and formats structured LLM feedback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import OCP.BRepAlgoAPI as BRepAlgo
import OCP.BRepCheck as BRepCheck
import OCP.GProp as GProp
import OCP.BRepGProp as BRepGProp
import OCP.TopoDS as TopoDS
import OCP.TopAbs as TopAbs
import OCP.TopExp as TopExp


@dataclass
class ClashReport:
    first_part: str
    second_part: str
    clash_volume: float
    description: str


@dataclass
class ClearanceReport:
    first_part: str
    second_part: str
    distance_mm: float
    point_on_first: Tuple[float, float, float]
    point_on_second: Tuple[float, float, float]
    status: str  # 'COLLISION', 'WARNING_PROXIMITY', 'CLEAR'



class ValidationEngineer:
    """Automated CAD verification engineer."""

    def __init__(self, clash_volume_tolerance: float = 0.05):
        self.clash_tolerance = clash_volume_tolerance

    def check_manifold(
        self, shape_or_name: Any, shape: Optional[TopoDS.TopoDS_Shape] = None
    ) -> bool:
        """Check if a solid or compound assembly is topologically valid and closed (watertight)."""
        target_shape = shape if shape is not None else shape_or_name
        if target_shape is None or target_shape.IsNull():
            return False

        if target_shape.ShapeType() == TopAbs.TopAbs_COMPOUND:
            exp = TopExp.TopExp_Explorer(target_shape, TopAbs.TopAbs_SOLID)
            if not exp.More():
                return bool(BRepCheck.BRepCheck_Analyzer(target_shape).IsValid())
            while exp.More():
                s = TopoDS.TopoDS.Solid_s(exp.Current())
                if not BRepCheck.BRepCheck_Analyzer(s).IsValid():
                    return False
                exp.Next()
            return True

        checker = BRepCheck.BRepCheck_Analyzer(target_shape)
        return bool(checker.IsValid())


    def check_clashes(self, solids: Dict[str, TopoDS.TopoDS_Shape]) -> List[ClashReport]:
        """
        Detect volumetric interferences (clashes) between pairs of parts.
        Complexity Architecture:
          - Broad-Phase: 1D Sweep-and-Prune on Axis-Aligned Bounding Boxes (AABB) in O(N log N).
            Sorts parts by X_min and prunes non-overlapping pairs before full 3D AABB testing.
          - Narrow-Phase: Exact OpenCASCADE B-Rep boolean intersection (BRepAlgoAPI_Common)
            executed ONLY on the K overlapping candidate pairs (O(K), where K << N²).
        """
        import OCP.Bnd as Bnd
        import OCP.BRepBndLib as BRepBndLib

        clashes: List[ClashReport] = []

        # 1. Precompute AABB bounding boxes in O(N)
        bboxes: Dict[str, Bnd.Bnd_Box] = {}
        intervals: List[Tuple[float, float, str]] = []
        for name, shape in solids.items():
            if shape is not None and not shape.IsNull():
                bbox = Bnd.Bnd_Box()
                BRepBndLib.BRepBndLib.Add_s(shape, bbox)
                xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
                bboxes[name] = bbox
                intervals.append((xmin, xmax, name))

        # 2. Broad-Phase 1D Sweep-and-Prune: sort intervals by X_min in O(N log N)
        intervals.sort(key=lambda item: item[0])
        num_intervals = len(intervals)

        candidate_pairs: List[Tuple[str, str]] = []
        for i in range(num_intervals):
            xmin_i, xmax_i, name1 = intervals[i]
            for j in range(i + 1, num_intervals):
                xmin_j, _, name2 = intervals[j]
                # If X_min of next part is greater than X_max of current, no further overlaps on X are possible
                if xmin_j > xmax_i:
                    break
                # Full 3D AABB overlap check (testing Y and Z extents)
                if not bboxes[name1].IsOut(bboxes[name2]):
                    candidate_pairs.append((name1, name2))

        # 3. Narrow-Phase: Exact OpenCASCADE Boolean Intersection on candidate pairs in O(K)
        for name1, name2 in candidate_pairs:
            shape1 = solids[name1]
            shape2 = solids[name2]

            common = BRepAlgo.BRepAlgoAPI_Common(shape1, shape2)
            if common.IsDone():
                intersect_shape = common.Shape()
                props = GProp.GProp_GProps()
                BRepGProp.BRepGProp.VolumeProperties_s(intersect_shape, props)
                vol = props.Mass()

                if vol > self.clash_tolerance:
                    clashes.append(
                        ClashReport(
                            first_part=name1,
                            second_part=name2,
                            clash_volume=round(vol, 3),
                            description=(
                                f"Clash detected between '{name1}' and '{name2}'! "
                                f"Intersection volume: {round(vol, 2)} mm³."
                            ),
                        )
                    )

        return clashes

    def generate_feedback(self, clashes: List[ClashReport]) -> Optional[str]:
        """Format clash errors into natural, structured feedback suitable for an LLM."""
        if not clashes:
            return None

        lines = ["[ValidationEngineer] Montaj Dogrulama Raporu:"]
        for c in clashes:
            lines.append(f" - [CAKISMA / CLASH] {c.first_part} ile {c.second_part} uzayda cakısıyor ({c.clash_volume} mm3).")
            lines.append(f"   [Oneri / Fix]: Montaj ofsetini veya parca konumunu revize edin.")

        return "\n".join(lines)


    def heal_and_sew(
        self,
        shape: TopoDS.TopoDS_Shape,
        tolerance: float = 1e-3,
        fix_manifold: bool = True,
    ) -> TopoDS.TopoDS_Shape:
        """
        Heal detached surface sheets, stitch micro-gaps, and fix topology
        to produce a clean, watertight manifold B-Rep solid.
        Uses OpenCASCADE BRepBuilderAPI_Sewing and ShapeFix_Shape.
        """
        import OCP.BRepBuilderAPI as BRepBuilderAPI
        import OCP.ShapeFix as ShapeFix

        # 1. Sewing faces together
        sewing = BRepBuilderAPI.BRepBuilderAPI_Sewing(tolerance)
        sewing.Add(shape)
        sewing.Perform()
        sewn_shape = sewing.SewedShape()

        # 2. ShapeFix geometry repair
        if fix_manifold:
            sfix = ShapeFix.ShapeFix_Shape(sewn_shape)
            sfix.SetPrecision(tolerance)
            sfix.SetMaxTolerance(tolerance * 10.0)
            sfix.Perform()
            return sfix.Shape()

        return sewn_shape

    def heal_shape(
        self,
        shape: TopoDS.TopoDS_Shape,
        tolerance: float = 1e-3,
        fix_manifold: bool = True,
    ) -> TopoDS.TopoDS_Shape:
        """Alias for heal_and_sew to fix imperfect external geometry."""
        return self.heal_and_sew(shape=shape, tolerance=tolerance, fix_manifold=fix_manifold)

    def compute_clearance(
        self,
        shape_a: TopoDS.TopoDS_Shape,
        shape_b: TopoDS.TopoDS_Shape,
    ) -> Dict[str, Any]:
        """
        Computes exact minimum distance (clearance) and closest 3D points
        between two solids using OpenCASCADE BRepExtrema_DistShapeShape.
        """
        import OCP.BRepExtrema as BRepExtrema

        if shape_a is None or shape_a.IsNull() or shape_b is None or shape_b.IsNull():
            raise ValueError("Invalid null shape passed to compute_clearance")

        dist_calc = BRepExtrema.BRepExtrema_DistShapeShape(shape_a, shape_b)
        dist_calc.Perform()

        if not dist_calc.IsDone():
            raise RuntimeError("BRepExtrema_DistShapeShape calculation failed")

        min_dist = float(dist_calc.Value())
        p1 = (0.0, 0.0, 0.0)
        p2 = (0.0, 0.0, 0.0)

        if dist_calc.NbSolution() > 0:
            pt1 = dist_calc.PointOnShape1(1)
            pt2 = dist_calc.PointOnShape2(1)
            p1 = (round(pt1.X(), 3), round(pt1.Y(), 3), round(pt1.Z(), 3))
            p2 = (round(pt2.X(), 3), round(pt2.Y(), 3), round(pt2.Z(), 3))

        return {
            "distance_mm": round(min_dist, 3),
            "point_on_a": p1,
            "point_on_b": p2,
            "num_closest_solutions": dist_calc.NbSolution(),
        }

    def check_clearances(
        self,
        solids: Dict[str, TopoDS.TopoDS_Shape],
        min_clearance_mm: float = 2.0,
    ) -> List[ClearanceReport]:
        """
        Evaluates minimum clearance across all part pairs in an assembly.
        Categorizes as COLLISION (dist < 0.05mm), WARNING_PROXIMITY (dist < min_clearance_mm),
        or CLEAR.
        """
        reports: List[ClearanceReport] = []
        names = list(solids.keys())

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                s1, s2 = solids[n1], solids[n2]
                if s1.IsNull() or s2.IsNull():
                    continue

                res = self.compute_clearance(s1, s2)
                d = res["distance_mm"]
                if d <= 0.05:
                    status = "COLLISION"
                elif d < min_clearance_mm:
                    status = "WARNING_PROXIMITY"
                else:
                    status = "CLEAR"

                reports.append(
                    ClearanceReport(
                        first_part=n1,
                        second_part=n2,
                        distance_mm=d,
                        point_on_first=res["point_on_a"],
                        point_on_second=res["point_on_b"],
                        status=status,
                    )
                )

        return reports


    def diagnose_for_llm(
        self,
        solids: Dict[str, TopoDS.TopoDS_Shape],
        ir: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Deep diagnostic analysis designed specifically for LLM self-correction.
        Analyzes:
        1. Non-manifoldness & watertightness per part.
        2. Volumetric part-on-part interference / clash.
        3. Formulates natural language repair guidance and parameter patch suggestions.
        """
        manifold_failures: List[str] = []
        for name, shape in solids.items():
            if shape.IsNull() or not self.check_manifold(shape):
                manifold_failures.append(name)

        clashes = self.check_clashes(solids)
        passed = (len(manifold_failures) == 0) and (len(clashes) == 0)

        prompt_lines: List[str] = []
        if passed:
            prompt_lines.append("[CADi Diagnostic]: All components are watertight (manifold) and zero clashes detected. Geometry passed solid integrity check (note: structural, tolerance, and manufacturability validation required for full production release).")
        else:
            prompt_lines.append("[CADi Diagnostic Failure Analysis]:")
            if manifold_failures:
                for mf in manifold_failures:
                    prompt_lines.append(f"  - HATA (Non-Manifold): '{mf}' parcasi acik yuzey barindiriyor veya kati geometrisi bozuk.")
                    prompt_lines.append(f"    [Duzeltme / Fix]: 'val.heal_and_sew()' uygulayin veya eskiz/profil cizgilerinin kapali oldugunu dogrulayin.")
            if clashes:
                for c in clashes:
                    prompt_lines.append(f"  - HATA (Cakisma / Clash): '{c.first_part}' ile '{c.second_part}' parcalari {c.clash_volume:.2f} mm3 hacminde birbirinin icine gecmis.")
                    prompt_lines.append(f"    [Duzeltme / Fix]: '{c.first_part}' veya '{c.second_part}' montaj konumunu (mate offset) cakisma yonunde en az {max(1.0, (c.clash_volume ** (1/3))):.1f} mm kaydirin ya da 'asm.cut()' kullanarak yuva bosaltin.")


        return {
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "manifold_errors": manifold_failures,
            "clashes": [
                {
                    "first_part": c.first_part,
                    "second_part": c.second_part,
                    "volume_mm3": c.clash_volume,
                    "description": c.description,
                }
                for c in clashes
            ],
            "llm_repair_prompt": "\n".join(prompt_lines),
        }

    def compute_mass_properties(
        self,
        shape: TopoDS.TopoDS_Shape,
        density_kg_m3: Optional[float] = None,
        material: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Computes physical mass properties, volume, surface area, center of gravity (CoG),
        and the 3x3 inertia tensor using OpenCASCADE GProp_GProps.

        Args:
            shape: OpenCASCADE TopoDS_Shape (solid or compound).
            density_kg_m3: Material density in kg/m^3 (e.g. 2700 for Aluminum, 7850 for Steel).
            material: Optional material name (e.g. 'Aluminum', 'Steel', 'CarbonFiber').
        """
        if shape is None or shape.IsNull():
            raise ValueError("Shape is Null, cannot compute mass properties")

        # Standard material density lookup (kg/m^3)
        MATERIAL_DENSITIES = {
            "steel": 7850.0,
            "carbon_steel": 7850.0,
            "stainless_steel": 7950.0,
            "aluminum": 2700.0,
            "al6061": 2700.0,
            "al7075": 2810.0,
            "titanium": 4430.0,
            "copper": 8960.0,
            "cast_iron": 7200.0,
            "carbon_fiber": 1600.0,
            "rubber": 1150.0,
            "nylon": 1140.0,
            "abs": 1050.0,
        }

        rho = density_kg_m3
        if rho is None and material:
            mat_key = material.lower().replace("-", "_").replace(" ", "_")
            for k, v in MATERIAL_DENSITIES.items():
                if k in mat_key:
                    rho = v
                    break
        if rho is None:
            rho = 2700.0  # Default to Aluminum Al6061

        # 1. Volume and Centroid via BRepGProp
        v_props = GProp.GProp_GProps()
        BRepGProp.BRepGProp.VolumeProperties_s(shape, v_props)
        vol_mm3 = v_props.Mass()  # mm^3

        cog_pnt = v_props.CentreOfMass()
        cog = (round(cog_pnt.X(), 3), round(cog_pnt.Y(), 3), round(cog_pnt.Z(), 3))

        # 2. Surface Area via SurfaceProperties
        s_props = GProp.GProp_GProps()
        BRepGProp.BRepGProp.SurfaceProperties_s(shape, s_props)
        area_mm2 = s_props.Mass()  # mm^2

        # 3. Mass calculation (1 m^3 = 1e9 mm^3)
        rho_kg_mm3 = rho / 1e9
        mass_kg = vol_mm3 * rho_kg_mm3

        # 4. Inertia tensor at origin
        mat_in = v_props.MatrixOfInertia()
        # Scale inertia from mm^5 to kg*mm^2
        ixx = mat_in.Value(1, 1) * rho_kg_mm3
        iyy = mat_in.Value(2, 2) * rho_kg_mm3
        izz = mat_in.Value(3, 3) * rho_kg_mm3
        ixy = mat_in.Value(1, 2) * rho_kg_mm3
        ixz = mat_in.Value(1, 3) * rho_kg_mm3
        iyz = mat_in.Value(2, 3) * rho_kg_mm3

        return {
            "volume_mm3": round(vol_mm3, 2),
            "surface_area_mm2": round(area_mm2, 2),
            "density_kg_m3": round(rho, 1),
            "mass_kg": round(mass_kg, 4),
            "mass_grams": round(mass_kg * 1000.0, 2),
            "center_of_gravity": cog,
            "cog_x": cog[0],
            "cog_y": cog[1],
            "cog_z": cog[2],
            "inertia_kg_mm2": {
                "Ixx": round(ixx, 3),
                "Iyy": round(iyy, 3),
                "Izz": round(izz, 3),
                "Ixy": round(ixy, 3),
                "Ixz": round(ixz, 3),
                "Iyz": round(iyz, 3),
            },
        }


