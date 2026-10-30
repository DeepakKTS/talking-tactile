"""S1's plan for touch on the laid-out sheet: line parts, groups, merge proposals and the
subject's silhouette. Pure functions, no I/O.

- Names to parts: S1 and S2 name parts by phrase. A phrase maps to the reconciled part S3
  made from it, by S3's part ids, so a teacher's rename keeps the mapping; after a merge, to
  the part that took it in. A part with no region on the sheet maps to nothing.
- A line separates two parts when both map to two different parts on the sheet; otherwise
  it keeps its parent's part, if that is on the sheet. Its labels for the teacher stay.
- A group is never drawn (Oct 30). Each member on the sheet carries the name of the group
  that lists it, the first in S1's order, and Explore says it with the member's label. A
  member that is itself a group passes the name to nothing: its own members carry its name.
- The silhouette is the outer contour of the subject, raised as a line but never textured
  and never touchable. Its line is drawn outline_width_mm wide on the contour, and only
  where every part outline is at least min_gap_mm away from the line's edge, and braille at
  least its clearance; pieces shorter than point_symbol_min_mm are left out, as a stub that
  short reads as a bump, not a line.
"""

from collections.abc import Mapping, Sequence

import shapely
from pydantic import BaseModel, ConfigDict
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union

from app.braille.models import Placement
from app.config import TactileRules
from app.geometry.layout import LayoutRegion
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.sheet import SheetLine, SheetMerge
from app.geometry.vectorize import mask_to_polygons_mm
from app.meta.types import Understanding
from app.models.mask import BoolImage, Mask

_PAIR = 2


class SheetPlan(BaseModel):
    """What S4 lays out from S1's plan and S2's silhouette."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    subject: str = ""
    silhouette: BoolImage | None = None
    lines: list[SheetLine] = []
    merges: list[SheetMerge] = []
    groups: dict[str, str] = {}  # part id -> the name of the group it is a member of


def part_ids(
    phrases: Sequence[str], before: Sequence[ReconciledPart], after: Sequence[ReconciledPart]
) -> dict[str, str]:
    """phrase -> the id of the part it ended in on the sheet, for phrases that have one.
    before is S3's output, after is it with the teacher's edits."""
    alive = {p.id for p in after}
    first: dict[str, str] = {}
    for p in before:
        first.setdefault(p.mask.label, p.id)
    out: dict[str, str] = {}
    for phrase in phrases:
        pid = first.get(phrase)
        if pid in alive:
            out[phrase] = pid
            continue
        took = [p.id for p in after if phrase in p.merged]
        if took:
            out[phrase] = took[0]
    return out


def sheet_groups(u: Understanding, ids: Mapping[str, str]) -> dict[str, str]:
    """Part id -> the name of S1's group that lists it. ids maps phrases to part ids."""
    out: dict[str, str] = {}
    for g in (q for q in u.parts if q.kind == "group"):
        for m in g.members:
            pid = ids.get(m)
            if pid is not None:
                out.setdefault(pid, g.phrase)
    return out


def sheet_lines(
    u: Understanding, ids: Mapping[str, str], labels: Mapping[str, str]
) -> list[SheetLine]:
    """S1's line parts. ids maps phrases to part ids; labels maps part ids to their labels."""
    out: list[SheetLine] = []
    for p in (q for q in u.parts if q.kind == "line"):
        between = None
        separates = None
        if len(p.separates) == _PAIR:  # S1 checked: two planned areas
            a, b = p.separates
            between = (labels.get(ids.get(a, ""), a), labels.get(ids.get(b, ""), b))
            ia, ib = ids.get(a), ids.get(b)
            if ia is not None and ib is not None and ia != ib:
                separates = (ia, ib)
        parent = ids.get(p.parent) if p.parent else None
        out.append(
            SheetLine(
                id=f"l{len(out) + 1}",
                label=p.phrase,
                separates=separates,
                between=between,
                parent=None if separates else parent,
            )
        )
    return out


def sheet_merges(
    merges: Sequence[tuple[Sequence[str], str, str]], ids: Mapping[str, str]
) -> list[SheetMerge]:
    """Each proposal (phrases, name, why) on the parts still apart on the sheet; one that
    has fewer than two left is dropped."""
    out = []
    for phrases, name, why in merges:
        pids = tuple(dict.fromkeys(ids[p] for p in phrases if p in ids))
        if len(pids) >= _PAIR:  # a merge needs two parts
            out.append(SheetMerge(name=name, part_ids=pids, why=why))
    return out


def silhouette_polygon(mask: BoolImage, fit: PageFit, rules: TactileRules) -> Polygon | None:
    """The silhouette's largest piece in page mm, within the regions.json point cap."""
    polys = mask_to_polygons_mm(
        Mask(data=mask, label="silhouette", score=1.0, source="sam"), fit, rules.vectorize
    )
    return polys[0] if polys else None


def contour(
    silhouette: Polygon,
    regions: Sequence[LayoutRegion],
    braille: Sequence[Placement],
    rules: TactileRules,
) -> list[LineString]:
    """The pieces of the silhouette's edge that can be raised (module docstring)."""
    half = rules.render.outline_width_mm / 2
    keep_out = [r.polygon.buffer(rules.spacing.min_gap_mm + half) for r in regions]
    clearance = rules.braille.clearance_to_line_mm + half
    keep_out += [p.line.rect.buffer(clearance) for p in braille]
    edge = silhouette.exterior
    free = edge.difference(unary_union(keep_out)) if keep_out else edge
    pieces = [
        g
        for g in getattr(free, "geoms", [free])
        if isinstance(g, LineString)
        and not g.is_empty
        and g.length >= rules.spacing.point_symbol_min_mm
    ]
    merged = shapely.line_merge(MultiLineString(pieces)) if pieces else None
    if merged is None:
        return []
    return [g for g in getattr(merged, "geoms", [merged]) if isinstance(g, LineString)]


def key_text(line: SheetLine, labels: Mapping[str, str]) -> str:
    """How the key lists a line part: its label, then where it lies."""
    if line.between is not None:
        return f"{line.label}, a line between {line.between[0]} and {line.between[1]}"
    if line.parent is not None and line.parent in labels:
        return f"{line.label}, a line in {labels[line.parent]}"
    return f"{line.label}, a line"


def band(piece: LineString, rules: TactileRules) -> Polygon:
    """The raised line drawn along a contour piece."""
    out = piece.buffer(rules.render.outline_width_mm / 2, cap_style="flat")
    return out if isinstance(out, Polygon) else Polygon()
