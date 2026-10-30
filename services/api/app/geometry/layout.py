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


def part_id_of(region_id: str) -> str:
    """The reconciled part a region came from: pieces after the first are <part>_<k>."""
    return region_id.partition("_")[0]


def regions_from_parts(
    parts: Sequence[ReconciledPart], fit: PageFit, rules: Vectorize
) -> list[LayoutRegion]:
    """One region per polygon piece. The largest piece keeps the part id; the others are
    <part>_<k>."""
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


def symbol_area(spacing: Spacing, layout: Layout, inset_mm: float) -> float:
    """The enterable area of a point symbol point_symbol_min_mm wide: inside its outline."""
    sym = point_symbol((0.0, 0.0), spacing.point_symbol_min_mm, layout.point_symbol_vertices)
    return float(sym.buffer(-inset_mm).area)


def enterable_area(poly: Polygon, inset_mm: float) -> float:
    """What a fingertip can enter: the area inside the raised outline, which takes half its
    width from the edge."""
    return float(poly.buffer(-inset_mm).area)


def under_floor(
    poly: Polygon, spacing: Spacing, layout: Layout, inset_mm: float, floor_mm2: float
) -> bool:
    """Smaller than a point symbol: the longest side under point_symbol_min_mm, or the
    enterable area under a point symbol's (a long thin sliver passes the first)."""
    return size_mm(poly) < spacing.point_symbol_min_mm or (
        enterable_area(poly, inset_mm) < floor_mm2 - _EPS
    )


def drop_small_pieces(
    regions: Sequence[LayoutRegion], spacing: Spacing, layout: Layout, inset_mm: float
) -> list[LayoutRegion]:
    """A part with a piece at or above the floor loses its pieces under it; its main piece
    records the repair (on its first piece left). A part with every piece under the floor
    keeps them all, as point symbols."""
    floor = symbol_area(spacing, layout, inset_mm)
    small = {
        r.id
        for r in regions
        if r.kind == "area" and under_floor(r.polygon, spacing, layout, inset_mm, floor)
    }
    parts: dict[str, list[LayoutRegion]] = {}
    for r in regions:
        parts.setdefault(r.group_key, []).append(r)
    drop: set[str] = set()
    for pieces in parts.values():
        if len(pieces) > 1 and any(p.id not in small for p in pieces):
            drop |= {p.id for p in pieces if p.id in small}
    out: list[LayoutRegion] = []
    for r in regions:
        if r.id in drop:
            continue
        pieces = parts[r.group_key]
        gone = [p for p in pieces if p.id in drop]
        first_left = next(p for p in pieces if p.id not in drop)
        if gone and r is first_left:
            out.append(
                r.noted(
                    f"repair: {len(gone)} piece{'s' if len(gone) > 1 else ''} smaller than a "
                    f"{spacing.point_symbol_min_mm} mm point symbol left out; the part keeps "
                    "its main piece"
                )
            )
        else:
            out.append(r)
    return out


def make_point_symbols(
    regions: Sequence[LayoutRegion], spacing: Spacing, layout: Layout, inset_mm: float = 0.0
) -> list[LayoutRegion]:
    floor = symbol_area(spacing, layout, inset_mm)
    out: list[LayoutRegion] = []
    for r in regions:
        if r.kind == "area" and under_floor(r.polygon, spacing, layout, inset_mm, floor):
            size = size_mm(r.polygon)
            center = inside_point(r.polygon, layout.inside_point_tolerance_mm)
            poly = point_symbol(center, spacing.point_symbol_min_mm, layout.point_symbol_vertices)
            note = (
                f"point symbol: {size:.1f} mm part is below the "
                f"{spacing.point_symbol_min_mm} mm minimum"
                if size < spacing.point_symbol_min_mm
                else f"point symbol: {enterable_area(r.polygon, inset_mm):.1f} mm2 to enter is "
                f"below a point symbol's {floor:.1f} mm2"
            )
            out.append(r.noted(note, polygon=poly, kind="point"))
        else:
            out.append(r)
    return out


def one_symbol_per_spot(regions: Sequence[LayoutRegion], min_gap_mm: float) -> list[LayoutRegion]:
    """Point symbols of one part closer than the minimum gap to one kept before are left out,
    recorded as a repair on the part's first piece: two pieces of a thin part (two veins
    under one label) can both fall under the floor side by side."""
    kept: dict[str, list[LayoutRegion]] = {}
    gone: dict[str, int] = {}
    for r in regions:
        mine = kept.setdefault(r.group_key, [])
        near = r.kind == "point" and any(
            q.kind == "point" and r.polygon.distance(q.polygon) < min_gap_mm for q in mine
        )
        if near:
            gone[r.group_key] = gone.get(r.group_key, 0) + 1
        else:
            mine.append(r)
    out = []
    for r in regions:
        mine = kept[r.group_key]
        if r not in mine:
            continue
        n = gone.get(r.group_key, 0)
        note = (
            f"repair: {n} more point symbol{'s' if n > 1 else ''} of this part left out, "
            f"closer than {min_gap_mm} mm to this one"
        )
        out.append(r.noted(note) if n and r is mine[0] else r)
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


def _pair_ok(
    regions: dict[str, LayoutRegion], a: str, b: str, gap: float, nested_gap: float
) -> bool:
    if a in _ancestors(regions, b):
        return _inner_clearance(regions[b].polygon, regions[a].polygon) >= nested_gap - _EPS
    if b in _ancestors(regions, a):
        return _inner_clearance(regions[a].polygon, regions[b].polygon) >= nested_gap - _EPS
    return float(regions[a].polygon.distance(regions[b].polygon)) >= gap - _EPS


class _Gaps(BaseModel):
    model_config = ConfigDict(frozen=True)

    gap: float  # between unrelated outlines
    nested: float  # from a child to its parent's edge
    tol: float  # simplification tolerance


def _cut(
    regions: dict[str, LayoutRegion], a: str, b: str, gaps: _Gaps
) -> tuple[str, Polygon | None]:
    """Which region to shrink for the pair (a, b), and its new outline."""
    ra, rb = regions[a], regions[b]
    tol = gaps.tol
    # One tolerance for the simplification, one for the chords of the buffered arcs.
    margin = gaps.gap + 2 * tol
    nested_margin = gaps.nested + 2 * tol
    for outer, inner in ((ra, rb), (rb, ra)):
        if outer.id in _ancestors(regions, inner.id):
            if inner.kind == "area":
                return inner.id, _tidy(inner.polygon & outer.polygon.buffer(-nested_margin), tol)
            return outer.id, _tidy(outer.polygon - inner.polygon.buffer(nested_margin), tol)
    if ra.kind == "point" and rb.kind == "area":
        shrink, keep = rb, ra
    elif rb.kind == "point" and ra.kind == "area":
        shrink, keep = ra, rb
    else:
        shrink, keep = (ra, rb) if ra.polygon.area >= rb.polygon.area else (rb, ra)
    return shrink.id, _tidy(shrink.polygon - keep.polygon.buffer(margin), tol)


def enforce_gaps(
    regions: Sequence[LayoutRegion], gap_mm: float, layout: Layout, line_mm: float
) -> tuple[list[LayoutRegion], list[tuple[str, str]]]:
    """Shrinks outlines until every pair of raised outlines is at least gap_mm apart.
    Outlines are drawn line_mm wide inside each part's edge, so a child keeps
    gap_mm + line_mm from its parent's edge. Point symbols never shrink; two point
    symbols that are too close are returned as unresolved, untouched."""
    nested_gap = gap_mm + line_mm
    cur = {r.id: r for r in regions}
    order = [r.id for r in regions]
    tol = layout.gap_simplify_tolerance_mm
    stuck: set[tuple[str, str]] = set()
    for _ in range(layout.gap_max_passes):
        changed = False
        for a, b in itertools.combinations(order, 2):
            if (a, b) in stuck or _pair_ok(cur, a, b, gap_mm, nested_gap):
                continue
            if cur[a].kind == "point" and cur[b].kind == "point":
                stuck.add((a, b))
                continue
            rid, poly = _cut(cur, a, b, _Gaps(gap=gap_mm, nested=nested_gap, tol=tol))
            if poly is None:
                stuck.add((a, b))
                continue
            other = b if rid == a else a
            cur[rid] = cur[rid].noted(f"shrunk for the {gap_mm} mm gap to {other}", polygon=poly)
            changed = True
        if not changed:
            break
    unresolved = [
        (a, b)
        for a, b in itertools.combinations(order, 2)
        if not _pair_ok(cur, a, b, gap_mm, nested_gap)
    ]
    return [cur[rid] for rid in order], unresolved
