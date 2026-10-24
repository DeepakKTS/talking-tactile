"""Centroids and neighbor directions, computed in code so no model ever guesses geometry.

Directions are on the page as the student holds it: up is toward the top edge (smaller y
in page mm). The direction from A to B is the direction of the shortest line from A's
outline to B's, so it is exactly opposite from B to A, and a bar under a chamber reads as
down even when its center is off to the side. A direct child is inside its parent and
the parent is around it.
"""

import itertools
import math
from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.ops import nearest_points, unary_union

from app.geometry.layout import LayoutRegion, inside_point
from app.models.regions import Direction, Neighbor

_SECTORS: tuple[Direction, ...] = (
    "right", "up_right", "up", "up_left", "left", "down_left", "down", "down_right",
)  # fmt: skip
_SECTOR_DEG = 360 / len(_SECTORS)

OPPOSITE: dict[Direction, Direction] = {
    "right": "left", "left": "right", "up": "down", "down": "up",
    "up_right": "down_left", "down_left": "up_right", "up_left": "down_right",
    "down_right": "up_left", "inside": "around", "around": "inside",
}  # fmt: skip


def direction_of(dx: float, dy: float) -> Direction:
    """One of 8 compass sectors for a page vector (y grows down the sheet)."""
    angle = math.degrees(math.atan2(-dy, dx))
    index = math.floor((angle + _SECTOR_DEG / 2) / _SECTOR_DEG) % len(_SECTORS)
    return _SECTORS[index]


def _own_area(r: LayoutRegion, regions: Sequence[LayoutRegion]) -> Polygon:
    """The part of r that no smaller region covers: where Explore says r's label, since the
    smallest region under a finger wins. Its largest piece, or all of r if nothing is left."""
    smaller = [
        x.polygon
        for x in regions
        if x.id != r.id and x.polygon.area < r.polygon.area and x.polygon.intersects(r.polygon)
    ]
    own = r.polygon.difference(unary_union(smaller)) if smaller else r.polygon
    pieces = [g for g in getattr(own, "geoms", [own]) if isinstance(g, Polygon) and not g.is_empty]
    return max(pieces, key=lambda g: g.area) if pieces else r.polygon


def centroids(
    regions: Sequence[LayoutRegion], tolerance_mm: float
) -> dict[str, tuple[float, float]]:
    """A point inside each region and off every smaller region on it: the center of the
    largest circle inscribed in what is left. A true centroid can fall outside a curved
    part, and guidance needs a target where the part's own label is spoken."""
    return {r.id: inside_point(_own_area(r, regions), tolerance_mm) for r in regions}


def _toward(a: LayoutRegion, b: LayoutRegion) -> Direction:
    pa, pb = nearest_points(a.polygon, b.polygon)
    dx, dy = pb.x - pa.x, pb.y - pa.y
    if dx == 0 and dy == 0:
        ca, cb = a.polygon.centroid, b.polygon.centroid
        dx, dy = cb.x - ca.x, cb.y - ca.y
    return direction_of(dx, dy)


def find_neighbors(regions: Sequence[LayoutRegion], max_gap_mm: float) -> dict[str, list[Neighbor]]:
    by_id = {r.id: r for r in regions}

    def ancestors(rid: str) -> set[str]:
        out: set[str] = set()
        cur = by_id[rid].parent
        while cur is not None and cur in by_id and cur not in out:
            out.add(cur)
            cur = by_id[cur].parent
        return out

    found: dict[str, list[tuple[float, str, Direction]]] = {r.id: [] for r in regions}
    for a, b in itertools.combinations(regions, 2):
        if b.parent == a.id or a.parent == b.id:
            parent, child = (a, b) if b.parent == a.id else (b, a)
            found[parent.id].append((0.0, child.id, "inside"))
            found[child.id].append((0.0, parent.id, "around"))
            continue
        if a.id in ancestors(b.id) or b.id in ancestors(a.id):
            continue  # a grandparent: the direct parent already says where it is
        gap = float(a.polygon.distance(b.polygon))
        if gap <= max_gap_mm:
            d = _toward(a, b)
            found[a.id].append((gap, b.id, d))
            found[b.id].append((gap, a.id, OPPOSITE[d]))
    return {
        rid: [Neighbor(id=nid, direction=d) for _, nid, d in sorted(items)]
        for rid, items in found.items()
    }
