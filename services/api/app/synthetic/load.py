"""Reads fixtures/synthetic/ back as the image, truth and Masks."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from app.models.mask import BoolImage, Mask
from app.synthetic.generate import OUT_DIR
from app.synthetic.truth import SyntheticTruth


@dataclass(frozen=True)
class SyntheticFigure:
    truth: SyntheticTruth
    image: NDArray[np.uint8]
    truth_masks: dict[str, Mask]  # part id -> exact mask
    raw_masks: dict[str, Mask]  # raw id -> what SAM would return


def read_mask(path: Path) -> BoolImage:
    pixels: BoolImage = np.asarray(Image.open(path).convert("1"), dtype=bool)
    return pixels


def load_synthetic(root: Path = OUT_DIR) -> SyntheticFigure:
    truth = SyntheticTruth.model_validate(
        json.loads((root / "truth.json").read_text(encoding="utf-8"))
    )
    image = np.asarray(Image.open(root / truth.image).convert("RGB"), dtype=np.uint8)
    truth_masks = {
        p.id: Mask(data=read_mask(root / p.mask), label=p.label, score=p.score, source="synthetic")
        for p in truth.parts
    }
    raw_masks = {
        r.id: Mask(data=read_mask(root / r.mask), label=r.phrase, score=r.score, source="synthetic")
        for r in truth.raw_masks
    }
    return SyntheticFigure(truth=truth, image=image, truth_masks=truth_masks, raw_masks=raw_masks)
