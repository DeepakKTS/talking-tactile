"""Rules on SAM's part masks before S3 (S2, Arm A v2f).

- Pieces: a mask keeps the 8-connected pieces that hold one of its prompt points, less
  pieces under S3's speck floor.
- Spill: a mask holding another part's prompt point spilled onto that part, unless the
  other part is its child (Spark's parent field).
- Oversize: a mask is also spill when it holds points of OVERSIZE_POINTS or more other parts,
  or covers more than OVERSIZE_SHARE of the figure's object area while Spark marked the part
  thin or gave it a parent. 25% was proposed; on the bake-off it would mark the flower's
  petal, whose v2 mask is 48.5% of the object area against 43.8% for the petals' yellow fill
  (IoU 0.72), and whose parent is the perianth group. At 50% the rule catches v2's filament
  (112%) and no mask that looked right.
- Contested pixels: each pixel claimed by several masks goes to the smallest; between masks
  of equal size, to the part whose nearest prompt point is closer. Spill masks take no part.
"""

from collections.abc import Mapping, Sequence

import cv2
import numpy as np
import numpy.typing as npt

Mask = npt.NDArray[np.bool_]
Point = tuple[int, int]

OVERSIZE_POINTS = 2
OVERSIZE_SHARE = 0.5


def keep_pieces(mask: Mask, points: Sequence[Point], floor_px: float) -> tuple[Mask, int]:
    """The pieces of mask that hold a point, less pieces under floor_px, and how many pieces
    were dropped."""
    n, labels, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    held = {int(labels[y, x]) for x, y in points} - {0}
    keep = [i for i in held if st[i, cv2.CC_STAT_AREA] >= floor_px]
    return np.isin(labels, keep), (n - 1) - len(keep)


def drop_specks(mask: Mask, floor_px: float) -> Mask:
    n, labels, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= floor_px]
    return np.isin(labels, keep)


def points_inside(
    part: str, mask: Mask, points: Mapping[str, Sequence[Point]], parents: Mapping[str, str]
) -> dict[str, Point]:
    """Other parts, not this part's children, with a prompt point inside mask: the first
    such point of each."""
    out = {}
    for q, pts in points.items():
        if q == part or parents.get(q) == part:
            continue
        inside = [p for p in pts if mask[p[1], p[0]]]
        if inside:
            out[q] = inside[0]
    return out


def oversize(
    held: Mapping[str, Point], mask: Mask, object_px: int, thin: bool, has_parent: bool
) -> str | None:
    """Why a mask counts as spill under the oversize rule, or None."""
    if len(held) >= OVERSIZE_POINTS:
        return f"holds points of {len(held)} other parts: {', '.join(sorted(held))}"
    share = mask.sum() / max(1, object_px)
    if share > OVERSIZE_SHARE and (thin or has_parent):
        return f"covers {share:.0%} of the object area, and the part is " + (
            "thin" if thin else "inside another part"
        )
    return None


Resolved = tuple[
    dict[str, Mask], dict[str, dict[str, int]], dict[str, dict[str, int]], dict[str, int]
]


def resolve(
    masks: Mapping[str, Mask], points: Mapping[str, Sequence[Point]], floor_px: float
) -> Resolved:
    """Contested pixels to the smallest mask, ties to the nearer prompt point. Returns the
    masks, the pixels each part lost to and won from each other part, and the pixels each
    lost to specks left by the resolution."""
    if not masks:
        return {}, {}, {}, {}
    order = list(masks)
    shape = masks[order[0]].shape
    span = float(np.hypot(*shape)) + 1  # a distance never outweighs one pixel of size
    best = np.full(shape, np.inf, np.float64)
    owner = np.full(shape, -1, np.int32)
    for i, p in enumerate(order):
        seeds = np.ones(shape, np.uint8)
        for x, y in points.get(p, []):
            seeds[y, x] = 0
        dist = cv2.distanceTransform(seeds, cv2.DIST_L2, 5) if not seeds.all() else span
        cost = int(masks[p].sum()) + np.asarray(dist) / span
        take = masks[p] & (cost < best)
        owner[take] = i
        best[take] = np.broadcast_to(cost, shape)[take]
    out: dict[str, Mask] = {}
    lost: dict[str, dict[str, int]] = {}
    won: dict[str, dict[str, int]] = {}
    respeck: dict[str, int] = {}
    for i, p in enumerate(order):
        mine = owner == i
        ids, counts = np.unique(owner[masks[p] & ~mine], return_counts=True)
        lost[p] = {order[int(j)]: int(c) for j, c in zip(ids, counts, strict=True)}
        won[p] = {}
        for j, q in enumerate(order):
            if j != i and (c := int((mine & masks[q]).sum())):
                won[p][q] = c
        cleaned = drop_specks(mine, floor_px)
        respeck[p] = int(mine.sum() - cleaned.sum())
        out[p] = cleaned
    return out, lost, won, respeck


def members_of(
    group: str, members: Mapping[str, Sequence[str]], groups: set[str], seen: set[str]
) -> list[str]:
    """A group's listed members, with member groups opened up."""
    out: list[str] = []
    for m in members.get(group, ()):
        if m in seen or m not in members:
            continue
        seen.add(m)
        out += members_of(m, members, groups, seen) if m in groups else [m]
    return out
