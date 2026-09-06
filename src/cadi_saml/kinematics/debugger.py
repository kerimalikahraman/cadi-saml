"""
cadi_saml.kinematics.debugger
=============================
Visual and analytical constraint diagnostic engine:
- Component degree-of-freedom (DOF) accounting
- Floating (unanchored) body detection
- Unconnected semantic port audit
- Over-constrained / contradictory mate detection
- Interactive HTML traffic-light visual report
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from ..core.assembly import Assembly


@dataclass
class PartConstraintDiagnostic:
    part_name: str
    status: str  # "FULLY_CONSTRAINED" | "UNDER_CONSTRAINED" | "FLOATING" | "OVER_CONSTRAINED"
    remaining_dof: int
    free_dofs: List[str]
    mates_count: int
    connected_ports: List[str]
    unconnected_ports: List[str]
    advice: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConstraintDebugReport:
    assembly_name: str
    total_parts: int
    fully_constrained_count: int
    under_constrained_count: int
    floating_count: int
    over_constrained_count: int
    diagnostics: List[PartConstraintDiagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assembly_name": self.assembly_name,
            "total_parts": self.total_parts,
            "fully_constrained_count": self.fully_constrained_count,
            "under_constrained_count": self.under_constrained_count,
            "floating_count": self.floating_count,
            "over_constrained_count": self.over_constrained_count,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Constraint & Kinematics Diagnostics: {self.assembly_name}",
            "",
            f"- **Fully Constrained:** `{self.fully_constrained_count}`",
            f"- **Under Constrained:** `{self.under_constrained_count}`",
            f"- **Floating / Unanchored:** `{self.floating_count}`",
            f"- **Over Constrained:** `{self.over_constrained_count}`",
            "",
            "| Part Name | Status | DOF | Mates | Connected Ports | Unconnected Ports | Recommendation |",
            "|:---|:---:|:---:|:---:|:---:|:---:|:---|",
        ]
        for d in self.diagnostics:
            lines.append(
                f"| {d.part_name} | {d.status} | {d.remaining_dof} | {d.mates_count} | "
                f"{len(d.connected_ports)} | {len(d.unconnected_ports)} | {d.advice} |"
            )
        return "\n".join(lines)

    def export_html_report(self, filepath: Optional[str] = None) -> str:
        status_colors = {
            "FULLY_CONSTRAINED": ("#dcfce7", "#166534", "OK"),
            "UNDER_CONSTRAINED": ("#fef3c7", "#92400e", "UNDER"),
            "FLOATING": ("#f3e8ff", "#6b21a8", "FLOATING"),
            "OVER_CONSTRAINED": ("#fee2e2", "#991b1b", "CONFLICT"),
        }

        cards = []
        for d in self.diagnostics:
            bg, fg, tag = status_colors.get(d.status, ("#f1f5f9", "#475569", d.status))
            c_ports_html = ", ".join(d.connected_ports) if d.connected_ports else "<em>None</em>"
            u_ports_html = ", ".join(d.unconnected_ports) if d.unconnected_ports else "<em>None</em>"
            dofs_str = ", ".join(d.free_dofs) if d.free_dofs else "Rigidly Locked (0 DOF)"

            cards.append(f"""
            <div class="card" style="border-left: 6px solid {fg};">
              <div class="card-header">
                <span class="part-title">{d.part_name}</span>
                <span class="badge" style="background:{bg}; color:{fg};">{tag}: {d.status}</span>
              </div>
              <div class="card-body">
                <p><strong>Remaining DOF:</strong> <span class="dof-pill">{d.remaining_dof}</span> ({dofs_str})</p>
                <p><strong>Active Mates:</strong> {d.mates_count}</p>
                <p><strong>Connected Ports:</strong> {c_ports_html}</p>
                <p><strong>Unconnected Ports:</strong> {u_ports_html}</p>
                <div class="advice"><strong>Advice:</strong> {d.advice}</div>
              </div>
            </div>
            """)

        cards_html = "\n".join(cards)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Constraint Debugger — {self.assembly_name}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 30px auto; max-width: 1100px; color: #1e293b; background: #f8fafc; padding: 0 20px;
    }}
    .header {{
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      color: #fff; padding: 24px; border-radius: 12px; margin-bottom: 24px;
    }}
    .header h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
    .stats-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 14px; }}
    .stat-box {{
      padding: 8px 16px; border-radius: 8px; font-size: 14px; background: rgba(255,255,255,0.1);
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }}
    .card {{
      background: #fff; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.06);
      padding: 16px; display: flex; flex-direction: column; justify-content: space-between;
    }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
    .part-title {{ font-size: 16px; font-weight: 700; color: #0f172a; }}
    .badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; }}
    .card-body p {{ margin: 6px 0; font-size: 13px; color: #475569; }}
    .card-body strong {{ color: #1e293b; }}
    .dof-pill {{
      display: inline-block; background: #e2e8f0; font-weight: 700; padding: 2px 6px;
      border-radius: 4px; font-size: 12px; color: #0f172a;
    }}
    .advice {{
      margin-top: 10px; background: #f1f5f9; padding: 8px 10px; border-radius: 6px;
      font-size: 12px; color: #334155; border-left: 3px solid #64748b;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Assembly Constraint Debugger: {self.assembly_name}</h1>
    <div class="stats-row">
      <div class="stat-box">Total Parts: <strong>{self.total_parts}</strong></div>
      <div class="stat-box">Fully Constrained: <strong style="color:#4ade80;">{self.fully_constrained_count}</strong></div>
      <div class="stat-box">Under-Constrained: <strong style="color:#fde047;">{self.under_constrained_count}</strong></div>
      <div class="stat-box">Floating: <strong style="color:#c084fc;">{self.floating_count}</strong></div>
      <div class="stat-box">Over-Constrained: <strong style="color:#f87171;">{self.over_constrained_count}</strong></div>
    </div>
  </div>

  <div class="grid">
    {cards_html}
  </div>
</body>
</html>
"""
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
        return html


class ConstraintDebugger:
    """Performs constraint and degrees-of-freedom auditing on an Assembly."""

    @staticmethod
    def audit(assembly: "Assembly") -> ConstraintDebugReport:
        from ..backend.occt_backend import OCCTBackend
        from ..core.ports import ConstraintStatus

        ir = assembly.to_ir()
        backend = OCCTBackend()

        # Compile to execute the compound DOF solver
        try:
            backend.compile(ir)
            dof_reports = getattr(backend, "_dof_reports", {})
        except Exception:
            dof_reports = {}

        # Collect port usage across mates
        connected_ports_by_part: Dict[str, Set[str]] = {p: set() for p in ir.parts}
        mates_count_by_part: Dict[str, int] = {p: 0 for p in ir.parts}

        for m in ir.mates:
            if m.first_part in connected_ports_by_part:
                if m.first_selector: connected_ports_by_part[m.first_part].add(m.first_selector)
                mates_count_by_part[m.first_part] += 1
            if m.second_part in connected_ports_by_part:
                if m.second_selector: connected_ports_by_part[m.second_part].add(m.second_selector)
                mates_count_by_part[m.second_part] += 1

        diagnostics: List[PartConstraintDiagnostic] = []
        fully_cnt = 0
        under_cnt = 0
        floating_cnt = 0
        over_cnt = 0

        # Ground component is typically first component (origin)
        part_names = list(ir.parts.keys())
        ground_part = part_names[0] if part_names else None

        for p_name, p_node in ir.parts.items():
            all_ports = set(p_node.ports.keys())
            conn_ports = sorted(list(connected_ports_by_part.get(p_name, set())))
            unconn_ports = sorted(list(all_ports - set(conn_ports)))
            m_count = mates_count_by_part.get(p_name, 0)

            if p_name == ground_part:
                status = ConstraintStatus.FULLY_CONSTRAINED.value
                dof = 0
                free_dofs = []
                advice = "Base/ground reference part anchored at world coordinate system origin."
                fully_cnt += 1
            elif m_count == 0:
                status = "FLOATING"
                dof = 6
                free_dofs = ["tx", "ty", "tz", "rx", "ry", "rz"]
                advice = "Component has no mates or joints. Attach it to a mating port via mate_coaxial or mate_flush."
                floating_cnt += 1
            else:
                rep = dof_reports.get(p_name)
                if rep:
                    status = rep.get("status", ConstraintStatus.FULLY_CONSTRAINED.value)
                    dof = rep.get("remaining_dof", 0)
                    free_dofs = rep.get("free_dofs", [])
                else:
                    status = ConstraintStatus.FULLY_CONSTRAINED.value
                    dof = 0
                    free_dofs = []

                if status == ConstraintStatus.FULLY_CONSTRAINED.value:
                    advice = "Component is completely locked with 0 degrees of freedom."
                    fully_cnt += 1
                elif status == ConstraintStatus.UNDER_CONSTRAINED.value:
                    advice = f"Part has {dof} free DOF ({', '.join(free_dofs)}). Add an anti-rotation or planar mate if rigidity is desired."
                    under_cnt += 1
                elif status == ConstraintStatus.OVER_CONSTRAINED.value:
                    advice = "Contradictory constraints detected. Review mates for redundant or conflicting alignments."
                    over_cnt += 1
                else:
                    advice = "Check constraints."

            diagnostics.append(
                PartConstraintDiagnostic(
                    part_name=p_name,
                    status=status,
                    remaining_dof=dof,
                    free_dofs=free_dofs,
                    mates_count=m_count,
                    connected_ports=conn_ports,
                    unconnected_ports=unconn_ports,
                    advice=advice,
                )
            )

        return ConstraintDebugReport(
            assembly_name=assembly.name,
            total_parts=len(ir.parts),
            fully_constrained_count=fully_cnt,
            under_constrained_count=under_cnt,
            floating_count=floating_cnt,
            over_constrained_count=over_cnt,
            diagnostics=diagnostics,
        )
