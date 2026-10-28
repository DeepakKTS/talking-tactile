"""S2 ground: one SAM call per proposed phrase, sam_concurrency at a time, plus one for
print text so it can be cut out of the raised layer."""

import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import Meta
from app.meta.client import MetaClient
from app.meta.types import Understanding
from app.models.mask import Mask, MaskSource
from app.pipeline.cache import load_mask, save_mask
from app.pipeline.s0_ingest import Ingested
from app.prompts import Prompt, schema_digest

PROMPT = "s2_ground.v1.json"
_FILE = "grounded.json"


class MaskEntry(BaseModel):
    """One mask as the cache stores it, beside its PNG."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["part", "text"]
    file: str
    label: str
    score: float
    source: MaskSource


SCHEMA_DIGEST = schema_digest(MaskEntry.model_json_schema())


class Grounded(BaseModel):
    model_config = ConfigDict(frozen=True)

    parts: list[Mask]  # in phrase order, then SAM's instance order
    text: list[Mask]


async def ground(
    client: MetaClient, ing: Ingested, u: Understanding, prompt: Prompt, rules: Meta
) -> Grounded:
    phrases = [p for p in dict.fromkeys(p.phrase for p in u.parts) if p != rules.text_phrase]
    gate = asyncio.Semaphore(rules.sam_concurrency)

    async def one(phrase: str) -> list[Mask]:
        async with gate:
            return await client.segment(ing.image, ing.figure_id, phrase, prompt)

    found = await asyncio.gather(*(one(p) for p in [*phrases, rules.text_phrase]))
    return Grounded(parts=[m for masks in found[:-1] for m in masks], text=found[-1])


def save(g: Grounded, out: Path) -> None:
    entries: list[MaskEntry] = []
    for kind, masks in (("part", g.parts), ("text", g.text)):
        for i, m in enumerate(masks):
            name = f"{kind}{i:03d}.png"
            save_mask(out / name, m.data)
            entries.append(
                MaskEntry(kind=kind, file=name, label=m.label, score=m.score, source=m.source)
            )
    (out / _FILE).write_text(json.dumps([e.model_dump() for e in entries], indent=1), "utf-8")


def load(src: Path) -> Grounded:
    masks: dict[str, list[Mask]] = {"part": [], "text": []}
    for obj in json.loads((src / _FILE).read_text("utf-8")):
        e = MaskEntry.model_validate(obj)
        mask = Mask(data=load_mask(src / e.file), label=e.label, score=e.score, source=e.source)
        masks[e.kind].append(mask)
    return Grounded(parts=masks["part"], text=masks["text"])
