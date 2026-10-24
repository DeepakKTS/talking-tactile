"""Loads and validates config/tactile_rules.yaml and config/explore.yaml.

Every tunable number in the backend comes from one of these files. Unknown keys are
refused so a typo cannot silently fall back to a default; there are no defaults.
"""

from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeVar

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from app.models.regions import MAX_TEXTURES, GradeBand, PageSize
from app.paths import EXPLORE_YAML, TACTILE_RULES_YAML


class ConfigError(Exception):
    """A config file is missing, unreadable or has a bad value."""


PosFloat = Annotated[StrictFloat, Field(gt=0)]
NonNegFloat = Annotated[StrictFloat, Field(ge=0)]
PosInt = Annotated[StrictInt, Field(gt=0)]
NonNegInt = Annotated[StrictInt, Field(ge=0)]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _ordered(name: str, pair: tuple[float, float]) -> None:
    if pair[0] > pair[1]:
        raise ValueError(f"{name} must be [low, high], got {list(pair)}")


# tactile_rules.yaml


class Spacing(_Section):
    min_gap_mm: PosFloat
    point_symbol_min_mm: PosFloat


class Textures(_Section):
    max_area_textures: PosInt
    max_area_textures_lower_grades: PosInt
    lower_grade_bands: list[GradeBand]

    def limit_for(self, grade_band: GradeBand | None) -> int:
        """Area textures allowed for a grade band. No band given means the general limit."""
        if grade_band in self.lower_grade_bands:
            return self.max_area_textures_lower_grades
        return self.max_area_textures

    @model_validator(mode="after")
    def _limits(self) -> Self:
        if self.max_area_textures > MAX_TEXTURES:
            raise ValueError(
                f"max_area_textures {self.max_area_textures} is above the {MAX_TEXTURES} "
                "allowed by docs/regions.schema.json"
            )
        if self.max_area_textures_lower_grades > self.max_area_textures:
            raise ValueError("max_area_textures_lower_grades must not exceed max_area_textures")
        return self


class Braille(_Section):
    dot_base_diameter_mm: tuple[PosFloat, PosFloat]
    cell_to_cell_mm: tuple[PosFloat, PosFloat]
    line_spacing_mm: PosFloat
    clearance_to_line_mm: PosFloat
    table: Annotated[StrictStr, Field(min_length=1)]
    display: Annotated[StrictStr, Field(min_length=1)]

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        _ordered("dot_base_diameter_mm", self.dot_base_diameter_mm)
        _ordered("cell_to_cell_mm", self.cell_to_cell_mm)
        return self


class PageRules(_Section):
    sizes: Annotated[list[PageSize], Field(min_length=1)]
    dimensions_mm: dict[PageSize, tuple[PosFloat, PosFloat]]
    margin_mm: PosFloat
    calibration_bar_mm: PosFloat

    @model_validator(mode="after")
    def _sizes_have_dimensions(self) -> Self:
        for size in self.sizes:
            if size not in self.dimensions_mm:
                raise ValueError(f"dimensions_mm has no entry for page size {size}")
            if 2 * self.margin_mm >= min(self.dimensions_mm[size]):
                raise ValueError(f"margin_mm leaves no figure area on {size}")
        return self

    def figure_area_mm(self, size: PageSize) -> tuple[float, float, float, float]:
        """The rectangle the figure is fitted into, as (x, y, width, height) in page mm."""
        width, height = self.dimensions_mm[size]
        m = self.margin_mm
        return (m, m, width - 2 * m, height - 2 * m)


class Pipeline(_Section):
    normalize_max_side_px: PosInt


Fraction = Annotated[StrictFloat, Field(gt=0, le=1)]


class Reconcile(_Section):
    duplicate_iou: Fraction
    contain_fraction: Fraction
    speck_max_area_mm2: NonNegFloat
    sliver_max_width_mm: NonNegFloat


class TactileRules(_Section):
    spacing: Spacing
    textures: Textures
    braille: Braille
    page: PageRules
    pipeline: Pipeline
    reconcile: Reconcile
    principles: list[StrictStr]


# explore.yaml


class Hysteresis(_Section):
    enter_shrink_mm: NonNegFloat
    exit_grow_mm: NonNegFloat
    enter_hold_ms: NonNegInt
    exit_hold_ms: NonNegInt


class Dwell(_Section):
    speed_below_mm_s: PosFloat
    hold_ms: PosInt


class Earcons(_Section):
    max_per_second: PosFloat


class OneEuro(_Section):
    mincutoff_hz: PosFloat
    beta: NonNegFloat
    dcutoff_hz: PosFloat


class Fingertip(_Section):
    contact_offset_mm: NonNegFloat
    filter: Literal["one_euro"]
    one_euro: OneEuro


class Guidance(_Section):
    update_ms: PosInt
    arrive_inside_ms: NonNegInt


class Health(_Section):
    no_hand_warn_ms: PosInt
    off_page_points_before_recal: PosInt


class ExploreConfig(_Section):
    hysteresis: Hysteresis
    dwell: Dwell
    earcons: Earcons
    fingertip: Fingertip
    guidance: Guidance
    health: Health


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path}: config file not found") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a mapping")
    return data


M = TypeVar("M", bound=BaseModel)


def _validate(model: type[M], path: Path) -> M:
    data = _read_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(top)'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigError(f"{path}: {problems}") from None


def load_tactile_rules(path: Path = TACTILE_RULES_YAML) -> TactileRules:
    return _validate(TactileRules, path)


def load_explore(path: Path = EXPLORE_YAML) -> ExploreConfig:
    return _validate(ExploreConfig, path)
