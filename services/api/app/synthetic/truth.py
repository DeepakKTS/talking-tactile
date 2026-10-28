"""truth.json for the synthetic figure. All coordinates are page millimeters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import GradeBand, PageSize
from app.synthetic.spec import RawFate


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TruthPart(_Model):
    id: str
    label: str
    category: str
    color: tuple[int, int, int]
    kind: Literal["rect", "rounded_rect", "ellipse"]
    bbox_mm: tuple[float, float, float, float]  # x0, y0, x1, y1
    outline_mm: list[tuple[float, float]]
    area_mm2: float
    parent: str | None
    score: float
    mask: str


class TruthRaw(_Model):
    id: str
    phrase: str
    score: float
    fate: RawFate
    becomes: str | None
    note: str
    mask: str


class TruthText(_Model):
    text: str
    part: str
    bbox_mm: tuple[float, float, float, float]
    mask: str


class Planted(_Model):
    rule: Literal["min_gap", "point_symbol", "texture_count"]
    parts: list[str]
    value: float
    unit: str
    note: str


class SyntheticTruth(_Model):
    spec_version: Literal[1]
    title: str
    summary: str
    page: PageSize
    grade_band: GradeBand
    color_carries_meaning: bool
    image: str
    width_px: int
    height_px: int
    px_per_mm: float
    figure_origin_mm: tuple[float, float]
    parts: list[TruthPart]
    raw_masks: list[TruthRaw]
    text_labels: list[TruthText]
    planted: list[Planted]
