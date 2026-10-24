"""Draws the synthetic figure and writes fixtures/synthetic/.

    uv run python -m app.synthetic.generate

Outputs figure.png (the normalized image), one 1-bit PNG per truth mask, raw SAM-like
mask and printed label, and truth.json. Deterministic: tests regenerate it and compare.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from app.config import TactileRules, load_tactile_rules
from app.models.mask import BoolImage
from app.paths import FIXTURES_DIR
from app.synthetic import spec
from app.synthetic.truth import Planted, SyntheticTruth, TruthPart, TruthRaw, TruthText

OUT_DIR = FIXTURES_DIR / "synthetic"
TEXT_PHRASE = "text label"
TEXT_SCORE = 0.9


@dataclass(frozen=True)
class Synthetic:
    truth: SyntheticTruth
    image: NDArray[np.uint8]  # H x W x 3 RGB
    masks: dict[str, BoolImage]  # file name -> pixels


@dataclass(frozen=True)
class _Grid:
    x: NDArray[np.float64]  # figure-area mm at each pixel center
    y: NDArray[np.float64]
    px_per_mm: float


def _grid(rules: TactileRules) -> _Grid:
    _, _, area_w, area_h = rules.page.figure_area_mm(spec.PAGE)
    s = rules.pipeline.normalize_max_side_px / max(area_w, area_h)
    w, h = round(area_w * s), round(area_h * s)
    cols = (np.arange(w, dtype=np.float64) + 0.5) / s
    rows = (np.arange(h, dtype=np.float64) + 0.5) / s
    x, y = np.meshgrid(cols, rows)
    return _Grid(x=x, y=y, px_per_mm=s)


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=px)


def _outline_band(mask: BoolImage, px: int) -> BoolImage:
    kernel = np.ones((2 * px + 1, 2 * px + 1), np.uint8)
    eroded = cv2.erode(mask.astype(np.uint8), kernel).astype(bool)
    band: BoolImage = mask & ~eroded
    return band


def generate(rules: TactileRules | None = None) -> Synthetic:
    rules = rules or load_tactile_rules()
    g = _grid(rules)
    s = g.px_per_mm
    ox, oy, _, _ = rules.page.figure_area_mm(spec.PAGE)
    h, w = g.x.shape

    def page(pt: tuple[float, float]) -> tuple[float, float]:
        return (round(pt[0] + ox, 4), round(pt[1] + oy, 4))

    masks: dict[str, BoolImage] = {}
    part_masks = {p.id: p.shape.inside(g.x, g.y) for p in spec.PARTS}

    # Fill parents before children, then outlines, then printed labels.
    canvas = np.empty((h, w, 3), np.uint8)
    canvas[:] = spec.BACKGROUND_RGB
    for p in sorted(spec.PARTS, key=lambda p: p.parent is not None):
        canvas[part_masks[p.id]] = spec.CATEGORY_RGB[p.category]
    band_px = max(1, round(spec.OUTLINE_MM * s / 2))
    for p in spec.PARTS:
        canvas[_outline_band(part_masks[p.id], band_px)] = spec.OUTLINE_RGB
    img = Image.fromarray(canvas)
    draw = ImageDraw.Draw(img)
    font = _font(round(spec.TEXT_HEIGHT_MM * s))
    pad = spec.TEXT_PAD_MM * s
    texts: list[TruthText] = []
    text_masks: dict[str, BoolImage] = {}
    for p in spec.PARTS:
        at = (p.text_at[0] * s, p.text_at[1] * s)
        draw.text(at, p.label, fill=spec.TEXT_RGB, font=font)
        x0, y0, x1, y1 = draw.textbbox(at, p.label, font=font)
        bx0, by0, bx1, by1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        name = f"masks/text_{p.id}.png"
        cols = (g.x * s >= bx0) & (g.x * s <= bx1)
        rows = (g.y * s >= by0) & (g.y * s <= by1)
        text_masks[p.id] = cols & rows
        masks[name] = text_masks[p.id]
        texts.append(
            TruthText(
                text=p.label,
                part=p.id,
                bbox_mm=(*page((bx0 / s, by0 / s)), *page((bx1 / s, by1 / s))),
                mask=name,
            )
        )
    image = np.asarray(img, dtype=np.uint8).copy()

    parts: list[TruthPart] = []
    for p in spec.PARTS:
        name = f"masks/part_{p.id}.png"
        masks[name] = part_masks[p.id]
        parts.append(
            TruthPart(
                id=p.id,
                label=p.label,
                category=p.category,
                color=spec.CATEGORY_RGB[p.category],
                kind=p.shape.kind,
                bbox_mm=(*page((p.shape.x0, p.shape.y0)), *page((p.shape.x1, p.shape.y1))),
                outline_mm=[page(v) for v in p.shape.outline()],
                area_mm2=round(p.shape.area(), 4),
                parent=p.parent,
                score=p.score,
                mask=name,
            )
        )

    raws: list[TruthRaw] = []
    for r in spec.RAW:
        name = f"masks/{r.id}.png"
        pixels = np.zeros((h, w), dtype=bool)
        for shape in r.shapes:
            pixels |= shape.inside(g.x, g.y)
        if r.with_text_of is not None:
            pixels |= text_masks[r.with_text_of]
        masks[name] = pixels
        raws.append(
            TruthRaw(
                id=r.id, phrase=r.phrase, score=r.score, fate=r.fate, becomes=r.becomes,
                note=r.note, mask=name,
            )
        )  # fmt: skip
    for t in texts:
        raws.append(
            TruthRaw(
                id=f"raw_text_{t.part}", phrase=TEXT_PHRASE, score=TEXT_SCORE, fate="text",
                becomes=None, note=f"printed label '{t.text}'", mask=t.mask,
            )
        )  # fmt: skip

    area_categories = sorted({p.category for p in spec.PARTS if p.id != "pore"})
    planted = [
        Planted(
            rule="min_gap", parts=["left_lobe", "right_lobe"], value=spec.PLANTED_GAP_MM,
            unit="mm", note="neighbors closer than spacing.min_gap_mm",
        ),
        Planted(
            rule="point_symbol", parts=["pore"], value=spec.PLANTED_POINT_MM, unit="mm",
            note="part smaller than spacing.point_symbol_min_mm",
        ),
        Planted(
            rule="texture_count",
            parts=[p.id for p in spec.PARTS if p.category in area_categories],
            value=len(area_categories), unit="categories",
            note=f"{', '.join(area_categories)} by color, above the lower-grade limit",
        ),
    ]  # fmt: skip

    truth = SyntheticTruth(
        spec_version=1,
        title=spec.TITLE,
        summary=spec.SUMMARY,
        page=spec.PAGE,
        grade_band=spec.GRADE_BAND,
        color_carries_meaning=True,
        image="figure.png",
        width_px=w,
        height_px=h,
        px_per_mm=s,
        figure_origin_mm=(ox, oy),
        parts=parts,
        raw_masks=raws,
        text_labels=texts,
        planted=planted,
    )
    return Synthetic(truth=truth, image=image, masks=masks)


def write(synthetic: Synthetic, out_dir: Path = OUT_DIR) -> None:
    (out_dir / "masks").mkdir(parents=True, exist_ok=True)
    for old in (out_dir / "masks").glob("*.png"):
        old.unlink()
    Image.fromarray(synthetic.image).save(out_dir / synthetic.truth.image, optimize=True)
    for name, pixels in synthetic.masks.items():
        Image.fromarray(pixels).save(out_dir / name, optimize=True)
    text = json.dumps(synthetic.truth.model_dump(mode="json"), indent=1) + "\n"
    (out_dir / "truth.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write(generate())
    print(f"wrote {OUT_DIR}")
