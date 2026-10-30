"""S3 reconcile, the code part, on S2's masks. The Muse Spark pass over numbered mask
outlines comes after the Spark spike; until then each part keeps the phrase SAM found it
for."""

import json
from pathlib import Path

from app.config import Reconcile
from app.geometry.reconcile import Dropped, Reconciled, ReconciledPart, reconcile
from app.geometry.scale import PageFit
from app.meta.types import Understanding
from app.models.mask import Mask
from app.pipeline.cache import load_mask, save_mask
from app.pipeline.s2_ground import Grounded

_FILE = "reconciled.json"


def without_groups(g: Grounded, u: Understanding) -> Grounded:
    """S2's output less any part S1 planned as a group: a group is never drawn, and never
    needs the teacher (Oct 30). S2 output cached before then holds group masks."""
    groups = {p.phrase for p in u.parts if p.kind == "group"}
    if not groups:
        return g
    parts = [m for m in g.parts if m.label not in groups]
    teacher = [t for t in g.teacher if t.phrase not in groups]
    nested = {c: q for c, q in g.nested.items() if c not in groups and q not in groups}
    return g.model_copy(update={"parts": parts, "teacher": teacher, "nested": nested})


def reconcile_masks(g: Grounded, fit: PageFit, rules: Reconcile) -> Reconciled:
    return reconcile(g.parts, g.text, fit.mm_per_px, rules, g.nested)


def save(rec: Reconciled, out: Path) -> None:
    parts = []
    for p in rec.parts:
        name = f"{p.id}.png"
        save_mask(out / name, p.mask.data)
        mask = p.mask.model_dump(exclude={"data"})
        parts.append({**p.model_dump(exclude={"mask"}), "mask": {**mask, "file": name}})
    dropped = [d.model_dump() for d in rec.dropped]
    (out / _FILE).write_text(json.dumps({"parts": parts, "dropped": dropped}, indent=1), "utf-8")


def load(src: Path) -> Reconciled:
    obj = json.loads((src / _FILE).read_text("utf-8"))
    parts = []
    for p in obj["parts"]:
        m = p.pop("mask")
        mask = Mask(data=load_mask(src / m.pop("file")), **m)
        parts.append(ReconciledPart(mask=mask, **p))
    return Reconciled(parts=parts, dropped=[Dropped(**d) for d in obj["dropped"]])
