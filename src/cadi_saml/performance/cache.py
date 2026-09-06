"""
High-Performance Incremental Compilation Cache and Spatial BVH Index for CADI-SAML.
Accelerates large assemblies (100+ components) through content-addressable shape caching
and O(N log N) broad-phase spatial collision indexing.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib
import json

try:
    import OCP.Bnd as Bnd
    import OCP.BRepBndLib as BRepBndLib
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


class ShapeCache:
    """
    In-memory content-addressable cache for compiled OpenCASCADE TopoDS_Shape solids.
    Key is SHA-256 hash of canonical part parameters and geometry node configuration.
    """

    _cache: Dict[str, Any] = {}
    _hits: int = 0
    _misses: int = 0

    @classmethod
    def compute_hash(cls, part_type: str, parameters: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 fingerprint for a parametric part definition."""
        payload = {
            "type": part_type,
            "params": {k: parameters[k] for k in sorted(parameters.keys()) if not k.startswith("_")},
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        if key in cls._cache:
            cls._hits += 1
            return cls._cache[key]
        cls._misses += 1
        return None

    @classmethod
    def put(cls, key: str, shape: Any) -> None:
        cls._cache[key] = shape

    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()
        cls._hits = 0
        cls._misses = 0

    @classmethod
    def stats(cls) -> Dict[str, Any]:
        return {
            "cached_shapes": len(cls._cache),
            "hits": cls._hits,
            "misses": cls._misses,
            "hit_ratio": round(cls._hits / max(1, cls._hits + cls._misses), 3),
        }


class AABB:
    """3D Axis-Aligned Bounding Box for fast broad-phase collision detection."""

    def __init__(self, xmin: float, ymin: float, zmin: float, xmax: float, ymax: float, zmax: float, tag: str = ""):
        self.xmin = xmin
        self.ymin = ymin
        self.zmin = zmin
        self.xmax = xmax
        self.ymax = ymax
        self.zmax = zmax
        self.tag = tag

    def intersects(self, other: "AABB", tolerance: float = 0.0) -> bool:
        """Determines if two AABB volumes overlap in 3D space."""
        return (
            (self.xmin - tolerance <= other.xmax)
            and (self.xmax + tolerance >= other.xmin)
            and (self.ymin - tolerance <= other.ymax)
            and (self.ymax + tolerance >= other.ymin)
            and (self.zmin - tolerance <= other.zmax)
            and (self.zmax + tolerance >= other.zmin)
        )


class SpatialIndex:
    """
    Broad-phase spatial collision index using Axis-Aligned Bounding Boxes.
    Filters candidate collision pairs before performing expensive exact B-Rep boolean cuts.
    """

    def __init__(self):
        self.boxes: List[AABB] = []

    def insert_shape(self, name: str, shape: Any) -> None:
        if not HAS_OCP or shape is None or shape.IsNull():
            return
        bbox = Bnd.Bnd_Box()
        BRepBndLib.BRepBndLib.Add_s(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        self.boxes.append(AABB(xmin, ymin, zmin, xmax, ymax, zmax, tag=name))

    def find_potential_clashes(self, tolerance_mm: float = 0.0) -> List[Tuple[str, str]]:
        """Finds all candidate overlapping pairs using O(N log N) sweep-and-prune."""
        candidates = []
        n = len(self.boxes)
        # Sort along X axis
        sorted_boxes = sorted(self.boxes, key=lambda b: b.xmin)

        for i in range(n):
            b1 = sorted_boxes[i]
            for j in range(i + 1, n):
                b2 = sorted_boxes[j]
                # If next box's min-X exceeds current box's max-X, no further boxes can overlap
                if b2.xmin > b1.xmax + tolerance_mm:
                    break
                if b1.intersects(b2, tolerance_mm):
                    candidates.append((b1.tag, b2.tag))

        return candidates
