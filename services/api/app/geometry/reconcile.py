"""S3 reconcile, the code part. Pure functions on Masks, no I/O.

Order of operations:
1. Cut printed text out of every part.
2. Remove speck components; drop parts left empty, and parts thinner than a sliver.
3. Near duplicates (IoU above duplicate_iou) collapse onto the higher score.
4. A part mostly inside another (contain_fraction) becomes its child; the parent is the
   smallest container. S2's nesting, by phrase, comes first when both parts are left.
   Parents keep their full area.
5. Any other overlap goes to the smaller part (then the higher score, then input order).
6. Specks left by trimming are removed again.

Ids are r1, r2, ... by input position, so they are stable whatever gets dropped.
"""

from collections.abc import Mapping, Sequence

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Reconcile
from app.models.mask import BoolImage, Mask

_CONNECTIVITY = 8


class ReconciledPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    mask: Mask
    parent: str | None = None
    merged: list[str] = []


class Dropped(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    reason: str


class Reconciled(BaseModel):
    model_config = ConfigDict(frozen=True)

    parts: list[ReconciledPart]
    dropped: list[Dropped]


Box = tuple[int, int, int, int]  # row0, row1, col0, col1 (exclusive ends)


def _bbox(data: BoolImage) -> Box | None:
    rows = np.flatnonzero(data.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(data.any(axis=0))
    return (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)


def _box_overlap(a: Box, b: Box) -> Box | None:
    r0, r1 = max(a[0], b[0]), min(a[1], b[1])
    c0, c1 = max(a[2], b[2]), min(a[3], b[3])
    return (r0, r1, c0, c1) if r0 < r1 and c0 < c1 else None


def _intersection_px(a: BoolImage, b: BoolImage) -> int:
    ba, bb = _bbox(a), _bbox(b)
    if ba is None or bb is None:
        return 0
    box = _box_overlap(ba, bb)
    if box is None:
        return 0
    r0, r1, c0, c1 = box
    return int(np.count_nonzero(a[r0:r1, c0:c1] & b[r0:r1, c0:c1]))


def remove_specks(data: BoolImage, max_area_px: float) -> BoolImage:
    """Drops 8-connected components whose area is below max_area_px."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        data.astype(np.uint8), connectivity=_CONNECTIVITY
    )
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= max_area_px
    out: BoolImage = keep[labels]
    return out


def max_width_px(data: BoolImage) -> float:
    """Width of the widest inscribed disc, in pixels. 1 for a one-pixel line."""
    padded = np.pad(data, 1).astype(np.uint8)
    dist = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return max(0.0, 2.0 * float(dist.max()) - 1.0)


class _State:
    """Working state shared by the steps: current pixels and facts per surviving id."""

    def __init__(self, parts: Sequence[Mask]) -> None:
        self.ids = [f"r{i + 1}" for i in range(len(parts))]
        self.source = dict(zip(self.ids, parts, strict=True))
        self.data: dict[str, BoolImage] = {}
        self.area: dict[str, int] = {}
        self.merged: dict[str, list[str]] = {}
        self.parent: dict[str, str | None] = {}
        self.alive: list[str] = []
        self.dropped: list[Dropped] = []

    def order(self, pid: str) -> int:
        return self.ids.index(pid)

    def drop(self, pid: str, reason: str) -> None:
        self.dropped.append(Dropped(id=pid, label=self.source[pid].label, reason=reason))

    def ancestors(self, pid: str) -> set[str]:
        out: set[str] = set()
        cur = self.parent[pid]
        while cur is not None:
            out.add(cur)
            cur = self.parent[cur]
        return out


def _clean(st: _State, text: Sequence[Mask], speck_px: float, sliver_px: float) -> None:
    text_union: BoolImage | None = None
    for t in text:
        text_union = t.data.copy() if text_union is None else text_union | t.data
    for pid in st.ids:
        m = st.source[pid]
        pixels = m.data & ~text_union if text_union is not None else m.data.copy()
        pixels = remove_specks(pixels, speck_px)
        if not pixels.any():
            st.drop(pid, "empty")
        elif max_width_px(pixels) < sliver_px:
            st.drop(pid, "sliver")
        else:
            st.data[pid] = pixels
            st.area[pid] = int(np.count_nonzero(pixels))
            st.merged[pid] = []


def _dedupe(st: _State, duplicate_iou: float) -> None:
    by_score = sorted(st.data, key=lambda pid: (-st.source[pid].score, st.order(pid)))
    kept: list[str] = []
    for pid in by_score:
        for kid in kept:
            inter = _intersection_px(st.data[pid], st.data[kid])
            union = st.area[pid] + st.area[kid] - inter
            if union and inter / union > duplicate_iou:
                st.merged[kid].append(st.source[pid].label)
                st.drop(pid, f"duplicate of {st.source[kid].label}")
                break
        else:
            kept.append(pid)
    st.alive = [pid for pid in st.ids if pid in kept]


def _nest(st: _State, contain_fraction: float, hints: Mapping[str, str]) -> None:
    by_label = {st.source[pid].label: pid for pid in reversed(st.alive)}  # the first piece
    for pid in st.alive:
        hint = by_label.get(hints.get(st.source[pid].label, ""))
        if hint is not None and hint != pid:
            st.parent[pid] = hint
            continue
        holders = [
            other
            for other in st.alive
            if other != pid
            and st.area[other] > st.area[pid]
            and _intersection_px(st.data[pid], st.data[other]) / st.area[pid] >= contain_fraction
        ]
        st.parent[pid] = min(holders, key=lambda o: (st.area[o], st.order(o))) if holders else None


def _trim_overlaps(st: _State) -> set[str]:
    def rank(pid: str) -> tuple[int, float, int]:
        return (st.area[pid], -st.source[pid].score, st.order(pid))

    trimmed: set[str] = set()
    for i, a in enumerate(st.alive):
        for b in st.alive[i + 1 :]:
            if a in st.ancestors(b) or b in st.ancestors(a):
                continue
            if _intersection_px(st.data[a], st.data[b]) == 0:
                continue
            winner, loser = (a, b) if rank(a) < rank(b) else (b, a)
            st.data[loser] = st.data[loser] & ~st.data[winner]
            trimmed.add(loser)
    return trimmed


def _finish(st: _State, trimmed: set[str], speck_px: float) -> Reconciled:
    out: list[ReconciledPart] = []
    for pid in st.alive:
        pixels = remove_specks(st.data[pid], speck_px) if pid in trimmed else st.data[pid]
        if not pixels.any():
            st.drop(pid, "empty after overlap")
            continue
        out.append(
            ReconciledPart(
                id=pid, mask=st.source[pid].with_data(pixels), parent=st.parent[pid],
                merged=st.merged[pid],
            )
        )  # fmt: skip
    alive_ids = {p.id for p in out}
    out = [
        p if p.parent is None or p.parent in alive_ids else p.model_copy(update={"parent": None})
        for p in out
    ]
    return Reconciled(parts=out, dropped=sorted(st.dropped, key=lambda d: st.order(d.id)))


def reconcile(
    parts: Sequence[Mask],
    text: Sequence[Mask],
    mm_per_px: float,
    rules: Reconcile,
    nested: Mapping[str, str] | None = None,
) -> Reconciled:
    """nested: S2's child phrase -> parent phrase."""
    shapes = {m.shape for m in [*parts, *text]}
    if len(shapes) > 1:
        raise ValueError(f"all masks must be the size of the normalized image, got {shapes}")
    speck_px = rules.speck_max_area_mm2 / mm_per_px**2
    sliver_px = rules.sliver_max_width_mm / mm_per_px
    st = _State(parts)
    _clean(st, text, speck_px, sliver_px)
    _dedupe(st, rules.duplicate_iou)
    _nest(st, rules.contain_fraction, nested or {})
    trimmed = _trim_overlaps(st)
    return _finish(st, trimmed, speck_px)
