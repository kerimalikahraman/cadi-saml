"""
cadi_saml.core.bom
==================
Automated Bill of Materials (BOM) extraction, standard hardware classification,
mass breakdown, and multi-format export (Markdown, CSV, JSON, HTML).
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .assembly import Assembly


@dataclass
class BOMItem:
    """Represents a single line-item in the engineering Bill of Materials."""
    item_no: int
    name: str
    category: str
    quantity: int
    material: str
    unit_mass_kg: float
    total_mass_kg: float
    unit_volume_mm3: float
    standard_code: str = "-"
    supplier_type: str = "Manufactured"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BOMReport:
    """Comprehensive Bill of Materials report for an assembly."""
    assembly_name: str
    units: str
    items: List[BOMItem] = field(default_factory=list)
    total_parts_count: int = 0
    unique_parts_count: int = 0
    total_mass_kg: float = 0.0
    total_volume_mm3: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assembly_name": self.assembly_name,
            "units": self.units,
            "total_parts_count": self.total_parts_count,
            "unique_parts_count": self.unique_parts_count,
            "total_mass_kg": round(self.total_mass_kg, 4),
            "total_volume_mm3": round(self.total_volume_mm3, 2),
            "items": [item.to_dict() for item in self.items],
        }

    def to_markdown(self) -> str:
        """Renders BOM as a GitHub-flavored Markdown table with totals."""
        lines = [
            f"# Bill of Materials: {self.assembly_name}",
            "",
            f"**Total Mass:** `{self.total_mass_kg:.3f} kg` | **Total Parts:** `{self.total_parts_count}` (Unique: `{self.unique_parts_count}`) | **Units:** `{self.units}`",
            "",
            "| Item | Name / Description | Standard / Code | Category | Qty | Material | Unit Mass (kg) | Total Mass (kg) |",
            "|:----:|:-------------------|:---------------:|:--------:|:---:|:--------:|:--------------:|:---------------:|",
        ]
        for it in self.items:
            std = it.standard_code if it.standard_code else "-"
            lines.append(
                f"| {it.item_no} | {it.name} | {std} | {it.category} | {it.quantity} | {it.material} | {it.unit_mass_kg:.4f} | {it.total_mass_kg:.4f} |"
            )
        lines.append(
            f"| **Total** | | | | **{self.total_parts_count}** | | | **{self.total_mass_kg:.4f} kg** |"
        )
        return "\n".join(lines)

    def to_csv(self, filepath: Optional[str] = None) -> str:
        """Exports BOM to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Item No", "Part Name", "Standard Code", "Category", "Quantity",
            "Material", "Unit Mass (kg)", "Total Mass (kg)", "Unit Volume (mm3)",
            "Supplier Type", "Description"
        ])
        for it in self.items:
            writer.writerow([
                it.item_no, it.name, it.standard_code, it.category, it.quantity,
                it.material, f"{it.unit_mass_kg:.4f}", f"{it.total_mass_kg:.4f}",
                f"{it.unit_volume_mm3:.2f}", it.supplier_type, it.description
            ])
        csv_content = output.getvalue()
        if filepath:
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                f.write(csv_content)
        return csv_content

    def to_json(self, filepath: Optional[str] = None, indent: int = 2) -> str:
        """Exports BOM to JSON format."""
        json_str = json.dumps(self.to_dict(), indent=indent)
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)
        return json_str

    def to_html(self, filepath: Optional[str] = None) -> str:
        """Renders an interactive, styled modern HTML Bill of Materials page."""
        rows = []
        for it in self.items:
            cat_badge = f'<span class="badge badge-{it.category.lower()}">{it.category}</span>'
            rows.append(f"""
            <tr>
              <td style="text-align:center; font-weight:600;">{it.item_no}</td>
              <td><strong>{it.name}</strong><br><small style="color:#64748b;">{it.description}</small></td>
              <td style="font-family:monospace; font-weight:600; color:#0f172a;">{it.standard_code}</td>
              <td>{cat_badge}</td>
              <td style="text-align:center; font-weight:700;">{it.quantity}</td>
              <td>{it.material}</td>
              <td style="text-align:right;">{it.unit_mass_kg:.4f}</td>
              <td style="text-align:right; font-weight:600;">{it.total_mass_kg:.4f}</td>
            </tr>
            """)
        table_rows_html = "\n".join(rows)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BOM — {self.assembly_name}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 30px auto;
      max-width: 1200px;
      color: #1e293b;
      background-color: #f8fafc;
      padding: 0 20px;
    }}
    .header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #ffffff;
      padding: 24px 32px;
      border-radius: 12px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
    }}
    .header h1 {{ margin: 0 0 8px 0; font-size: 26px; font-weight: 700; }}
    .stats-bar {{
      display: flex; gap: 20px; flex-wrap: wrap; margin-top: 14px;
    }}
    .stat-item {{
      background: rgba(255,255,255,0.12); padding: 8px 16px; border-radius: 8px; font-size: 14px;
    }}
    .stat-item strong {{ color: #38bdf8; }}
    table {{
      width: 100%; border-collapse: collapse; background: #ffffff;
      border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    th {{
      background: #f1f5f9; color: #475569; font-size: 13px; text-transform: uppercase;
      letter-spacing: 0.05em; padding: 12px 16px; text-align: left; border-bottom: 2px solid #e2e8f0;
    }}
    td {{
      padding: 12px 16px; border-bottom: 1px solid #e2e8f0; font-size: 14px;
    }}
    tr:hover {{ background-color: #f8fafc; }}
    .badge {{
      display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 600;
    }}
    .badge-fastener {{ background: #e0e7ff; color: #3730a3; }}
    .badge-bearing {{ background: #fef3c7; color: #92400e; }}
    .badge-transmission {{ background: #dcfce7; color: #166534; }}
    .badge-structural {{ background: #e2e8f0; color: #334155; }}
    .badge-seal {{ background: #fce7f3; color: #9d174d; }}
    .badge-coupling {{ background: #cffafe; color: #155e75; }}
    .badge-manufactured {{ background: #f1f5f9; color: #475569; }}
    tfoot td {{
      font-weight: 700; background: #f8fafc; border-top: 2px solid #cbd5e1;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Bill of Materials: {self.assembly_name}</h1>
    <div class="stats-bar">
      <div class="stat-item">Total Mass: <strong>{self.total_mass_kg:.3f} kg</strong></div>
      <div class="stat-item">Total Parts: <strong>{self.total_parts_count}</strong></div>
      <div class="stat-item">Unique Components: <strong>{self.unique_parts_count}</strong></div>
      <div class="stat-item">Total Volume: <strong>{self.total_volume_mm3 / 1000.0:.2f} cm³</strong></div>
      <div class="stat-item">Units: <strong>{self.units}</strong></div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="text-align:center;">#</th>
        <th>Part Name</th>
        <th>Standard Code</th>
        <th>Category</th>
        <th style="text-align:center;">Qty</th>
        <th>Material</th>
        <th style="text-align:right;">Unit Mass (kg)</th>
        <th style="text-align:right;">Total Mass (kg)</th>
      </tr>
    </thead>
    <tbody>
      {table_rows_html}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="4" style="text-align:right;">Total Assembly:</td>
        <td style="text-align:center;">{self.total_parts_count}</td>
        <td></td>
        <td></td>
        <td style="text-align:right;">{self.total_mass_kg:.4f} kg</td>
      </tr>
    </tfoot>
  </table>
</body>
</html>
"""
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
        return html


def _classify_part(name: str, part_node: Any) -> Dict[str, str]:
    """Classifies part category, standard code, and supplier type."""
    name_l = name.lower()
    meta = getattr(part_node, "metadata", {}) or {}
    params = getattr(part_node, "parameters", {}) or {}
    std_code = meta.get("standard_code") or meta.get("standard") or params.get("standard_code") or ""
    category = meta.get("category") or ""
    supplier = "Off-the-shelf" if std_code else "Manufactured"

    if not category:
        if any(k in name_l for k in ["bolt", "screw", "fastener"]):
            category = "Fastener"
            supplier = "Standard Hardware"
            if not std_code:
                m = re.search(r"m\d+(?:x\d+)?", name_l)
                if m:
                    std_code = f"ISO 4014 {m.group(0).upper()}"
                elif "size" in params:
                    std_code = f"ISO 4014 {params['size'].upper()}"
                else:
                    std_code = "ISO Fastener"
        elif "nut" in name_l:
            category = "Fastener"
            supplier = "Standard Hardware"
            if not std_code:
                m = re.search(r"m\d+", name_l)
                std_code = f"ISO 4032 {m.group(0).upper()}" if m else "ISO Nut"
        elif "washer" in name_l:
            category = "Fastener"
            supplier = "Standard Hardware"
            if not std_code:
                m = re.search(r"m\d+", name_l)
                std_code = f"ISO 7089 {m.group(0).upper()}" if m else "ISO Washer"
        elif "bearing" in name_l:
            category = "Bearing"
            supplier = "Standard Hardware"
            if not std_code:
                m = re.search(r"\b(6\d{3}|7\d{3}|3\d{4})\b", name_l)
                std_code = f"DIN 625 {m.group(0)}" if m else "Standard Ball Bearing"
        elif any(k in name_l for k in ["gear", "pinion", "sprocket", "pulley"]):
            category = "Transmission"
            std_code = std_code or "ISO Involute Gear"
        elif any(k in name_l for k in ["seal", "oring", "o_ring"]):
            category = "Seal"
            supplier = "Standard Hardware"
            std_code = std_code or "DIN 3760 / ISO 3601"
        elif "coupling" in name_l:
            category = "Coupling"
            std_code = std_code or "Shaft Coupling"
        elif any(k in name_l for k in ["motor", "stepper", "servo"]):
            category = "Actuator"
            supplier = "Off-the-shelf"
            std_code = std_code or "Motor"
        elif any(k in name_l for k in ["profile", "extrusion", "beam", "rail"]):
            category = "Structural"
            supplier = "Commercial Profile"
            std_code = std_code or "T-Slot Extrusion"
        else:
            category = "Structural"

    return {
        "category": category,
        "standard_code": std_code or "-",
        "supplier_type": supplier,
    }


def extract_assembly_bom(assembly: "Assembly") -> BOMReport:
    """
    Extracts an engineered BOMReport from an Assembly.
    Groups identical parts, accounts for linear/radial pattern instances,
    computes exact masses, and classifies components.
    """
    ir = assembly.to_ir()
    mass_props = assembly.get_mass_properties()
    parts_data = mass_props.get("parts", {})

    # Group components by base name / type to aggregate quantities
    grouped: Dict[str, Dict[str, Any]] = {}

    for solid_name, p_info in parts_data.items():
        # Strip pattern suffixes to find base component
        base_name = solid_name.split("_pattern_")[0]
        # Check if part has indexed duplicate e.g. bolt_0, bolt_1
        canonical_key = re.sub(r"_\d+$", "", base_name)

        part_node = ir.parts.get(base_name) or ir.parts.get(canonical_key)
        cls_info = _classify_part(base_name, part_node)

        material = p_info.get("material", "Al6061")
        vol_mm3 = p_info.get("volume_mm3", 0.0)
        mass_kg = p_info.get("mass_kg", 0.0)

        group_key = f"{canonical_key}_{material}_{cls_info['standard_code']}"

        if group_key not in grouped:
            display_name = canonical_key.replace("_", " ").title()
            grouped[group_key] = {
                "name": display_name,
                "category": cls_info["category"],
                "quantity": 1,
                "material": material,
                "unit_mass_kg": mass_kg,
                "total_mass_kg": mass_kg,
                "unit_volume_mm3": vol_mm3,
                "standard_code": cls_info["standard_code"],
                "supplier_type": cls_info["supplier_type"],
                "description": getattr(part_node, "description", "") or "",
            }
        else:
            grouped[group_key]["quantity"] += 1
            grouped[group_key]["total_mass_kg"] += mass_kg

    items: List[BOMItem] = []
    item_no = 1
    total_qty = 0
    total_mass = 0.0
    total_vol = 0.0

    for g in grouped.values():
        item = BOMItem(
            item_no=item_no,
            name=g["name"],
            category=g["category"],
            quantity=g["quantity"],
            material=g["material"],
            unit_mass_kg=round(g["unit_mass_kg"], 4),
            total_mass_kg=round(g["total_mass_kg"], 4),
            unit_volume_mm3=round(g["unit_volume_mm3"], 2),
            standard_code=g["standard_code"],
            supplier_type=g["supplier_type"],
            description=g["description"],
        )
        items.append(item)
        total_qty += item.quantity
        total_mass += item.total_mass_kg
        total_vol += item.unit_volume_mm3 * item.quantity
        item_no += 1

    units_val = ir.metadata.units.value if hasattr(ir.metadata.units, "value") else str(ir.metadata.units)

    return BOMReport(
        assembly_name=assembly.name,
        units=units_val,
        items=items,
        total_parts_count=total_qty,
        unique_parts_count=len(items),
        total_mass_kg=round(total_mass, 4),
        total_volume_mm3=round(total_vol, 2),
    )
