"""S2 ground. When S1 located the parts (live), by points: app/pipeline/s2_points.py. Else
(mock mode), one SAM call per proposed phrase, sam_concurrency at a time, plus one for print
text so it can be cut out of the raised layer."""

import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import TactileRules
from app.meta.client import MetaClient
from app.meta.types import Understanding
from app.models.mask import Mask, MaskSource
from app.pipeline import s2_points
from app.pipeline.cache import load_mask, save_mask
from app.pipeline.s0_ingest import Ingested
from app.pipeline.s2_types import Grounded, MergeProposal, TeacherPart
from app.prompts import Prompt, schema_digest

__all__ = ["PROMPT", "SCHEMA_DIGEST", "Grounded", "TeacherPart", "ground", "load", "save"]

PROMPT = "s2_ground.v1.json"
_FILE = "grounded.json"
_NOTES = "teacher.json"
_SILHOUETTE = "silhouette.png"


class MaskEntry(BaseModel):
    """One mask as the cache stores it, beside its PNG."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["part", "text"]
    file: str
    label: str
    score: float
    source: MaskSource


SCHEMA_DIGEST = schema_digest(MaskEntry.model_json_schema())


async def ground(
    client: MetaClient, ing: Ingested, u: Understanding, prompt: Prompt, all_rules: TactileRules
) -> Grounded:
    if u.located:
        return await s2_points.ground_points(client, ing, u, prompt, all_rules)
    rules = all_rules.meta
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
    teacher = []
    for i, t in enumerate(g.teacher):
        obj = t.model_dump(exclude={"suggestion"})
        if t.suggestion is not None:
            obj["file"] = f"suggestion{i:03d}.png"
            save_mask(out / obj["file"], t.suggestion)
        teacher.append(obj)
    notes = {
        "flags": g.flags,
        "teacher": teacher,
        "facts": g.facts,
        "nested": g.nested,
        "merges": [m.model_dump(mode="json") for m in g.merges],
    }
    (out / _NOTES).write_text(json.dumps(notes, indent=1), "utf-8")
    if g.silhouette is not None:
        save_mask(out / _SILHOUETTE, g.silhouette)


def load(src: Path) -> Grounded:
    masks: dict[str, list[Mask]] = {"part": [], "text": []}
    for obj in json.loads((src / _FILE).read_text("utf-8")):
        e = MaskEntry.model_validate(obj)
        mask = Mask(data=load_mask(src / e.file), label=e.label, score=e.score, source=e.source)
        masks[e.kind].append(mask)
    notes = json.loads((src / _NOTES).read_text("utf-8")) if (src / _NOTES).exists() else {}
    teacher = []
    for t in notes.get("teacher", []):
        file = t.pop("file", None)
        teacher.append(TeacherPart(**t, suggestion=None if file is None else load_mask(src / file)))
    return Grounded(
        parts=masks["part"],
        text=masks["text"],
        flags=notes.get("flags", {}),
        teacher=teacher,
        facts=notes.get("facts", {}),
        nested=notes.get("nested", {}),
        merges=[MergeProposal.model_validate(m) for m in notes.get("merges", [])],
        silhouette=load_mask(src / _SILHOUETTE) if (src / _SILHOUETTE).exists() else None,
    )
