"""Rules on SAM's part masks before S3 (S2, Arm A v2f).

- Pieces: a mask keeps the 8-connected pieces that hold one of its prompt points, less
  pieces under S3's speck floor.
- Relations:
  - Shared region, from the first masks: two masks with IoU of SHARED_IOU or more are one
    drawn shape, as are the areas Spark marked shares_region.
  - Nesting: when NEST_INSIDE or more of B's mask lies inside A's and B is smaller, B is
    nested in A, whatever Spark said. The spill check tests it against the mask it checks:
    a first mask, or a retry's. The nesting S2 records, and S3 uses, is tested again on
    the masks S2 keeps, with the smallest such A as the parent: a first mask that took the
    whole figure nests everything in it, but the retry that replaces it may not.
    Shared pairs do not nest.
  - NEST_INSIDE, from the first masks of the five eval figures (eval/plan/RESULTS.md, Oct
    30): 0.9 was proposed. The parts Spark gave a parent sat at 0.893 to 1.0 inside it; the
    0.893 (a gyrus in its lobe) is excused by Spark's parent anyway. Between 0.90 and 0.95
    every pair that was not a shared region was a mask running over its neighbour (left
    atrium in the septum's first mask at 0.906, style and pedicel in the filament's at
    0.919 and 0.906), and none a nesting. So 0.95, which is also S3's contain_fraction.
    Spill masks above 0.95 remain (the chambers in the septum's first mask, 0.97 to 0.99);
    the retry and the test on the kept mask are what keep those apart.
- Spill: a mask holding another part's prompt point spilled onto that part, unless the
  other part is its child (Spark's parent field), is nested in the mask, or shares its
  region.
- Oversize: a mask is also spill when it holds points of OVERSIZE_POINTS or more other parts,
  or covers more than OVERSIZE_SHARE of the figure's object area while Spark marked the part
  thin or gave it a parent. 25% was proposed; on the bake-off it would mark the flower's
  petal, whose v2 mask is 48.5% of the object area against 43.8% for the petals' yellow fill
  (IoU 0.72), and whose parent is the perianth group. At 50% the rule catches v2's filament
  (112%) and no mask that looked right.
- Contested pixels: each pixel claimed by several masks goes to the smallest; between masks
  of equal size, to the part whose nearest prompt point is closer. Near-identical masks
  (IoU of SHARED_IOU or more: SAM gave each part the whole shape) are then split by the
  nearer point among them. A nested child's pixels stay in its parent's outline too, as S3
  keeps a parent's full area, so the child is raised inside it. Spill masks take no part.
"""

from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import combinations

import cv2
import numpy as np
import numpy.typing as npt

Mask = npt.NDArray[np.bool_]
Point = tuple[int, int]

OVERSIZE_POINTS = 2
OVERSIZE_SHARE = 0.5
NEST_INSIDE = 0.95  # eval/plan/RESULTS.md; S3's contain_fraction is the same
SHARED_IOU = 0.8
RECORD_SHARE = 0.25  # inside shares and IoUs from here up go in S2's facts, as eval data
_GROUP_MIN = 2


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
    part: str,
    mask: Mask,
    points: Mapping[str, Sequence[Point]],
    parents: Mapping[str, str],
    ignore: AbstractSet[str] = frozenset(),
) -> dict[str, Point]:
    """Other parts, not this part's children nor those in ignore, with a prompt point inside
    mask: the first such point of each."""
    out = {}
    for q, pts in points.items():
        if q == part or parents.get(q) == part or q in ignore:
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


Box = tuple[int, int, int, int]  # row0, row1, col0, col1 (exclusive ends)


def _box(m: Mask) -> Box | None:
    rows = np.flatnonzero(m.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(m.any(axis=0))
    return int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1


def _shared_px(a: Mask, b: Mask, ba: Box, bb: Box) -> int:
    r0, r1, c0, c1 = max(ba[0], bb[0]), min(ba[1], bb[1]), max(ba[2], bb[2]), min(ba[3], bb[3])
    if r0 >= r1 or c0 >= c1:
        return 0
    return int(np.count_nonzero(a[r0:r1, c0:c1] & b[r0:r1, c0:c1]))


class Relations:
    """What the first masks say about each other (module docstring, Relations)."""

    def __init__(
        self,
        nested: dict[str, str],
        shared: list[set[str]],
        inside: dict[str, dict[str, float]],
        iou: dict[str, dict[str, float]],
        alike: list[set[str]] | None = None,
    ) -> None:
        self.nested = nested  # child -> parent
        self.shared = shared  # groups of two or more parts, by IoU or by Spark
        self.inside = inside  # part -> {other: share of part's mask inside other's}
        self.iou = iou  # part -> {other: IoU}
        self.alike = alike or []  # the groups by IoU alone: near-identical masks


def relate(masks: Mapping[str, Mask], spark_shared: Iterable[Iterable[str]] = ()) -> Relations:
    """Nesting and shared regions among the masks. spark_shared are the groups Spark marked
    shares_region; their parts join the shared groups whether or not they have masks."""
    sizes = {p: int(m.sum()) for p, m in masks.items()}
    boxes = {p: _box(m) for p, m in masks.items()}
    inside: dict[str, dict[str, float]] = {p: {} for p in masks}
    iou: dict[str, dict[str, float]] = {p: {} for p in masks}
    pairs: list[tuple[str, str]] = []
    for a, b in combinations(masks, 2):
        ba, bb = boxes[a], boxes[b]
        if ba is None or bb is None:
            continue
        both = _shared_px(masks[a], masks[b], ba, bb)
        if not both:
            continue
        j = both / (sizes[a] + sizes[b] - both)
        for x, y in ((a, b), (b, a)):
            if both / sizes[x] >= RECORD_SHARE:
                inside[x][y] = round(both / sizes[x], 4)
            if j >= RECORD_SHARE:
                iou[x][y] = round(j, 4)
        if j >= SHARED_IOU:
            pairs.append((a, b))
    shared = _groups([*pairs, *(tuple(g) for g in spark_shared)])
    mates = {p: g for g in shared for p in g}
    nested: dict[str, str] = {}
    for child, shares in inside.items():
        holders = [
            q
            for q, share in shares.items()
            if share >= NEST_INSIDE and sizes[q] > sizes[child] and q not in mates.get(child, ())
        ]
        if holders:
            nested[child] = min(holders, key=lambda q: (sizes[q], list(masks).index(q)))
    return Relations(nested=nested, shared=shared, inside=inside, iou=iou, alike=_groups(pairs))


def inside_share(a: Mask, b: Mask) -> float:
    """The share of a's pixels inside b."""
    ba, bb = _box(a), _box(b)
    if ba is None or bb is None:
        return 0.0
    return _shared_px(a, b, ba, bb) / int(a.sum())


def children_by_geometry(part: str, mask: Mask, others: Mapping[str, Mask]) -> set[str]:
    """The other parts whose masks are smaller than mask and NEST_INSIDE or more inside it:
    nested in it, as children or deeper."""
    size = int(mask.sum())
    return {
        q
        for q, m in others.items()
        if q != part and int(m.sum()) < size and inside_share(m, mask) >= NEST_INSIDE
    }


def _groups(links: Iterable[Sequence[str]]) -> list[set[str]]:
    """Connected groups of the linked names, in first-seen order."""
    groups: list[set[str]] = []
    for link in links:
        names = set(link)
        if len(names) < _GROUP_MIN:
            continue
        touching = [g for g in groups if g & names]
        for g in touching:
            names |= g
            groups.remove(g)
        groups.append(names)
    return groups


def descendants(part: str, nested: Mapping[str, str]) -> set[str]:
    out: set[str] = set()
    todo = [part]
    while todo:
        cur = todo.pop()
        for child, parent in nested.items():
            if parent == cur and child not in out and child != part:
                out.add(child)
                todo.append(child)
    return out


Resolved = tuple[
    dict[str, Mask], dict[str, dict[str, int]], dict[str, dict[str, int]], dict[str, int]
]


def resolve(
    masks: Mapping[str, Mask],
    points: Mapping[str, Sequence[Point]],
    floor_px: float,
    nested: Mapping[str, str] | None = None,
    alike: Sequence[AbstractSet[str]] = (),
) -> Resolved:
    """Contested pixels to the smallest mask, ties to the nearer prompt point. Then, within
    each group of near-identical masks, a pixel the group won goes to whichever member
    claiming it has the nearer point. A nested child's pixels stay in its parent too.
    Returns the masks, the pixels each part lost to and won from each other part, and the
    pixels each lost to specks left by the resolution."""
    if not masks:
        return {}, {}, {}, {}
    nested = nested or {}
    order = list(masks)
    shape = masks[order[0]].shape
    span = float(np.hypot(*shape)) + 1  # a distance never outweighs one pixel of size
    best = np.full(shape, np.inf, np.float64)
    owner = np.full(shape, -1, np.int32)
    dists: dict[str, npt.NDArray[np.float64]] = {}
    for i, p in enumerate(order):
        seeds = np.ones(shape, np.uint8)
        for x, y in points.get(p, []):
            seeds[y, x] = 0
        dist = (
            np.asarray(cv2.distanceTransform(seeds, cv2.DIST_L2, 5), np.float64)
            if not seeds.all()
            else np.full(shape, span)
        )
        if any(p in g for g in alike):
            dists[p] = dist
        cost = int(masks[p].sum()) + dist / span
        take = masks[p] & (cost < best)
        owner[take] = i
        best[take] = cost[take]
    for g in alike:
        members = [p for p in order if p in g]
        won = np.isin(owner, [order.index(p) for p in members])
        near = np.full(shape, np.inf, np.float64)
        for p in members:
            take = won & masks[p] & (dists[p] < near)
            owner[take] = order.index(p)
            near[take] = dists[p][take]
    out: dict[str, Mask] = {}
    lost: dict[str, dict[str, int]] = {}
    won_from: dict[str, dict[str, int]] = {}
    respeck: dict[str, int] = {}
    for i, p in enumerate(order):
        kin = descendants(p, nested)
        kids = [order.index(c) for c in kin if c in masks]
        mine = (owner == i) | (masks[p] & np.isin(owner, kids)) if kids else owner == i
        ids, counts = np.unique(owner[masks[p] & ~mine], return_counts=True)
        lost[p] = {order[int(j)]: int(c) for j, c in zip(ids, counts, strict=True)}
        won_from[p] = {}
        for j, q in enumerate(order):
            if j != i and q not in kin and (c := int((mine & masks[q]).sum())):
                won_from[p][q] = c
        cleaned = drop_specks(mine, floor_px)
        respeck[p] = int(mine.sum() - cleaned.sum())
        out[p] = cleaned
    return out, lost, won_from, respeck


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
