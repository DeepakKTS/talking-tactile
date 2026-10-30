"""Teacher edits: their own versioned layer in SQLite, never written into the stage cache.

Edits name regions as regions.json shows them and act on the reconciled part each region
came from. They are replayed in order on S3's parts before S4, and the hash of the list
joins the S4 and S5 cache keys, so an edit re-runs layout and render and nothing earlier.

- label: a new label for the part.
- check: the teacher has looked at the part and its outline (Mark checked); also names
  other regions, so "Mark all parts checked" is one edit.
- describe: a description for the part, written to regions.json.
- merge: the part's pixels join another part, which keeps its own label.
- delete: the part goes; its children move up to its parent.
- add: a part SAM finds by name on request (cached like any SAM answer). Mostly inside one
  part, it becomes that part's child. Otherwise it takes only pixels no other part holds,
  and parts mostly inside it become its children.
- outline: the teacher's points for one listed part, positive and negative, in pixels of
  the normalized image. SAM's mask from those points replaces the part's S2 mask, or gives
  a part S2 left to the teacher its first one, before S3: S3's rules run again on it. The
  hash of the outline edits joins the S3 key. Its mask is marked set by the teacher.

A part a teacher checked, labelled, described, merged into or added is marked verified, as
is one whose outline the teacher set (its mask's source is teacher). Only a verified part is
touchable (Oct 30)."""

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.geometry.layout import part_id_of
from app.geometry.reconcile import ReconciledPart
from app.models.mask import BoolImage, Mask
from app.pipeline import db

RegionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{1,32}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class _Edit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LabelEdit(_Edit):
    op: Literal["label"]
    region: RegionId
    label: Text


class CheckEdit(_Edit):
    op: Literal["check"]
    region: RegionId
    also: Annotated[list[RegionId], Field(max_length=500)] = []


class DescribeEdit(_Edit):
    op: Literal["describe"]
    region: RegionId
    description: LongText


class MergeEdit(_Edit):
    op: Literal["merge"]
    region: RegionId
    into: RegionId


class DeleteEdit(_Edit):
    op: Literal["delete"]
    region: RegionId


class AddEdit(_Edit):
    op: Literal["add"]
    name: Text


Px = Annotated[int, Field(ge=0, le=20_000)]
MAX_POINTS = 20


class OutlineEdit(_Edit):
    op: Literal["outline"]
    region: RegionId  # where the teacher pressed Fix outline, for the record
    part: Text  # the listed part it sets: S2's phrase, found by the service from the region
    positive: Annotated[list[tuple[Px, Px]], Field(min_length=1, max_length=MAX_POINTS)]
    negative: Annotated[list[tuple[Px, Px]], Field(max_length=MAX_POINTS)] = []
    spill: list[Text] = []  # parts whose prompt points the accepted mask held


Edit = Annotated[
    LabelEdit | CheckEdit | DescribeEdit | MergeEdit | DeleteEdit | AddEdit | OutlineEdit,
    Field(discriminator="op"),
]
EDIT = TypeAdapter(Edit)
EDITS = TypeAdapter(list[Edit])


class EditError(Exception):
    """An edit names a region that is not there, or cannot be applied."""


def edits_digest(edits: Sequence[Edit]) -> str:
    return hashlib.sha256(EDITS.dump_json(list(edits))).hexdigest()


def outlines(edits: Sequence[Edit]) -> list[OutlineEdit]:
    """The outline edits, in order. A later one for the same part replaces an earlier one."""
    last = {e.part: e for e in edits if isinstance(e, OutlineEdit)}
    return list(last.values())


def outlines_digest(edits: Sequence[Edit]) -> str:
    """The S3 key's share of the edits: only outlines act before S3."""
    return hashlib.sha256(EDITS.dump_json(list(outlines(edits)))).hexdigest()


def added_names(edits: Sequence[Edit]) -> list[str]:
    return list(dict.fromkeys(e.name for e in edits if isinstance(e, AddEdit)))


class Annotations(BaseModel):
    model_config = ConfigDict(frozen=True)

    descriptions: dict[str, str]  # part id -> description
    verified: frozenset[str]  # part ids


def _added_id(n: int) -> str:
    return f"t{n}"


def annotations(edits: Sequence[Edit]) -> Annotations:
    """What S5 writes into regions.json besides the geometry. Needs no masks."""
    descriptions: dict[str, str] = {}
    verified: set[str] = set()
    added = 0
    for e in edits:
        if isinstance(e, LabelEdit):
            verified.add(part_id_of(e.region))
        elif isinstance(e, CheckEdit):
            verified |= {part_id_of(r) for r in (e.region, *e.also)}
        elif isinstance(e, DescribeEdit):
            descriptions[part_id_of(e.region)] = e.description
            verified.add(part_id_of(e.region))
        elif isinstance(e, MergeEdit):
            verified.add(part_id_of(e.into))
        elif isinstance(e, AddEdit):
            added += 1
            verified.add(_added_id(added))
    return Annotations(descriptions=descriptions, verified=frozenset(verified))


class _Parts:
    def __init__(self, parts: Sequence[ReconciledPart]) -> None:
        self.parts = {p.id: p for p in parts}

    def get(self, region: str) -> ReconciledPart:
        pid = part_id_of(region)
        if pid not in self.parts:
            raise EditError(f"There is no region {region}.")
        return self.parts[pid]

    def put(self, part: ReconciledPart) -> None:
        self.parts[part.id] = part

    def reparent(self, old: str, new: str | None) -> None:
        for p in list(self.parts.values()):
            if p.parent == old:
                self.put(p.model_copy(update={"parent": new}))

    def remove(self, pid: str) -> None:
        gone = self.parts.pop(pid)
        self.reparent(pid, gone.parent)

    def ancestors(self, pid: str) -> set[str]:
        out: set[str] = set()
        cur = self.parts[pid].parent
        while cur is not None and cur not in out:
            out.add(cur)
            cur = self.parts[cur].parent if cur in self.parts else None
        return out


def _overlap(a: BoolImage, b: BoolImage) -> int:
    return int(np.count_nonzero(a & b))


def _merge(st: _Parts, e: MergeEdit) -> None:
    src, dst = st.get(e.region), st.get(e.into)
    if src.id == dst.id:
        raise EditError(f"{e.region} and {e.into} are the same part.")
    parent = src.parent if src.id in st.ancestors(dst.id) else dst.parent
    pixels = dst.mask.data | src.mask.data
    merged = [*dst.merged, src.mask.label, *src.merged]
    st.put(
        dst.model_copy(
            update={"mask": dst.mask.with_data(pixels), "merged": merged, "parent": parent}
        )
    )
    del st.parts[src.id]
    st.reparent(src.id, dst.id)


def _add(st: _Parts, pid: str, name: str, masks: Sequence[Mask], contain: float) -> None:
    if not masks:
        raise EditError(f"No part called {name} was found in the figure.")
    pixels = np.logical_or.reduce([m.data for m in masks])
    area = int(np.count_nonzero(pixels))
    holders = [
        p
        for p in st.parts.values()
        if p.mask.area_px > area and _overlap(pixels, p.mask.data) >= contain * area
    ]
    parent = min(holders, key=lambda p: p.mask.area_px).id if holders else None
    keep_out = set() if parent is None else {parent, *st.ancestors(parent)}
    children: list[str] = []
    for p in list(st.parts.values()):
        if p.id in keep_out:
            continue
        inside = _overlap(p.mask.data, pixels) >= contain * p.mask.area_px
        if parent is None and inside and p.mask.area_px < area:
            children.append(p.id)
        else:
            pixels = pixels & ~p.mask.data
    if not pixels.any():
        raise EditError(f"Every part of {name} already belongs to another region.")
    score = max(m.score for m in masks)
    mask = Mask(data=pixels, label=name, score=score, source=masks[0].source)
    st.put(ReconciledPart(id=pid, mask=mask, parent=parent))
    for cid in children:
        child = st.parts[cid]
        if child.parent is None or st.parts[child.parent].mask.area_px > area:
            st.put(child.model_copy(update={"parent": pid}))


def apply_edits(
    parts: Sequence[ReconciledPart],
    edits: Sequence[Edit],
    added: Mapping[str, Sequence[Mask]],
    contain_fraction: float,
) -> list[ReconciledPart]:
    """S3's parts with the edits replayed in order. Raises EditError for an edit that names
    a region that is gone or cannot be applied."""
    st = _Parts(parts)
    n_added = 0
    for e in edits:
        if isinstance(e, LabelEdit):
            p = st.get(e.region)
            st.put(p.model_copy(update={"mask": p.mask.model_copy(update={"label": e.label})}))
        elif isinstance(e, DescribeEdit):
            st.get(e.region)
        elif isinstance(e, CheckEdit):
            for r in (e.region, *e.also):
                st.get(r)
        elif isinstance(e, MergeEdit):
            _merge(st, e)
        elif isinstance(e, DeleteEdit):
            st.remove(st.get(e.region).id)
        elif isinstance(e, OutlineEdit):
            continue  # applied to S2's masks before S3
        else:
            n_added += 1
            _add(st, _added_id(n_added), e.name, added.get(e.name, []), contain_fraction)
    return list(st.parts.values())  # S3 order, added parts last


class EditStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        db.init(path)

    def append(self, figure_id: str, edit: Edit) -> int:
        """Stores the edit as the figure's next version and returns that version."""
        with db.connect(self.path) as conn:
            version = (
                1
                + conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM edits WHERE figure_id = ?", (figure_id,)
                ).fetchone()[0]
            )
            conn.execute(
                "INSERT INTO edits (figure_id, version, edit, created_at) VALUES (?, ?, ?, ?)",
                (figure_id, version, EDIT.dump_json(edit).decode(), db.now()),
            )
        return int(version)

    def version(self, figure_id: str) -> int:
        with db.connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM edits WHERE figure_id = ?", (figure_id,)
            ).fetchone()
        return int(row[0])

    def list(self, figure_id: str, upto: int) -> list[Edit]:
        with db.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT edit FROM edits WHERE figure_id = ? AND version <= ? ORDER BY version",
                (figure_id, upto),
            ).fetchall()
        return [EDIT.validate_json(r["edit"]) for r in rows]
