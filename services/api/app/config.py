"""Loads and validates config/tactile_rules.yaml and config/explore.yaml.

Every tunable number in the backend comes from one of these files. Unknown keys are
refused so a typo cannot silently fall back to a default; there are no defaults.
"""

from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeVar, get_args

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from app.models.regions import MAX_TEXTURES, GradeBand, PageSize, TextureId
from app.paths import EXPLORE_YAML, TACTILE_RULES_YAML


class ConfigError(Exception):
    """A config file is missing, unreadable or has a bad value."""


PosFloat = Annotated[StrictFloat, Field(gt=0)]
NonNegFloat = Annotated[StrictFloat, Field(ge=0)]
PosInt = Annotated[StrictInt, Field(gt=0)]
NonNegInt = Annotated[StrictInt, Field(ge=0)]
Gain = Annotated[StrictFloat, Field(gt=0, le=1)]


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
    order: Annotated[list[TextureId], Field(min_length=1)]

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
        if len(set(self.order)) != len(self.order):
            raise ValueError("order lists a texture twice")
        if len(self.order) < self.max_area_textures:
            raise ValueError("order must name at least max_area_textures textures")
        return self


class Braille(_Section):
    dot_base_diameter_mm: tuple[PosFloat, PosFloat]
    cell_to_cell_mm: tuple[PosFloat, PosFloat]
    line_spacing_mm: PosFloat
    clearance_to_line_mm: PosFloat
    dot_to_dot_mm: tuple[PosFloat, PosFloat]
    table: Annotated[StrictStr, Field(min_length=1)]
    display: Annotated[StrictStr, Field(min_length=1)]
    search_step_mm: PosFloat
    max_outside_offset_mm: PosFloat
    abbrev_letters: PosInt
    translate_timeout_s: PosFloat

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        _ordered("dot_base_diameter_mm", self.dot_base_diameter_mm)
        _ordered("cell_to_cell_mm", self.cell_to_cell_mm)
        _ordered("dot_to_dot_mm", self.dot_to_dot_mm)
        if 2 * self.dot_to_dot_mm[0] + self.dot_base_diameter_mm[0] >= self.line_spacing_mm:
            raise ValueError("line_spacing_mm leaves no room between braille lines")
        if self.dot_to_dot_mm[0] + self.dot_base_diameter_mm[0] >= self.cell_to_cell_mm[0]:
            raise ValueError("cell_to_cell_mm leaves no room between braille cells")
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
    max_upload_mb: PosFloat
    pdf_render_dpi: PosInt
    min_sharpness: NonNegFloat
    deskew_min_area_fraction: Annotated[StrictFloat, Field(gt=0, lt=1)]
    deskew_max_area_fraction: Annotated[StrictFloat, Field(gt=0, le=1)]
    deskew_min_contrast: NonNegFloat

    @model_validator(mode="after")
    def _deskew_range(self) -> Self:
        if self.deskew_min_area_fraction >= self.deskew_max_area_fraction:
            raise ValueError("deskew_min_area_fraction must be below deskew_max_area_fraction")
        return self


Fraction = Annotated[StrictFloat, Field(gt=0, le=1)]


class Prices(_Section):
    input_per_mtok: NonNegFloat | None = None
    cached_input_per_mtok: NonNegFloat | None = None
    output_per_mtok: NonNegFloat | None = None
    per_image: NonNegFloat | None = None
    per_audio_hour: NonNegFloat | None = None


class MetaModels(_Section):
    """Standard models only (RULES.md 1.4). The model id chooses the mode on the Model API:
    "switch between the two by choosing the model ID" (dev.meta.ai/docs/models), and a
    Contributor model is the id with -contributor, such as muse-spark-1.3-contributor."""

    spark: Annotated[StrictStr, Field(min_length=1)]
    sam: Annotated[StrictStr, Field(min_length=1)]
    voice: Annotated[StrictStr, Field(min_length=1)]

    @model_validator(mode="after")
    def _standard(self) -> Self:
        for model in (self.spark, self.sam, self.voice):
            if "contributor" in model.lower():
                raise ValueError(
                    f"models: {model} is a Contributor model, whose content Meta may use to "
                    "train its models; this build sends a student's question and uses "
                    "Standard models only"
                )
        return self


class JobCalls(_Section):
    spark: PosInt
    per_part: PosInt
    ceiling: PosInt


class Meta(_Section):
    budget_usd: PosFloat
    warn_at_fractions: list[Annotated[StrictFloat, Field(gt=0, lt=1)]]
    max_parts: PosInt
    sam_concurrency: PosInt
    text_phrase: Annotated[StrictStr, Field(min_length=1)]
    live_call_cap: PosInt
    job_calls: JobCalls
    fix_call_cap: PosInt
    models: MetaModels
    prices_usd: dict[StrictStr, Prices]

    @model_validator(mode="after")
    def _ascending(self) -> Self:
        if self.warn_at_fractions != sorted(set(self.warn_at_fractions)):
            raise ValueError("warn_at_fractions must be ascending without repeats")
        return self

    @model_validator(mode="after")
    def _priced(self) -> Self:
        for model in (self.models.spark, self.models.sam, self.models.voice):
            if model not in self.prices_usd:
                raise ValueError(f"models: {model} has no entry in prices_usd")
        return self


class Reconcile(_Section):
    duplicate_iou: Fraction
    contain_fraction: Fraction
    speck_max_area_mm2: NonNegFloat
    sliver_max_width_mm: NonNegFloat


class Vectorize(_Section):
    simplify_tolerance_mm: PosFloat


class Layout(_Section):
    point_symbol_vertices: Annotated[StrictInt, Field(ge=8)]
    gap_simplify_tolerance_mm: PosFloat
    gap_max_passes: PosInt
    color_group_max_delta: PosFloat
    inside_point_tolerance_mm: PosFloat
    neighbor_max_gap_mm: PosFloat


class Render(_Section):
    outline_width_mm: PosFloat
    texture_line_mm: PosFloat
    texture_dot_mm: PosFloat
    texture_spacing_mm: PosFloat
    texture_min_piece_mm: PosFloat
    guide_line_mm: PosFloat
    mark_arm_mm: PosFloat
    print_text_mm: PosFloat
    bar_height_mm: PosFloat
    key_swatch_mm: tuple[PosFloat, PosFloat]
    coordinate_decimals: NonNegInt


class TactileRules(_Section):
    spacing: Spacing
    textures: Textures
    braille: Braille
    page: PageRules
    pipeline: Pipeline
    meta: Meta
    reconcile: Reconcile
    vectorize: Vectorize
    layout: Layout
    render: Render
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
    speed_window_ms: PosInt


class Earcons(_Section):
    max_per_second: PosFloat
    texture_hz: dict[TextureId, PosFloat]
    default_hz: PosFloat
    tone_ms: PosInt
    gain: Gain
    exit_tick_hz: PosFloat
    exit_tick_ms: PosInt
    exit_tick_gain: Gain

    @model_validator(mode="after")
    def _every_texture_has_a_pitch(self) -> Self:
        missing = set(get_args(TextureId)) - set(self.texture_hz)
        if missing:
            raise ValueError(f"texture_hz has no pitch for {sorted(missing)}")
        return self


class OneEuro(_Section):
    mincutoff_hz: PosFloat
    beta: NonNegFloat
    dcutoff_hz: PosFloat


class Fingertip(_Section):
    contact_offset_mm: NonNegFloat
    filter: Literal["one_euro"]
    one_euro: OneEuro
    lost_reset_ms: PosInt


class Hands(_Section):
    max_hands: Annotated[StrictInt, Field(ge=1, le=2)]
    min_curled: Annotated[StrictInt, Field(ge=1, le=3)]  # of middle, ring and pinky
    require_pointing: StrictBool


class Guidance(_Section):
    update_ms: PosInt
    arrive_inside_ms: NonNegInt
    beep_hz: PosFloat
    beep_ms: PosInt
    beeps_per_s_far: PosFloat
    beeps_per_s_near: PosFloat
    far_mm: PosFloat
    chime_hz: Annotated[list[PosFloat], Field(min_length=1)]
    chime_note_ms: PosInt

    @model_validator(mode="after")
    def _beeps_speed_up_when_near(self) -> Self:
        if self.beeps_per_s_near <= self.beeps_per_s_far:
            raise ValueError("beeps_per_s_near must be above beeps_per_s_far")
        return self


class Intents(_Section):
    min_label_similarity: Annotated[StrictFloat, Field(gt=0, le=1)]


class Health(_Section):
    no_hand_warn_ms: PosInt
    dark_frame_below: Annotated[StrictFloat, Field(gt=0, lt=1)]
    dark_warn_ms: PosInt
    off_page_points_before_recal: PosInt


class Registration(_Section):
    mark_inset_mm: PosFloat


class ExploreConfig(_Section):
    hysteresis: Hysteresis
    dwell: Dwell
    earcons: Earcons
    fingertip: Fingertip
    hands: Hands
    guidance: Guidance
    intents: Intents
    health: Health
    registration: Registration


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
