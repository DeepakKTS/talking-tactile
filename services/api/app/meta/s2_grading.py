"""Grading aids for the S2 bake-off sheets: flags from the data, and a one part at a time view.

    uv run python -m app.meta.s2_grading

No live calls. Each figure's bake-off is replayed from fixtures/recorded/bakeoff_*.json to get
its masks back, then read against the live results.json. Writes, per figure, img/focus_*.jpg
(git-ignored) and a new index.html with the view and the flags, and for all three
eval/s2-bakeoff/overlaps.json. Nothing here says pass or fail.

Flags, per part and arm:
- point_outside: Arm A's prompt point is not inside its own mask (results.json point_in_mask).
- whole_object: the mask covers more than WHOLE_OBJECT of the figure's object area. Object
  pixels differ from the median border color by more than OBJECT_DIFF in some channel, so a
  white page or Japan's blue sea is not object; printed labels and leader lines are.
- overlaps: another part of the same arm whose mask covers more than OVERLAP of the smaller of
  the two masks.
- no_regions: Arm B gave the part no valid region id.
Arm A confidence is shown and sortable, not flagged."""

import asyncio
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from app.meta import s2_bakeoff as bake

OBJECT_DIFF = 40  # stable from 40 to 60 on all three figures; 20 catches the flower's tint
WHOLE_OBJECT = 0.5
OVERLAP = 0.2
FADE = 0.3  # the figure outside the mask, as opacity over white
FOCUS_SIDE = 900  # px, the longer side of a focus image
OUTLINE_PX = 2
# Outline colors to choose from; each mask gets the one farthest from the colors around it.
OUTLINE_COLORS = [(0, 200, 255), (255, 0, 200), (0, 190, 0), (255, 140, 0), (40, 40, 255)]

Mask = npt.NDArray[np.bool_]


def object_mask(image: npt.NDArray[np.uint8]) -> Mask:
    border = np.concatenate([image[0], image[-1], image[:, 0], image[:, -1]]).astype(int)
    background = np.median(border, axis=0)
    return np.asarray(np.abs(image.astype(int) - background).max(axis=2) > OBJECT_DIFF)


def overlap_pairs(masks: dict[str, Mask]) -> list[dict[str, Any]]:
    """Pairs of parts whose masks share more than OVERLAP of the smaller mask."""
    out = []
    for (p, a), (q, b) in combinations(masks.items(), 2):
        smaller = min(int(a.sum()), int(b.sum()))
        shared = int((a & b).sum())
        if smaller and shared / smaller > OVERLAP:
            out.append(
                {"parts": [p, q], "overlap_px": shared, "of_smaller": round(shared / smaller, 3)}
            )
    return out


def grade(
    result: dict[str, Any], masks: dict[str, dict[str, Mask]], object_px: int
) -> dict[str, Any]:
    """The flags for one figure, from its live results.json and its replayed masks."""
    a_rows = {r["part"]: r for r in result["arm_a_rows"]}
    b_rows = {r["part"]: r for r in result["arm_b_rows"]}
    pairs = {arm: overlap_pairs(masks[arm]) for arm in ("a", "b")}

    def area(arm: str, part: str) -> dict[str, Any]:
        m = masks[arm].get(part)
        if m is None:
            return {"area_px": None, "of_object": None, "whole_object": False}
        frac = int(m.sum()) / object_px
        return {
            "area_px": int(m.sum()),
            "of_object": round(frac, 3),
            "whole_object": frac > WHOLE_OBJECT,
        }

    def partners(arm: str, part: str) -> list[str]:
        return [q for pr in pairs[arm] for q in pr["parts"] if part in pr["parts"] and q != part]

    parts = []
    for p in result["parts"]:
        part = p["phrase"]
        a, b = a_rows.get(part, {}), b_rows.get(part, {})
        confs = [c for c in a.get("confidences") or [] if c is not None]
        ids = b.get("region_ids") or []
        valid = [i for i in ids if i not in (b.get("invalid_ids") or [])]
        parts.append(
            {
                "part": part,
                "print_label": p["print_label"],
                "a": {
                    "confidence": max(confs) if confs else None,
                    "point_px": a.get("point_px"),
                    "point_outside": a.get("point_in_mask") is False,
                    **area("a", part),
                    "overlaps": partners("a", part),
                },
                "b": {
                    "region_ids": valid,
                    "no_regions": not valid,
                    **area("b", part),
                    "overlaps": partners("b", part),
                },
            }
        )
    counts = {
        "a_point_outside": sum(x["a"]["point_outside"] for x in parts),
        "a_whole_object": sum(x["a"]["whole_object"] for x in parts),
        "a_overlap_pairs": len(pairs["a"]),
        "b_whole_object": sum(x["b"]["whole_object"] for x in parts),
        "b_overlap_pairs": len(pairs["b"]),
        "b_no_regions": sum(x["b"]["no_regions"] for x in parts),
    }
    return {
        "figure": result["figure"],
        "object_px": object_px,
        "parts": parts,
        "pairs": pairs,
        "counts": counts,
        "summary": summary_line(result["figure"], len(parts), counts),
    }


def summary_line(figure: str, n: int, c: dict[str, int]) -> str:
    return (
        f"{figure}, {n} parts. Arm A: point outside its mask {c['a_point_outside']}, "
        f"over 50% of the object {c['a_whole_object']}, overlapping pairs "
        f"{c['a_overlap_pairs']}. Arm B: no regions {c['b_no_regions']}, over 50% of the "
        f"object {c['b_whole_object']}, overlapping pairs {c['b_overlap_pairs']}."
    )


def outline_color(samples: npt.NDArray[np.uint8]) -> tuple[int, int, int]:
    """The candidate farthest, at its 5th percentile, from the given pixel colors."""
    if not len(samples):
        return OUTLINE_COLORS[0]
    px = samples.astype(np.float32)

    def score(c: tuple[int, int, int]) -> float:
        return float(np.percentile(np.linalg.norm(px - np.array(c, np.float32), axis=1), 5))

    return max(OUTLINE_COLORS, key=score)


def focus_view(
    image: npt.NDArray[np.uint8], mask: Mask | None, point: list[int] | None
) -> Image.Image:
    """The figure at FADE opacity over white, the mask's pixels at full opacity with a
    2 px outline just outside them, and the Arm A point as a black crosshair on white."""
    h, w = image.shape[:2]
    scale = min(1.0, FOCUS_SIDE / max(w, h))
    size = (round(w * scale), round(h * scale))
    small = np.asarray(Image.fromarray(image).resize(size, Image.Resampling.LANCZOS))
    out = small.astype(np.float32) * FADE + 255.0 * (1 - FADE)
    if mask is not None:
        m = cv2.resize(mask.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
        out[m] = small[m]
        k = 2 * OUTLINE_PX + 1
        band = cv2.dilate(m.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool) & ~m
        out[band] = outline_color(np.concatenate([out[band], small[m]]).astype(np.uint8))
    img = Image.fromarray(out.round().astype(np.uint8))
    if point is not None:
        x, y = point[0] * scale, point[1] * scale
        draw = ImageDraw.Draw(img)
        arm, gap = 16, 4
        for width, color in ((5, (255, 255, 255)), (2, (0, 0, 0))):
            draw.line((x - arm, y, x - gap, y), fill=color, width=width)
            draw.line((x + gap, y, x + arm, y), fill=color, width=width)
            draw.line((x, y - arm, x, y - gap), fill=color, width=width)
            draw.line((x, y + gap, x, y + arm), fill=color, width=width)
    return img


async def replay_masks(name: str) -> tuple[bake.Figure, dict[str, dict[str, Mask]]]:
    """A figure's masks per arm, from its recorded calls. Also redraws its img/."""
    fig = bake.load_figure(name, bake.FIGURES[name])
    run = bake.Bakeoff(bake.replayer(name), fig, False, bake.OUT_ROOT / name)
    await run.run()
    return fig, run.masks


def save_focus(
    fig: bake.Figure, graded: dict[str, Any], masks: dict[str, dict[str, Mask]], out_dir: Path
) -> None:
    d = out_dir / "img"
    d.mkdir(parents=True, exist_ok=True)
    for p in graded["parts"]:
        point = p["a"]["point_px"]
        for arm in ("a", "b"):
            view = focus_view(fig.image, masks[arm].get(p["part"]), point)
            view.save(d / f"focus_{arm}_{bake.slug(p['part'])}.jpg", quality=85)


def main() -> None:
    every = {}
    for name in sorted(bake.FIGURES):
        fig, masks = asyncio.run(replay_masks(name))
        out_dir = bake.OUT_ROOT / name
        result = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
        graded = grade(result, masks, int(object_mask(fig.image).sum()))
        save_focus(fig, graded, masks, out_dir)
        bake.write_sheet(result, out_dir, graded)
        every[name] = graded
        print(graded["summary"])
    rules = {
        "object_diff": OBJECT_DIFF,
        "whole_object": WHOLE_OBJECT,
        "overlap": OVERLAP,
        "object_area": "pixels more than object_diff from the median border color in some channel",
    }
    path = bake.OUT_ROOT / "overlaps.json"
    path.write_text(
        json.dumps(
            {"summaries": [g["summary"] for g in every.values()], "rules": rules, "figures": every},
            indent=1,
        )
        + "\n",
        "utf-8",
    )
    print(f"wrote {bake.shown(path)}")


if __name__ == "__main__":
    main()
