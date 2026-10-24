"""Places braille on a laid-out sheet, in this order for each part:

1. the full label on the part,
2. its abbreviation on the part,
3. its abbreviation beside the part (within max_outside_offset_mm),
4. nothing on the sheet: the part is listed as key only for the teacher to review.

Every braille block keeps clearance_to_line_mm from every raised line (the part's edge plus
the outline width drawn inside it), min_gap_mm from
other braille, stays in the figure area, and never sits on a part other than its own (or
one that contains it). Abbreviations used on the sheet are listed in the key. Pure: the
translations are made beforehand by translate_for_sheet.
"""

from typing import Literal

import numpy as np
import shapely
from pydantic import BaseModel, ConfigDict
from shapely.geometry import box
from shapely.ops import unary_union

from app.braille.abbrev import abbreviations
from app.braille.cells import block_size
from app.braille.louis import Translator
from app.braille.models import BrailleLine, KeyEntry, Placement
from app.config import Braille, TactileRules
from app.geometry.layout import LayoutRegion, inside_point
from app.geometry.sheet import Sheet

_EPS = 1e-9


class Translations(BaseModel):
    model_config = ConfigDict(frozen=True)

    abbrevs: dict[str, str]  # label -> abbreviation
    braille: dict[str, str]  # print text -> Unicode braille, for labels and abbreviations


class BrailleLayout(BaseModel):
    model_config = ConfigDict(frozen=True)

    placements: list[Placement]
    key: list[KeyEntry]
    key_only: list[str]  # region ids with no braille on the sheet


KEY_TITLE = "key"


def translate_for_sheet(sheet: Sheet, translator: Translator, rules: Braille) -> Translations:
    """Braille for every label, abbreviation and texture meaning, and the key page title."""
    labels = list(dict.fromkeys(r.label for r in sheet.regions))
    abbrevs = abbreviations(labels, rules.abbrev_letters)
    meanings = [t.meaning for t in sheet.textures]
    texts = list(dict.fromkeys([*labels, *abbrevs.values(), *meanings, KEY_TITLE]))
    return Translations(
        abbrevs=abbrevs, braille=dict(zip(texts, translator.translate(texts), strict=True))
    )


class _Placer:
    def __init__(self, sheet: Sheet, t: Translations, rules: TactileRules) -> None:
        self.t = t
        self.b = rules.braille
        self.gap = rules.spacing.min_gap_mm
        # Outlines are drawn inside each part's edge, so braille keeps the line width extra.
        self.clearance = rules.braille.clearance_to_line_mm + rules.render.outline_width_mm
        ax, ay, aw, ah = rules.page.figure_area_mm(sheet.page)
        self.area = box(ax, ay, ax + aw, ay + ah)
        self.regions = sheet.regions
        self.by_id = {r.id: r for r in sheet.regions}
        self.lines = unary_union([r.polygon.exterior for r in sheet.regions])
        shapely.prepare(self.lines)
        self.placed: list[Placement] = []

    def ancestors(self, rid: str) -> set[str]:
        out: set[str] = set()
        cur = self.by_id[rid].parent
        while cur is not None and cur in self.by_id and cur not in out:
            out.add(cur)
            cur = self.by_id[cur].parent
        return out

    def search(self, r: LayoutRegion, text: str, inside: bool) -> BrailleLine | None:
        cells = self.t.braille[text]
        w, h = block_size(len(cells), self.b)
        step = self.b.search_step_mm
        clearance = self.clearance
        domain: shapely.Geometry
        if inside:
            domain = r.polygon.buffer(-clearance)
        else:
            domain = r.polygon.buffer(self.b.max_outside_offset_mm + max(w, h)) & self.area
        if domain.is_empty:
            return None
        minx, miny, maxx, maxy = domain.bounds
        xs = np.arange(minx, maxx - w + _EPS, step)
        ys = np.arange(miny, maxy - h + _EPS, step)
        if xs.size == 0 or ys.size == 0:
            return None
        gx, gy = (a.ravel() for a in np.meshgrid(xs, ys))
        rects = shapely.box(gx, gy, gx + w, gy + h)

        keep = shapely.within(rects, self.area)
        if inside:
            keep &= shapely.within(rects, r.polygon)
        else:
            keep &= shapely.distance(rects, r.polygon) <= self.b.max_outside_offset_mm
        allowed = self.ancestors(r.id) | ({r.id} if inside else set())
        blocked = [q.polygon for q in self.regions if q.id not in allowed]
        if blocked:
            keep[keep] = ~shapely.intersects(rects[keep], unary_union(blocked))
        if keep.any():
            keep[keep] = shapely.distance(rects[keep], self.lines) >= clearance - _EPS
        if self.placed and keep.any():
            others = unary_union([p.line.rect for p in self.placed])
            keep[keep] = shapely.distance(rects[keep], others) >= self.gap - _EPS
        if not keep.any():
            return None

        idx = np.flatnonzero(keep)
        if inside:
            ax, ay = inside_point(r.polygon, step)
            cx, cy = gx[idx] + w / 2, gy[idx] + h / 2
            cost = np.hypot(cx - ax, cy - ay)
        else:
            cost = shapely.distance(rects[idx], r.polygon)
        best = idx[np.lexsort((gx[idx], gy[idx], np.round(cost, 6)))[0]]
        return BrailleLine(text=text, braille=cells, x_mm=float(gx[best]), y_mm=float(gy[best]),
                           width_mm=w, height_mm=h)  # fmt: skip

    def add(
        self, r: LayoutRegion, kind: Literal["label", "abbrev"], line: BrailleLine, inside: bool
    ) -> None:
        self.placed.append(Placement(region_id=r.id, kind=kind, inside=inside, line=line))


def place_braille(sheet: Sheet, t: Translations, rules: TactileRules) -> BrailleLayout:
    p = _Placer(sheet, t, rules)
    beside: list[LayoutRegion] = []
    for r in sheet.regions:
        if r.kind == "area":
            line = p.search(r, r.label, inside=True)
            if line is not None:
                p.add(r, "label", line, inside=True)
                continue
            line = p.search(r, t.abbrevs[r.label], inside=True)
            if line is not None:
                p.add(r, "abbrev", line, inside=True)
                continue
        beside.append(r)
    key_only: list[str] = []
    for r in beside:
        line = p.search(r, t.abbrevs[r.label], inside=False)
        if line is None:
            key_only.append(r.id)
        else:
            p.add(r, "abbrev", line, inside=False)

    key: list[KeyEntry] = []
    keyed: set[str] = set()
    for placement in p.placed:
        label = p.by_id[placement.region_id].label
        if placement.kind == "abbrev" and label not in keyed:
            keyed.add(label)
            abbrev = t.abbrevs[label]
            key.append(KeyEntry(abbrev=abbrev, abbrev_braille=t.braille[abbrev], label=label,
                                label_braille=t.braille[label]))  # fmt: skip
    return BrailleLayout(placements=p.placed, key=key, key_only=key_only)
