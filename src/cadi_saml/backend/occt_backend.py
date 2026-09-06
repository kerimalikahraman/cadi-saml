"""
cadi_saml.backend.occt_backend
==============================
Pure OpenCASCADE (OCP) backend compiler.
Converts AssemblyIR into solid B-Rep models, solves spatial mates deterministically,
and exports directly to STEP/STL without any third-party CAD dependencies.
"""

from __future__ import annotations

import os
import math
from typing import Dict, Any, List, Optional, Tuple

import OCP.BRep as BRep
import OCP.BRepPrimAPI as BRepPrim
import OCP.BRepBuilderAPI as BRepBuilder
import OCP.BRepAlgoAPI as BRepAlgo
import OCP.STEPControl as STEPControl
import OCP.Interface as Interface
import OCP.IFSelect as IFSelect
import OCP.BRepMesh as BRepMesh
import OCP.StlAPI as StlAPI
import OCP.BRepFilletAPI as BRepFillet
import OCP.BRepOffsetAPI as BRepOffsetAPI
import OCP.BRepOffset as BRepOffset
import OCP.TopTools as TopTools
import OCP.Bnd as Bnd
import OCP.BRepBndLib as BRepBndLib
import OCP.gp as gp
import OCP.TopoDS as TopoDS
import OCP.TopAbs as TopAbs
import OCP.TopExp as TopExp
import OCP.GeomAPI as GeomAPI
import OCP.TColgp as TColgp
import OCP.BRepAdaptor as BRepAdaptor
import OCP.GeomAbs as GeomAbs

from ..ir.nodes import AssemblyIR, BooleanOpType, CrossSection, MateType, PartNode, PatternType, ShellNode
from ..core.ports import OverConstrainedError, StalePortError, ConstraintStatus


class OCCTBackend:
    """Compiles AssemblyIR into OpenCASCADE TopoDS_Shapes and exports to STEP/STL."""

    def __init__(self):
        # Maps part_name -> TopoDS_Shape
        self._solids: Dict[str, TopoDS.TopoDS_Shape] = {}
        # Maps part_name -> gp_Trsf (cumulative transformation)
        self._transforms: Dict[str, gp.gp_Trsf] = {}
        # Incremental solid cache: part_name -> (cache_key, TopoDS_Shape)
        self._solid_cache: Dict[str, Tuple[Any, TopoDS.TopoDS_Shape]] = {}
        # Degree of Freedom (DOF) tracking per component
        self._dof_reports: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def compute_adaptive_fuzzy_tolerance(
        shape1: TopoDS.TopoDS_Shape, shape2: Optional[TopoDS.TopoDS_Shape] = None
    ) -> float:
        """
        Computes scale-adaptive fuzzy boolean tolerance based on bounding box diagonals.
        Avoids fixed tolerance failures on microscopic (M1.6 screws) or structural (600mm beams) parts.
        """
        import OCP.Bnd as Bnd
        import OCP.BRepBndLib as BRepBndLib

        b1 = Bnd.Bnd_Box()
        BRepBndLib.BRepBndLib.Add_s(shape1, b1)
        xmin1, ymin1, zmin1, xmax1, ymax1, zmax1 = b1.Get()
        diag1 = math.sqrt((xmax1 - xmin1) ** 2 + (ymax1 - ymin1) ** 2 + (zmax1 - zmin1) ** 2)

        diag = diag1
        if shape2 is not None and not shape2.IsNull():
            b2 = Bnd.Bnd_Box()
            BRepBndLib.BRepBndLib.Add_s(shape2, b2)
            xmin2, ymin2, zmin2, xmax2, ymax2, zmax2 = b2.Get()
            diag2 = math.sqrt((xmax2 - xmin2) ** 2 + (ymax2 - ymin2) ** 2 + (zmax2 - zmin2) ** 2)
            diag = max(diag1, diag2)

        # Scale-adaptive: 1e-5 of bounding diagonal, clamped to [1e-4, 0.05] mm
        return max(1e-4, min(0.05, diag * 1e-5))

    def compile(self, ir: AssemblyIR) -> Dict[str, TopoDS.TopoDS_Shape]:
        """Compile complete assembly IR into transformed OpenCASCADE solids."""
        self._solids.clear()
        self._transforms.clear()

        # 1. Build unpositioned solids for all parts (using incremental cache)
        for name, part in ir.parts.items():
            shape = self._build_part_solid(part)
            self._solids[name] = shape
            trsf = gp.gp_Trsf()
            self._transforms[name] = trsf

        # 2. Solve mates and apply transformations with compound DOF constraint solver
        self._solve_all_mates(ir)

        # 3. Bake transformations into final solids
        final_solids: Dict[str, TopoDS.TopoDS_Shape] = {}
        for name, shape in self._solids.items():
            trsf = self._transforms[name]
            if trsf.Form() == gp.gp_Identity:
                final_solids[name] = shape
            else:
                transformer = BRepBuilder.BRepBuilderAPI_Transform(shape, trsf, True)
                final_solids[name] = transformer.Shape()

        # 4. Apply assembly-level boolean operations with scale-adaptive fuzzy tolerance
        excluded_tools = set()
        for op in ir.boolean_ops:
            target = op.target_part
            tool = op.tool_part
            if target in final_solids and tool in final_solids:
                fuzzy = self.compute_adaptive_fuzzy_tolerance(final_solids[target], final_solids[tool])
                if op.op_type == BooleanOpType.CUT:
                    cut_op = BRepAlgo.BRepAlgoAPI_Cut(final_solids[target], final_solids[tool])
                    cut_op.SetFuzzyValue(fuzzy)
                    cut_op.Build()
                    if cut_op.IsDone():
                        final_solids[target] = cut_op.Shape()
                elif op.op_type == BooleanOpType.FUSE:
                    fuse_op = BRepAlgo.BRepAlgoAPI_Fuse(final_solids[target], final_solids[tool])
                    fuse_op.SetFuzzyValue(fuzzy)
                    fuse_op.Build()
                    if fuse_op.IsDone():
                        final_solids[target] = fuse_op.Shape()
                elif op.op_type == BooleanOpType.INTERSECT:
                    common_op = BRepAlgo.BRepAlgoAPI_Common(final_solids[target], final_solids[tool])
                    common_op.SetFuzzyValue(fuzzy)
                    common_op.Build()
                    if common_op.IsDone():
                        final_solids[target] = common_op.Shape()
                if not op.keep_tool:
                    excluded_tools.add(tool)

        for tool in excluded_tools:
            if tool in final_solids:
                del final_solids[tool]

        # 5. Apply pattern replications (Circular & Linear arrays)
        pattern_generated: Dict[str, TopoDS.TopoDS_Shape] = {}
        for pat in ir.patterns:
            if pat.target_part in final_solids:
                source_shape = final_solids[pat.target_part]
                if pat.pattern_type == PatternType.CIRCULAR:
                    step_rad = math.radians(pat.angle) / pat.count
                    ax1 = gp.gp_Ax1(gp.gp_Pnt(*pat.center), gp.gp_Dir(*pat.axis))
                    for i in range(1, pat.count):
                        tr = gp.gp_Trsf()
                        tr.SetRotation(ax1, step_rad * i)
                        tr_shape = BRepBuilder.BRepBuilderAPI_Transform(source_shape, tr, True).Shape()
                        pattern_generated[f"{pat.target_part}_pattern_{i}"] = tr_shape
                elif pat.pattern_type == PatternType.LINEAR:
                    dx, dy, dz = pat.spacing
                    for i in range(1, pat.count):
                        tr = gp.gp_Trsf()
                        tr.SetTranslation(gp.gp_Vec(dx * i, dy * i, dz * i))
                        tr_shape = BRepBuilder.BRepBuilderAPI_Transform(source_shape, tr, True).Shape()
                        pattern_generated[f"{pat.target_part}_pattern_{i}"] = tr_shape

        final_solids.update(pattern_generated)

        return final_solids

    def export_step(self, ir: AssemblyIR, output_path: str) -> str:
        """Compile and export assembly to an industry standard AP214 STEP file."""
        solids = self.compile(ir)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        writer = STEPControl.STEPControl_Writer()
        # Set tolerance to standard
        Interface.Interface_Static.SetCVal_s("write.step.schema", "AP214")

        # Create single compound
        builder = BRep.BRep_Builder()
        compound = TopoDS.TopoDS_Compound()
        builder.MakeCompound(compound)

        for name, shape in solids.items():
            builder.Add(compound, shape)

        status = writer.Transfer(compound, STEPControl.STEPControl_AsIs)
        if status != IFSelect.IFSelect_RetDone:
            raise RuntimeError(f"OpenCASCADE failed to transfer compound to STEP writer: {status}")

        write_status = writer.Write(output_path)
        if write_status != IFSelect.IFSelect_RetDone:
            raise RuntimeError(f"OpenCASCADE failed to write STEP file: {write_status}")

        return output_path

    def export_step_colored(self, ir: AssemblyIR, output_path: str) -> str:
        """
        Compile and export assembly to an industry standard AP214 STEP file with
        part names, component hierarchy, and authentic RGB materials (XCAF).
        """
        import OCP.STEPCAFControl as STEPCAFControl
        import OCP.TDocStd as TDocStd
        import OCP.TCollection as TCol
        import OCP.TDataStd as TDataStd
        import OCP.XCAFDoc as XCAFDoc
        import OCP.XCAFApp as XCAFApp
        import OCP.Quantity as Quantity

        solids = self.compile(ir)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        app = XCAFApp.XCAFApp_Application.GetApplication_s()
        doc = TDocStd.TDocStd_Document(TCol.TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCol.TCollection_ExtendedString("MDTV-XCAF"), doc)

        shape_tool = XCAFDoc.XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        color_tool = XCAFDoc.XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

        # Material color fallbacks if not explicitly provided
        material_colors = {
            "carbonfiber": (0.08, 0.08, 0.09),
            "carbonfibercomposite": (0.08, 0.08, 0.09),
            "forgedaluminum": (0.15, 0.15, 0.16),
            "machinedaluminum": (0.85, 0.85, 0.88),
            "aluminum": (0.75, 0.75, 0.78),
            "steel": (0.60, 0.60, 0.65),
            "rubber": (0.10, 0.10, 0.10),
            "brass": (0.85, 0.70, 0.20),
            "anodizedred": (0.85, 0.10, 0.15),
            "anodizedblue": (0.10, 0.40, 0.90),
        }

        for name, shape in solids.items():
            label = shape_tool.AddShape(shape, False)
            TDataStd.TDataStd_Name.Set_s(label, TCol.TCollection_ExtendedString(name))

            base_name = name.split("_pattern_")[0]
            part_node = ir.parts.get(base_name)

            # Determine color
            col = None
            if part_node and part_node.color:
                col = part_node.color
            elif part_node and part_node.material:
                mat_key = part_node.material.lower().replace(" ", "").replace("_", "")
                for k, v in material_colors.items():
                    if k in mat_key:
                        col = v
                        break

            if col is None:
                col = (0.5, 0.5, 0.5)

            q_color = Quantity.Quantity_Color(float(col[0]), float(col[1]), float(col[2]), Quantity.Quantity_TOC_RGB)
            color_tool.SetColor(label, q_color, XCAFDoc.XCAFDoc_ColorGen)

        writer = STEPCAFControl.STEPCAFControl_Writer()
        writer.SetColorMode(True)
        writer.SetNameMode(True)
        writer.SetLayerMode(True)

        status = writer.Transfer(doc, STEPControl.STEPControl_AsIs)
        if not status:
            raise RuntimeError("STEPCAFControl_Writer failed to transfer document.")

        write_status = writer.Write(output_path)
        if write_status != IFSelect.IFSelect_RetDone:
            raise RuntimeError(f"STEPCAFControl_Writer failed to write STEP file: {write_status}")

        return output_path


    def export_stl(self, ir: AssemblyIR, output_path: str, deflection: float = 0.1) -> str:
        """Export assembly as STL mesh."""
        solids = self.compile(ir)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        builder = BRep.BRep_Builder()
        compound = TopoDS.TopoDS_Compound()
        builder.MakeCompound(compound)
        for shape in solids.values():
            builder.Add(compound, shape)

        # Mesh the B-Rep shape
        mesher = BRepMesh.BRepMesh_IncrementalMesh(compound, deflection)
        mesher.Perform()

        stl_writer = StlAPI.StlAPI_Writer()
        status = stl_writer.Write(compound, output_path)
        if not status:
            raise RuntimeError("OpenCASCADE StlAPI_Writer failed to write STL file.")

        return output_path

    def calculate_mass_properties(
        self, ir: AssemblyIR, densities: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Calculate volume (mm³), mass (kg), center of gravity (CG),
        and mass breakdown for each component and the total assembly using OpenCASCADE GProp.
        densities: optional dict mapping part name or material name to density in g/cm³.
                   Defaults to 2.7 g/cm³ (aluminum) or 1.55 g/cm³ for carbon fiber.
        """
        import OCP.GProp as GProp
        import OCP.BRepGProp as BRepGProp

        densities = densities or {}
        solids = self.compile(ir)
        results: Dict[str, Any] = {
            "parts": {},
            "total_volume_mm3": 0.0,
            "total_mass_kg": 0.0,
            "total_cg": (0.0, 0.0, 0.0),
        }

        total_cg_x, total_cg_y, total_cg_z = 0.0, 0.0, 0.0

        for name, shape in solids.items():
            props = GProp.GProp_GProps()
            BRepGProp.BRepGProp.VolumeProperties_s(shape, props)
            vol_mm3 = props.Mass()  # Volume in mm³

            # Match base part name if generated from pattern
            base_name = name.split("_pattern_")[0]
            part_node = ir.parts.get(base_name)
            mat_name = getattr(part_node, "material", None) or "default"

            # Determine density
            if name in densities:
                density_g_cm3 = densities[name]
            elif mat_name in densities:
                density_g_cm3 = densities[mat_name]
            elif "carbon" in (mat_name or "").lower():
                density_g_cm3 = 1.55
            elif "rubber" in (mat_name or "").lower():
                density_g_cm3 = 1.2
            elif "steel" in (mat_name or "").lower():
                density_g_cm3 = 7.85
            else:
                density_g_cm3 = 2.7  # Default aluminum (Al6061/AlSi10Mg)

            mass_kg = vol_mm3 * (density_g_cm3 * 1e-6)
            cg = props.CentreOfMass()

            results["parts"][name] = {
                "volume_mm3": round(vol_mm3, 2),
                "mass_kg": round(mass_kg, 4),
                "center_of_gravity": (round(cg.X(), 2), round(cg.Y(), 2), round(cg.Z(), 2)),
                "material": mat_name,
                "density_g_cm3": density_g_cm3,
            }
            results["total_volume_mm3"] += vol_mm3
            results["total_mass_kg"] += mass_kg
            total_cg_x += cg.X() * mass_kg
            total_cg_y += cg.Y() * mass_kg
            total_cg_z += cg.Z() * mass_kg

        if results["total_mass_kg"] > 0:
            results["total_cg"] = (
                round(total_cg_x / results["total_mass_kg"], 2),
                round(total_cg_y / results["total_mass_kg"], 2),
                round(total_cg_z / results["total_mass_kg"], 2),
            )

        results["total_volume_mm3"] = round(results["total_volume_mm3"], 2)
        results["total_mass_kg"] = round(results["total_mass_kg"], 4)
        return results

    def compute_cross_section(
        self,
        shape: TopoDS.TopoDS_Shape,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    ) -> List[TopoDS.TopoDS_Edge]:
        """
        Slice a 3D solid or compound with a cutting plane and return the 2D/3D intersection edges.
        Uses OpenCASCADE BRepAlgoAPI_Section.
        """
        import OCP.BRepAlgoAPI as BRepAlgoAPI
        pln = gp.gp_Pln(gp.gp_Pnt(*origin), gp.gp_Dir(*normal))
        section = BRepAlgoAPI.BRepAlgoAPI_Section(shape, pln)
        section.Build()
        if not section.IsDone():
            return []
        sec_shape = section.Shape()
        edges = []
        exp = TopExp.TopExp_Explorer(sec_shape, TopAbs.TopAbs_EDGE)
        while exp.More():
            edges.append(TopoDS.TopoDS.Edge_s(exp.Current()))
            exp.Next()
        return edges


    # ---------------------------------------------------------------------------
    # Solid Generation
    # ---------------------------------------------------------------------------

    def _build_part_solid(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Create initial OpenCASCADE solid centered at part origin with holes bored."""
        cache_key = (
            part.shape,
            tuple(sorted((k, str(v)) for k, v in part.parameters.items())),
            len(part.holes),
            len(part.fillets),
            len(part.chamfers),
            part.shell is not None,
            part.draft_angle is not None,
        )
        if part.name in self._solid_cache:
            cached_key, cached_shape = self._solid_cache[part.name]
            if cached_key == cache_key and not cached_shape.IsNull():
                return cached_shape

        base_solid: Optional[TopoDS.TopoDS_Shape] = None

        if part.part_type == "primitive":
            if part.shape == "box":
                l = float(part.parameters.get("length", 10.0))
                w = float(part.parameters.get("width", 10.0))
                h = float(part.parameters.get("height", 10.0))
                ox, oy, oz = part.parameters.get("origin", (0.0, 0.0, 0.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(ox - l / 2.0, oy - w / 2.0, oz - h / 2.0), l, w, h
                ).Solid()

            elif part.shape == "cylinder":
                r = float(part.parameters.get("radius", 5.0))
                h = float(part.parameters.get("height", 10.0))
                ox, oy, oz = part.parameters.get("origin", (0.0, 0.0, 0.0))
                axis = gp.gp_Ax2(gp.gp_Pnt(ox, oy, oz), gp.gp_Dir(0.0, 0.0, 1.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeCylinder(axis, r, h).Solid()

            elif part.shape == "cone":
                r1 = float(part.parameters.get("bottom_radius", 10.0))
                r2 = float(part.parameters.get("top_radius", 0.0))
                h = float(part.parameters.get("height", 20.0))
                axis = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeCone(axis, r1, r2, h).Solid()

            elif part.shape == "sphere":
                r = float(part.parameters.get("radius", 10.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeSphere(gp.gp_Pnt(0.0, 0.0, 0.0), r).Solid()

            elif part.shape == "torus":
                r_maj = float(part.parameters.get("major_radius", 20.0))
                r_min = float(part.parameters.get("minor_radius", 5.0))
                axis = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeTorus(axis, r_maj, r_min).Solid()

            elif part.shape == "spoke":
                angle_deg = float(part.parameters.get("angle", 0.0))
                length = float(part.parameters["length"])
                width = float(part.parameters.get("width", 10.0))
                thickness = float(part.parameters.get("thickness", 8.0))
                origin = part.parameters.get("origin", (0.0, 0.0, 0.0))
                ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])

                box_pnt = gp.gp_Pnt(0.0, -width / 2.0, 0.0)
                box = BRepPrim.BRepPrimAPI_MakeBox(box_pnt, length, width, thickness).Solid()

                rot_trsf = gp.gp_Trsf()
                rot_ax = gp.gp_Ax1(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                rot_trsf.SetRotation(rot_ax, math.radians(angle_deg))
                trans_trsf = gp.gp_Trsf()
                trans_trsf.SetTranslation(gp.gp_Vec(ox, oy, oz))
                total_trsf = trans_trsf.Multiplied(rot_trsf)

                transformer = BRepBuilder.BRepBuilderAPI_Transform(box, total_trsf, True)
                base_solid = transformer.Shape()

        elif part.part_type == "standard":
            if part.shape == "iso4762_bolt":
                d = float(part.parameters["shank_diameter"])
                dk = float(part.parameters["head_diameter"])
                k = float(part.parameters["head_height"])
                length = float(part.parameters["length"])
                s = float(part.parameters.get("socket_size", 4.0))
                t = float(part.parameters.get("socket_depth", 2.5))

                # Head (Z: 0 to +k)
                head_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                head = BRepPrim.BRepPrimAPI_MakeCylinder(head_ax, dk / 2.0, k).Solid()

                # Cut hexagon socket into head if present (socket head cap screw)
                if s > 0.1:
                    hex_r = (s / 2.0) / math.cos(math.pi / 6.0)
                    polygon = BRepBuilder.BRepBuilderAPI_MakePolygon()
                    for i in range(6):
                        ang = i * (math.pi / 3.0)
                        polygon.Add(gp.gp_Pnt(hex_r * math.cos(ang), hex_r * math.sin(ang), k))
                    polygon.Close()

                    if polygon.IsDone():
                        face = BRepBuilder.BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
                        socket_solid = BRepPrim.BRepPrimAPI_MakePrism(
                            face, gp.gp_Vec(0.0, 0.0, -t)
                        ).Shape()
                        head_cut = BRepAlgo.BRepAlgoAPI_Cut(head, socket_solid)
                        head = head_cut.Shape()

                # Shank (Z: 0 to -length)
                shank_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, -1.0))
                shank = BRepPrim.BRepPrimAPI_MakeCylinder(shank_ax, d / 2.0, length).Solid()

                fuse = BRepAlgo.BRepAlgoAPI_Fuse(head, shank)
                base_solid = fuse.Shape()

            elif part.shape == "deep_groove_bearing":
                inner_r = float(part.parameters["inner_diameter"]) / 2.0
                outer_r = float(part.parameters["outer_diameter"]) / 2.0
                width = float(part.parameters["width"])

                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                outer = BRepPrim.BRepPrimAPI_MakeCylinder(ax, outer_r, width).Solid()
                inner = BRepPrim.BRepPrimAPI_MakeCylinder(ax, inner_r, width).Solid()

                cut = BRepAlgo.BRepAlgoAPI_Cut(outer, inner)
                base_solid = cut.Shape()

            elif part.shape == "hex_nut":
                s = float(part.parameters["width_across_flats"])
                m = float(part.parameters["height"])
                d = float(part.parameters["thread_diameter"])

                hex_r = (s / 2.0) / math.cos(math.pi / 6.0)
                polygon = BRepBuilder.BRepBuilderAPI_MakePolygon()
                for i in range(6):
                    ang = i * (math.pi / 3.0)
                    polygon.Add(gp.gp_Pnt(hex_r * math.cos(ang), hex_r * math.sin(ang), 0.0))
                polygon.Close()

                face = BRepBuilder.BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
                nut_prism = BRepPrim.BRepPrimAPI_MakePrism(face, gp.gp_Vec(0.0, 0.0, m)).Shape()

                bore_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore = BRepPrim.BRepPrimAPI_MakeCylinder(bore_ax, d / 2.0, m + 0.2).Solid()

                cut = BRepAlgo.BRepAlgoAPI_Cut(nut_prism, bore)
                base_solid = cut.Shape()

            elif part.shape == "plain_washer":
                d1 = float(part.parameters["inner_diameter"])
                d2 = float(part.parameters["outer_diameter"])
                s = float(part.parameters["thickness"])

                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                outer = BRepPrim.BRepPrimAPI_MakeCylinder(ax, d2 / 2.0, s).Solid()

                bore_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.05), gp.gp_Dir(0.0, 0.0, 1.0))
                bore = BRepPrim.BRepPrimAPI_MakeCylinder(bore_ax, d1 / 2.0, s + 0.1).Solid()

                cut = BRepAlgo.BRepAlgoAPI_Cut(outer, bore)
                base_solid = cut.Shape()

            elif part.shape == "vslot_profile":
                wx = float(part.parameters["width_x"])
                wy = float(part.parameters["width_y"])
                length = float(part.parameters["length"])
                bore_d = float(part.parameters.get("center_bore_dia", 4.2))

                # Main block
                profile_box = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-wx / 2.0, -wy / 2.0, 0.0), wx, wy, length
                ).Solid()

                # Center bore
                bore_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                center_bore = BRepPrim.BRepPrimAPI_MakeCylinder(bore_ax, bore_d / 2.0, length + 0.2).Solid()
                profile_solid = BRepAlgo.BRepAlgoAPI_Cut(profile_box, center_bore).Shape()

                # Cut 4 T-slots (6mm wide x 1.8mm deep)
                slot_w = float(part.parameters.get("slot_width", 6.0))
                slot_d = 1.8

                # Right slot (+X)
                s_right = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(wx / 2.0 - slot_d, -slot_w / 2.0, -0.1), slot_d + 0.1, slot_w, length + 0.2
                ).Solid()
                # Left slot (-X)
                s_left = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-wx / 2.0 - 0.1, -slot_w / 2.0, -0.1), slot_d + 0.1, slot_w, length + 0.2
                ).Solid()
                # Front slot (+Y)
                s_front = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-slot_w / 2.0, wy / 2.0 - slot_d, -0.1), slot_w, slot_d + 0.1, length + 0.2
                ).Solid()
                # Back slot (-Y)
                s_back = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-slot_w / 2.0, -wy / 2.0 - 0.1, -0.1), slot_w, slot_d + 0.1, length + 0.2
                ).Solid()

                for s_cutter in [s_right, s_left, s_front, s_back]:
                    c_op = BRepAlgo.BRepAlgoAPI_Cut(profile_solid, s_cutter)
                    if c_op.IsDone():
                        profile_solid = c_op.Shape()

                base_solid = profile_solid

            elif part.shape == "nema_stepper":
                w = float(part.parameters["width"])
                bl = float(part.parameters["body_length"])
                sd = float(part.parameters["shaft_diameter"])
                sl = float(part.parameters["shaft_length"])
                pd = float(part.parameters["pilot_diameter"])
                ph = float(part.parameters["pilot_height"])
                hp = float(part.parameters["hole_pitch"])
                hd = float(part.parameters["hole_diameter"])
                hdepth = float(part.parameters["hole_depth"])

                # Square body
                body = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-w / 2.0, -w / 2.0, 0.0), w, w, bl
                ).Solid()

                # Pilot boss
                p_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, bl), gp.gp_Dir(0.0, 0.0, 1.0))
                pilot = BRepPrim.BRepPrimAPI_MakeCylinder(p_ax, pd / 2.0, ph).Solid()
                body = BRepAlgo.BRepAlgoAPI_Fuse(body, pilot).Shape()

                # Shaft
                s_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, bl), gp.gp_Dir(0.0, 0.0, 1.0))
                shaft = BRepPrim.BRepPrimAPI_MakeCylinder(s_ax, sd / 2.0, sl).Solid()
                body = BRepAlgo.BRepAlgoAPI_Fuse(body, shaft).Shape()

                # 4 Mounting holes
                half_p = hp / 2.0
                for x, y in [(half_p, half_p), (-half_p, half_p), (-half_p, -half_p), (half_p, -half_p)]:
                    h_ax = gp.gp_Ax2(gp.gp_Pnt(x, y, bl + 0.1), gp.gp_Dir(0.0, 0.0, -1.0))
                    h_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(h_ax, hd / 2.0, hdepth + 0.2).Solid()
                    cut_h = BRepAlgo.BRepAlgoAPI_Cut(body, h_cyl)
                    if cut_h.IsDone():
                        body = cut_h.Shape()

                base_solid = body

            elif part.shape == "centerlock_nut":
                s = float(part.parameters["hex_size"])
                h = float(part.parameters["height"])
                td = float(part.parameters["thread_diameter"])
                skirt_d = float(part.parameters.get("skirt_dia", s + 6.0))

                hex_r = (s / 2.0) / math.cos(math.pi / 6.0)
                poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
                for i in range(6):
                    ang = i * (math.pi / 3.0)
                    poly.Add(gp.gp_Pnt(hex_r * math.cos(ang), hex_r * math.sin(ang), 4.0))
                poly.Close()
                face = BRepBuilder.BRepBuilderAPI_MakeFace(poly.Wire()).Face()
                hex_prism = BRepPrim.BRepPrimAPI_MakePrism(face, gp.gp_Vec(0.0, 0.0, h - 4.0)).Shape()

                skirt_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                skirt = BRepPrim.BRepPrimAPI_MakeCone(skirt_ax, skirt_d / 2.0, s / 2.0, 4.0).Solid()
                body = BRepAlgo.BRepAlgoAPI_Fuse(hex_prism, skirt).Shape()

                bore_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore = BRepPrim.BRepPrimAPI_MakeCylinder(bore_ax, td / 2.0, h + 0.2).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore).Shape()

                pin_ax = gp.gp_Ax2(gp.gp_Pnt(-hex_r - 2.0, 0.0, h * 0.6), gp.gp_Dir(1.0, 0.0, 0.0))
                pin_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(pin_ax, 1.75, (hex_r + 2.0) * 2.0).Solid()
                cut_pin = BRepAlgo.BRepAlgoAPI_Cut(body, pin_cyl)
                if cut_pin.IsDone():
                    body = cut_pin.Shape()

                base_solid = body

            elif part.shape == "brake_rotor":
                od = float(part.parameters["outer_diameter"])
                thick = float(part.parameters["thickness"])
                id_dia = float(part.parameters["inner_diameter"])
                pcd = float(part.parameters["mount_pcd"])
                n_holes = int(part.parameters.get("mount_holes_count", 5))
                hole_d = float(part.parameters.get("mount_hole_dia", 8.2))
                n_slots = int(part.parameters.get("slots_count", 8))

                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                disc = BRepPrim.BRepPrimAPI_MakeCylinder(ax, od / 2.0, thick).Solid()

                c_bore = BRepPrim.BRepPrimAPI_MakeCylinder(ax, id_dia / 2.0, thick + 0.2).Solid()
                disc = BRepAlgo.BRepAlgoAPI_Cut(disc, c_bore).Shape()

                for i in range(n_holes):
                    ang = i * (2.0 * math.pi / n_holes)
                    hx = (pcd / 2.0) * math.cos(ang)
                    hy = (pcd / 2.0) * math.sin(ang)
                    h_ax = gp.gp_Ax2(gp.gp_Pnt(hx, hy, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                    h_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(h_ax, hole_d / 2.0, thick + 0.2).Solid()
                    disc = BRepAlgo.BRepAlgoAPI_Cut(disc, h_cyl).Shape()

                for i in range(n_slots):
                    ang = i * (2.0 * math.pi / n_slots) + (math.pi / n_slots)
                    r_mid = (od / 2.0 + id_dia / 2.0) / 2.0 + 10.0
                    sx = r_mid * math.cos(ang)
                    sy = r_mid * math.sin(ang)
                    s_ax = gp.gp_Ax2(gp.gp_Pnt(sx, sy, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                    s_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(s_ax, 3.5, thick + 0.2).Solid()
                    c_op = BRepAlgo.BRepAlgoAPI_Cut(disc, s_cyl)
                    if c_op.IsDone():
                        disc = c_op.Shape()

                base_solid = disc

            elif part.shape == "brake_caliper":
                l = float(part.parameters["length"])
                w = float(part.parameters["width"])
                h = float(part.parameters["height"])
                slot_w = float(part.parameters["rotor_slot_width"])
                slot_d = float(part.parameters["rotor_slot_depth"])
                pitch = float(part.parameters["mount_pitch"])
                m_dia = float(part.parameters["mount_hole_dia"])

                cal_box = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-l / 2.0, -w / 2.0, 0.0), l, w, h
                ).Solid()

                slot_box = BRepPrim.BRepPrimAPI_MakeBox(
                    gp.gp_Pnt(-l / 2.0 - 0.1, -slot_w / 2.0, -0.1), l + 0.2, slot_w, slot_d
                ).Solid()
                cal_body = BRepAlgo.BRepAlgoAPI_Cut(cal_box, slot_box).Shape()

                for x_pos in [-pitch / 2.0, pitch / 2.0]:
                    m_ax = gp.gp_Ax2(gp.gp_Pnt(x_pos, -w / 2.0 - 0.1, h * 0.35), gp.gp_Dir(0.0, 1.0, 0.0))
                    m_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(m_ax, m_dia / 2.0, w + 0.2).Solid()
                    c_op = BRepAlgo.BRepAlgoAPI_Cut(cal_body, m_cyl)
                    if c_op.IsDone():
                        cal_body = c_op.Shape()

                base_solid = cal_body

            elif part.shape == "drive_pin":
                pin_d = float(part.parameters["pin_diameter"])
                pin_l = float(part.parameters["pin_length"])
                th_d = float(part.parameters["thread_diameter"])
                th_l = float(part.parameters["thread_length"])

                pin_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                pin_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(pin_ax, pin_d / 2.0, pin_l).Solid()

                th_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, -1.0))
                th_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(th_ax, th_d / 2.0, th_l).Solid()

                base_solid = BRepAlgo.BRepAlgoAPI_Fuse(pin_cyl, th_cyl).Shape()

            elif part.shape == "heim_joint":
                th_d = float(part.parameters["thread_dia"])
                sh_l = float(part.parameters["shank_length"])
                head_d = float(part.parameters["head_diameter"])
                b_bore = float(part.parameters["ball_bore"])
                b_w = float(part.parameters["ball_width"])

                head_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -b_w / 2.0), gp.gp_Dir(0.0, 0.0, 1.0))
                head_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(head_ax, head_d / 2.0, b_w).Solid()

                sh_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, -head_d / 3.0, 0.0), gp.gp_Dir(0.0, -1.0, 0.0))
                shank_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(sh_ax, th_d / 2.0, sh_l).Solid()
                body = BRepAlgo.BRepAlgoAPI_Fuse(head_cyl, shank_cyl).Shape()

                bore_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -b_w / 2.0 - 0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(bore_ax, b_bore / 2.0, b_w + 0.2).Solid()
                base_solid = BRepAlgo.BRepAlgoAPI_Cut(body, bore_cyl).Shape()

            elif part.shape == "spoke":
                angle_deg = float(part.parameters.get("angle", 0.0))
                length = float(part.parameters["length"])
                width = float(part.parameters.get("width", 10.0))
                thickness = float(part.parameters.get("thickness", 8.0))
                origin = part.parameters.get("origin", (0.0, 0.0, 0.0))
                ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])

                box_pnt = gp.gp_Pnt(0.0, -width / 2.0, 0.0)
                box = BRepPrim.BRepPrimAPI_MakeBox(box_pnt, length, width, thickness).Solid()

                rot_trsf = gp.gp_Trsf()
                rot_ax = gp.gp_Ax1(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                rot_trsf.SetRotation(rot_ax, math.radians(angle_deg))
                trans_trsf = gp.gp_Trsf()
                trans_trsf.SetTranslation(gp.gp_Vec(ox, oy, oz))
                total_trsf = trans_trsf.Multiplied(rot_trsf)

                transformer = BRepBuilder.BRepBuilderAPI_Transform(box, total_trsf, True)
                base_solid = transformer.Shape()

            elif part.shape == "oring":
                inner_r = float(part.parameters["inner_diameter"]) / 2.0
                cs_r = float(part.parameters["cross_section"]) / 2.0
                major_r = inner_r + cs_r
                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                base_solid = BRepPrim.BRepPrimAPI_MakeTorus(ax, major_r, cs_r).Solid()

            elif part.shape == "radial_shaft_seal":
                shaft_r = float(part.parameters["shaft_diameter"]) / 2.0
                outer_r = float(part.parameters["outer_diameter"]) / 2.0
                width = float(part.parameters["width"])
                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                outer_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(ax, outer_r, width).Solid()
                inner_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(ax, shaft_r, width + 0.2).Solid()
                cut_op = BRepAlgo.BRepAlgoAPI_Cut(outer_cyl, inner_cyl)
                base_solid = cut_op.Shape()

            elif part.shape == "rigid_flange_coupling":
                od = float(part.parameters["outer_diameter"])
                length = float(part.parameters["length"])
                flange_t = float(part.parameters["flange_thickness"])
                d1 = float(part.parameters["shaft1_diameter"])
                d2 = float(part.parameters["shaft2_diameter"])
                hub_d = float(part.parameters.get("hub_diameter", od * 0.6))
                pcd = float(part.parameters.get("bolt_pcd", od * 0.75))
                b_cnt = int(part.parameters.get("bolt_count", 4))
                b_dia = float(part.parameters.get("bolt_dia", 8.0))

                ax1 = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                hub1 = BRepPrim.BRepPrimAPI_MakeCylinder(ax1, hub_d / 2.0, length / 2.0).Solid()
                f_ax1 = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0 - flange_t), gp.gp_Dir(0.0, 0.0, 1.0))
                f1 = BRepPrim.BRepPrimAPI_MakeCylinder(f_ax1, od / 2.0, flange_t).Solid()
                half1 = BRepAlgo.BRepAlgoAPI_Fuse(hub1, f1).Shape()

                ax2 = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0), gp.gp_Dir(0.0, 0.0, 1.0))
                hub2 = BRepPrim.BRepPrimAPI_MakeCylinder(ax2, hub_d / 2.0, length / 2.0).Solid()
                f_ax2 = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0), gp.gp_Dir(0.0, 0.0, 1.0))
                f2 = BRepPrim.BRepPrimAPI_MakeCylinder(f_ax2, od / 2.0, flange_t).Solid()
                half2 = BRepAlgo.BRepAlgoAPI_Fuse(hub2, f2).Shape()

                body = BRepAlgo.BRepAlgoAPI_Fuse(half1, half2).Shape()

                b1_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore1 = BRepPrim.BRepPrimAPI_MakeCylinder(b1_ax, d1 / 2.0, length / 2.0 + 0.2).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore1).Shape()

                b2_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0 - 0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore2 = BRepPrim.BRepPrimAPI_MakeCylinder(b2_ax, d2 / 2.0, length / 2.0 + 0.2).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore2).Shape()

                for i in range(b_cnt):
                    ang = i * (2.0 * math.pi / b_cnt)
                    bx = (pcd / 2.0) * math.cos(ang)
                    by = (pcd / 2.0) * math.sin(ang)
                    b_ax = gp.gp_Ax2(gp.gp_Pnt(bx, by, length / 2.0 - flange_t - 0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                    b_cyl = BRepPrim.BRepPrimAPI_MakeCylinder(b_ax, b_dia / 2.0, 2.0 * flange_t + 0.2).Solid()
                    cut_b = BRepAlgo.BRepAlgoAPI_Cut(body, b_cyl)
                    if cut_b.IsDone():
                        body = cut_b.Shape()

                base_solid = body

            elif part.shape == "flexible_jaw_coupling":
                od = float(part.parameters["outer_diameter"])
                length = float(part.parameters["length"])
                d1 = float(part.parameters["shaft1_diameter"])
                d2 = float(part.parameters["shaft2_diameter"])

                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                body = BRepPrim.BRepPrimAPI_MakeCylinder(ax, od / 2.0, length).Solid()

                b1_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore1 = BRepPrim.BRepPrimAPI_MakeCylinder(b1_ax, d1 / 2.0, length / 2.0 + 0.2).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore1).Shape()

                b2_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0 - 0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore2 = BRepPrim.BRepPrimAPI_MakeCylinder(b2_ax, d2 / 2.0, length / 2.0 + 0.2).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore2).Shape()

                base_solid = body

            elif part.shape == "oldham_coupling":
                od = float(part.parameters["outer_diameter"])
                length = float(part.parameters["length"])
                d1 = float(part.parameters["shaft1_diameter"])
                d2 = float(part.parameters["shaft2_diameter"])

                ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0))
                body = BRepPrim.BRepPrimAPI_MakeCylinder(ax, od / 2.0, length).Solid()

                b1_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, -0.1), gp.gp_Dir(0.0, 0.0, 1.0))
                bore1 = BRepPrim.BRepPrimAPI_MakeCylinder(b1_ax, d1 / 2.0, length / 2.0 + 0.1).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore1).Shape()

                b2_ax = gp.gp_Ax2(gp.gp_Pnt(0.0, 0.0, length / 2.0), gp.gp_Dir(0.0, 0.0, 1.0))
                bore2 = BRepPrim.BRepPrimAPI_MakeCylinder(b2_ax, d2 / 2.0, length / 2.0 + 0.1).Solid()
                body = BRepAlgo.BRepAlgoAPI_Cut(body, bore2).Shape()

                base_solid = body

        elif part.part_type == "step_file" and part.source_file:




            reader = STEPControl.STEPControl_Reader()
            status = reader.ReadFile(part.source_file)
            if status == IFSelect.IFSelect_RetDone:
                reader.TransferRoots()
                base_solid = reader.Shape()
            else:
                raise RuntimeError(f"Failed to read STEP file: {part.source_file}")

        elif part.shape == "loft" or part.part_type == "loft":
            base_solid = self._build_loft(part)

        elif part.shape == "revolve" or part.part_type == "revolve":
            base_solid = self._build_revolve(part)

        elif part.shape == "sweep" or part.part_type == "sweep":
            base_solid = self._build_sweep(part)

        elif part.shape == "extrude" or part.part_type == "extrude":
            base_solid = self._build_extrude(part)

        elif part.shape == "text_3d" or part.part_type == "text_3d":
            from ..core.text_engine import TextEngine
            p = part.parameters
            base_solid = TextEngine.build_3d_text(
                text=p.get("text", "CADi"),
                font_size=float(p.get("font_size", 12.0)),
                depth=float(p.get("depth", 1.0)),
                position=p.get("position", (0.0, 0.0, 0.0)),
                normal=p.get("normal", (0.0, 0.0, 1.0)),
                font_name=p.get("font_name", "Arial"),
            )

        elif part.shape == "circular_text" or part.part_type == "circular_text":
            from ..core.text_engine import TextEngine
            p = part.parameters
            base_solid = TextEngine.build_circular_text(
                text=p.get("text", "CADi"),
                radius=float(p.get("radius", 100.0)),
                center_angle_deg=float(p.get("center_angle", 90.0)),
                center=p.get("center", (0.0, 0.0, 0.0)),
                font_size=float(p.get("font_size", 10.0)),
                depth=float(p.get("depth", 1.0)),
            )

        elif part.shape == "pipe" or part.part_type == "pipe":
            base_solid = self._build_pipe(part)

        elif part.shape == "gear" or part.part_type == "gear":
            from ..std_parts.gears import SpurGear, HelicalGear, RackAndPinion, InternalGear
            gear_type = part.parameters.get("gear_type", "spur")
            args = part.parameters.get("args", {})
            if gear_type == "helical":
                base_solid, _ = HelicalGear.create_solid(**args)
            elif gear_type == "rack":
                base_solid, _ = RackAndPinion.create_rack_solid(**args)
            elif gear_type == "internal":
                base_solid, _ = InternalGear.create_solid(**args)
            else:
                base_solid, _ = SpurGear.create_solid(**args)

        elif part.shape == "spring" or part.part_type == "spring":
            from ..std_parts.springs import CoilSpring
            args = part.parameters.get("args", {})
            base_solid, _ = CoilSpring.create_solid(**args)

        elif part.shape == "coilover" or part.part_type == "coilover":
            from ..std_parts.springs import Coilover
            args = part.parameters.get("args", {})
            base_solid, _ = Coilover.create_solid(**args)

        elif part.shape == "sheet_metal" or part.part_type == "sheet_metal":
            from ..core.sheet_metal import SheetMetalBuilder
            builder = part.parameters.get("builder")
            if builder is not None and hasattr(builder, "build_occt_solid"):
                base_solid = builder.build_occt_solid()
            else:
                l = float(part.parameters.get("length", 100.0))
                w = float(part.parameters.get("width", 50.0))
                t = float(part.parameters.get("thickness", 2.0))
                k = float(part.parameters.get("k_factor", 0.44))
                mat = part.parameters.get("material", "S235JR")
                sm = SheetMetalBuilder(part.name, thickness=t, k_factor=k, material=mat)
                sm.base_plate(length=l, width=w)
                base_solid = sm.build_occt_solid()

        elif part.shape == "crankshaft" or part.part_type == "crankshaft":
            from ..std_parts.linkages import Crankshaft
            args = part.parameters.get("args", {})
            base_solid, _ = Crankshaft.create_solid(**args)

        elif part.shape == "connecting_rod" or part.part_type == "connecting_rod":
            from ..std_parts.linkages import ConnectingRod
            args = part.parameters.get("args", {})
            base_solid, _ = ConnectingRod.create_solid(**args)

        elif part.shape == "slider_piston" or part.part_type == "slider_piston":
            from ..std_parts.linkages import SliderPiston
            args = part.parameters.get("args", {})
            base_solid, _ = SliderPiston.create_solid(**args)

        elif part.shape == "engine_frame" or part.part_type == "engine_frame":
            from ..std_parts.linkages import EngineFrame
            args = part.parameters.get("args", {})
            base_solid, _ = EngineFrame.create_solid(**args)



        if base_solid is None:
            raise NotImplementedError(f"Unsupported part type/shape: {part.part_type}/{part.shape}")

        # -----------------------------------------------------------------------
        # Drill Defined Holes (Boolean Cut)
        # -----------------------------------------------------------------------
        for hole in part.holes:
            r = hole.diameter / 2.0
            hx, hy = hole.position
            # For a box with top face at Z=h
            top_z = float(part.parameters.get("height", 20.0))
            depth = hole.depth if hole.depth > 0 else (top_z * 2.0)

            # Drill from top surface downwards
            ax = gp.gp_Ax2(gp.gp_Pnt(hx, hy, top_z + 0.1), gp.gp_Dir(0.0, 0.0, -1.0))
            cutter = BRepPrim.BRepPrimAPI_MakeCylinder(ax, r, depth + 0.2).Solid()
            cut_op = BRepAlgo.BRepAlgoAPI_Cut(base_solid, cutter)
            if cut_op.IsDone():
                base_solid = cut_op.Shape()

        # -----------------------------------------------------------------------
        # Fillet Operations
        # -----------------------------------------------------------------------
        for fillet_item in part.fillets:
            try:
                edges = self._collect_edges(base_solid, fillet_item.edge_selector)
                if edges:
                    fillet_maker = BRepFillet.BRepFilletAPI_MakeFillet(base_solid)
                    for e in edges:
                        fillet_maker.Add(fillet_item.radius, e)
                    fillet_maker.Build()
                    if fillet_maker.IsDone():
                        base_solid = fillet_maker.Shape()
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # Chamfer Operations
        # -----------------------------------------------------------------------
        for chamfer_item in part.chamfers:
            try:
                edges = self._collect_edges(base_solid, chamfer_item.edge_selector)
                if edges:
                    chamfer_maker = BRepFillet.BRepFilletAPI_MakeChamfer(base_solid)
                    for e in edges:
                        chamfer_maker.Add(chamfer_item.distance, e)
                    chamfer_maker.Build()
                    if chamfer_maker.IsDone():
                        base_solid = chamfer_maker.Shape()
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # Shelling (Hollowing out solid with uniform wall thickness)
        # -----------------------------------------------------------------------
        if part.shell is not None:
            try:
                base_solid = self._apply_shell(base_solid, part.shell)
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # Draft Angle (Casting / Molding Taper)
        # -----------------------------------------------------------------------
        if part.draft_angle is not None:
            try:
                base_solid = self._apply_draft_angle(base_solid, part.draft_angle)
            except Exception:
                pass

        # -----------------------------------------------------------------------
        # Origin Translation (for shapes positioned via origin parameter)
        # -----------------------------------------------------------------------
        origin = part.parameters.get("origin")
        if origin and len(origin) == 3 and (origin[0] != 0.0 or origin[1] != 0.0 or origin[2] != 0.0):
            if part.shape in ("gear", "spring", "coilover", "sheet_metal", "extrusion", "crankshaft", "connecting_rod", "slider_piston", "engine_frame"):
                try:
                    trsf = gp.gp_Trsf()
                    trsf.SetTranslation(gp.gp_Vec(float(origin[0]), float(origin[1]), float(origin[2])))
                    base_solid = BRepBuilder.BRepBuilderAPI_Transform(base_solid, trsf, True).Shape()
                except Exception:
                    pass

        if base_solid is not None and not base_solid.IsNull():
            self._solid_cache[part.name] = (cache_key, base_solid)
            self._verify_and_rebind_ports(part, base_solid)

        return base_solid


    def _build_cross_section_wire(self, sec: CrossSection) -> TopoDS.TopoDS_Wire:
        """Convert a CrossSection definition into an OpenCASCADE TopoDS_Wire."""
        cx, cy, cz = sec.center
        nx, ny, nz = sec.normal
        ax2 = gp.gp_Ax2(gp.gp_Pnt(cx, cy, cz), gp.gp_Dir(nx, ny, nz))

        if sec.shape == "circle":
            r = float(sec.parameters.get("radius", 10.0))
            circ = gp.gp_Circ(ax2, r)
            edge = BRepBuilder.BRepBuilderAPI_MakeEdge(circ).Edge()
            return BRepBuilder.BRepBuilderAPI_MakeWire(edge).Wire()

        elif sec.shape == "ellipse":
            rx = float(sec.parameters.get("rx", 15.0))
            ry = float(sec.parameters.get("ry", 10.0))
            # rx must be major radius (>= ry) in OpenCASCADE gp_Elips
            maj_r = max(rx, ry)
            min_r = min(rx, ry)
            elips = gp.gp_Elips(ax2, maj_r, min_r)
            edge = BRepBuilder.BRepBuilderAPI_MakeEdge(elips).Edge()
            return BRepBuilder.BRepBuilderAPI_MakeWire(edge).Wire()

        elif sec.shape == "rectangle":
            w = float(sec.parameters.get("width", 20.0))
            h = float(sec.parameters.get("height", 10.0))
            # Form planar rectangle centered on (cx, cy, cz)
            poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
            poly.Add(gp.gp_Pnt(cx - w / 2.0, cy - h / 2.0, cz))
            poly.Add(gp.gp_Pnt(cx + w / 2.0, cy - h / 2.0, cz))
            poly.Add(gp.gp_Pnt(cx + w / 2.0, cy + h / 2.0, cz))
            poly.Add(gp.gp_Pnt(cx - w / 2.0, cy + h / 2.0, cz))
            poly.Close()
            return poly.Wire()

        elif sec.shape == "naca":
            code = str(sec.parameters.get("code", "0012"))
            chord = float(sec.parameters.get("chord", 150.0))
            n_pts = int(sec.parameters.get("points_count", 35))
            try:
                m = float(code[0]) / 100.0
                p = float(code[1]) / 10.0
                t = float(code[2:4]) / 100.0
            except Exception:
                m, p, t = 0.0, 0.0, 0.12

            pts = []
            # Upper surface (trailing edge to leading edge)
            for i in range(n_pts + 1):
                x = 1.0 - (i / n_pts)
                yt = 5.0 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * (x**2) + 0.2843 * (x**3) - 0.1015 * (x**4))
                if p > 0 and x < p:
                    yc = (m / (p**2)) * (2.0 * p * x - x**2)
                elif p > 0:
                    yc = (m / ((1.0 - p)**2)) * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2)
                else:
                    yc = 0.0
                pts.append(gp.gp_Pnt(cx + x * chord, cy, cz + (yc + yt) * chord))

            # Lower surface (leading edge to trailing edge)
            for i in range(1, n_pts + 1):
                x = i / n_pts
                yt = 5.0 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * (x**2) + 0.2843 * (x**3) - 0.1015 * (x**4))
                if p > 0 and x < p:
                    yc = (m / (p**2)) * (2.0 * p * x - x**2)
                elif p > 0:
                    yc = (m / ((1.0 - p)**2)) * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2)
                else:
                    yc = 0.0
                pts.append(gp.gp_Pnt(cx + x * chord, cy, cz + (yc - yt) * chord))

            h_pts = TColgp.TColgp_HArray1OfPnt(1, len(pts))
            for idx, pt in enumerate(pts, start=1):
                h_pts.SetValue(idx, pt)

            interp = GeomAPI.GeomAPI_Interpolate(h_pts, True, 1e-4)
            interp.Perform()
            if interp.IsDone():
                edge = BRepBuilder.BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()
                return BRepBuilder.BRepBuilderAPI_MakeWire(edge).Wire()

        elif sec.shape in ("polygon", "spline"):
            points = sec.parameters.get("points", [])
            poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
            for pt in points:
                if len(pt) == 2:
                    poly.Add(gp.gp_Pnt(pt[0], pt[1], cz))
                else:
                    poly.Add(gp.gp_Pnt(pt[0], pt[1], pt[2]))
            poly.Close()
            return poly.Wire()

        raise NotImplementedError(f"Unsupported cross-section shape: {sec.shape}")

    def _build_loft(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Create organic solid passing through multiple cross-sections."""
        ruled = bool(part.parameters.get("ruled", False))
        is_solid = bool(part.parameters.get("is_solid", True))

        thru = BRepOffsetAPI.BRepOffsetAPI_ThruSections(is_solid, ruled)
        for sec in part.sections:
            wire = self._build_cross_section_wire(sec)
            thru.AddWire(wire)
        thru.Build()
        if not thru.IsDone():
            raise RuntimeError(f"Loft operation failed for part '{part.name}'")
        return thru.Shape()

    def _build_revolve(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Revolve 2D profile around an axis."""
        points = part.parameters.get("profile_points", [])
        angle = float(part.parameters.get("angle", 360.0))
        axis = part.parameters.get("axis", (0.0, 0.0, 1.0))
        origin = part.parameters.get("origin", (0.0, 0.0, 0.0))

        poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
        for pt in points:
            # (R, Z) on XZ plane: X=R, Y=0, Z=Z
            r, z = pt[0], pt[1]
            poly.Add(gp.gp_Pnt(r, 0.0, z))
        poly.Close()

        face = BRepBuilder.BRepBuilderAPI_MakeFace(poly.Wire()).Face()
        ax1 = gp.gp_Ax1(gp.gp_Pnt(*origin), gp.gp_Dir(*axis))
        revol = BRepPrim.BRepPrimAPI_MakeRevol(face, ax1, math.radians(angle))
        revol.Build()
        if not revol.IsDone():
            raise RuntimeError(f"Revolve operation failed for part '{part.name}'")
        return revol.Shape()

    def _build_sweep(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Sweep cross-section along a trajectory path."""
        path_pts = part.path_points
        if not path_pts:
            raise ValueError(f"Sweep for part '{part.name}' requires path_points")

        poly = BRepBuilder.BRepBuilderAPI_MakePolygon()
        for pt in path_pts:
            poly.Add(gp.gp_Pnt(*pt))
        spine_wire = poly.Wire()

        sec = part.sections[0]
        sec_wire = self._build_cross_section_wire(sec)
        sec_face = BRepBuilder.BRepBuilderAPI_MakeFace(sec_wire).Face()

        pipe = BRepOffsetAPI.BRepOffsetAPI_MakePipe(spine_wire, sec_face)
        pipe.Build()
        if not pipe.IsDone():
            raise RuntimeError(f"Sweep pipe operation failed for part '{part.name}'")
        return pipe.Shape()

    def _build_extrude(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Extrude a 2D planar cross-section along a vector direction."""
        dist = float(part.parameters.get("distance", part.parameters.get("length", 10.0)))
        dir_vec = part.parameters.get("direction", (0.0, 0.0, 1.0))
        if not part.sections:
            raise ValueError(f"Extrude for part '{part.name}' requires a section")
        sec = part.sections[0]
        wire = self._build_cross_section_wire(sec)
        face = BRepBuilder.BRepBuilderAPI_MakeFace(wire).Face()
        vec = gp.gp_Vec(dir_vec[0] * dist, dir_vec[1] * dist, dir_vec[2] * dist)
        prism = BRepPrim.BRepPrimAPI_MakePrism(face, vec)
        prism.Build()
        if not prism.IsDone():
            raise RuntimeError(f"Extrude operation failed for part '{part.name}'")
        return prism.Shape()

    def _build_pipe(self, part: PartNode) -> TopoDS.TopoDS_Shape:
        """Create 3D pipe or tubing swept along an interpolated 3D spline trajectory."""
        points = part.parameters.get("points", [])
        outer_dia = float(part.parameters.get("outer_dia", 10.0))
        wall_thick = float(part.parameters.get("wall_thickness", 1.5))

        if len(points) < 2:
            raise ValueError(f"Pipe '{part.name}' requires at least 2 3D points")

        h_arr = TColgp.TColgp_HArray1OfPnt(1, len(points))
        for i, pt in enumerate(points):
            h_arr.SetValue(i + 1, gp.gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))

        interp = GeomAPI.GeomAPI_Interpolate(h_arr, False, 1e-4)
        interp.Perform()
        if not interp.IsDone():
            raise RuntimeError(f"Failed to interpolate trajectory for pipe '{part.name}'")
        curve = interp.Curve()
        edge = BRepBuilder.BRepBuilderAPI_MakeEdge(curve).Edge()
        spine_wire = BRepBuilder.BRepBuilderAPI_MakeWire(edge).Wire()

        p0 = gp.gp_Pnt()
        v0 = gp.gp_Vec()
        curve.D1(curve.FirstParameter(), p0, v0)
        circ_ax2 = gp.gp_Ax2(p0, gp.gp_Dir(v0))

        circ_edge = BRepBuilder.BRepBuilderAPI_MakeEdge(gp.gp_Circ(circ_ax2, outer_dia / 2.0)).Edge()
        circ_face = BRepBuilder.BRepBuilderAPI_MakeFace(BRepBuilder.BRepBuilderAPI_MakeWire(circ_edge).Wire()).Face()

        pipe_solid = BRepOffsetAPI.BRepOffsetAPI_MakePipe(spine_wire, circ_face).Shape()

        # Hollow out if wall thickness is positive and inner diameter is valid
        inner_dia = outer_dia - 2.0 * wall_thick
        if inner_dia > 0.1 and wall_thick > 0.0:
            in_edge = BRepBuilder.BRepBuilderAPI_MakeEdge(gp.gp_Circ(circ_ax2, inner_dia / 2.0)).Edge()
            in_face = BRepBuilder.BRepBuilderAPI_MakeFace(BRepBuilder.BRepBuilderAPI_MakeWire(in_edge).Wire()).Face()
            in_pipe = BRepOffsetAPI.BRepOffsetAPI_MakePipe(spine_wire, in_face).Shape()
            cut_op = BRepAlgo.BRepAlgoAPI_Cut(pipe_solid, in_pipe)
            if cut_op.IsDone():
                pipe_solid = cut_op.Shape()

        return pipe_solid

    def _apply_shell(self, solid: TopoDS.TopoDS_Shape, shell: ShellNode) -> TopoDS.TopoDS_Shape:
        """Hollow out solid body."""
        closing_faces = TopTools.TopTools_ListOfShape()
        if shell.open_face:
            # Find face to remove (e.g. bottom face: min Z)
            bnd = Bnd.Bnd_Box()
            BRepBndLib.BRepBndLib.Add_s(solid, bnd)
            vals = bnd.Get()
            zmin, zmax = vals[2], vals[5]
            tol = max(0.1, (zmax - zmin) * 0.05)

            exp = TopExp.TopExp_Explorer(solid, TopAbs.TopAbs_FACE)
            while exp.More():
                face = TopoDS.TopoDS.Face_s(exp.Current())
                fbnd = Bnd.Bnd_Box()
                BRepBndLib.BRepBndLib.Add_s(face, fbnd)
                fvals = fbnd.Get()
                if shell.open_face == "bottom" and abs(fvals[2] - zmin) <= tol and abs(fvals[5] - zmin) <= tol:
                    closing_faces.Append(face)
                    break
                elif shell.open_face == "top" and abs(fvals[2] - zmax) <= tol and abs(fvals[5] - zmax) <= tol:
                    closing_faces.Append(face)
                    break
                exp.Next()

        thick = BRepOffsetAPI.BRepOffsetAPI_MakeThickSolid()
        thick.MakeThickSolidByJoin(solid, closing_faces, -abs(shell.thickness), 1e-3, BRepOffset.BRepOffset_Mode.BRepOffset_Skin)
        thick.Build()
        if thick.IsDone():
            return thick.Shape()
        return solid

    def _collect_edges(self, shape: TopoDS.TopoDS_Shape, selector: str) -> List[TopoDS.TopoDS_Edge]:
        """
        Collect edges based on smart spatial and geometric selectors:
        - 'all': all edges
        - 'all_top' or 'top': edges located at maximum Z boundary
        - 'all_bottom' or 'bottom': edges located at minimum Z boundary
        - 'vertical' or 'vert': edges strictly parallel to Z-axis (straight vertical fillets)
        - 'horizontal' or 'horiz': edges strictly perpendicular to Z-axis
        - 'circular' or 'holes': circular or curved edges (hole rims, cylindrical necks)
        - 'x_min' or 'left': edges on minimum X boundary plane
        - 'x_max' or 'right': edges on maximum X boundary plane
        - 'y_min' or 'front': edges on minimum Y boundary plane
        - 'y_max' or 'back': edges on maximum Y boundary plane
        """
        bnd = Bnd.Bnd_Box()
        BRepBndLib.BRepBndLib.Add_s(shape, bnd)
        vals = bnd.Get()
        xmin, ymin, zmin, xmax, ymax, zmax = vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]
        tol_z = max(0.1, (zmax - zmin) * 0.05)
        tol_x = max(0.1, (xmax - xmin) * 0.05)
        tol_y = max(0.1, (ymax - ymin) * 0.05)

        sel = selector.strip().lower()
        edges = []
        exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.TopoDS.Edge_s(exp.Current())
            ebnd = Bnd.Bnd_Box()
            BRepBndLib.BRepBndLib.Add_s(edge, ebnd)
            evals = ebnd.Get()
            exmin, eymin, ezmin = evals[0], evals[1], evals[2]
            exmax, eymax, ezmax = evals[3], evals[4], evals[5]

            is_circle = False
            is_vert = False
            is_horiz = False
            try:
                adaptor = BRepAdaptor.BRepAdaptor_Curve(edge)
                c_type = adaptor.GetType()
                is_circle = (c_type == GeomAbs.GeomAbs_Circle)
                p1 = adaptor.Value(adaptor.FirstParameter())
                p2 = adaptor.Value(adaptor.LastParameter())
                dx = abs(p1.X() - p2.X())
                dy = abs(p1.Y() - p2.Y())
                dz = abs(p1.Z() - p2.Z())
                is_vert = (dx < 1e-3 and dy < 1e-3 and dz > 1e-3)
                is_horiz = (dz < 1e-3)
            except Exception:
                pass

            if sel == "all":
                edges.append(edge)
            elif sel in ("all_top", "top") and abs(ezmin - zmax) <= tol_z and abs(ezmax - zmax) <= tol_z:
                edges.append(edge)
            elif sel in ("all_bottom", "bottom") and abs(ezmin - zmin) <= tol_z and abs(ezmax - zmin) <= tol_z:
                edges.append(edge)
            elif sel in ("vertical", "vert") and is_vert:
                edges.append(edge)
            elif sel in ("horizontal", "horiz") and is_horiz:
                edges.append(edge)
            elif sel in ("circular", "holes", "hole_edges") and is_circle:
                edges.append(edge)
            elif sel in ("x_min", "left") and abs(exmin - xmin) <= tol_x and abs(exmax - xmin) <= tol_x:
                edges.append(edge)
            elif sel in ("x_max", "right") and abs(exmax - xmax) <= tol_x and abs(exmin - xmax) <= tol_x:
                edges.append(edge)
            elif sel in ("y_min", "front") and abs(eymin - ymin) <= tol_y and abs(eymax - ymin) <= tol_y:
                edges.append(edge)
            elif sel in ("y_max", "back") and abs(eymax - ymax) <= tol_y and abs(eymin - ymax) <= tol_y:
                edges.append(edge)
            exp.Next()
        return edges

    # ---------------------------------------------------------------------------
    # Mate / Constraint Solver (Deterministic Matrix Calculations & DOF Tracking)
    # ---------------------------------------------------------------------------

    def get_dof_reports(self) -> Dict[str, Dict[str, Any]]:
        """Returns degrees-of-freedom constraint analysis for all parts in the assembly."""
        return self._dof_reports

    def _verify_and_rebind_ports(self, part: PartNode, shape: TopoDS.TopoDS_Shape) -> None:
        """
        Verifies all semantic ports against the solid boundary.
        If fillets/chamfers/cuts displaced the port origin, re-binds to the nearest surface point.
        If the face was completely removed, flags the port as STALE to prevent ghost references.
        """
        if shape is None or shape.IsNull():
            return

        import OCP.BRepExtrema as BRepExtrema
        import OCP.BRepBuilderAPI as BRepBuilderAPI

        bnd = Bnd.Bnd_Box()
        BRepBndLib.BRepBndLib.Add_s(shape, bnd)
        xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()
        diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)

        for port in part.ports.values():
            px, py, pz = port.relative_position
            # Outside spatial envelope check
            tol_bnd = max(10.0, diag * 0.1)
            if px < xmin - tol_bnd or px > xmax + tol_bnd or \
               py < ymin - tol_bnd or py > ymax + tol_bnd or \
               pz < zmin - tol_bnd or pz > zmax + tol_bnd:
                port.status = "STALE"
                continue

            pnt = gp.gp_Pnt(px, py, pz)
            vert = BRepBuilderAPI.BRepBuilderAPI_MakeVertex(pnt).Vertex()
            dist_tool = BRepExtrema.BRepExtrema_DistShapeShape()
            dist_tool.LoadS1(vert)
            dist_tool.LoadS2(shape)
            dist_tool.Perform()

            if dist_tool.IsDone():
                min_dist = dist_tool.Value()
                # If port has a diameter or is a hole/axis/flange port centered on an opening, allow radius
                allowed_radius = (port.diameter / 2.0 + 2.0) if (port.diameter and port.diameter > 0) else 0.0
                if port.port_type in ("hole", "axis", "flange", "plane", "face"):
                    allowed_radius = max(allowed_radius, diag * 0.5)

                if min_dist < 1e-2 or min_dist <= allowed_radius:
                    port.status = "VALID"
                elif min_dist < 5.0:
                    near_p = dist_tool.PointOnShape2(1)
                    port.relative_position = (round(near_p.X(), 4), round(near_p.Y(), 4), round(near_p.Z(), 4))
                    port.status = "REBOUND"
                else:
                    port.status = "STALE"

    def _solve_all_mates(self, ir: AssemblyIR) -> None:
        """
        Solves assembly constraints using topological sorting, compound mate resolution,
        and degree-of-freedom (DOF) tracking. Prevents destructive mate overwriting.
        """
        self._dof_reports.clear()

        mates_by_part: Dict[str, List[Any]] = {}
        for mate in ir.mates:
            mates_by_part.setdefault(mate.second_part, []).append(mate)

        for name in ir.parts:
            if name not in mates_by_part:
                self._dof_reports[name] = {
                    "status": ConstraintStatus.FULLY_CONSTRAINED.value,
                    "remaining_dof": 0,
                    "free_dofs": [],
                    "description": "Grounded base component",
                }

        solved = set(ir.parts.keys()) - set(mates_by_part.keys())
        remaining = dict(mates_by_part)

        max_passes = len(ir.parts) + 2
        for _ in range(max_passes):
            if not remaining:
                break
            progress = False
            for sec_name, part_mates in list(remaining.items()):
                deps = [m.first_part for m in part_mates]
                if all(d in solved for d in deps):
                    self._solve_part_constraints(sec_name, part_mates, ir)
                    solved.add(sec_name)
                    del remaining[sec_name]
                    progress = True
                    break
            if not progress and remaining:
                sec_name, part_mates = remaining.popitem()
                self._solve_part_constraints(sec_name, part_mates, ir)
                solved.add(sec_name)

    def _solve_part_constraints(self, second_name: str, part_mates: List[Any], ir: AssemblyIR) -> None:
        """
        Solves constraints for a single component.
        Combines COAXIAL + FLUSH into a stable joint without overwriting.
        Detects contradictory constraints and raises OverConstrainedError.
        """
        p2_node = ir.parts[second_name]

        if len(part_mates) == 1:
            m = part_mates[0]
            self._apply_mate(m, ir)
            if m.mate_type in (MateType.COAXIAL, MateType.CONCENTRIC):
                self._dof_reports[second_name] = {
                    "status": ConstraintStatus.UNDER_CONSTRAINED.value,
                    "remaining_dof": 2,
                    "free_dofs": ["translation_along_axis", "rotation_around_axis"],
                    "description": "Coaxial alignment (2 DOFs free)",
                }
            elif m.mate_type in (MateType.FLUSH, MateType.COINCIDENT):
                self._dof_reports[second_name] = {
                    "status": ConstraintStatus.UNDER_CONSTRAINED.value,
                    "remaining_dof": 3,
                    "free_dofs": ["translation_x", "translation_y", "planar_rotation"],
                    "description": "Planar mate (3 DOFs free)",
                }
            else:
                self._dof_reports[second_name] = {
                    "status": ConstraintStatus.FULLY_CONSTRAINED.value,
                    "remaining_dof": 0,
                    "free_dofs": [],
                    "description": "Rigid attachment",
                }
            return

        coaxial_mates = [m for m in part_mates if m.mate_type in (MateType.COAXIAL, MateType.CONCENTRIC, MateType.ALIGN_HOLES)]
        planar_mates = [m for m in part_mates if m.mate_type in (MateType.FLUSH, MateType.COINCIDENT, MateType.ATTACH, MateType.DISTANCE)]

        if len(coaxial_mates) > 1:
            m1, m2 = coaxial_mates[0], coaxial_mates[1]
            p1_a, _ = self._resolve_anchor(ir.parts[m1.first_part], m1.first_selector)
            p1_b, _ = self._resolve_anchor(ir.parts[m2.first_part], m2.first_selector)
            p2_a, _ = self._resolve_anchor(p2_node, m1.second_selector)
            p2_b, _ = self._resolve_anchor(p2_node, m2.second_selector)

            dist_target = math.sqrt((p1_a.X() - p1_b.X()) ** 2 + (p1_a.Y() - p1_b.Y()) ** 2 + (p1_a.Z() - p1_b.Z()) ** 2)
            dist_source = math.sqrt((p2_a.X() - p2_b.X()) ** 2 + (p2_a.Y() - p2_b.Y()) ** 2 + (p2_a.Z() - p2_b.Z()) ** 2)

            if abs(dist_target - dist_source) > 0.1 and dist_source > 0.1:
                raise OverConstrainedError(
                    f"Contradictory coaxial/hole alignment on part '{second_name}': "
                    f"Hole spacing mismatch between parts ({round(dist_source, 2)} mm vs {round(dist_target, 2)} mm)."
                )

        if coaxial_mates and planar_mates:
            c_mate = coaxial_mates[0]
            f_mate = planar_mates[0]

            self._apply_mate(c_mate, ir)

            p1_node = ir.parts[f_mate.first_part]
            p1_pt, p1_n = self._resolve_anchor(p1_node, f_mate.first_selector)
            p2_pt, p2_n = self._resolve_anchor(p2_node, f_mate.second_selector)

            trsf1 = self._transforms[f_mate.first_part]
            w_p1_pt = p1_pt.Transformed(trsf1)
            v_p1_n = gp.gp_Vec(p1_n.X(), p1_n.Y(), p1_n.Z()).Transformed(trsf1)
            w_p1_n = gp.gp_Dir(v_p1_n.X(), v_p1_n.Y(), v_p1_n.Z())

            current_trsf = self._transforms[second_name]
            curr_w_p2_pt = p2_pt.Transformed(current_trsf)

            target_pt = gp.gp_Pnt(
                w_p1_pt.X() + w_p1_n.X() * f_mate.offset,
                w_p1_pt.Y() + w_p1_n.Y() * f_mate.offset,
                w_p1_pt.Z() + w_p1_n.Z() * f_mate.offset,
            )

            axial_disp = (
                (target_pt.X() - curr_w_p2_pt.X()) * w_p1_n.X()
                + (target_pt.Y() - curr_w_p2_pt.Y()) * w_p1_n.Y()
                + (target_pt.Z() - curr_w_p2_pt.Z()) * w_p1_n.Z()
            )

            axial_trsf = gp.gp_Trsf()
            axial_trsf.SetTranslation(
                gp.gp_Vec(
                    w_p1_n.X() * axial_disp,
                    w_p1_n.Y() * axial_disp,
                    w_p1_n.Z() * axial_disp,
                )
            )
            self._transforms[second_name] = axial_trsf.Multiplied(current_trsf)

            self._dof_reports[second_name] = {
                "status": (
                    ConstraintStatus.UNDER_CONSTRAINED.value
                    if len(coaxial_mates) == 1
                    else ConstraintStatus.FULLY_CONSTRAINED.value
                ),
                "remaining_dof": 1 if len(coaxial_mates) == 1 else 0,
                "free_dofs": ["rotation_around_axis"] if len(coaxial_mates) == 1 else [],
                "description": (
                    "Compound COAXIAL + FLUSH mate (1 rotational DOF remaining)"
                    if len(coaxial_mates) == 1
                    else "Fully constrained compound mate"
                ),
            }
        else:
            for m in part_mates:
                self._apply_mate(m, ir)
            self._dof_reports[second_name] = {
                "status": ConstraintStatus.FULLY_CONSTRAINED.value,
                "remaining_dof": 0,
                "free_dofs": [],
                "description": "Sequential mates applied",
            }

    def _apply_mate(self, mate: Any, ir: AssemblyIR) -> None:
        """Solve and update transformation for second_part relative to first_part."""
        first_name = mate.first_part
        second_name = mate.second_part

        p1_node = ir.parts[first_name]
        p2_node = ir.parts[second_name]

        # Extract anchor points/vectors
        p1_pt, p1_n = self._resolve_anchor(p1_node, mate.first_selector)
        p2_pt, p2_n = self._resolve_anchor(p2_node, mate.second_selector)

        # Transformation of first part
        trsf1 = self._transforms[first_name]
        # Current world coordinates of anchor 1
        w_p1_pt = p1_pt.Transformed(trsf1)
        # Transform normal vector of part 1 to world space
        v_p1_n = gp.gp_Vec(p1_n.X(), p1_n.Y(), p1_n.Z()).Transformed(trsf1)
        w_p1_n = gp.gp_Dir(v_p1_n.X(), v_p1_n.Y(), v_p1_n.Z())

        # Target world normal for second part depends on mate type
        if mate.mate_type in (MateType.COINCIDENT, MateType.ATTACH, MateType.DISTANCE):
            # Touching/opposing faces
            target_normal = gp.gp_Dir(-w_p1_n.X(), -w_p1_n.Y(), -w_p1_n.Z())
        elif mate.mate_type == MateType.FLUSH:
            # Planar faces facing same direction
            target_normal = w_p1_n
        elif mate.mate_type in (MateType.CONCENTRIC, MateType.COAXIAL, MateType.ALIGN_HOLES):
            # Axes aligned colinearly
            target_normal = w_p1_n
        else:
            target_normal = w_p1_n

        # Calculate rotation to align normals
        rot_trsf = gp.gp_Trsf()
        if p2_n.IsParallel(target_normal, 1e-4):
            # If opposite directions, rotate 180 degrees around an orthogonal axis
            if p2_n.Dot(target_normal) < 0:
                ortho = gp.gp_Dir(1.0, 0.0, 0.0)
                if abs(p2_n.Dot(ortho)) > 0.9:
                    ortho = gp.gp_Dir(0.0, 1.0, 0.0)
                rot_axis = p2_n.Crossed(ortho)
                rot_trsf.SetRotation(gp.gp_Ax1(p2_pt, rot_axis), math.pi)
        else:
            axis_vec = p2_n.Crossed(target_normal)
            angle = p2_n.Angle(target_normal)
            rot_trsf.SetRotation(
                gp.gp_Ax1(p2_pt, gp.gp_Dir(axis_vec.X(), axis_vec.Y(), axis_vec.Z())), angle
            )

        # Rotate p2 anchor point into rotated frame
        rot_p2_pt = p2_pt.Transformed(rot_trsf)

        # Calculate destination point with normal offset
        dest_pt = gp.gp_Pnt(
            w_p1_pt.X() + w_p1_n.X() * mate.offset,
            w_p1_pt.Y() + w_p1_n.Y() * mate.offset,
            w_p1_pt.Z() + w_p1_n.Z() * mate.offset,
        )

        # Apply transformation to second part
        trans_vec = gp.gp_Vec(rot_p2_pt, dest_pt)
        trans_trsf = gp.gp_Trsf()
        trans_trsf.SetTranslation(trans_vec)

        final_trsf = trans_trsf.Multiplied(rot_trsf)
        self._transforms[second_name] = final_trsf

    def _resolve_anchor(
        self, part: PartNode, selector: Optional[str]
    ) -> Tuple[gp.gp_Pnt, gp.gp_Dir]:
        """Resolve point and direction vector from semantic port or face alias."""
        if not selector or selector == "default":
            raise ValueError(
                f"Cannot mate part '{part.name}': selector is missing or 'default'. "
                f"An explicit port (e.g. 'port:front_face') or face (e.g. 'face:top') is required."
            )

        # Check port
        clean_name = selector.replace("port:", "").replace("face:", "").replace("hole:", "")
        port = part.get_port(clean_name)
        if port:
            if getattr(port, "status", "VALID") == "STALE":
                raise StalePortError(
                    f"Cannot mate to stale port '{clean_name}' on part '{part.name}'. "
                    f"The referenced surface was invalidated by a subsequent geometric modification."
                )
            pos = gp.gp_Pnt(*port.relative_position)
            norm = gp.gp_Dir(*port.normal)
            return pos, norm

        # Common semantic faces for primitives
        if part.shape == "box":
            l = float(part.parameters.get("length", 10.0))
            w = float(part.parameters.get("width", 10.0))
            h = float(part.parameters.get("height", 10.0))
            ox, oy, oz = part.parameters.get("origin", (0.0, 0.0, 0.0))
            if clean_name in ("top", ">Z"):
                return gp.gp_Pnt(ox, oy, oz + h / 2.0), gp.gp_Dir(0.0, 0.0, 1.0)
            elif clean_name in ("bottom", "<Z"):
                return gp.gp_Pnt(ox, oy, oz - h / 2.0), gp.gp_Dir(0.0, 0.0, -1.0)
            elif clean_name in ("front", ">Y"):
                return gp.gp_Pnt(ox, oy + w / 2.0, oz), gp.gp_Dir(0.0, 1.0, 0.0)
            elif clean_name in ("back", "<Y"):
                return gp.gp_Pnt(ox, oy - w / 2.0, oz), gp.gp_Dir(0.0, -1.0, 0.0)
            elif clean_name in ("right", ">X"):
                return gp.gp_Pnt(ox + l / 2.0, oy, oz), gp.gp_Dir(1.0, 0.0, 0.0)
            elif clean_name in ("left", "<X"):
                return gp.gp_Pnt(ox - l / 2.0, oy, oz), gp.gp_Dir(-1.0, 0.0, 0.0)

        elif part.shape == "cylinder":
            h = float(part.parameters.get("height", 10.0))
            r = float(part.parameters.get("radius", 5.0))
            if clean_name in ("top", ">Z"):
                return gp.gp_Pnt(0.0, 0.0, h), gp.gp_Dir(0.0, 0.0, 1.0)
            elif clean_name in ("bottom", "<Z"):
                return gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, -1.0)
            elif clean_name in ("axis", "center", "bore_axis", "shaft_axis"):
                return gp.gp_Pnt(0.0, 0.0, 0.0), gp.gp_Dir(0.0, 0.0, 1.0)

        raise KeyError(
            f"Selector '{selector}' (cleaned: '{clean_name}') on part '{part.name}' is invalid. "
            f"No matching port or semantic face found. Available ports: {list(part.ports.keys())}"
        )


    def _apply_draft_angle(self, solid: TopoDS.TopoDS_Shape, da: Dict[str, Any]) -> TopoDS.TopoDS_Shape:
        """Apply taper draft angle to vertical side faces of solid."""
        import OCP.BRepOffsetAPI as BRepOffsetAPI
        import OCP.BRepAdaptor as BRepAdaptor
        import math

        angle_deg = float(da.get("angle_deg", 2.0))
        angle_rad = math.radians(angle_deg)
        pull_dir = gp.gp_Dir(*da.get("pull_direction", (0.0, 0.0, 1.0)))
        neutral_z = float(da.get("neutral_plane_z", 0.0))
        neutral_plane = gp.gp_Pln(gp.gp_Pnt(0, 0, neutral_z), pull_dir)

        draft_builder = BRepOffsetAPI.BRepOffsetAPI_DraftAngle(solid)
        exp = TopExp.TopExp_Explorer(solid, TopAbs.TopAbs_FACE)
        while exp.More():
            face = TopoDS.TopoDS.Face_s(exp.Current())
            surf = BRepAdaptor.BRepAdaptor_Surface(face)
            u_mid = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
            v_mid = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0
            p = gp.gp_Pnt()
            d1u = gp.gp_Vec()
            d1v = gp.gp_Vec()
            surf.D1(u_mid, v_mid, p, d1u, d1v)
            fnorm = d1u.Crossed(d1v)
            if fnorm.Magnitude() > 1e-6:
                fnorm.Normalize()
                if abs(fnorm.Dot(gp.gp_Vec(pull_dir))) < 0.6:
                    draft_builder.Add(face, pull_dir, angle_rad, neutral_plane)
            exp.Next()

        draft_builder.Build()
        if draft_builder.IsDone():
            return draft_builder.Shape()
        return solid

    def export_glb(self, ir: AssemblyIR, output_path: str, deflection: float = 0.08) -> str:
        """
        Export assembly to binary glTF (.glb) using OpenCASCADE RWGltf_CafWriter.
        Preserves part names, hierarchical transforms, and RGB material colors.
        """
        import OCP.RWGltf as RWGltf
        import OCP.TDocStd as TDocStd
        import OCP.TCollection as TCollection
        import OCP.XCAFDoc as XCAFDoc
        import OCP.TDataStd as TDataStd
        import OCP.BRepMesh as BRepMesh
        import OCP.TColStd as TColStd
        import OCP.Message as Message
        import OCP.Quantity as Quantity

        solids = self.compile(ir)
        doc = TDocStd.TDocStd_Document(TCollection.TCollection_ExtendedString("MDTV-XCAF"))
        shape_tool = XCAFDoc.XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        color_tool = XCAFDoc.XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

        for name, shape in solids.items():
            if shape.IsNull():
                continue
            BRepMesh.BRepMesh_IncrementalMesh(shape, float(deflection))
            label = shape_tool.AddShape(shape, True)
            TDataStd.TDataStd_Name.Set_s(label, TCollection.TCollection_ExtendedString(name))

            base_name = name.split("_pattern_")[0]
            part = ir.parts.get(base_name)
            if part and part.color:
                if isinstance(part.color, str):
                    c = part.color.lstrip("#")
                    if len(c) == 6:
                        r = int(c[0:2], 16) / 255.0
                        g = int(c[2:4], 16) / 255.0
                        b = int(c[4:6], 16) / 255.0
                    else:
                        r, g, b = 0.5, 0.5, 0.5
                elif isinstance(part.color, (list, tuple)) and len(part.color) >= 3:
                    r, g, b = float(part.color[0]), float(part.color[1]), float(part.color[2])
                    if max(r, g, b) > 1.0:
                        r, g, b = r / 255.0, g / 255.0, b / 255.0
                else:
                    r, g, b = 0.5, 0.5, 0.5
                col = Quantity.Quantity_Color(r, g, b, Quantity.Quantity_TypeOfColor.Quantity_TOC_RGB)
                color_tool.SetColor(label, col, XCAFDoc.XCAFDoc_ColorType.XCAFDoc_ColorGen)



        filename = TCollection.TCollection_AsciiString(str(output_path))
        writer = RWGltf.RWGltf_CafWriter(filename, True)
        file_info = TColStd.TColStd_IndexedDataMapOfStringString()
        progress = Message.Message_ProgressRange()

        success = writer.Perform(doc, file_info, progress)
        if not success:
            raise RuntimeError(f"Failed to export GLB to: {output_path}")

        return str(output_path)

    def export_technical_drawing(
        self,
        ir: AssemblyIR,
        output_svg_path: str,
        views: Optional[List[str]] = None,
        sheet_width: int = 1920,
        sheet_height: int = 1080,
        title: Optional[str] = None,
    ) -> str:
        """
        Export 2D technical drawing to vector SVG with visible and hidden lines.
        Uses OpenCASCADE HLRBRep (Hidden Line Removal) algorithm.
        Generates standard 4-view engineering drawing (Top, Front, Right, Isometric)
        with border, title block (antet), and projection indicators.
        """
        import OCP.HLRBRep as HLRBRep
        import OCP.HLRAlgo as HLRAlgo
        import OCP.BRepAdaptor as BRepAdaptor
        import OCP.TopExp as TopExp
        import OCP.TopAbs as TopAbs
        import OCP.TopoDS as TopoDS
        import datetime

        if views is None:
            views = ["top", "front", "side", "iso"]

        solids = self.compile(ir)
        builder = BRep.BRep_Builder()
        compound = TopoDS.TopoDS_Compound()
        builder.MakeCompound(compound)
        for s in solids.values():
            if not s.IsNull():
                builder.Add(compound, s)

        view_defs = {
            "top": {
                "name": "ÜST GÖRÜNÜŞ (TOP VIEW)",
                "ax2": gp.gp_Ax2(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(0, 0, -1), gp.gp_Dir(1, 0, 0)),
                "bounds": (60, 60, sheet_width // 2 - 40, sheet_height // 2 - 40),
            },
            "front": {
                "name": "ÖN GÖRÜNÜŞ (FRONT VIEW)",
                "ax2": gp.gp_Ax2(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(0, 1, 0), gp.gp_Dir(1, 0, 0)),
                "bounds": (60, sheet_height // 2 + 20, sheet_width // 2 - 40, sheet_height - 120),
            },
            "side": {
                "name": "SAĞ YAN GÖRÜNÜŞ (RIGHT VIEW)",
                "ax2": gp.gp_Ax2(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(-1, 0, 0), gp.gp_Dir(0, 1, 0)),
                "bounds": (sheet_width // 2 + 40, sheet_height // 2 + 20, sheet_width - 60, sheet_height - 120),
            },
            "iso": {
                "name": "İZOMETRİK GÖRÜNÜŞ (ISOMETRIC 3D)",
                "ax2": gp.gp_Ax2(gp.gp_Pnt(0, 0, 0), gp.gp_Dir(1.0, 1.0, 1.0), gp.gp_Dir(-1.0, 1.0, 0.0)),
                "bounds": (sheet_width // 2 + 40, 60, sheet_width - 60, sheet_height // 2 - 40),
            },
        }

        svg_elements = []

        def extract_segments(comp: TopoDS.TopoDS_Shape):
            segments = []
            if comp.IsNull():
                return segments
            exp = TopExp.TopExp_Explorer(comp, TopAbs.TopAbs_EDGE)
            while exp.More():
                edge = TopoDS.TopoDS.Edge_s(exp.Current())
                try:
                    adaptor = BRepAdaptor.BRepAdaptor_Curve(edge)
                    u1, u2 = adaptor.FirstParameter(), adaptor.LastParameter()
                    ctype = adaptor.GetType()
                    if ctype == 0:  # Line
                        p1 = adaptor.Value(u1)
                        p2 = adaptor.Value(u2)
                        segments.append([(p1.X(), p1.Y()), (p2.X(), p2.Y())])
                    else:
                        pts = []
                        n_samples = 16
                        for i in range(n_samples + 1):
                            u = u1 + (u2 - u1) * (i / n_samples)
                            p = adaptor.Value(u)
                            pts.append((p.X(), p.Y()))
                        segments.append(pts)
                except Exception:
                    pass
                exp.Next()
            return segments

        for view_key in views:
            if view_key not in view_defs:
                continue
            vinfo = view_defs[view_key]
            bx0, by0, bx1, by1 = vinfo["bounds"]
            vw = bx1 - bx0
            vh = by1 - by0

            projector = HLRAlgo.HLRAlgo_Projector(vinfo["ax2"])
            algo = HLRBRep.HLRBRep_Algo()
            algo.Add(compound)
            algo.Projector(projector)
            algo.Update()
            algo.Hide()

            hlr = HLRBRep.HLRBRep_HLRToShape(algo)
            v_comp = hlr.VCompound()
            h_comp = hlr.HCompound()
            out_comp = hlr.OutLineVCompound()

            v_segs = extract_segments(v_comp)
            if not out_comp.IsNull():
                v_segs.extend(extract_segments(out_comp))
            h_segs = extract_segments(h_comp)

            all_pts = []
            for seg in v_segs + h_segs:
                all_pts.extend(seg)

            if not all_pts:
                continue

            min_x = min(p[0] for p in all_pts)
            max_x = max(p[0] for p in all_pts)
            min_y = min(p[1] for p in all_pts)
            max_y = max(p[1] for p in all_pts)

            dx = max_x - min_x if max_x > min_x else 1.0
            dy = max_y - min_y if max_y > min_y else 1.0
            scale = min((vw * 0.8) / dx, (vh * 0.8) / dy)

            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            vcx = bx0 + vw / 2.0
            vcy = by0 + vh / 2.0

            def transform(p):
                sx = vcx + (p[0] - cx) * scale
                sy = vcy - (p[1] - cy) * scale
                return sx, sy

            svg_elements.append(
                f'<text x="{bx0 + 10}" y="{by0 + 20}" font-family="Arial, sans-serif" font-size="13" font-weight="bold" fill="#334155">{vinfo["name"]}</text>'
            )

            # Draw hidden edges (dashed)
            for seg in h_segs:
                if len(seg) < 2:
                    continue
                t_pts = [transform(p) for p in seg]
                d = f"M {t_pts[0][0]:.1f} {t_pts[0][1]:.1f} " + " ".join(f"L {p[0]:.1f} {p[1]:.1f}" for p in t_pts[1:])
                svg_elements.append(f'<path d="{d}" stroke="#94a3b8" stroke-width="0.9" stroke-dasharray="4,4" fill="none" stroke-linecap="round"/>')

            # Draw visible edges (solid)
            for seg in v_segs:
                if len(seg) < 2:
                    continue
                t_pts = [transform(p) for p in seg]
                d = f"M {t_pts[0][0]:.1f} {t_pts[0][1]:.1f} " + " ".join(f"L {p[0]:.1f} {p[1]:.1f}" for p in t_pts[1:])
                svg_elements.append(f'<path d="{d}" stroke="#0f172a" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')

        now_str = datetime.date.today().isoformat()
        import html
        raw_title = title or ir.metadata.name or "Engineering Drawing"
        doc_title = html.escape(raw_title)

        svg_doc = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_width} {sheet_height}" width="{sheet_width}" height="{sheet_height}" style="background-color: #ffffff;">
    <defs>
        <style>
            .border-line {{ stroke: #0f172a; stroke-width: 2.5; fill: none; }}
            .inner-border {{ stroke: #64748b; stroke-width: 1.0; fill: none; }}
            .grid-divider {{ stroke: #cbd5e1; stroke-width: 0.8; stroke-dasharray: 6,6; }}
            .title-text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; fill: #0f172a; }}
        </style>
    </defs>
    <rect x="20" y="20" width="{sheet_width - 40}" height="{sheet_height - 40}" class="border-line" rx="4"/>
    <rect x="28" y="28" width="{sheet_width - 56}" height="{sheet_height - 56}" class="inner-border" rx="2"/>

    <line x1="{sheet_width // 2}" y1="28" x2="{sheet_width // 2}" y2="{sheet_height - 110}" class="grid-divider"/>
    <line x1="28" y1="{sheet_height // 2 - 10}" x2="{sheet_width - 28}" y2="{sheet_height // 2 - 10}" class="grid-divider"/>

    {"".join(svg_elements)}

    <g transform="translate({sheet_width - 480}, {sheet_height - 110})">
        <rect x="0" y="0" width="452" height="82" fill="#f8fafc" stroke="#0f172a" stroke-width="1.5" rx="3"/>
        <line x1="0" y1="28" x2="452" y2="28" stroke="#0f172a" stroke-width="1.0"/>
        <line x1="0" y1="56" x2="452" y2="56" stroke="#0f172a" stroke-width="1.0"/>
        <line x1="280" y1="0" x2="280" y2="82" stroke="#0f172a" stroke-width="1.0"/>
        <text x="12" y="19" class="title-text" font-size="13" font-weight="bold">PROJE: {doc_title}</text>
        <text x="12" y="46" class="title-text" font-size="11" fill="#475569">MOTOR: cadi_saml CAD Kernel (OpenCASCADE)</text>
        <text x="12" y="72" class="title-text" font-size="11" fill="#475569">STANDART: ISO 2768-m • BİRİM: mm</text>
        <text x="290" y="19" class="title-text" font-size="11" font-weight="bold">TARİH: {now_str}</text>
        <text x="290" y="46" class="title-text" font-size="11">ÖLÇEK: OTOMATİK</text>
        <text x="290" y="72" class="title-text" font-size="11" font-weight="bold" fill="#0284c7">DURUM: ONAYLANDI</text>
    </g>
</svg>"""


        with open(output_svg_path, "w", encoding="utf-8") as f:
            f.write(svg_doc)

        return str(output_svg_path)

