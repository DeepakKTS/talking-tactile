"""S4 layout on polygons in page mm: regions from reconciled parts, point symbols for parts
below the minimum size, and gap enforcement that shrinks outlines but never moves them.
Pure functions, no I/O."""

import itertools
import math
from collections.abc import Sequence
from typing import Annotated, Any, Literal

import shapely
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import Polygon
from shapely.ops import polylabel

from app.config import Layout, Spacing, Vectorize
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.vectorize import mask_to_polygons_mm
from app.models.mask import MaskSource
from app.models.regions import MAX_POLYGON_POINTS, TextureId

RegionKind = Literal["area", "point"]
_EPS = 1e-9


class LayoutRegion(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    label: str
    polygon: Polygon
    parent: str | None = None
    kind: RegionKind = "area"
    texture: TextureId | None = None
    score: Annotated[float, Field(ge=0, le=1)]
    source: MaskSource
    part_id: str | None = None  # the reconciled part this piece came from, when it is a piece
    notes: tuple[str, ...] = ()

    @field_validator("polygon", mode="before")
    @classmethod
    def _valid_polygon(cls, value: Any) -> Polygon:
        if not isinstance(value, Polygon) or value.is_empty or not value.is_valid:
            raise ValueError("polygon must be a valid, non-empty shapely Polygon")
        return value

    @property
    def group_key(self) -> str:
        return self.part_id or self.id

    def noted(self, note: str, **update: Any) -> "LayoutRegion":
        notes = self.notes if note in self.notes else (*self.notes, note)
        return self.model_copy(update={**update, "notes": notes})


def regions_from_parts(
    parts: Sequence[ReconciledPart], fit: PageFit, rules: Vectorize
) -> list[LayoutRegion]:
    """One region per polygon piece. The largest piece keeps the part id."""
    out: list[LayoutRegion] = []
    for part in parts:
        for k, poly in enumerate(mask_to_polygons_mm(part.mask, fit, rules), start=1):
            out.append(
                LayoutRegion(
                    id=part.id if k == 1 else f"{part.id}_{k}",
                    label=part.mask.label,
                    polygon=poly,
                    parent=part.parent,
                    score=part.mask.score,
                    source=part.mask.source,
                    part_id=None if k == 1 else part.id,
                )
            )
    return out


def size_mm(poly: Polygon) -> float:
    """Longest side of the minimum rotated bounding rectangle."""
    rect = poly.minimum_rotated_rectangle
    if not isinstance(rect, Polygon):
        return 0.0
    xs, ys = rect.exterior.coords.xy
    sides = [math.dist((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(len(xs) - 1)]
    return max(sides, default=0.0)


def inside_point(poly: Polygon, tolerance_mm: float) -> tuple[float, float]:
    """A point well inside the polygon: the center of its largest inscribed circle."""
    p = polylabel(poly, tolerance=tolerance_mm)
    return (p.x, p.y)


def point_symbol(center: tuple[float, float], width_mm: float, vertices: int) -> Polygon:
    """A regular polygon at least width_mm across in every direction."""
    r = (width_mm / 2) / math.cos(math.pi / vertices)
    cx, cy = center
    return Polygon(
        [
            (
                cx + r * math.cos(2 * math.pi * i / vertices),
                cy + r * math.sin(2 * math.pi * i / vertices),
            )
            for i in range(vertices)
        ]
    )


def make_point_symbols(
    regions: Sequence[LayoutRegion], spacing: Spacing, layout: Layout
) -> list[LayoutRegion]:
    out: list[LayoutRegion] = []
    for r in regions:
        size = size_mm(r.polygon)
        if r.kind == "area" and size < spacing.point_symbol_min_mm:
            center = inside_point(r.polygon, layout.inside_point_tolerance_mm)
            poly = point_symbol(center, spacing.point_symbol_min_mm, layout.point_symbol_vertices)
            note = (
                f"point symbol: {size:.1f} mm part is below the "
                f"{spacing.point_symbol_min_mm} mm minimum"
            )
            out.append(r.noted(note, polygon=poly, kind="point"))
        else:
            out.append(r)
    return out


def _largest(geom: shapely.Geometry) -> Polygon | None:
    polys = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon) and not g.is_empty]
    return max(polys, key=lambda p: p.area) if polys else None


def _tidy(geom: shapely.Geometry, tolerance: float) -> Polygon | None:
    poly = _largest(shapely.make_valid(geom))
    if poly is None:
        return None
    tol = tolerance
    simple = _largest(shapely.make_valid(poly.simplify(tol, preserve_topology=True)))
    while simple is not None and len(simple.exterior.coords) - 1 > MAX_POLYGON_POINTS:
        tol *= 2
        simple = _largest(shapely.make_valid(poly.simplify(tol, preserve_topology=True)))
    return simple


def _ancestors(regions: dict[str, LayoutRegion], rid: str) -> set[str]:
    out: set[str] = set()
    cur = regions[rid].parent
    while cur is not None and cur in regions and cur not in out:
        out.add(cur)
        cur = regions[cur].parent
    return out


def _inner_clearance(child: Polygon, parent: Polygon) -> float:
    if not child.within(parent):
        return 0.0
    return float(parent.exterior.distance(child))


def _pair_ok(regions: dict[str, LayoutRegion], a: str, b: str, gap: float) -> bool:
    if a in _ancestors(regions, b):
        return _inner_clearance(regions[b].polygon, regions[a].polygon) >= gap - _EPS
    if b in _ancestors(regions, a):
        return _inner_clearance(regions[a].polygon, regions[b].polygon) >= gap - _EPS
    return float(regions[a].polygon.distance(regions[b].polygon)) >= gap - _EPS


def _cut(
    regions: dict[str, LayoutRegion], a: str, b: str, gap: float, tol: float
) -> tuple[str, Polygon | None]:
    """Which region to shrink for the pair (a, b), and its new outline."""
    ra, rb = regions[a], regions[b]
    # One tolerance for the simplification, one for the chords of the buffered arcs.
    margin = gap + 2 * tol
    for outer, inner in ((ra, rb), (rb, ra)):
        if outer.id in _ancestors(regions, inner.id):
            if inner.kind == "area":
                return inner.id, _tidy(inner.polygon & outer.polygon.buffer(-margin), tol)
            return outer.id, _tidy(outer.polygon - inner.polygon.buffer(margin), tol)
    if ra.kind == "point" and rb.kind == "area":
        shrink, keep = rb, ra
    elif rb.kind == "point" and ra.kind == "area":
        shrink, keep = ra, rb
    else:
        shrink, keep = (ra, rb) if ra.polygon.area >= rb.polygon.area else (rb, ra)
    return shrink.id, _tidy(shrink.polygon - keep.polygon.buffer(margin), tol)


def enforce_gaps(
    regions: Sequence[LayoutRegion], gap_mm: float, layout: Layout
) -> tuple[list[LayoutRegion], list[tuple[str, str]]]:
    """Shrinks outlines until every pair of raised outlines is at least gap_mm apart.
    A child keeps gap_mm from its parent's outline. Point symbols never shrink; two point
    symbols that are too close are returned as unresolved, untouched."""
    cur = {r.id: r for r in regions}
    order = [r.id for r in regions]
    tol = layout.gap_simplify_tolerance_mm
    stuck: set[tuple[str, str]] = set()
    for _ in range(layout.gap_max_passes):
        changed = False
        for a, b in itertools.combinations(order, 2):
            if (a, b) in stuck or _pair_ok(cur, a, b, gap_mm):
                continue
            if cur[a].kind == "point" and cur[b].kind == "point":
                stuck.add((a, b))
                continue
            rid, poly = _cut(cur, a, b, gap_mm, tol)
            if poly is None:
                stuck.add((a, b))
                continue
            other = b if rid == a else a
            cur[rid] = cur[rid].noted(f"shrunk for the {gap_mm} mm gap to {other}", polygon=poly)
            changed = True
        if not changed:
            break
    unresolved = [
        (a, b) for a, b in itertools.combinations(order, 2) if not _pair_ok(cur, a, b, gap_mm)
    ]
    return [cur[rid] for rid in order], unresolved
