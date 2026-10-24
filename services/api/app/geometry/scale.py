"""Pixel to page millimeters. The normalized image is fitted, centered and unrotated, into
the figure area of the page (the page inside its margin)."""

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from app.config import PageRules
from app.models.regions import PageSize

Points = NDArray[np.float64]  # N x 2, (x, y)


class PageFit(BaseModel):
    """Image pixel coordinates are continuous: pixel (col, row) covers [col, col + 1)."""

    model_config = ConfigDict(frozen=True)

    page: PageSize
    width_px: int
    height_px: int
    mm_per_px: float
    origin_mm: tuple[float, float]  # page position of the image's top-left corner

    def to_page_mm(self, pts: Points) -> Points:
        out: Points = np.asarray(pts, dtype=np.float64) * self.mm_per_px + np.array(self.origin_mm)
        return out

    def to_image_px(self, pts: Points) -> Points:
        out: Points = (
            np.asarray(pts, dtype=np.float64) - np.array(self.origin_mm)
        ) / self.mm_per_px
        return out


def fit_to_page(width_px: int, height_px: int, page: PageSize, rules: PageRules) -> PageFit:
    if width_px <= 0 or height_px <= 0:
        raise ValueError(f"image must have a size, got {width_px} x {height_px}")
    ax, ay, aw, ah = rules.figure_area_mm(page)
    mm_per_px = min(aw / width_px, ah / height_px)
    ox = ax + (aw - width_px * mm_per_px) / 2
    oy = ay + (ah - height_px * mm_per_px) / 2
    return PageFit(
        page=page, width_px=width_px, height_px=height_px, mm_per_px=mm_per_px, origin_mm=(ox, oy)
    )
