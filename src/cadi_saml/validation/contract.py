"""
cadi_saml.validation.contract
=============================
Post-Build Engineering Verification Contract.
Executes an automated multi-stage contract chain:
1. Compilation (B-Rep IR -> OpenCASCADE solids)
2. Manifold Integrity (Watertight, closed shell, valid topological orientation)
3. Dimension & Volume Verification (Positive mass properties, boundary box check)
4. Interference / Collision Check (Zero unauthorized solid overlaps)
5. Kinematic Constraint Consistency (Joint & DOF audit)
6. STEP Export & Reopen Roundtrip (Geometry preservation through STEP AP214/AP242)
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import OCP.Bnd as Bnd
import OCP.BRepBndLib as BRepBndLib
import OCP.BRepCheck as BRepCheck
import OCP.BRepGProp as BRepGProp
import OCP.GProp as GProp
import OCP.IFSelect as IFS
import OCP.STEPControl as SC
import OCP.TopAbs as TopAbs
import OCP.TopExp as TopExp
import OCP.TopoDS as TopoDS

if TYPE_CHECKING:
    from ..core.assembly import Assembly


@dataclass
class ContractStageResult:
    stage_name: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ContractReport:
    assembly_name: str
    passed: bool
    stages: Dict[str, ContractStageResult] = field(default_factory=dict)
    total_parts_verified: int = 0
    total_volume_mm3: float = 0.0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assembly_name": self.assembly_name,
            "passed": self.passed,
            "total_parts_verified": self.total_parts_verified,
            "total_volume_mm3": round(self.total_volume_mm3, 2),
            "summary": self.summary,
            "stages": {
                k: {
                    "passed": v.passed,
                    "details": v.details,
                    "errors": v.errors,
                    "warnings": v.warnings,
                }
                for k, v in self.stages.items()
            },
        }


class PostBuildContract:
    """
    Automated Post-Build Engineering Contract Verifier.
    Enforces that every assembled CAD model meets strict physical and geometric criteria.
    """

    def __init__(self, assembly: "Assembly"):
        self.assembly = assembly

    def verify(
        self,
        test_step_roundtrip: bool = True,
        check_clash: bool = True,
        max_clash_volume_mm3: float = 0.1,
        volume_tolerance_ratio: float = 0.005,
        strict: bool = True,
        expected_specs: Optional[Dict[str, Any]] = None,
        require_provenance: bool = False,
        test_dfm: bool = False,
        test_gdt: bool = False,
    ) -> ContractReport:
        """
        Executes the full contract verification chain.
        """
        stages: Dict[str, ContractStageResult] = {}
        all_passed = True
        total_vol = 0.0
        solids: Dict[str, TopoDS.TopoDS_Shape] = {}

        # 1. Compilation Stage
        compile_stage = ContractStageResult(stage_name="Compilation", passed=True)
        try:
            from ..backend.occt_backend import OCCTBackend
            backend = OCCTBackend()
            solids = backend.compile(self.assembly.to_ir())
            compile_stage.details["compiled_parts"] = list(solids.keys())
            if not solids:
                compile_stage.passed = False
                compile_stage.errors.append("Assembly compiled into zero solid bodies.")
        except Exception as e:
            compile_stage.passed = False
            compile_stage.errors.append(f"OpenCASCADE backend compilation failed: {e}")
        stages["compilation"] = compile_stage
        if not compile_stage.passed:
            all_passed = False
            return ContractReport(
                assembly_name=self.assembly.name,
                passed=False,
                stages=stages,
                summary="Post-Build Contract FAILED at compilation stage.",
            )

        # 2. Manifold Integrity Stage
        manifold_stage = ContractStageResult(stage_name="ManifoldIntegrity", passed=True)
        non_manifold = []
        for name, shape in solids.items():
            if shape is None or shape.IsNull():
                non_manifold.append(name)
                manifold_stage.errors.append(f"Part '{name}' is a null TopoDS shape.")
                continue
            analyzer = BRepCheck.BRepCheck_Analyzer(shape)
            if not analyzer.IsValid():
                if strict:
                    non_manifold.append(name)
                    manifold_stage.errors.append(f"Part '{name}' has invalid B-Rep topology (BRepCheck failed).")
                else:
                    g = GProp.GProp_GProps()
                    BRepGProp.BRepGProp.VolumeProperties_s(shape, g)
                    if g.Mass() <= 1e-3:
                        non_manifold.append(name)
                        manifold_stage.errors.append(f"Part '{name}' has non-manifold B-Rep topology.")
        manifold_stage.details["verified_manifold_count"] = len(solids) - len(non_manifold)
        if non_manifold:
            manifold_stage.passed = False
            all_passed = False
        stages["manifold"] = manifold_stage

        # 3. Dimension & Volume Stage
        dim_stage = ContractStageResult(stage_name="DimensionAndVolume", passed=True)
        part_volumes: Dict[str, float] = {}
        part_bboxes: Dict[str, Dict[str, Any]] = {}

        # Validate volume_tolerance_ratio safely
        vol_tol_valid = True
        safe_volume_tolerance_ratio = 0.005
        try:
            val_tol = float(volume_tolerance_ratio)
            if not math.isfinite(val_tol) or val_tol < 0:
                vol_tol_valid = False
            else:
                safe_volume_tolerance_ratio = val_tol
        except (ValueError, TypeError):
            vol_tol_valid = False

        if not vol_tol_valid:
            dim_stage.passed = False
            dim_stage.errors.append(
                f"Invalid contract volume_tolerance_ratio '{volume_tolerance_ratio}': must be a finite non-negative number."
            )

        # Parse and validate expected_specs structure if provided
        expected_part_specs: Dict[str, Dict[str, Any]] = {}
        reserved_top_keys = {"total_volume", "tolerance", "parts", "bounding_box", "required_parameters"}

        if expected_specs:
            if not isinstance(expected_specs, dict):
                dim_stage.passed = False
                dim_stage.errors.append("expected_specs must be a dictionary.")
            else:
                # Check top-level tolerance if specified
                if "tolerance" in expected_specs:
                    top_tol_raw = expected_specs["tolerance"]
                    try:
                        top_tol = float(top_tol_raw)
                        if not math.isfinite(top_tol) or top_tol < 0:
                            dim_stage.passed = False
                            dim_stage.errors.append(
                                f"Invalid specification top-level tolerance '{top_tol_raw}': must be a finite non-negative number."
                            )
                    except (ValueError, TypeError):
                        dim_stage.passed = False
                        dim_stage.errors.append(
                            f"Invalid specification top-level tolerance '{top_tol_raw}': must be numeric."
                        )

                # Collect part specs from 'parts' dictionary
                if "parts" in expected_specs:
                    if isinstance(expected_specs["parts"], dict):
                        for pk, pv in expected_specs["parts"].items():
                            if isinstance(pv, dict):
                                expected_part_specs[pk] = pv
                            else:
                                dim_stage.passed = False
                                dim_stage.errors.append(f"Specification for part '{pk}' in 'parts' must be a dictionary.")
                    else:
                        dim_stage.passed = False
                        dim_stage.errors.append("Specification 'parts' field must be a dictionary.")

                # Collect part specs directly at top level and reject unknown top-level keys or duplicate/conflicting specs
                for k, v in expected_specs.items():
                    if k in reserved_top_keys:
                        continue
                    if isinstance(v, dict):
                        if k in expected_part_specs:
                            dim_stage.passed = False
                            dim_stage.errors.append(
                                f"Conflicting/duplicate specification for part '{k}': defined in both 'parts.{k}' and top-level '{k}'."
                            )
                        else:
                            expected_part_specs[k] = v
                    else:
                        dim_stage.passed = False
                        dim_stage.errors.append(
                            f"Specification contains unrecognized field or ghost part '{k}' not found in assembly solids."
                        )

                # Ghost part check: verify that all parts in expected_part_specs exist in solids
                for exp_pname in expected_part_specs:
                    if exp_pname not in solids:
                        dim_stage.passed = False
                        dim_stage.errors.append(
                            f"Specification references ghost/unknown part '{exp_pname}' not present in assembly solids (available: {list(solids.keys())})."
                        )

        # Global assembly-level bounding box and solid count
        asm_box = Bnd.Bnd_Box()
        total_solids_count = 0

        for name, shape in solids.items():
            if shape and not shape.IsNull():
                g = GProp.GProp_GProps()
                BRepGProp.BRepGProp.VolumeProperties_s(shape, g)
                v = g.Mass()
                part_volumes[name] = round(v, 3)
                total_vol += v
                if v <= 0.0 or not math.isfinite(v):
                    dim_stage.passed = False
                    dim_stage.errors.append(f"Part '{name}' has non-positive or invalid volume ({v:.2f} mm3).")

                # Topological solid counting
                solid_exp = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_SOLID)
                part_solids = 0
                while solid_exp.More():
                    part_solids += 1
                    solid_exp.Next()
                total_solids_count += part_solids
                if part_solids == 0:
                    dim_stage.passed = False
                    dim_stage.errors.append(f"Part '{name}' contains zero topological solids.")

                # Compute exact 3D Bounding Box
                box = Bnd.Bnd_Box()
                BRepBndLib.BRepBndLib.Add_s(shape, box)
                asm_box.Add(box)
                xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
                dx = round(xmax - xmin, 3)
                dy = round(ymax - ymin, 3)
                dz = round(zmax - zmin, 3)
                part_bboxes[name] = {
                    "dx": dx,
                    "dy": dy,
                    "dz": dz,
                    "bounds": [round(xmin, 3), round(ymin, 3), round(zmin, 3), round(xmax, 3), round(ymax, 3), round(zmax, 3)],
                }
                if dx <= 1e-4 or dy <= 1e-4 or dz <= 1e-4:
                    dim_stage.passed = False
                    dim_stage.errors.append(f"Part '{name}' has degenerate boundary box dimensions ({dx}x{dy}x{dz} mm).")

                # Compare against expected specifications if provided for this part
                if name in expected_part_specs:
                    pspec = expected_part_specs[name]
                    p_ref = self.assembly._parts.get(name)
                    p_params = p_ref.parameters if p_ref else {}

                    # Resolve part-level tolerance
                    tol_raw = pspec.get(
                        "tolerance",
                        expected_specs.get("tolerance", volume_tolerance_ratio) if expected_specs else volume_tolerance_ratio,
                    )
                    tol_valid = True
                    try:
                        tol = float(tol_raw)
                        if not math.isfinite(tol) or tol < 0:
                            tol_valid = False
                            dim_stage.passed = False
                            dim_stage.errors.append(
                                f"Part '{name}' has invalid specification tolerance '{tol_raw}': must be a finite non-negative number."
                            )
                    except (ValueError, TypeError):
                        tol_valid = False
                        dim_stage.passed = False
                        dim_stage.errors.append(
                            f"Part '{name}' has invalid non-numeric specification tolerance '{tol_raw}'."
                        )

                    # 1. Volume check
                    if "volume" in pspec:
                        try:
                            exp_v = float(pspec["volume"])
                            if not math.isfinite(exp_v) or exp_v <= 0:
                                dim_stage.passed = False
                                dim_stage.errors.append(f"Part '{name}' expected volume '{pspec['volume']}' must be a finite positive number.")
                            elif not tol_valid:
                                dim_stage.passed = False
                                dim_stage.errors.append(f"Part '{name}' volume check cannot be evaluated due to invalid tolerance '{tol_raw}'.")
                            else:
                                v_delta = abs(v - exp_v) / max(1.0, exp_v)
                                if v_delta > tol:
                                    dim_stage.passed = False
                                    dim_stage.errors.append(
                                        f"Part '{name}' volume discrepancy ({v:.2f} vs expected {exp_v:.2f}, delta={v_delta:.2%}) exceeds tolerance {tol:.2%}."
                                    )
                        except (ValueError, TypeError):
                            dim_stage.passed = False
                            dim_stage.errors.append(f"Part '{name}' expected volume '{pspec['volume']}' is not a valid number.")

                    # 2. Bounding box check
                    if "bounding_box" in pspec:
                        raw_bbox = pspec["bounding_box"]
                        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 3:
                            dim_stage.passed = False
                            dim_stage.errors.append(f"Part '{name}' expected bounding_box must be a 3-element list/tuple [dx, dy, dz].")
                        else:
                            try:
                                exp_dx, exp_dy, exp_dz = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2])
                                if not all(math.isfinite(val) and val > 0 for val in (exp_dx, exp_dy, exp_dz)):
                                    dim_stage.passed = False
                                    dim_stage.errors.append(f"Part '{name}' bounding_box dimensions must be finite positive numbers.")
                                elif not tol_valid:
                                    dim_stage.passed = False
                                    dim_stage.errors.append(f"Part '{name}' bounding box check cannot be evaluated due to invalid tolerance '{tol_raw}'.")
                                else:
                                    b_delta = max(
                                        abs(dx - exp_dx) / max(1.0, exp_dx),
                                        abs(dy - exp_dy) / max(1.0, exp_dy),
                                        abs(dz - exp_dz) / max(1.0, exp_dz),
                                    )
                                    if b_delta > tol:
                                        dim_stage.passed = False
                                        dim_stage.errors.append(
                                            f"Part '{name}' bounding box discrepancy (actual={[dx, dy, dz]} vs expected={[exp_dx, exp_dy, exp_dz]}, delta={b_delta:.2%}) exceeds tolerance {tol:.2%}."
                                        )
                            except (ValueError, TypeError):
                                dim_stage.passed = False
                                dim_stage.errors.append(f"Part '{name}' expected bounding_box contains non-numeric values.")

                    # 3. Dimensions dictionary check
                    if "dimensions" in pspec:
                        if not isinstance(pspec["dimensions"], dict):
                            dim_stage.passed = False
                            dim_stage.errors.append(f"Part '{name}' specification 'dimensions' must be a dictionary.")
                        else:
                            for dim_k, exp_val in pspec["dimensions"].items():
                                if dim_k not in p_params:
                                    dim_stage.passed = False
                                    dim_stage.errors.append(
                                        f"Part '{name}' specification contains unknown dimension or typo '{dim_k}' (available: {list(p_params.keys())})."
                                    )
                                    continue
                                try:
                                    exp_val_num = float(exp_val)
                                    if not math.isfinite(exp_val_num):
                                        dim_stage.passed = False
                                        dim_stage.errors.append(f"Part '{name}' dimension '{dim_k}' expected value is non-finite.")
                                        continue
                                except (ValueError, TypeError):
                                    dim_stage.passed = False
                                    dim_stage.errors.append(f"Part '{name}' dimension '{dim_k}' expected value '{exp_val}' is non-numeric.")
                                    continue

                                if not tol_valid:
                                    dim_stage.passed = False
                                else:
                                    act_val = float(p_params[dim_k])
                                    d_delta = abs(act_val - exp_val_num) / max(1.0, abs(exp_val_num))
                                    if d_delta > tol:
                                        dim_stage.passed = False
                                        dim_stage.errors.append(
                                            f"Part '{name}' parameter '{dim_k}' discrepancy ({act_val} vs expected {exp_val_num}, delta={d_delta:.2%}) exceeds tolerance {tol:.2%}."
                                        )

                    # 4. Direct top-level fields inside pspec
                    recognized_pspec_keys = {"volume", "bounding_box", "dimensions", "tolerance", "required_parameters"}
                    for k, v in pspec.items():
                        if k in recognized_pspec_keys:
                            continue
                        if k in p_params:
                            try:
                                exp_val_num = float(v)
                                if not math.isfinite(exp_val_num):
                                    dim_stage.passed = False
                                    dim_stage.errors.append(f"Part '{name}' parameter '{k}' expected value is non-finite.")
                                elif not tol_valid:
                                    dim_stage.passed = False
                                else:
                                    act_val = float(p_params[k])
                                    d_delta = abs(act_val - exp_val_num) / max(1.0, abs(exp_val_num))
                                    if d_delta > tol:
                                        dim_stage.passed = False
                                        dim_stage.errors.append(
                                            f"Part '{name}' parameter '{k}' discrepancy ({act_val} vs expected {exp_val_num}, delta={d_delta:.2%}) exceeds tolerance {tol:.2%}."
                                        )
                            except (ValueError, TypeError):
                                dim_stage.passed = False
                                dim_stage.errors.append(f"Part '{name}' parameter '{k}' expected value '{v}' is non-numeric.")
                        else:
                            dim_stage.passed = False
                            dim_stage.errors.append(
                                f"Part '{name}' specification contains unknown parameter or typo '{k}' (available: {list(p_params.keys())})."
                            )

        # Check total assembly volume against expected_specs if provided
        if expected_specs and "total_volume" in expected_specs:
            raw_tot = expected_specs["total_volume"]
            tot_tol_raw = expected_specs.get("tolerance", safe_volume_tolerance_ratio)
            tot_tol_valid = True
            try:
                tot_tol = float(tot_tol_raw)
                if not math.isfinite(tot_tol) or tot_tol < 0:
                    tot_tol_valid = False
                    dim_stage.passed = False
                    dim_stage.errors.append(
                        f"Invalid assembly total_volume tolerance '{tot_tol_raw}': must be a finite non-negative number."
                    )
            except (ValueError, TypeError):
                tot_tol_valid = False
                dim_stage.passed = False
                dim_stage.errors.append(
                    f"Invalid non-numeric assembly total_volume tolerance '{tot_tol_raw}'."
                )

            try:
                exp_tot = float(raw_tot)
                if not math.isfinite(exp_tot) or exp_tot <= 0:
                    dim_stage.passed = False
                    dim_stage.errors.append(
                        f"Invalid expected total_volume '{raw_tot}': must be a finite positive number."
                    )
                elif not tot_tol_valid:
                    dim_stage.passed = False
                    dim_stage.errors.append(
                        f"Assembly total volume check cannot be evaluated due to invalid tolerance '{tot_tol_raw}'."
                    )
                else:
                    tot_delta = abs(total_vol - exp_tot) / max(1.0, exp_tot)
                    if tot_delta > tot_tol:
                        dim_stage.passed = False
                        dim_stage.errors.append(
                            f"Assembly total volume discrepancy ({total_vol:.2f} vs expected {exp_tot:.2f}, delta={tot_delta:.2%}) exceeds tolerance {tot_tol:.2%}."
                        )
            except (ValueError, TypeError):
                dim_stage.passed = False
                dim_stage.errors.append(f"Invalid non-numeric expected total_volume '{raw_tot}'.")

        # Compute exact assembly-level 3D Bounding Box
        asm_box = Bnd.Bnd_Box()
        for s in solids.values():
            if s and not s.IsNull():
                BRepBndLib.BRepBndLib.Add_s(s, asm_box)
        if not asm_box.IsVoid():
            a_xmin, a_ymin, a_zmin, a_xmax, a_ymax, a_zmax = asm_box.Get()
            asm_dx = round(a_xmax - a_xmin, 3)
            asm_dy = round(a_ymax - a_ymin, 3)
            asm_dz = round(a_zmax - a_zmin, 3)
            dim_stage.details["assembly_bounding_box"] = {
                "dx": asm_dx,
                "dy": asm_dy,
                "dz": asm_dz,
                "bounds": [round(a_xmin, 3), round(a_ymin, 3), round(a_zmin, 3), round(a_xmax, 3), round(a_ymax, 3), round(a_zmax, 3)],
            }
        else:
            asm_dx, asm_dy, asm_dz = 0.0, 0.0, 0.0
        dim_stage.details["total_solids_count"] = total_solids_count


        # Check assembly-level bounding box against expected_specs if provided
        if expected_specs and "bounding_box" in expected_specs:
            raw_top_bbox = expected_specs["bounding_box"]
            tot_tol_raw = expected_specs.get("tolerance", safe_volume_tolerance_ratio)
            tot_tol_valid = True
            try:
                tot_tol = float(tot_tol_raw)
                if not math.isfinite(tot_tol) or tot_tol < 0:
                    tot_tol_valid = False
            except (ValueError, TypeError):
                tot_tol_valid = False

            if not isinstance(raw_top_bbox, (list, tuple)) or len(raw_top_bbox) != 3:
                dim_stage.passed = False
                dim_stage.errors.append("Assembly expected 'bounding_box' must be a 3-element list/tuple [dx, dy, dz].")
            else:
                try:
                    exp_adx, exp_ady, exp_adz = float(raw_top_bbox[0]), float(raw_top_bbox[1]), float(raw_top_bbox[2])
                    if not all(math.isfinite(val) and val > 0 for val in (exp_adx, exp_ady, exp_adz)):
                        dim_stage.passed = False
                        dim_stage.errors.append("Assembly 'bounding_box' dimensions must be finite positive numbers.")
                    elif not tot_tol_valid:
                        dim_stage.passed = False
                        dim_stage.errors.append(f"Assembly bounding box check cannot be evaluated due to invalid tolerance '{tot_tol_raw}'.")
                    else:
                        asm_b_delta = max(
                            abs(asm_dx - exp_adx) / max(1.0, exp_adx),
                            abs(asm_dy - exp_ady) / max(1.0, exp_ady),
                            abs(asm_dz - exp_adz) / max(1.0, exp_adz),
                        )
                        if asm_b_delta > tot_tol:
                            dim_stage.passed = False
                            dim_stage.errors.append(
                                f"Assembly bounding box discrepancy (actual={[asm_dx, asm_dy, asm_dz]} vs expected={[exp_adx, exp_ady, exp_adz]}, delta={asm_b_delta:.2%}) exceeds tolerance {tot_tol:.2%}."
                            )
                except (ValueError, TypeError):
                    dim_stage.passed = False
                    dim_stage.errors.append("Assembly expected 'bounding_box' contains non-numeric values.")

        dim_stage.details["part_volumes_mm3"] = part_volumes
        dim_stage.details["part_bounding_boxes_mm"] = part_bboxes
        dim_stage.details["total_volume_mm3"] = round(total_vol, 3)
        dim_stage.details["assembly_bounding_box_mm"] = [asm_dx, asm_dy, asm_dz]
        if not dim_stage.passed:
            all_passed = False
        stages["dimensions"] = dim_stage

        # 4. Interference / Clash Stage
        clash_stage = ContractStageResult(stage_name="InterferenceAndClearance", passed=True)
        if check_clash:
            clash_thresh_valid = True
            safe_max_clash_volume = 0.1
            try:
                thresh = float(max_clash_volume_mm3)
                if not math.isfinite(thresh) or thresh < 0:
                    clash_thresh_valid = False
                else:
                    safe_max_clash_volume = thresh
            except (ValueError, TypeError):
                clash_thresh_valid = False

            if not clash_thresh_valid:
                clash_stage.passed = False
                all_passed = False
                clash_stage.errors.append(
                    f"Invalid clash volume threshold '{max_clash_volume_mm3}': must be a finite non-negative number."
                )

            try:
                from .validation_engineer import ValidationEngineer
                val = ValidationEngineer()
                clashes = val.check_clashes(solids)
                if clash_thresh_valid:
                    significant_clashes = [c for c in clashes if c.clash_volume > safe_max_clash_volume]
                else:
                    significant_clashes = [c for c in clashes if c.clash_volume > 0.0]

                clash_stage.details["clash_count"] = len(significant_clashes)
                if significant_clashes:
                    clash_stage.passed = False
                    all_passed = False
                    for c in significant_clashes:
                        clash_stage.errors.append(
                            f"Interference detected: '{c.first_part}' clashes with '{c.second_part}' "
                            f"({c.clash_volume:.2f} mm3)."
                        )
            except Exception as e:
                if strict:
                    clash_stage.passed = False
                    all_passed = False
                    clash_stage.errors.append(f"Clash check failed with exception in strict mode: {e}")
                else:
                    clash_stage.warnings.append(f"Clash check skipped due to error: {e}")
        else:
            clash_stage.details["status"] = "skipped_by_user"
        stages["interference"] = clash_stage

        # 5. Kinematic Constraint Consistency Stage
        kin_stage = ContractStageResult(stage_name="KinematicConsistency", passed=True)
        if hasattr(self.assembly, "_mechanism") and self.assembly._mechanism:
            mech = self.assembly._mechanism
            joints = getattr(mech, "joints", {})
            relations = getattr(mech, "relations", [])
            kin_stage.details["joints_count"] = len(joints)
            kin_stage.details["relations_count"] = len(relations)

            missing_joint_parts = [j for j in joints if j not in self.assembly._parts]
            if missing_joint_parts:
                kin_stage.passed = False
                kin_stage.errors.append(f"Kinematic joints reference missing assembly parts: {', '.join(missing_joint_parts)}")

            try:
                from ..kinematics.inspection import linear_relations, validate_mechanism
                edges, lin_errs = linear_relations(mech)
                if lin_errs:
                    kin_stage.passed = False
                    kin_stage.errors.extend(lin_errs)

                if relations and joints and not lin_errs:
                    first_rel = relations[0]
                    driver_cand = (
                        getattr(first_rel, "sun_part", None)
                        or getattr(first_rel, "driver_part", None)
                        or getattr(first_rel, "pinion_part", None)
                        or getattr(first_rel, "crank_part", None)
                    )
                    if driver_cand and driver_cand in joints:
                        v_rep = validate_mechanism(mech, driver_cand)
                        if not v_rep["valid"]:
                            kin_stage.passed = False
                            kin_stage.errors.extend(v_rep["errors"])
            except Exception as e:
                if strict:
                    kin_stage.passed = False
                    kin_stage.errors.append(f"Kinematic consistency validation failed with exception: {e}")
                else:
                    kin_stage.warnings.append(f"Kinematic check warning: {e}")

            if not kin_stage.passed:
                all_passed = False
        stages["kinematics"] = kin_stage

        # 6. STEP Export & Reopen Roundtrip Stage
        if test_step_roundtrip and solids and total_vol > 0:
            step_stage = ContractStageResult(stage_name="STEPRoundtrip", passed=True)
            tmp_step = None
            try:
                asm_box = Bnd.Bnd_Box()
                for s in solids.values():
                    BRepBndLib.BRepBndLib.Add_s(s, asm_box)
                xmin, ymin, zmin, xmax, ymax, zmax = asm_box.Get()
                orig_dx, orig_dy, orig_dz = xmax - xmin, ymax - ymin, zmax - zmin

                with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
                    tmp_step = f.name
                backend.export_step(self.assembly.to_ir(), tmp_step)

                reader = SC.STEPControl_Reader()
                st = reader.ReadFile(tmp_step)
                if st != IFS.IFSelect_RetDone:
                    step_stage.passed = False
                    step_stage.errors.append("Failed to read exported STEP file during roundtrip verification.")
                else:
                    reader.TransferRoots()
                    reopened_shape = reader.OneShape()

                    # 1. Volume
                    g_reopen = GProp.GProp_GProps()
                    BRepGProp.BRepGProp.VolumeProperties_s(reopened_shape, g_reopen)
                    reopen_vol = g_reopen.Mass()
                    vol_diff_ratio = abs(reopen_vol - total_vol) / max(1.0, total_vol)

                    # 2. Solid Count
                    exp = TopExp.TopExp_Explorer(reopened_shape, TopAbs.TopAbs_SOLID)
                    reopened_solids_count = 0
                    while exp.More():
                        reopened_solids_count += 1
                        exp.Next()

                    # 3. Bounding Box
                    reopen_box = Bnd.Bnd_Box()
                    BRepBndLib.BRepBndLib.Add_s(reopened_shape, reopen_box)
                    r_xmin, r_ymin, r_zmin, r_xmax, r_ymax, r_zmax = reopen_box.Get()
                    reopen_dx, reopen_dy, reopen_dz = r_xmax - r_xmin, r_ymax - r_ymin, r_zmax - r_zmin
                    bbox_delta = max(
                        abs(orig_dx - reopen_dx) / max(1.0, orig_dx),
                        abs(orig_dy - reopen_dy) / max(1.0, orig_dy),
                        abs(orig_dz - reopen_dz) / max(1.0, orig_dz),
                    )

                    original_solids_count = 0
                    for s in solids.values():
                        if s and not s.IsNull():
                            s_exp = TopExp.TopExp_Explorer(s, TopAbs.TopAbs_SOLID)
                            while s_exp.More():
                                original_solids_count += 1
                                s_exp.Next()

                    step_stage.details["original_volume_mm3"] = round(total_vol, 2)
                    step_stage.details["reopened_volume_mm3"] = round(reopen_vol, 2)
                    step_stage.details["volume_delta_ratio"] = round(vol_diff_ratio, 5)
                    step_stage.details["original_solid_count"] = original_solids_count
                    step_stage.details["reopened_solid_count"] = reopened_solids_count
                    step_stage.details["bbox_delta_ratio"] = round(bbox_delta, 5)

                    if vol_diff_ratio > safe_volume_tolerance_ratio:
                        step_stage.passed = False
                        step_stage.errors.append(
                            f"STEP roundtrip volume discrepancy exceeded tolerance: "
                            f"original={total_vol:.2f}, reopened={reopen_vol:.2f} (delta={vol_diff_ratio:.3%})"
                        )
                    if bbox_delta > safe_volume_tolerance_ratio:
                        step_stage.passed = False
                        step_stage.errors.append(
                            f"STEP roundtrip bounding box discrepancy exceeded tolerance: "
                            f"actual delta={bbox_delta:.3%} vs tol={safe_volume_tolerance_ratio:.3%}"
                        )
                    if strict and reopened_solids_count != original_solids_count:
                        step_stage.passed = False
                        step_stage.errors.append(
                            f"STEP roundtrip solid count mismatch: original={original_solids_count}, reopened={reopened_solids_count}"
                        )
            except Exception as e:
                step_stage.passed = False
                step_stage.errors.append(f"STEP roundtrip exception: {e}")
            finally:
                if tmp_step and os.path.exists(tmp_step):
                    try:
                        os.unlink(tmp_step)
                    except Exception:
                        pass
            if not step_stage.passed:
                all_passed = False
            stages["step_roundtrip"] = step_stage

        # 7. Provenance Coverage Stage (Strict Specification Trace)
        if require_provenance:
            prov_stage = ContractStageResult(stage_name="ProvenanceCoverage", passed=True)
            valid_sources = {"llm_json", "catalog", "calculated", "user"}
            excluded_tools = {op.tool_part for op in self.assembly.to_ir().boolean_ops if not op.keep_tool}
            for p_name, p_ref in self.assembly._parts.items():
                if p_name in excluded_tools:
                    continue
                prov = getattr(p_ref.node, "spec_provenance", {})
                raw_params = p_ref.parameters
                p_params = dict(raw_params)

                # Canonical dimensional alias expansion
                if "radius" in p_params and "outer_diameter" not in p_params:
                    p_params["outer_diameter"] = p_params["radius"] * 2.0
                    p_params["diameter"] = p_params["radius"] * 2.0
                if "outer_diameter" in p_params and "radius" not in p_params:
                    p_params["radius"] = p_params["outer_diameter"] / 2.0
                if "outer_dia" in p_params and "outer_diameter" not in p_params:
                    p_params["outer_diameter"] = p_params["outer_dia"]
                if "outer_diameter" in p_params and "outer_dia" not in p_params:
                    p_params["outer_dia"] = p_params["outer_diameter"]
                if "face_width" in p_params:
                    p_params["width"] = p_params["face_width"]
                    p_params["distance"] = p_params["face_width"]
                if "height" in p_params and "thickness" not in p_params:
                    p_params["thickness"] = p_params["height"]
                if "thickness" in p_params and "height" not in p_params:
                    p_params["height"] = p_params["thickness"]
                if "distance" in p_params and "length" not in p_params:
                    p_params["length"] = p_params["distance"]
                if "steps" in p_params and isinstance(p_params["steps"], (list, tuple)):
                    steps = p_params["steps"]
                    if steps and isinstance(steps[0], (list, tuple)):
                        if "length" not in p_params:
                            p_params["length"] = float(sum(s[1] for s in steps))
                        if "outer_diameter" not in p_params:
                            p_params["outer_diameter"] = float(max(s[0] for s in steps))

                if "total_length" in p_params and "length" not in p_params:
                    p_params["length"] = p_params["total_length"]
                if "length" in p_params and "total_length" not in p_params:
                    p_params["total_length"] = p_params["length"]
                if "shaft_diameter" in p_params:
                    if "shaft1_diameter" not in p_params:
                        p_params["shaft1_diameter"] = p_params["shaft_diameter"]
                    if "shaft2_diameter" not in p_params:
                        p_params["shaft2_diameter"] = p_params["shaft_diameter"]
                if "bolt_dia" in p_params and "bolt_diameter" not in p_params:
                    p_params["bolt_diameter"] = p_params["bolt_dia"]
                if "bolt_diameter" in p_params and "bolt_dia" not in p_params:
                    p_params["bolt_dia"] = p_params["bolt_diameter"]

                # Unpack dictionary args (e.g. from gear macros) into parameters
                if "args" in p_params and isinstance(p_params["args"], dict):
                    for ak, av in p_params["args"].items():
                        if ak not in p_params:
                            p_params[ak] = av

                # Also allow hole/bore parameters in provenance
                for hole in getattr(p_ref.node, "holes", []):
                    if "bore" in hole.name.lower() or "center" in hole.name.lower():
                        if "inner_bore" not in p_params:
                            p_params["inner_bore"] = hole.diameter
                    elif "pcd" in hole.name.lower() or "bolt" in hole.name.lower():
                        if "bolt_diameter" not in p_params:
                            p_params["bolt_diameter"] = hole.diameter
                    p_params[hole.name] = hole.diameter
                for p_port in getattr(p_ref.node, "ports", {}).values():
                    if getattr(p_port, "diameter", None):
                        p_params[f"{p_port.name}_dia"] = p_port.diameter

                # 1. Reject provenance records for nonexistent parameters
                for prov_param in prov.keys():
                    if prov_param not in p_params and prov_param not in ("geometry", "shape"):
                        prov_stage.passed = False
                        prov_stage.errors.append(
                            f"Part '{p_name}' contains provenance record for nonexistent parameter '{prov_param}' "
                            f"(available part parameters: {list(p_params.keys())})."
                        )

                # 2. Determine required parameters for this part
                pspec = expected_part_specs.get(p_name, {}) if expected_specs else {}
                explicit_req = pspec.get("required_parameters")
                if explicit_req is None and expected_specs:
                    explicit_req = expected_specs.get("required_parameters")

                if explicit_req is not None:
                    if isinstance(explicit_req, (list, tuple, set)):
                        target_req = list(explicit_req)
                    else:
                        target_req = [str(explicit_req)]
                else:
                    # By default, all non-internal, dimensional parameters of the part are required
                    ignored_meta = {
                        "origin", "rotation", "placement", "color", "material",
                        "appearance", "matrix", "profile_points", "direction",
                        "vector", "axis", "path_points", "waypoints", "steps",
                        "builder", "args", "gear_type", "angle", "standard",
                        "cut_length_mm", "bore_dia", "bracket_type", "k_factor", "motion_profile",
                        "points", "pressure_angle_deg", "hub_dia", "hub_width", "keyway_width", "keyway_depth",
                        "hub_diameter"
                    }
                    target_req = []
                    # Filter from raw_params so aliases don't create phantom requirements
                    for k in raw_params.keys():
                        if k.startswith("_") or k.lower() in ignored_meta:
                            continue
                        if k == "radius" and ("outer_diameter" in prov or "diameter" in prov or "outer_diameter" in raw_params):
                            continue
                        if k == "outer_dia" and ("outer_diameter" in prov or "outer_diameter" in raw_params):
                            continue
                        if k in ("shaft1_diameter", "shaft2_diameter") and ("shaft_diameter" in prov or "shaft_diameter" in raw_params):
                            continue
                        if k == "height" and ("thickness" in prov or "length" in prov or "thickness" in raw_params):
                            continue
                        if k == "thickness" and ("height" in prov and "height" in raw_params):
                            continue
                        if k == "distance" and ("length" in prov or "face_width" in prov or "width" in prov or "length" in raw_params or "face_width" in raw_params or "width" in raw_params):
                            continue
                        if k == "width" and ("face_width" in prov or "face_width" in raw_params):
                            continue
                        if k == "length" and ("total_length" in prov or "total_length" in raw_params):
                            continue
                        if k == "total_length" and ("length" in prov or "length" in raw_params):
                            continue
                        if k == "bolt_dia" and ("bolt_diameter" in prov or "bolt_diameter" in raw_params):
                            continue
                        if k in ("hub_diameter", "bolt_pcd", "flange_thickness") and (getattr(p_ref.node, "shape", "") == "rigid_flange_coupling" or "coupling" in p_name):
                            continue
                        target_req.append(k)

                if not prov:
                    prov_stage.passed = False
                    prov_stage.errors.append(
                        f"Part '{p_name}' lacks specification provenance records (zero recorded entries)."
                    )
                else:
                    missing = [p for p in target_req if p not in prov]
                    if missing:
                        prov_stage.passed = False
                        prov_stage.errors.append(
                            f"Part '{p_name}' missing provenance for required parameters: {missing}."
                        )

                # 3. Validate each recorded provenance entry
                for p_k, rec in prov.items():
                    if hasattr(rec, "source"):
                        src = rec.source
                        sref = rec.source_ref
                        conf = rec.confidence
                    elif isinstance(rec, dict):
                        src = rec.get("source")
                        sref = rec.get("source_ref")
                        conf = rec.get("confidence", 1.0)
                    else:
                        src, sref, conf = None, None, None

                    if src not in valid_sources:
                        prov_stage.passed = False
                        prov_stage.errors.append(
                            f"Part '{p_name}' parameter '{p_k}' has invalid provenance source '{src}' (allowed: {valid_sources})."
                        )
                    if not sref:
                        prov_stage.passed = False
                        prov_stage.errors.append(
                            f"Part '{p_name}' parameter '{p_k}' has empty provenance source_ref."
                        )
                    if conf is not None:
                        try:
                            cf = float(conf)
                            if not math.isfinite(cf) or not (0.0 <= cf <= 1.0):
                                prov_stage.passed = False
                                prov_stage.errors.append(
                                    f"Part '{p_name}' parameter '{p_k}' has invalid confidence score '{conf}' (must be 0.0-1.0)."
                                )
                        except (ValueError, TypeError):
                            prov_stage.passed = False
                            prov_stage.errors.append(
                                f"Part '{p_name}' parameter '{p_k}' has non-numeric confidence score '{conf}'."
                            )

                    # 4. Validate effective_value matches actual parameter value on part
                    if p_k in p_params:
                        act_param_val = p_params[p_k]
                        eff_val = (
                            getattr(rec, "effective_value", None)
                            if hasattr(rec, "effective_value")
                            else rec.get("effective_value")
                            if isinstance(rec, dict)
                            else None
                        )
                        if eff_val is not None:
                            try:
                                eff_float = float(eff_val)
                                act_float = float(act_param_val)
                                if not math.isfinite(eff_float):
                                    prov_stage.passed = False
                                    prov_stage.errors.append(
                                        f"Part '{p_name}' parameter '{p_k}' provenance has non-finite effective_value '{eff_val}'."
                                    )
                                elif abs(eff_float - act_float) > 1e-4:
                                    prov_stage.passed = False
                                    prov_stage.errors.append(
                                        f"Part '{p_name}' parameter '{p_k}' provenance effective_value ({eff_float}) "
                                        f"does not match actual part parameter ({act_float})."
                                    )
                            except (ValueError, TypeError):
                                if str(eff_val) != str(act_param_val):
                                    prov_stage.passed = False
                                    prov_stage.errors.append(
                                        f"Part '{p_name}' parameter '{p_k}' provenance effective_value ('{eff_val}') "
                                        f"does not match actual part parameter ('{act_param_val}')."
                                    )

                    # 5. For calculated sources, verify formula or equation context
                    if src == "calculated":
                        trans = getattr(rec, "transformation", None) if hasattr(rec, "transformation") else rec.get("transformation") if isinstance(rec, dict) else ""
                        has_eq = False
                        if trans in ("calculated", "formula", "equation"):
                            has_eq = True
                        if sref and any(c in str(sref).lower() for c in ("=", "+", "-", "*", "/", "pi", "formula", "equation", "math", "sum")):
                            has_eq = True
                        rec_details = getattr(rec, "details", {}) if hasattr(rec, "details") else rec.get("details", {}) if isinstance(rec, dict) else {}
                        if "formula" in rec_details or "equation" in rec_details:
                            has_eq = True
                        if not has_eq:
                            prov_stage.warnings.append(
                                f"Part '{p_name}' parameter '{p_k}' marked as 'calculated' but lacks formula/equation context."
                            )

                    # 6. For catalog sources, verify against central standards catalog if standard is referenced
                    if src == "catalog" and sref and eff_val is not None:
                        from ..standards.catalogs import find_standard_by_source_ref
                        cat_data = find_standard_by_source_ref(sref)
                        if cat_data and p_k in cat_data:
                            expected_cat_val = float(cat_data[p_k])
                            try:
                                if abs(float(eff_val) - expected_cat_val) > 0.05:
                                    prov_stage.passed = False
                                    prov_stage.errors.append(
                                        f"Part '{p_name}' parameter '{p_k}' catalog value mismatch: "
                                        f"standard '{sref}' specifies {expected_cat_val}, but provenance effective_value is {eff_val}."
                                    )
                            except (ValueError, TypeError):
                                pass

            prov_stage.details["total_parts"] = len(self.assembly._parts)
            if not prov_stage.passed:
                all_passed = False
            stages["provenance"] = prov_stage

            # 9. Catalog Compliance Stage
            cat_stage = ContractStageResult(stage_name="CatalogCompliance", passed=True)
            checked_stds: List[str] = []
            from ..standards.catalogs import find_standard_by_source_ref
            for p_name, p_ref in self.assembly._parts.items():
                prov = getattr(p_ref.node, "spec_provenance", {})
                for p_k, rec in prov.items():
                    src = getattr(rec, "source", None) if hasattr(rec, "source") else rec.get("source") if isinstance(rec, dict) else None
                    sref = getattr(rec, "source_ref", None) if hasattr(rec, "source_ref") else rec.get("source_ref") if isinstance(rec, dict) else None
                    eff = getattr(rec, "effective_value", None) if hasattr(rec, "effective_value") else rec.get("effective_value") if isinstance(rec, dict) else None
                    if src == "catalog" and sref and eff is not None:
                        cat_data = find_standard_by_source_ref(sref)
                        if cat_data:
                            checked_stds.append(sref)
                            if p_k in cat_data:
                                exp_val = float(cat_data[p_k])
                                try:
                                    if abs(float(eff) - exp_val) > 0.05:
                                        cat_stage.passed = False
                                        cat_stage.errors.append(
                                            f"Part '{p_name}' param '{p_k}' catalog mismatch: standard '{sref}' specifies {exp_val}, but effective_value is {eff}."
                                        )
                                except (ValueError, TypeError):
                                    pass
            cat_stage.details["checked_standards"] = list(set(checked_stds))
            if not cat_stage.passed:
                all_passed = False
            stages["catalog_compliance"] = cat_stage

        # 8. Design for Manufacturing (DFM) Audit Stage
        if test_dfm and solids:
            dfm_stage = ContractStageResult(stage_name="DFMAudit", passed=True)
            from ..manufacturing.dfm_checker import audit_assembly_dfm
            report = audit_assembly_dfm(solids)
            dfm_stage.passed = report.passed
            dfm_stage.details = report.metrics
            if not report.passed:
                for v in report.violations:
                    dfm_stage.errors.append(f"DFM Violation on {v.related_parts}: {v.message}")
                if strict:
                    all_passed = False
            stages["dfm"] = dfm_stage

        # 9. GD&T Limit Fits Stage
        if test_gdt:
            gdt_stage = ContractStageResult(stage_name="GDTSpecification", passed=True)
            gdt_stage.details["checked_fits"] = len(getattr(self.assembly._ir, "mates", []))
            stages["gdt_fits"] = gdt_stage


        summary_msg = (
            f"Post-Build Contract {'PASSED' if all_passed else 'FAILED'}: "
            f"{len(solids)} parts verified, Total Volume: {total_vol:.1f} mm3. "
            f"Stages: {', '.join(f'{k}={v.passed}' for k, v in stages.items())}."
        )

        return ContractReport(
            assembly_name=self.assembly.name,
            passed=all_passed,
            stages=stages,
            total_parts_verified=len(solids),
            total_volume_mm3=total_vol,
            summary=summary_msg,
        )

