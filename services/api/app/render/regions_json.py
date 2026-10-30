"""regions.json from a laid-out sheet: the file Explore runs from.

Parts S2 or S3 could not make touchable go in too, for the teacher: a spill mask as a
suggestion region with touchable false, and a part with no shape in needs_teacher."""

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet

from pydantic import BaseModel, ConfigDict

from app.braille.place import BrailleLayout
from app.config import TactileRules
from app.geometry.layout import LayoutRegion
from app.geometry.neighbors import centroids, find_neighbors
from app.geometry.sheet import Sheet
from app.models.mask import region_source
from app.models.regions import (
    FigureType,
    Flag,
    Page,
    PointMm,
    Region,
    RegionsFile,
    TeacherEntry,
)


class Suggestion(BaseModel):
    """A spill mask, outlined in page mm, for the teacher."""

    model_config = ConfigDict(frozen=True)

    label: str
    polygons_mm: list[list[tuple[float, float]]]
    detail: str


class TeacherInfo(BaseModel):
    """What S2 and S3 left to the teacher, and S2's flags on touchable parts."""

    model_config = ConfigDict(frozen=True)

    flags: dict[str, list[Flag]] = {}  # by reconciled part id
    suggestions: list[Suggestion] = []
    needs_teacher: list[TeacherEntry] = []


class FigureInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    figure_id: str
    title: str
    figure_type: FigureType
    summary: str


def build_regions_file(
    sheet: Sheet,
    braille: BrailleLayout,
    info: FigureInfo,
    rules: TactileRules,
    descriptions: Mapping[str, str] | None = None,
    verified: AbstractSet[str] = frozenset(),
    teacher: TeacherInfo | None = None,
) -> RegionsFile:
    """descriptions and verified come from teacher edits, keyed by reconciled part id; every
    piece of a part shares them, and so do S2's flags in teacher."""
    descriptions = descriptions or {}
    teacher = teacher or TeacherInfo()
    d = rules.render.coordinate_decimals
    width, height = rules.page.dimensions_mm[sheet.page]
    abbrev = {p.region_id: p.line.text for p in braille.placements if p.kind == "abbrev"}
    centers = centroids(sheet.regions, rules.layout.inside_point_tolerance_mm)
    neighbors = find_neighbors(sheet.regions, rules.layout.neighbor_max_gap_mm)
    regions: list[Region] = []
    for r in sheet.regions:
        pts = ring_mm(list(r.polygon.exterior.coords)[:-1], d)
        cx, cy = centers[r.id]
        flags = region_flags(r, teacher)
        optional = {
            "abbrev": abbrev.get(r.id),
            "texture": r.texture,
            "description": descriptions.get(r.group_key),
        }
        regions.append(
            Region(
                id=r.id,
                label=r.label,
                polygon_mm=pts,
                centroid_mm=(round(cx, d), round(cy, d)),
                parent=r.parent,
                neighbors=neighbors[r.id],
                source=region_source(r.source),
                confidence=r.score,
                verified_by_teacher=r.group_key in verified,
                touchable=True,
                # The schema allows these to be missing but not null.
                **{k: v for k, v in optional.items() if v is not None},
                **({"flags": flags} if flags else {}),
            )
        )
    regions += suggestion_regions(teacher.suggestions, {r.id for r in regions}, d)
    return RegionsFile(
        schema_version=2,
        figure_id=info.figure_id,
        title=info.title,
        figure_type=info.figure_type,
        page=Page(size=sheet.page, width_mm=width, height_mm=height),
        summary=info.summary,
        textures=sheet.textures,
        regions=regions,
        needs_teacher=teacher.needs_teacher,
        # Like the region fields above: the schema allows grade_band missing, not null.
        **({} if sheet.grade_band is None else {"grade_band": sheet.grade_band}),
    )


def ring_mm(coords: Sequence[Sequence[float]], decimals: int) -> list[PointMm]:
    """A polygon ring rounded for regions.json, with repeated points left out."""
    pts: list[PointMm] = []
    for x, y in coords:
        pt = (round(x, decimals), round(y, decimals))
        if not pts or pts[-1] != pt:
            pts.append(pt)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def region_flags(r: LayoutRegion, teacher: TeacherInfo) -> list[Flag]:
    flags = list(teacher.flags.get(r.group_key, []))
    if r.kind == "point":
        flags.append(
            Flag(
                reason="under_point_symbol",
                detail="smaller than a point symbol, so the sheet shows it as one",
            )
        )
    return flags


def suggestion_regions(
    suggestions: list[Suggestion], taken: AbstractSet[str], decimals: int
) -> list[Region]:
    """One untouchable region per piece of each suggestion, ids s1, s2 and on."""
    out: list[Region] = []
    n = 0
    for sug in suggestions:
        for poly in sug.polygons_mm:
            pts = ring_mm(poly, decimals)
            if len(pts) < 3:  # noqa: PLR2004 - a polygon needs three points
                continue
            n += 1
            while f"s{n}" in taken:
                n += 1
            out.append(
                Region(
                    id=f"s{n}",
                    label=sug.label,
                    polygon_mm=pts,
                    parent=None,
                    source="sam",
                    verified_by_teacher=False,
                    touchable=False,
                    flags=[Flag(reason="spill", detail=sug.detail)],
                )
            )
    return out
