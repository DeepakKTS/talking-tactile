"""S1 understand: Muse Spark reads the figure. More than max_parts parts are cut, keeping
the first ones. Live, a second call locates each part (app/meta/live_client.py)."""

import logging
from pathlib import Path

from app.config import Meta
from app.meta.client import MetaClient
from app.meta.types import LISTING_SCHEMA, LOCATE_SCHEMA, Understanding
from app.pipeline.s0_ingest import Ingested
from app.prompts import Prompt, schema_digest

log = logging.getLogger(__name__)

PROMPT = "s1_understand.v1.json"
LOCATE_PROMPT = "s1_locate.v1.json"
SCHEMA_DIGEST = schema_digest(
    {
        "understanding": Understanding.model_json_schema(),
        "listing": LISTING_SCHEMA,
        "locate": LOCATE_SCHEMA,
    }
)
_FILE = "understanding.json"


async def understand(
    client: MetaClient, ing: Ingested, prompt: Prompt, locate: Prompt, rules: Meta
) -> Understanding:
    u = await client.understand(ing.image, ing.figure_id, prompt, locate)
    if len(u.parts) > rules.max_parts:
        log.warning("S1 proposed %d parts, keeping %d", len(u.parts), rules.max_parts)
        u = u.model_copy(update={"parts": u.parts[: rules.max_parts]})
    return u


def save(u: Understanding, out: Path) -> None:
    (out / _FILE).write_text(u.model_dump_json(indent=1), "utf-8")


def load(src: Path) -> Understanding:
    return Understanding.model_validate_json((src / _FILE).read_text("utf-8"))
