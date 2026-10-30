"""S4 layout on S3's parts with the teacher's edits applied: polygons in page mm, point
symbols, gaps, textures and braille, and S1's plan: line parts, merge proposals and the
subject's silhouette from S2. Polygons are cached as WKB, so a sheet read back is the
sheet that was saved."""

import json
from collections.abc import Sequence
from pathlib import Path

import shapely
from shapely.geometry import LineString, Polygon

from app.braille.louis import Translator
from app.braille.models import Placement
from app.braille.place import BrailleLayout, Translations
from app.config import Earcons, TactileRules
from app.geometry import plan
from app.geometry.compose import ComposedSheet, build_sheet
from app.geometry.layout import LayoutRegion
from app.geometry.plan import SheetPlan
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.sheet import Sheet, SheetLine, SheetMerge
from app.meta.types import Understanding
from app.models.regions import GradeBand, Texture
from app.pipeline.s0_ingest import Ingested
from app.pipeline.s2_types import Grounded

_FILE = "sheet.json"
_PLAN = {"lines", "merges", "subject"}


def sheet_plan(
    u: Understanding,
    g: Grounded,
    before: Sequence[ReconciledPart],
    parts: Sequence[ReconciledPart],
) -> SheetPlan:
    """S1's lines and S2's merge proposals on the parts as edited, and the silhouette."""
    ids = plan.part_ids([p.phrase for p in u.parts], before, parts)
    labels = {p.id: p.mask.label for p in parts}
    merges = [(m.parts, m.name, m.why) for m in g.merges]
    return SheetPlan(
        subject=u.subject,
        silhouette=g.silhouette,
        lines=plan.sheet_lines(u, ids, labels),
        merges=plan.sheet_merges(merges, ids),
    )


def layout(  # noqa: PLR0913  the stage's inputs, each from the runner
    parts: Sequence[ReconciledPart],
    ing: Ingested,
    u: Understanding,
    fit: PageFit,
    grade_band: GradeBand | None,
    rules: TactileRules,
    earcons: Earcons,
    translator: Translator,
    *,
    sheet_plan: SheetPlan | None = None,
) -> ComposedSheet:
    return build_sheet(
        parts=parts,
        image=ing.image,
        fit=fit,
        grade_band=grade_band,
        color_carries_meaning=u.color_carries_meaning,
        rules=rules,
        earcons=earcons,
        translator=translator,
        plan=sheet_plan,
    )


def save(c: ComposedSheet, out: Path) -> None:
    regions = [
        {
            **r.model_dump(mode="json", exclude={"polygon"}),
            "polygon_wkb": shapely.to_wkb(r.polygon, hex=True),
        }
        for r in c.sheet.regions
    ]
    s = c.sheet
    plan_fields = {
        "lines": [x.model_dump(mode="json") for x in s.lines],
        "merges": [x.model_dump(mode="json") for x in s.merges],
        "subject": s.subject,
        "silhouette_wkb": None if s.silhouette is None else shapely.to_wkb(s.silhouette, hex=True),
        "contour_wkb": [shapely.to_wkb(x, hex=True) for x in s.contour],
    }
    dumped = s.model_dump(mode="json", exclude={"regions", *_PLAN, "silhouette", "contour"})
    obj = {
        "sheet": {**dumped, "regions": regions, **plan_fields},
        "braille": c.braille.model_dump(mode="json"),
        "translations": c.translations.model_dump(mode="json"),
        "unresolved_gaps": c.unresolved_gaps,
    }
    (out / _FILE).write_text(json.dumps(obj, indent=1), "utf-8")


def _region(obj: dict[str, object]) -> LayoutRegion:
    polygon = shapely.from_wkb(str(obj.pop("polygon_wkb")))
    if not isinstance(polygon, Polygon):
        raise ValueError("a cached region is not a polygon")
    return LayoutRegion.model_validate({**obj, "polygon": polygon})


def _polygon(wkb: str | None) -> Polygon | None:
    if wkb is None:
        return None
    geom = shapely.from_wkb(wkb)
    if not isinstance(geom, Polygon):
        raise ValueError("a cached silhouette is not a polygon")
    return geom


def _line(wkb: str) -> LineString:
    geom = shapely.from_wkb(wkb)
    if not isinstance(geom, LineString):
        raise ValueError("a cached contour piece is not a line")
    return geom


def load(src: Path) -> ComposedSheet:
    obj = json.loads((src / _FILE).read_text("utf-8"))
    s = obj["sheet"]
    sheet = Sheet(
        page=s["page"],
        grade_band=s["grade_band"],
        regions=[_region(r) for r in s["regions"]],
        textures=[Texture.model_validate(t) for t in s["textures"]],
        braille=[Placement.model_validate(p) for p in s["braille"]],
        lines=[SheetLine.model_validate(x) for x in s.get("lines", [])],
        merges=[SheetMerge.model_validate(x) for x in s.get("merges", [])],
        subject=s.get("subject", ""),
        silhouette=_polygon(s.get("silhouette_wkb")),
        contour=[_line(x) for x in s.get("contour_wkb", [])],
    )
    return ComposedSheet(
        sheet=sheet,
        braille=BrailleLayout.model_validate(obj["braille"]),
        translations=Translations.model_validate(obj["translations"]),
        unresolved_gaps=[(a, b) for a, b in obj["unresolved_gaps"]],
    )
