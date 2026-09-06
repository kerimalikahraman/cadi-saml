"""
cadi_saml.core.batch
===================
Parametric variant batch sweep, automated multi-format export (STEP, STL, SVG, HTML),
and batch execution reporting.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

if TYPE_CHECKING:
    from .assembly import Assembly


@dataclass
class VariantExportResult:
    variant_name: str
    parameters: Dict[str, Any]
    status: str  # "SUCCESS" | "FAILED"
    elapsed_seconds: float
    output_files: Dict[str, str] = field(default_factory=dict)
    mass_kg: Optional[float] = None
    volume_mm3: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchReport:
    assembly_name: str
    total_variants: int
    successful_count: int
    failed_count: int
    total_elapsed_seconds: float
    output_directory: str
    variants: List[VariantExportResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assembly_name": self.assembly_name,
            "total_variants": self.total_variants,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "total_elapsed_seconds": round(self.total_elapsed_seconds, 3),
            "output_directory": self.output_directory,
            "variants": [v.to_dict() for v in self.variants],
        }

    def save_summary(self, filepath: Optional[str] = None) -> str:
        target = filepath or os.path.join(self.output_directory, "batch_summary.json")
        data = self.to_dict()
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return target


class BatchExportPipeline:
    """
    Orchestrates batch generation and multi-format compilation
    for parametric assembly variants.
    """

    @staticmethod
    def run(
        model_or_factory: Union["Assembly", Callable[[Dict[str, Any]], "Assembly"]],
        variants: List[Dict[str, Any]],
        output_dir: str = "./variants",
        formats: Optional[List[str]] = None,
        prefix: str = "var",
    ) -> BatchReport:
        """
        Executes batch export over a list of parameter sets.
        Formats supported: 'step', 'stl', 'svg', 'html' (motion).
        """
        formats = [f.lower().strip(".") for f in (formats or ["step"])]
        os.makedirs(output_dir, exist_ok=True)

        results: List[VariantExportResult] = []
        t0_total = time.time()

        from .assembly import Assembly
        from ..backend.occt_backend import OCCTBackend
        from ..validation.validation_engineer import ValidationEngineer

        val_eng = ValidationEngineer()

        for idx, var_params in enumerate(variants):
            v_name = var_params.get("name") or f"{prefix}_{idx:03d}"
            v_dir = os.path.join(output_dir, v_name)
            os.makedirs(v_dir, exist_ok=True)

            t0 = time.time()
            out_files: Dict[str, str] = {}

            try:
                # 1. Build or clone Assembly instance
                if callable(model_or_factory):
                    asm: Assembly = model_or_factory(var_params)
                else:
                    # Clone base assembly and apply parameter patch
                    proposal = model_or_factory.preview_patch(var_params)
                    val_res = proposal.validate()
                    if not val_res.get("valid", False):
                        raise ValueError(f"Invalid variant parameters: {val_res.get('errors')}")
                    # Create candidate clone
                    asm = proposal._create_candidate()

                # 2. Compile solids via OCCTBackend
                backend = OCCTBackend()
                solids = backend.compile(asm.to_ir())

                # Validate watertight solid
                for s_name, shape in solids.items():
                    val_eng.check_manifold(shape)

                # 3. Calculate mass properties
                mass_info = asm.get_mass_properties()
                total_mass = mass_info.get("total_mass_kg", 0.0)
                total_vol = mass_info.get("total_volume_mm3", 0.0)

                # 4. Multi-format export
                if "step" in formats or "stp" in formats:
                    step_path = os.path.join(v_dir, f"{v_name}.step")
                    backend.export_step(asm.to_ir(), step_path)
                    out_files["step"] = step_path

                if "stl" in formats:
                    stl_path = os.path.join(v_dir, f"{v_name}.stl")
                    backend.export_stl(asm.to_ir(), stl_path)
                    out_files["stl"] = stl_path

                if "svg" in formats:
                    svg_path = os.path.join(v_dir, f"{v_name}_drawing.svg")
                    asm.export_drawing(svg_path, title=f"VARIANT: {v_name.upper()}")
                    out_files["svg"] = svg_path

                if "html" in formats:
                    html_path = os.path.join(v_dir, f"{v_name}_motion.html")
                    asm.export_motion_html(html_path, title=f"Motion — {v_name}")
                    out_files["html"] = html_path

                results.append(
                    VariantExportResult(
                        variant_name=v_name,
                        parameters=var_params,
                        status="SUCCESS",
                        elapsed_seconds=round(time.time() - t0, 3),
                        output_files=out_files,
                        mass_kg=round(total_mass, 4),
                        volume_mm3=round(total_vol, 2),
                    )
                )

            except Exception as e:
                results.append(
                    VariantExportResult(
                        variant_name=v_name,
                        parameters=var_params,
                        status="FAILED",
                        elapsed_seconds=round(time.time() - t0, 3),
                        error_message=str(e),
                    )
                )

        total_elapsed = time.time() - t0_total
        success_cnt = sum(1 for r in results if r.status == "SUCCESS")
        fail_cnt = len(results) - success_cnt

        asm_title = (
            model_or_factory.name
            if hasattr(model_or_factory, "name")
            else "Parametric_Batch"
        )

        report = BatchReport(
            assembly_name=asm_title,
            total_variants=len(variants),
            successful_count=success_cnt,
            failed_count=fail_cnt,
            total_elapsed_seconds=total_elapsed,
            output_directory=output_dir,
            variants=results,
        )
        report.save_summary()
        return report
