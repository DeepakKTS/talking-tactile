"""Author's overlap warning (Oct 30): a part's outline that also covers the drawn region
where another listed part's prompt point lies. A warning for the teacher, never a gate.

The detector is the minimal-clip logic of the touch-safety study (eval on Oct 30, tracker
d5-12): drawn regions from app/geometry/boundaries.py; a part owns the regions of its own
prompt points and of its nested children's; any pixel of its outline in a region that holds
another part's point, that part not its nested child, is an overlap. Nothing is clipped.
A region the part owns too counts only when the two parts' fills are within FILL_DELTA:
shaded lobes blend into one drawn region (the Blausen brain), and there the colors are the
boundary.

Parts are the sheet's parts as the teacher edited them. Listed phrases map to them through
S3's ids (geometry/plan.part_ids), so a rename or a merge keeps the mapping, and a merged
part owns the points of every phrase merged into it."""

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import TactileRules
from app.geometry import plan
from app.geometry.boundaries import FILL_DELTA, Drawn
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.vectorize import mask_to_polygons_mm
from app.meta.types import Understanding
from app.models.mask import Mask

Point = tuple[int, int]
PointMm = tuple[float, float]
_DECIMALS = 2


class OverlapWarning(BaseModel):
    model_config = ConfigDict(frozen=True)

    region_id: str  # the part's main region id on the sheet
    part: str  # its label
    other: str  # the part whose drawn region it covers, by its label on the sheet
    area_mm: list[list[PointMm]]  # the covered area, for Show on sheet; may be empty

    @property
    def text(self) -> str:
        return f"This outline also covers the area where {self.other} is"


def _kin(phrases: set[str], parents: Mapping[str, str]) -> set[str]:
    out: set[str] = set()
    todo = list(phrases)
    while todo:
        cur = todo.pop()
        for child, parent in parents.items():
            if parent == cur and child not in out and child not in phrases:
                out.add(child)
                todo.append(child)
    return out


def _regions(drawn: Drawn, pts: Sequence[Point]) -> set[int]:
    return {r for r in (drawn.region_of(p) for p in pts) if r}


def overlaps(
    parts: Sequence[ReconciledPart],
    before: Sequence[ReconciledPart],
    u: Understanding,
    points: Mapping[str, Sequence[Point]],
    nested: Mapping[str, str],
    drawn: Drawn,
    fit: PageFit,
    rules: TactileRules,
) -> list[OverlapWarning]:
    """One warning per part and other part whose drawn region its outline covers."""
    ids = plan.part_ids(list(points), before, parts)
    parents = {**{p.phrase: p.parent for p in u.parts if p.parent}, **nested}
    label_of = {p.id: p.mask.label for p in parts}
    regions = {q: _regions(drawn, pts) for q, pts in points.items()}
    out: list[OverlapWarning] = []
    seen: set[tuple[str, str]] = set()
    for part in parts:
        own = {q for q, pid in ids.items() if pid == part.id}
        skip = own | _kin(own, parents)
        mine = [p for q in skip for p in points.get(q, [])]
        owned = set().union(*(regions[q] for q in skip if q in regions))
        for q in points:
            if q in skip or not regions[q]:
                continue
            hit = regions[q] - owned
            if regions[q] & owned and drawn.fill_delta(mine, points[q]) <= FILL_DELTA:
                hit |= regions[q] & owned
            area = part.mask.data & np.isin(drawn.labels, list(hit))
            other = label_of.get(ids.get(q, ""), q)
            if not area.any() or (part.id, other) in seen:
                continue
            seen.add((part.id, other))
            covered = Mask(data=area, label=q, score=1.0, source="code")
            polys = mask_to_polygons_mm(covered, fit, rules.vectorize)
            out.append(
                OverlapWarning(
                    region_id=part.id,
                    part=part.mask.label,
                    other=other,
                    area_mm=[
                        [(round(x, _DECIMALS), round(y, _DECIMALS)) for x, y in p.exterior.coords]
                        for p in polys
                    ],
                )
            )
    return out
