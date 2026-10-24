"""S4 layout on S3's parts with the teacher's edits applied: polygons in page mm, point
symbols, gaps, textures and braille. Polygons are cached as WKB, so a sheet read back is the
sheet that was saved."""

import json
from collections.abc import Sequence
from pathlib import Path

import shapely
from shapely.geometry import Polygon

from app.braille.louis import Translator
from app.braille.models import Placement
from app.braille.place import BrailleLayout, Translations
from app.config import Earcons, TactileRules
from app.geometry.compose import ComposedSheet, build_sheet
from app.geometry.layout import LayoutRegion
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.sheet import Sheet
from app.meta.types import Understanding
from app.models.regions import GradeBand, Texture
from app.pipeline.s0_ingest import Ingested

_FILE = "sheet.json"


def layout(
    parts: Sequence[ReconciledPart],
    ing: Ingested,
    u: Understanding,
    fit: PageFit,
    grade_band: GradeBand | None,
    rules: TactileRules,
    earcons: Earcons,
    translator: Translator,
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
    )


def save(c: ComposedSheet, out: Path) -> None:
    regions = [
        {
            **r.model_dump(mode="json", exclude={"polygon"}),
            "polygon_wkb": shapely.to_wkb(r.polygon, hex=True),
        }
        for r in c.sheet.regions
    ]
    obj = {
        "sheet": {**c.sheet.model_dump(mode="json", exclude={"regions"}), "regions": regions},
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


def load(src: Path) -> ComposedSheet:
    obj = json.loads((src / _FILE).read_text("utf-8"))
    s = obj["sheet"]
    sheet = Sheet(
        page=s["page"],
        grade_band=s["grade_band"],
        regions=[_region(r) for r in s["regions"]],
        textures=[Texture.model_validate(t) for t in s["textures"]],
        braille=[Placement.model_validate(p) for p in s["braille"]],
    )
    return ComposedSheet(
        sheet=sheet,
        braille=BrailleLayout.model_validate(obj["braille"]),
        translations=Translations.model_validate(obj["translations"]),
        unresolved_gaps=[(a, b) for a, b in obj["unresolved_gaps"]],
    )
