"""S1 understand: Muse Spark reads the figure. More than max_parts parts are cut, keeping
the first ones. Live, a second call plans each part for touch on this sheet and locates it
(app/meta/live_client.py), so S1 depends on the grade band and the page."""

import logging
from pathlib import Path

from app.config import TactileRules
from app.geometry.scale import PageFit
from app.meta.client import MetaClient
from app.meta.types import LISTING_SCHEMA, LOCATE_SCHEMA, SheetContext, Understanding
from app.models.regions import GradeBand
from app.pipeline.s0_ingest import Ingested
from app.prompts import Prompt, schema_digest

log = logging.getLogger(__name__)

PROMPT = "s1_understand.v1.json"
LOCATE_PROMPT = "s1_locate.v2.json"
SCHEMA_DIGEST = schema_digest(
    {
        "understanding": Understanding.model_json_schema(),
        "listing": LISTING_SCHEMA,
        "locate": LOCATE_SCHEMA,
    }
)
_FILE = "understanding.json"
_READERS: dict[GradeBand, str] = {
    "k5": " in grades K to 5",
    "6_8": " in grades 6 to 8",
    "9_12": " in grades 9 to 12",
    "college": " in college",
}


def sheet_context(
    ing: Ingested, fit: PageFit, grade_band: GradeBand | None, rules: TactileRules
) -> SheetContext:
    h, w = ing.image.shape[:2]
    return SheetContext(
        reader="" if grade_band is None else _READERS[grade_band],
        width_mm=w * fit.mm_per_px,
        height_mm=h * fit.mm_per_px,
        min_part_mm=rules.spacing.point_symbol_min_mm,
        gap_mm=rules.spacing.min_gap_mm,
    )


async def understand(
    client: MetaClient,
    ing: Ingested,
    prompt: Prompt,
    locate: Prompt,
    sheet: SheetContext,
    rules: TactileRules,
) -> Understanding:
    u = await client.understand(ing.image, ing.figure_id, prompt, locate, sheet)
    if len(u.parts) > rules.meta.max_parts:
        log.warning("S1 proposed %d parts, keeping %d", len(u.parts), rules.meta.max_parts)
        u = u.model_copy(update={"parts": u.parts[: rules.meta.max_parts]})
    return u


def save(u: Understanding, out: Path) -> None:
    (out / _FILE).write_text(u.model_dump_json(indent=1), "utf-8")


def load(src: Path) -> Understanding:
    return Understanding.model_validate_json((src / _FILE).read_text("utf-8"))
