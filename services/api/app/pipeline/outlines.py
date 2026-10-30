"""Teacher outlines (Fix outline in Author): SAM masks from the teacher's points, applied to
S2's masks before S3.

A teacher's click is deliberate, so the clearance rule of S2's guard does not apply; the
background check does: a positive point off the figure is refused. A click on label text or
a leader line is allowed, with a warning. The mask keeps the pieces that hold a positive
point, less S3's specks, as in S2. It replaces the part's S2 mask in place, so S3's ids for
the other parts do not move; a part S2 left to the teacher gets its first mask at the end.
The spill check is S2's: the mask holds another part's prompt point, not a child's."""

from collections.abc import Sequence

import numpy as np

from app.geometry import part_masks as pm
from app.geometry import points as gp
from app.meta.types import Understanding
from app.models.mask import BoolImage, Mask
from app.pipeline.s2_types import Grounded

Point = tuple[int, int]


class OutlineError(Exception):
    """Points that cannot be sent: off the image, or a positive point off the figure."""


def check_points(
    scene: gp.Scene, positive: Sequence[Point], negative: Sequence[Point]
) -> list[str]:
    """Warnings for the teacher; raises OutlineError for points that cannot be sent."""
    h, w = scene.obj.shape
    warnings = []
    for kind, pts in (("positive", positive), ("negative", negative)):
        for x, y in pts:
            if not (0 <= x < w and 0 <= y < h):
                raise OutlineError(f"Point ({x}, {y}) is outside the figure.")
            if kind == "positive" and not scene.obj[y, x]:
                raise OutlineError(f"Point ({x}, {y}) is on the page, not the figure.")
            m = scene.marks
            on = [k for k, a in (("label text", m.text), ("a leader line", m.line)) if a[y, x]]
            if on:
                warnings.append(f"The {kind} point at ({x}, {y}) is on {' and '.join(on)}.")
    return warnings


def keep(mask: BoolImage, positive: Sequence[Point], floor_px: float) -> BoolImage:
    return pm.keep_pieces(mask, positive, floor_px)[0]


def prompt_points(g: Grounded) -> dict[str, list[Point]]:
    """Each part's points as S2 sent them."""
    out: dict[str, list[Point]] = {}
    for part, facts in g.facts.items():
        sent = [p["sent"] for inst in facts.get("points", []) for p in inst if p.get("sent")]
        if sent:
            out[part] = [(int(x), int(y)) for x, y in sent]
    return out


def spill_of(part: str, mask: BoolImage, g: Grounded, u: Understanding) -> list[str]:
    parents = {p.phrase: p.parent for p in u.parts}
    return sorted(pm.points_inside(part, mask, prompt_points(g), parents))


def with_outlines(g: Grounded, outlined: Sequence[tuple[str, BoolImage]]) -> Grounded:
    parts = list(g.parts)
    for phrase, data in outlined:
        new = Mask(data=data, label=phrase, score=1.0, source="teacher")
        at = [i for i, m in enumerate(parts) if m.label == phrase]
        if at:
            parts[at[0]] = new
            for i in reversed(at[1:]):  # mock mode can give one phrase several masks
                del parts[i]
        else:
            parts.append(new)
    done = {phrase for phrase, _ in outlined}
    teacher = [t for t in g.teacher if t.phrase not in done]
    return g.model_copy(update={"parts": parts, "teacher": teacher})


def old_outline(phrase: str, g: Grounded) -> BoolImage | None:
    """What the part has now, to show beside the new mask: its S2 mask, or the spill
    suggestion S2 left to the teacher."""
    masks = [m.data for m in g.parts if m.label == phrase]
    if masks:
        return np.asarray(np.logical_or.reduce(masks), bool)
    sug = [t.suggestion for t in g.teacher if t.phrase == phrase and t.suggestion is not None]
    return sug[0] if sug else None
