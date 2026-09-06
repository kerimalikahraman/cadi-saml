"""
cadi_saml.macros.piping_macros
==============================
Industrial 3D Piping & Tubing Route Sweep Wizard with Zero-Coordinate Semantic Ports.
- EN 10220 / DIN 2448 standard pipe schedules (DN15 - DN100)
- Zero-coordinate semantic connection: from_port='pump:outlet', to_port='tank:inlet'
- Automatic orthogonal and tangent bend routing generator
- Automatic developed centerline cut length and port attachment
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from ..core.exceptions import CADISpecificationError

if TYPE_CHECKING:
    from ..core.assembly import Assembly, PartReference


@dataclass(frozen=True)
class PipeStandardSpec:
    nominal_size: str
    outer_dia: float
    wall_thickness: float
    default_bend_radius: float


from ..standards.catalogs import ISO_4200_PIPING

# EN 10220 / DIN 2448 Seamless Steel Tube Standards (sourced from central catalogs)
PIPE_SCHEDULES: Dict[str, PipeStandardSpec] = {
    des: PipeStandardSpec(
        nominal_size=des,
        outer_dia=spec["outer_diameter"],
        wall_thickness=spec["wall_thickness"],
        default_bend_radius=spec["bend_radius"],
    )
    for des, spec in ISO_4200_PIPING.items()
    if des.startswith("DN")
}



def _resolve_port_pos_and_normal(
    assembly: "Assembly",
    port_spec: Union[str, Tuple[str, str], Tuple[float, float, float], List[float]],
    default_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Resolves a semantic port or part reference to world 3D position and normal.
    Supports:
      - (x, y, z) coordinates
      - 'part_name:port_name'
      - ('part_name', 'port_name')
      - 'part_name:top' or 'part_name:face:top'
      - 'part_name' (snaps to top face center)
    """
    # 1. Direct coordinate tuple or list
    if isinstance(port_spec, (list, tuple)) and len(port_spec) == 3 and all(isinstance(v, (int, float)) for v in port_spec):
        return (float(port_spec[0]), float(port_spec[1]), float(port_spec[2])), default_normal

    # 2. Tuple of (part_name, port_name)
    part_name = ""
    selector = ""
    if isinstance(port_spec, tuple) and len(port_spec) == 2:
        part_name, selector = str(port_spec[0]), str(port_spec[1])
    elif isinstance(port_spec, str):
        if ":" in port_spec:
            parts = port_spec.split(":", 1)
            part_name, selector = parts[0], parts[1]
        else:
            part_name = port_spec
            selector = "top"
    else:
        raise ValueError(f"Invalid port specification: {port_spec}")

    if part_name not in assembly._parts:
        raise CADISpecificationError(
            parameter_name="port_specification",
            provided_value=part_name,
            valid_options=list(assembly._parts.keys()),
            suggested_fix=f"Part '{part_name}' does not exist in assembly. Check spelling or register part first.",
        )

    part_ref = assembly._parts[part_name]
    origin = part_ref.parameters.get("origin", (0.0, 0.0, 0.0))

    # Check registered ports on part
    clean_selector = selector.replace("face:", "").replace("port:", "")
    for p in part_ref.ports.values() if isinstance(part_ref.ports, dict) else part_ref.ports:
        p_name = p.name if hasattr(p, "name") else str(p)
        if p_name.lower() == clean_selector.lower():
            # Found matching port
            pos = p.position if hasattr(p, "position") and p.position else getattr(p, "relative_position", (0.0, 0.0, 0.0))
            norm = p.normal if hasattr(p, "normal") and p.normal else default_normal
            world_pos = (origin[0] + pos[0], origin[1] + pos[1], origin[2] + pos[2])
            part_ref.track_provenance(
                parameter=f"port_{p_name}",
                source="calculated",
                source_ref=f"registered_port:{p_name}",
                effective_value=world_pos,
                transformation="exact",
                confidence=1.0,
            )
            return world_pos, norm

    # If selector is face or generic
    # Box parameters: length, width, height
    l = float(part_ref.parameters.get("length", 0.0))
    w = float(part_ref.parameters.get("width", 0.0))
    h = float(part_ref.parameters.get("height", 0.0))
    # Cylinder parameters: radius, height
    r = float(part_ref.parameters.get("radius", 0.0))
    if r > 0.0 and h > 0.0:
        if clean_selector in ("top", "+z"):
            pos = (origin[0], origin[1], origin[2] + h)
            part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:top", effective_value=pos)
            return pos, (0.0, 0.0, 1.0)
        elif clean_selector in ("bottom", "-z"):
            pos = (origin[0], origin[1], origin[2])
            part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:bottom", effective_value=pos)
            return pos, (0.0, 0.0, -1.0)
        elif clean_selector in ("side", "+x"):
            pos = (origin[0] + r, origin[1], origin[2] + h / 2.0)
            part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:side", effective_value=pos)
            return pos, (1.0, 0.0, 0.0)

    if clean_selector in ("top", "+z"):
        pos = (origin[0], origin[1], origin[2] + h / 2.0)
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:top", effective_value=pos)
        return pos, (0.0, 0.0, 1.0)
    elif clean_selector in ("bottom", "-z"):
        pos = (origin[0], origin[1], origin[2] - h / 2.0)
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:bottom", effective_value=pos)
        return pos, (0.0, 0.0, -1.0)
    elif clean_selector in ("right", "+x"):
        pos = (origin[0] + l / 2.0, origin[1], origin[2])
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:right", effective_value=pos)
        return pos, (1.0, 0.0, 0.0)
    elif clean_selector in ("left", "-x"):
        pos = (origin[0] - l / 2.0, origin[1], origin[2])
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:left", effective_value=pos)
        return pos, (-1.0, 0.0, 0.0)
    elif clean_selector in ("back", "+y"):
        pos = (origin[0], origin[1] + w / 2.0, origin[2])
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:back", effective_value=pos)
        return pos, (0.0, 1.0, 0.0)
    elif clean_selector in ("front", "-y"):
        pos = (origin[0], origin[1] - w / 2.0, origin[2])
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:front", effective_value=pos)
        return pos, (0.0, -1.0, 0.0)
    elif clean_selector in ("center", "centroid"):
        pos = (origin[0], origin[1], origin[2] + h / 2.0) if h > 0.0 else origin
        part_ref.track_provenance(f"face_{clean_selector}", "calculated", f"{part_name}:center", effective_value=pos)
        return pos, default_normal

    valid_faces = ["top", "+z", "bottom", "-z", "right", "+x", "left", "-x", "back", "+y", "front", "-y", "center"]
    if r > 0.0 and h > 0.0:
        valid_faces.append("side")
    ports_list = list(part_ref.ports.keys()) if isinstance(part_ref.ports, dict) else [p.name for p in part_ref.ports]
    raise CADISpecificationError(
        parameter_name="port_selector",
        provided_value=selector,
        valid_options=valid_faces + ports_list,
        suggested_fix=f"Unknown port or face selector '{selector}' on part '{part_name}'. Use a valid semantic face alias or register a port.",
    )


def add_pipe_route(
    assembly: "Assembly",
    name: str,
    from_port: Optional[Union[str, Tuple[str, str], Tuple[float, float, float], List[float]]] = None,
    to_port: Optional[Union[str, Tuple[str, str], Tuple[float, float, float], List[float]]] = None,
    standard: Optional[str] = None,
    outer_dia: Optional[float] = None,
    outer_diameter: Optional[float] = None,
    wall_thickness: Optional[float] = None,
    bend_radius: Optional[float] = None,
    waypoints: Optional[List[Tuple[float, float, float]]] = None,
    color: Tuple[float, float, float] = (0.2, 0.6, 0.85),
    material: str = "StainlessSteel316",
) -> Dict[str, Any]:
    """
    Creates a complete 3D swept pipe or tubing route with Zero-Coordinate Semantic Ports.
    
    Parameters:
    -----------
    assembly: Assembly instance to add the pipe to.
    name: Unique name for the pipe part.
    from_port: Source port or part name (e.g. 'pump:outlet', ('pump', 'outlet'), or coordinate).
    to_port: Destination port or part name (e.g. 'tank:inlet', ('tank', 'inlet'), or coordinate).
    standard: Standard pipe schedule size (e.g. 'DN15', 'DN25', 'DN50'). Overrides OD/wall.
    outer_dia: Custom pipe outer diameter in mm.
    wall_thickness: Custom pipe wall thickness in mm.
    bend_radius: Minimum centerline bend radius for elbows in mm.
    waypoints: Optional explicit intermediate 3D routing points.
    """
    if outer_dia is None and outer_diameter is not None:
        outer_dia = outer_diameter

    # 1. Determine pipe dimensions from standard or arguments
    std_spec = None
    if standard:
        clean_std = standard.upper().strip()
        if clean_std in PIPE_SCHEDULES:
            std_spec = PIPE_SCHEDULES[clean_std]
            od = std_spec.outer_dia
            wt = std_spec.wall_thickness
            br = bend_radius if bend_radius is not None else std_spec.default_bend_radius
        else:
            raise CADISpecificationError(
                message=f"Bilinmeyen boru normu: '{standard}'.",
                parameter_name="standard",
                provided_value=standard,
                valid_options=list(PIPE_SCHEDULES.keys()),
                suggested_fix=f"EN 10220 standart boru normlarından birini seçin: {', '.join(PIPE_SCHEDULES.keys())}",
            )
    else:
        if outer_dia is None or float(outer_dia) <= 0.0:
            raise CADISpecificationError(
                message="Boru dış çapı (outer_dia) pozitif bir sayı olmalıdır veya geçerli bir 'standard' belirtilmelidir.",
                parameter_name="outer_dia",
                provided_value=outer_dia,
                suggested_fix="Örn: outer_dia=25.0 veya standard='DN25'",
            )
        od = float(outer_dia)
        wt = float(wall_thickness if wall_thickness is not None else 2.0)
        if wt <= 0.0 or wt >= od / 2.0:
            raise CADISpecificationError(
                message=f"Geçersiz et kalınlığı: {wt} mm (Dış çap: {od} mm). Et kalınlığı pozitif ve yarıçaptan küçük olmalıdır.",
                parameter_name="wall_thickness",
                provided_value=wt,
                suggested_fix=f"0.5 ile {od / 2.0 - 0.5:.1f} mm arasında bir et kalınlığı belirtin.",
            )
        br = float(bend_radius if bend_radius is not None else od * 1.5)

    # 2. Resolve start and end coordinates
    if from_port is None and waypoints:
        from_port = waypoints[0]
    if to_port is None and waypoints:
        to_port = waypoints[-1]
    p_start, n_start = _resolve_port_pos_and_normal(assembly, from_port, default_normal=(0.0, 0.0, 1.0))
    p_end, n_end = _resolve_port_pos_and_normal(assembly, to_port, default_normal=(0.0, 0.0, -1.0))

    # 3. Generate route waypoints if not explicitly given
    if waypoints is not None:
        if len(waypoints) < 2:
            raise CADISpecificationError(
                message="Boru rotası için en az 2 nokta (waypoints) gereklidir.",
                parameter_name="route_points",
                provided_value=waypoints,
                suggested_fix="Örn: waypoints=[(0,0,0), (100,0,0)]",
            )
        route_pts = [(float(p[0]), float(p[1]), float(p[2])) for p in waypoints]
    else:
        dist_start_end = math.sqrt(sum((p_end[i] - p_start[i]) ** 2 for i in range(3)))
        if dist_start_end < 1.0:
            raise CADISpecificationError(
                message=f"Boru başlangıç ve bitiş portları çakışık (mesafe {dist_start_end:.2f} mm < 1.0 mm).",
                parameter_name="route_points",
                provided_value=[p_start, p_end],
                suggested_fix="Başlangıç (from_port) ve bitiş (to_port) için farklı konumlar veya portlar belirtin.",
            )
        # Generate clean industrial orthogonal path with standoffs
        standoff = max(br, 35.0)
        # Point 1: exit from start along its normal
        s1 = (
            p_start[0] + n_start[0] * standoff,
            p_start[1] + n_start[1] * standoff,
            p_start[2] + n_start[2] * standoff,
        )
        # Point 2: entrance to end along inverse of its normal
        s2 = (
            p_end[0] - n_end[0] * standoff,
            p_end[1] - n_end[1] * standoff,
            p_end[2] - n_end[2] * standoff,
        )

        route_pts = [p_start, s1]

        # Check if bridge intermediate points are needed
        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        dz = s2[2] - s1[2]

        if abs(dx) > 1.0 and abs(dy) > 1.0:
            # Add intermediate dog-leg corner
            corner = (s2[0], s1[1], (s1[2] + s2[2]) / 2.0)
            route_pts.append(corner)
        elif abs(dx) > 1.0 or abs(dy) > 1.0 or abs(dz) > 1.0:
            mid = ((s1[0] + s2[0]) / 2.0, (s1[1] + s2[1]) / 2.0, (s1[2] + s2[2]) / 2.0)
            route_pts.append(mid)

        route_pts.append(s2)
        route_pts.append(p_end)

    # Clean consecutive duplicate points
    filtered_pts = [route_pts[0]]
    for pt in route_pts[1:]:
        dist_sq = sum((pt[i] - filtered_pts[-1][i]) ** 2 for i in range(3))
        if dist_sq > 0.25:  # at least 0.5mm apart
            filtered_pts.append(pt)

    if len(filtered_pts) < 2:
        raise CADISpecificationError(
            message=f"Geçersiz boru rotası '{name}': Başlangıç ({p_start}) ve bitiş ({p_end}) noktaları çakışık veya mesafe yetersiz.",
            parameter_name="route",
            provided_value={"from": from_port, "to": to_port},
            suggested_fix="Başlangıç ve bitiş portlarının farklı konumlarda olduğunu veya açık 'waypoints' verildiğini doğrulayın.",
        )

    # 4. Calculate total developed cut length
    cut_length = 0.0
    for i in range(len(filtered_pts) - 1):
        seg_len = math.sqrt(sum((filtered_pts[i + 1][j] - filtered_pts[i][j]) ** 2 for j in range(3)))
        cut_length += seg_len

    # 5. Add pipe part to assembly
    part_ref = assembly.add_pipe(
        name=name,
        points=filtered_pts,
        outer_dia=od,
        wall_thickness=wt,
        color=color,
        material=material,
    )

    # Tag pipe metadata
    part_ref.node.parameters["standard"] = standard or "CUSTOM"
    part_ref.node.parameters["outer_diameter"] = od
    part_ref.node.parameters["outer_dia"] = od
    part_ref.node.parameters["wall_thickness"] = wt
    part_ref.node.parameters["bend_radius"] = br
    part_ref.node.parameters["cut_length_mm"] = round(cut_length, 2)
    part_ref.node.parameters["waypoints"] = filtered_pts

    return {
        "pipe_name": name,
        "standard": standard or "CUSTOM",
        "outer_dia_mm": od,
        "wall_thickness_mm": wt,
        "bend_radius_mm": br,
        "cut_length_mm": round(cut_length, 2),
        "num_waypoints": len(filtered_pts),
        "from_port": str(from_port),
        "to_port": str(to_port),
    }
