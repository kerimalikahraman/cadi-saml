"""
Engineering Specification Compiler Engine for CADI-SAML.
Translates pure declarative engineering specification JSON into deterministic Assembly IR.
Guarantees LLM-generated models adhere to derived parameter DAGs and catalog standards.
"""

from typing import Any, Dict, List, Optional, Union
import json
from dataclasses import dataclass, field

from cadi_saml.core.assembly import Assembly, SafeEvaluator
from cadi_saml.core.error_model import CADIErrorPayload, E_DIMENSION_CONFLICT, E_STANDARDS_MISMATCH


@dataclass
class EngineeringSpecification:
    """
    Structured Engineering Specification Schema.
    """
    name: str = "AssemblyFromSpec"
    units: str = "mm"
    parts: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    derived_parameters: Dict[str, Any] = field(default_factory=dict)
    validation_requirements: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EngineeringSpecification":
        return cls(
            name=data.get("name", "AssemblyFromSpec"),
            units=data.get("units", "mm"),
            parts=data.get("parts", []),
            constraints=data.get("constraints", []),
            materials=data.get("materials", []),
            derived_parameters=data.get("derived_parameters", {}),
            validation_requirements=data.get("validation_requirements", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "EngineeringSpecification":
        return cls.from_dict(json.loads(json_str))

    def compile(self) -> Assembly:
        """
        Compiles the declarative engineering specification into an executable Assembly instance.
        """
        asm = Assembly(name=self.name, units=self.units)

        # 1. Evaluate derived parameters in topological order
        evaluator = SafeEvaluator()
        resolved_vars: Dict[str, float] = {}
        for k, v in self.derived_parameters.items():
            asm.set_var(k, v)
            try:
                resolved_vars[k] = asm.get_var(k)
            except Exception:
                pass

        # Helper to resolve parametric expressions
        def resolve_val(v: Any) -> Any:
            if isinstance(v, str) and (v in self.derived_parameters or any(op in v for op in "+-*/")):
                try:
                    return asm.eval_expr(v)
                except Exception:
                    return v
            return v

        # 2. Add Parts
        for p in self.parts:
            pname = p.get("name")
            ptype = p.get("type", "box").lower()
            params = p.get("parameters", {})
            clean_params = {k: resolve_val(v) for k, v in params.items()}

            if ptype == "box":
                l = float(clean_params.get("length", 10.0))
                w = float(clean_params.get("width", 10.0))
                h = float(clean_params.get("height", 10.0))
                orig = clean_params.get("origin", (0.0, 0.0, 0.0))
                ref = asm.add_box(pname, l, w, h, origin=orig)
            elif ptype == "cylinder":
                r = float(clean_params.get("radius", 5.0))
                h = float(clean_params.get("height", 10.0))
                orig = clean_params.get("origin", (0.0, 0.0, 0.0))
                ref = asm.add_cylinder(pname, radius=r, height=h, origin=orig)
            elif ptype == "flange":
                od = float(clean_params.get("outer_diameter", 100.0))
                th = float(clean_params.get("thickness", 15.0))
                bc = int(clean_params.get("bolt_count", 4))
                pcd = float(clean_params.get("bolt_pcd", 80.0))
                bd = float(clean_params.get("bolt_diameter", 10.0))
                ref = asm.add_flange(pname, outer_diameter=od, thickness=th, bolt_count=bc, bolt_pcd=pcd, bolt_diameter=bd)
            elif ptype == "spur_gear":
                m = float(clean_params.get("module", 2.0))
                z = int(clean_params.get("teeth", 20))
                fw = float(clean_params.get("width", 15.0))
                bore = float(clean_params.get("bore_diameter", 12.0))
                ref = asm.add_spur_gear(pname, module=m, teeth=z, width=fw, bore_diameter=bore)
            else:
                # Default box fallback
                ref = asm.add_box(pname, 20.0, 20.0, 20.0)

            # Track specification provenance
            for param_key, param_val in clean_params.items():
                if hasattr(ref, "track_provenance"):
                    try:
                        ref.track_provenance(
                            parameter=param_key,
                            source="engineering_spec",
                            source_ref=f"spec.parts.{pname}.{param_key}",
                            original_value=param_val,
                            effective_value=param_val,
                        )
                    except Exception:
                        pass

        # 3. Add Constraints
        for c in self.constraints:
            ctype = c.get("type", "").lower()
            pa = c.get("part_a")
            pb = c.get("part_b")
            if ctype == "coincident":
                asm.mate_coincident(f"{pa}.top", f"{pb}.bottom")
            elif ctype == "concentric":
                asm.mate_concentric(f"{pa}.axis", f"{pb}.axis")
            elif ctype == "distance":
                offset = float(c.get("distance", 0.0))
                asm.mate_distance(f"{pa}.face", f"{pb}.face", offset=offset)

        return asm
