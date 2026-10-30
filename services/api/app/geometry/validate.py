"""The tactile rules check (.claude/skills/tactile-rules-check). Reports every violation
with the regions involved, the rule, the measured value and the limit. It never fixes or
loosens anything: fixes belong in the geometry stages.

Checks: ids and parents, polygon validity and the point cap, inside the figure area, the
minimum gap between outlines and inside a parent, the point symbol size, the area texture
count for the grade band, and braille: clearance to every line, the gap between braille
blocks, and never sitting on another part. SVG ids are checked with the render stage.
"""

import itertools
from collections import Counter

from pydantic import BaseModel, ConfigDict
from shapely.geometry import box
from shapely.ops import unary_union

from app.config import TactileRules
from app.geometry.layout import LayoutRegion, size_mm
from app.geometry.sheet import Sheet
from app.models.regions import MAX_POLYGON_POINTS, MIN_POLYGON_POINTS, RegionsFile
from app.render.svg import sheet_ids

_EPS = 1e-6


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    regions: list[str]
    measured: float
    limit: float
    message: str


def _ids(sheet: Sheet) -> list[Violation]:
    out: list[Violation] = []
    counts = Counter(r.id for r in sheet.regions)
    for rid, n in counts.items():
        if n > 1:
            out.append(
                Violation(
                    rule="ids",
                    regions=[rid],
                    measured=n,
                    limit=1,
                    message=f"region id {rid} is used {n} times",
                )
            )
    for r in sheet.regions:
        if r.parent is not None and r.parent not in counts:
            out.append(
                Violation(
                    rule="ids",
                    regions=[r.id],
                    measured=0,
                    limit=1,
                    message=f"{r.id} has parent {r.parent}, which does not exist",
                )
            )
    return out


def _polygons(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    out: list[Violation] = []
    ax, ay, aw, ah = rules.page.figure_area_mm(sheet.page)
    area = box(ax, ay, ax + aw, ay + ah).buffer(_EPS)
    for r in sheet.regions:
        n = len(r.polygon.exterior.coords) - 1
        if not r.polygon.is_valid or not MIN_POLYGON_POINTS <= n <= MAX_POLYGON_POINTS:
            out.append(
                Violation(
                    rule="polygon",
                    regions=[r.id],
                    measured=n,
                    limit=MAX_POLYGON_POINTS,
                    message=f"{r.id} has {n} points or is not a valid polygon",
                )
            )
        if not r.polygon.within(area):
            outside = float(r.polygon.difference(area).area)
            out.append(
                Violation(
                    rule="inside_page",
                    regions=[r.id],
                    measured=outside,
                    limit=0,
                    message=f"{r.id} has {outside:.1f} mm2 outside the figure area",
                )
            )
    return out


def _ancestors(by_id: dict[str, LayoutRegion], rid: str) -> set[str]:
    out: set[str] = set()
    cur = by_id[rid].parent
    while cur is not None and cur in by_id and cur not in out:
        out.add(cur)
        cur = by_id[cur].parent
    return out


def _gaps(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    gap = rules.spacing.min_gap_mm
    # Outlines are drawn inside each part's edge: a child needs the line width extra.
    nested_gap = gap + rules.render.outline_width_mm
    by_id = {r.id: r for r in sheet.regions}
    out: list[Violation] = []
    for a, b in itertools.combinations(sheet.regions, 2):
        if a.id == b.id:
            continue
        if a.id in _ancestors(by_id, b.id) or b.id in _ancestors(by_id, a.id):
            parent, child = (a, b) if a.id in _ancestors(by_id, b.id) else (b, a)
            inside = child.polygon.within(parent.polygon)
            d = float(parent.polygon.exterior.distance(child.polygon)) if inside else 0.0
            where = f"{d:.2f} mm inside" if inside else "partly outside"
            msg = f"{child.id} is {where} its parent {parent.id}"
            ids, need = [parent.id, child.id], nested_gap
        else:
            d = float(a.polygon.distance(b.polygon))
            msg = f"{a.id} and {b.id} are {d:.2f} mm apart"
            ids, need = [a.id, b.id], gap
        if d < need - _EPS:
            out.append(
                Violation(
                    rule="min_gap",
                    regions=ids,
                    measured=d,
                    limit=need,
                    message=f"{msg}, the minimum is {need} mm",
                )
            )
    return out


def _point_sizes(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    minimum = rules.spacing.point_symbol_min_mm
    out: list[Violation] = []
    for r in sheet.regions:
        if r.kind == "point":
            measured = 2 * float(r.polygon.centroid.distance(r.polygon.exterior))
            what = "point symbol is"
        else:
            measured = size_mm(r.polygon)
            what = "area is"
        if measured < minimum - _EPS:
            out.append(
                Violation(
                    rule="point_symbol",
                    regions=[r.id],
                    measured=measured,
                    limit=minimum,
                    message=f"{r.id}: {what} {measured:.1f} mm across, the minimum is {minimum} mm",
                )
            )
    return out


def _textures(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    out: list[Violation] = []
    listed = {t.id for t in sheet.textures}
    used = {r.texture for r in sheet.regions if r.texture is not None}
    for r in sheet.regions:
        if r.texture is not None and r.texture not in listed:
            out.append(
                Violation(
                    rule="texture_unknown",
                    regions=[r.id],
                    measured=0,
                    limit=0,
                    message=f"{r.id} uses {r.texture}, which is not in the key",
                )
            )
        if r.kind == "point" and r.texture is not None:
            out.append(
                Violation(
                    rule="texture_on_point",
                    regions=[r.id],
                    measured=1,
                    limit=0,
                    message=f"point symbol {r.id} has an area texture",
                )
            )
    count = len(listed | used)
    limit = rules.textures.limit_for(sheet.grade_band)
    if count > limit:
        out.append(
            Violation(
                rule="texture_count",
                regions=[],
                measured=count,
                limit=limit,
                message=f"{count} area textures, the limit for grade band "
                f"{sheet.grade_band} is {limit}",
            )
        )
    return out


def _braille(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    if not sheet.braille:
        return []
    clearance = rules.braille.clearance_to_line_mm + rules.render.outline_width_mm
    gap = rules.spacing.min_gap_mm
    ax, ay, aw, ah = rules.page.figure_area_mm(sheet.page)
    area = box(ax, ay, ax + aw, ay + ah).buffer(_EPS)
    by_id = {r.id: r for r in sheet.regions}
    lines = unary_union([r.polygon.exterior for r in sheet.regions])
    out: list[Violation] = []
    for p in sheet.braille:
        rect, rid = p.line.rect, p.region_id
        if not rect.within(area):
            out.append(
                Violation(
                    rule="inside_page",
                    regions=[rid],
                    measured=0,
                    limit=0,
                    message=f"braille for {rid} is outside the figure area",
                )
            )
        d = float(rect.distance(lines))
        if d < clearance - _EPS:
            out.append(
                Violation(
                    rule="braille_clearance",
                    regions=[rid],
                    measured=d,
                    limit=clearance,
                    message=f"braille for {rid} is {d:.2f} mm from a line, "
                    f"the minimum is {clearance} mm",
                )
            )
        allowed = (_ancestors(by_id, rid) if rid in by_id else set()) | (
            {rid} if p.inside else set()
        )
        for q in sheet.regions:
            if q.id not in allowed and rect.intersects(q.polygon):
                out.append(
                    Violation(
                        rule="braille_overlap",
                        regions=[rid, q.id],
                        measured=1,
                        limit=0,
                        message=f"braille for {rid} sits on {q.id}",
                    )
                )
    for a, b in itertools.combinations(sheet.braille, 2):
        d = float(a.line.rect.distance(b.line.rect))
        if d < gap - _EPS:
            out.append(
                Violation(
                    rule="braille_gap",
                    regions=[a.region_id, b.region_id],
                    measured=d,
                    limit=gap,
                    message=f"braille for {a.region_id} and {b.region_id} is "
                    f"{d:.2f} mm apart, the minimum is {gap} mm",
                )
            )
    return out


def check_svg_ids(svg: str, regions_file: RegionsFile) -> list[Violation]:
    """Every touchable region in regions.json is drawn in tactile.svg, and the reverse. A
    teacher suggestion (touchable false) is not raised, so it is not drawn."""
    drawn = set(sheet_ids(svg))
    listed = {r.id for r in regions_file.regions if r.touchable}
    out: list[Violation] = []
    for rid in sorted(listed - drawn):
        out.append(
            Violation(
                rule="svg_ids",
                regions=[rid],
                measured=0,
                limit=1,
                message=f"{rid} is in regions.json but not drawn in tactile.svg",
            )
        )
    for rid in sorted(drawn - listed):
        out.append(
            Violation(
                rule="svg_ids",
                regions=[rid],
                measured=1,
                limit=0,
                message=f"{rid} is drawn in tactile.svg but not in regions.json",
            )
        )
    return out


def validate_sheet(sheet: Sheet, rules: TactileRules) -> list[Violation]:
    return [
        *_ids(sheet),
        *_polygons(sheet, rules),
        *_gaps(sheet, rules),
        *_point_sizes(sheet, rules),
        *_textures(sheet, rules),
        *_braille(sheet, rules),
    ]
