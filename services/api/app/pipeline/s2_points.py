"""S2 by points, Arm A v2f (S2 locked Oct 30; eval/s2-bakeoff/, tracker decisions).

For each part S1 located:
1. Its points through the guard (app/geometry/points.py): on the background, dropped; on or
   near a print mark, moved within GUARD_PX or dropped. A part with none left needs the
   teacher (no points).
2. One SAM call per part that is not a group, one object per instance with its points, at
   most sam_concurrency calls at a time. Each instance keeps the pieces of its mask that
   hold one of its points, less specks (app/geometry/part_masks.py).
3. Spill retry, after every first call: a mask holding another part's point (not a child's)
   is asked for once more with that point as a negative. If the new mask is free, it is
   used; if not, the smaller is kept as spill.
4. Oversize rule on the rest. Spill masks go to the teacher as suggestions: never touchable,
   and no part in step 5.
5. Contested pixels to the smallest mask, ties to the nearer point. Pixels won and lost
   are recorded per part.
6. A group's mask is the union of its members'. A part left with no mask needs the teacher.

S2 has no page size, so its speck floor is S3's on a letter page. Print text found in code
(app/geometry/print_marks.py) is the text mask S3 cuts out of the raised layer."""

import asyncio
from collections.abc import Sequence
from typing import Any

import httpx
import numpy as np

from app.config import TactileRules
from app.geometry import part_masks as pm
from app.geometry import points as gp
from app.geometry import print_marks
from app.geometry.scale import fit_to_page
from app.meta.client import MetaClient
from app.meta.live import LiveCallCapError, LiveCallError
from app.meta.mock import MockFixtureMissingError
from app.meta.types import PartPhrase, Understanding
from app.models.mask import BoolImage, Mask
from app.pipeline.s0_ingest import Ingested
from app.pipeline.s2_types import Grounded, TeacherPart
from app.prompts import Prompt

Point = tuple[int, int]
# The stage cache keys on this and SETTINGS, not on the code, so a code change never pays
# for Meta calls again. Bump the version when a change would send other prompts.
METHOD = "arm-a-v2f.1"
MAX_OBJECTS = 16  # sam/segmenting: box and point prompts name up to 16 objects
SETTINGS = {
    "method": METHOD,
    "guard_px": gp.GUARD_PX,
    "clearance_px": gp.CLEARANCE_PX,
    "object_diff": gp.OBJECT_DIFF,
    "oversize_points": pm.OVERSIZE_POINTS,
    "oversize_share": pm.OVERSIZE_SHARE,
    "max_objects": MAX_OBJECTS,
    "print_marks": {k: v for k, v in vars(print_marks).items() if k.isupper()},
}
_CALL_ERRORS = (LiveCallError, LiveCallCapError, httpx.HTTPError, MockFixtureMissingError)


def grid_to_px(v: float, size: int) -> int:
    """A 0-1000 grid value to an integer pixel, clamped to the image (docs: Spark can
    answer a little outside the grid)."""
    return min(size - 1, max(0, int(v * size // 1000)))


def speck_floor_px(image: BoolImage | np.ndarray, rules: TactileRules) -> float:
    h, w = image.shape[:2]
    mm = fit_to_page(w, h, "letter", rules.page).mm_per_px
    return rules.reconcile.speck_max_area_mm2 / mm**2


class _Run:
    def __init__(
        self,
        client: MetaClient,
        ing: Ingested,
        u: Understanding,
        prompt: Prompt,
        rules: TactileRules,
    ) -> None:
        self.client, self.ing, self.prompt, self.rules = client, ing, prompt, rules
        self.parts = {p.phrase: p for p in u.parts}
        self.scene = gp.scene_of(ing.image, float(rules.layout.color_group_max_delta))
        self.floor = speck_floor_px(ing.image, rules)
        self.gate = asyncio.Semaphore(rules.meta.sam_concurrency)
        self.flags: dict[str, list[str]] = {p: [] for p in self.parts}
        self.facts: dict[str, dict[str, Any]] = {p: {} for p in self.parts}
        self.teacher: dict[str, TeacherPart] = {}
        self.sent: dict[str, list[list[Point]]] = {}  # per part, per instance

    def need_teacher(
        self, part: str, reason: str, detail: str, suggestion: BoolImage | None = None
    ) -> None:
        self.teacher.setdefault(part, TeacherPart(phrase=part, reason=reason, detail=detail))
        if suggestion is not None:
            self.teacher[part] = self.teacher[part].model_copy(update={"suggestion": suggestion})
        self.flags[part].append(f"needs teacher: {reason.replace('_', ' ')}")

    def guard(self, p: PartPhrase) -> None:
        h, w = self.ing.image.shape[:2]
        if p.kind is None:
            self.need_teacher(p.phrase, "no_points", "Spark did not locate this part")
            return
        if p.kind == "thin":
            self.flags[p.phrase].append("thin")
        if p.kind == "group":
            return
        instances = []
        for inst in p.instances:
            pts = [(grid_to_px(g.x, w), grid_to_px(g.y, h)) for g in inst.points]
            guarded = gp.guard_instance(self.scene, pts)
            self.flags[p.phrase] += [
                f"point {g['px']} dropped: {gp.where_on(g['on'])}" for g in guarded if g["dropped"]
            ]
            sent = [(g["sent"][0], g["sent"][1]) for g in guarded if g["sent"]]
            if sent:
                instances.append(sent)
            self.facts[p.phrase].setdefault("points", []).append(guarded)
        if len(instances) > MAX_OBJECTS:
            self.flags[p.phrase].append(f"{len(instances)} instances, sent the first {MAX_OBJECTS}")
            instances = instances[:MAX_OBJECTS]
        if not instances:
            self.need_teacher(p.phrase, "no_points", "every point was dropped by the guard")
            return
        self.sent[p.phrase] = instances

    def points(self) -> dict[str, list[Point]]:
        return {part: [p for inst in insts for p in inst] for part, insts in self.sent.items()}

    async def call(
        self, part: str, negatives: Sequence[Point], retry: bool
    ) -> tuple[BoolImage, list[float | None]] | str:
        """One SAM call for a part: the union of each instance's pieces that hold its
        points, with the confidences; or the error, as text."""
        insts = self.sent[part]
        async with self.gate:
            try:
                answer = await self.client.segment_points(
                    self.ing.image,
                    self.ing.figure_id,
                    part,
                    [(pos, list(negatives)) for pos in insts],
                    self.prompt,
                    retry,
                )
            except _CALL_ERRORS as exc:
                return f"{type(exc).__name__}: {exc}"
        by_id = {a.object_id: a for a in answer}
        mask = np.zeros(self.ing.image.shape[:2], bool)
        confs: list[float | None] = []
        for k, pos in enumerate(insts, 1):
            a = by_id.get(k)
            confs.append(None if a is None else a.confidence)
            if a is not None:
                mask |= pm.keep_pieces(a.mask, pos, self.floor)[0]
        return mask, confs

    async def first(self, part: str) -> tuple[str, BoolImage | None]:
        got = await self.call(part, [], False)
        if isinstance(got, str):
            self.need_teacher(part, "no_mask", f"SAM call failed: {got}")
            return part, None
        mask, confs = got
        self.facts[part]["confidence"] = confs
        if not mask.any():
            self.need_teacher(part, "no_mask", "SAM's mask holds none of the part's points")
            return part, None
        return part, mask

    async def retry(self, part: str, mask: BoolImage) -> tuple[str, BoolImage, str | None]:
        """The mask to keep, and why it is spill, or None."""
        parents = {q: p.parent for q, p in self.parts.items()}
        pts = self.points()
        held = pm.points_inside(part, mask, pts, parents)
        if not held:
            return part, mask, None
        names = ", ".join(sorted(held))
        own = pts[part]
        add = [
            p
            for p in held.values()
            if all(np.hypot(p[0] - a, p[1] - b) > gp.GUARD_PX for a, b in own)
        ]
        if not add:
            return part, mask, f"holds points of {names}; no retry: the points are next to its own"
        got = await self.call(part, add, True)
        if isinstance(got, str):
            return part, mask, f"holds points of {names}; the retry call failed: {got}"
        again = got[0]
        still = pm.points_inside(part, again, pts, parents)
        if again.any() and not still:
            self.flags[part].append(f"spill onto {names} cleared by a retry")
            return part, again, None
        keep = again if again.any() and again.sum() < mask.sum() else mask
        left = still if keep is again else held
        return part, keep, f"holds points of {', '.join(sorted(left))} after a retry"

    def split_spill(self, retried: list[tuple[str, BoolImage, str | None]]) -> dict[str, BoolImage]:
        """The masks that stay touchable; spill, by the retry or the oversize rule, goes to
        the teacher as a suggestion."""
        parents = {q: p.parent for q, p in self.parts.items()}
        object_px = int(self.scene.obj.sum())
        touch: dict[str, BoolImage] = {}
        for part, mask, after_retry in retried:
            p = self.parts[part]
            spill = after_retry
            if spill is None:
                held = pm.points_inside(part, mask, self.points(), parents)
                spill = pm.oversize(held, mask, object_px, p.kind == "thin", bool(p.parent))
            if spill is None:
                touch[part] = mask
            else:
                self.need_teacher(part, "spill", spill, suggestion=mask)
        return touch

    def unite_groups(self, final: dict[str, BoolImage]) -> None:
        groups = {q for q, p in self.parts.items() if p.kind == "group"}
        members = {q: p.members for q, p in self.parts.items()}
        for g in groups:
            union = np.zeros(self.ing.image.shape[:2], bool)
            for m in pm.members_of(g, members, groups, {g}):
                if m in final:
                    union |= final[m]
            if union.any():
                final[g] = union
            else:
                self.need_teacher(g, "no_mask", "no member of the group has a mask")

    def result(self, final: dict[str, BoolImage]) -> Grounded:
        order = list(self.parts)
        for part in order:
            if part not in final and part not in self.teacher:
                self.need_teacher(part, "no_mask", "nothing of its mask is left")
        masks = []
        for part, data in final.items():
            confs = [c for c in self.facts[part].get("confidence", []) if c is not None]
            score = min(1.0, max(confs)) if confs else 1.0
            masks.append(Mask(data=data, label=part, score=score, source="sam"))
        masks.sort(key=lambda m: order.index(m.label))
        text = self.scene.marks.text
        phrase = self.rules.meta.text_phrase
        return Grounded(
            parts=masks,
            text=[Mask(data=text, label=phrase, score=1.0, source="code")] if text.any() else [],
            flags={p: f for p, f in self.flags.items() if f},
            teacher=[self.teacher[p] for p in order if p in self.teacher],
            facts=self.facts,
        )

    async def ground(self) -> Grounded:
        for p in self.parts.values():
            self.guard(p)
        firsts = await asyncio.gather(*(self.first(part) for part in self.sent))
        kept = {part: m for part, m in firsts if m is not None}
        retried = await asyncio.gather(*(self.retry(part, m) for part, m in kept.items()))
        touch = self.split_spill(list(retried))
        final, lost, won, respeck = pm.resolve(touch, self.points(), self.floor)
        for part in final:
            self.facts[part] |= {
                "lost_to": lost[part],
                "won_from": won[part],
                "respeck_px": respeck[part],
            }
        self.unite_groups(final)
        return self.result(final)


async def ground_points(
    client: MetaClient, ing: Ingested, u: Understanding, prompt: Prompt, rules: TactileRules
) -> Grounded:
    return await _Run(client, ing, u, prompt, rules).ground()
