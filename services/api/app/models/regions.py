"""Pydantic models for regions.json, the contract between Author and Explore.

docs/regions.schema.json is the source of truth. These models accept exactly what the
schema accepts (tests/test_contract.py checks this by mutation), and the numeric limits
are read from the schema itself so they cannot drift. Validation uses strict
types for every scalar: no string-to-number coercion, no bools as numbers.

Cross-references (unique ids, parents and neighbors that exist) are not part of the
schema, so they live in check_references rather than in the models.
"""

import json
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictStr,
    model_validator,
)

from app.paths import REGIONS_SCHEMA

_SCHEMA: dict[str, Any] = json.loads(REGIONS_SCHEMA.read_text(encoding="utf-8"))
_REGION_PROPS: dict[str, Any] = _SCHEMA["properties"]["regions"]["items"]["properties"]

SCHEMA_VERSION: int = _SCHEMA["properties"]["schema_version"]["const"]
MIN_POLYGON_POINTS: int = _REGION_PROPS["polygon_mm"]["minItems"]
MAX_POLYGON_POINTS: int = _REGION_PROPS["polygon_mm"]["maxItems"]
MAX_TEXTURES: int = _SCHEMA["properties"]["textures"]["maxItems"]
_CONFIDENCE_MIN: float = _REGION_PROPS["confidence"]["minimum"]
_CONFIDENCE_MAX: float = _REGION_PROPS["confidence"]["maximum"]

FigureType = Literal["labeled_diagram", "bar_chart", "line_graph", "map", "flow_diagram", "other"]
GradeBand = Literal["k5", "6_8", "9_12", "college"]
PageSize = Literal["letter", "a4"]
TextureId = Literal["dots", "lines", "cross", "grid", "solid"]
Direction = Literal[
    "up", "down", "left", "right", "up_left", "up_right", "down_left", "down_right",
    "inside", "around",
]  # fmt: skip
RegionSource = Literal["sam", "teacher"]

PointMm = tuple[StrictFloat, StrictFloat]


def _not_bool(value: Any) -> Any:
    # Literal[1] alone accepts True, because True == 1 in Python. JSON Schema does not.
    if isinstance(value, bool):
        raise ValueError("expected a number, got a bool")
    return value


class ContractModel(BaseModel):
    """Base for contract models. Optional fields may be missing but not null, unless the
    schema allows null for that field (listed in _nullable)."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    _nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_null_optionals(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for name in cls.model_fields:
                if name in data and data[name] is None and name not in cls._nullable:
                    raise ValueError(f"{name} may be missing but not null")
        return data


class Page(ContractModel):
    size: PageSize
    width_mm: StrictFloat
    height_mm: StrictFloat


class Texture(ContractModel):
    id: TextureId
    meaning: StrictStr
    earcon_hz: StrictFloat


class Neighbor(ContractModel):
    id: StrictStr
    direction: Direction


class Region(ContractModel):
    _nullable: ClassVar[frozenset[str]] = frozenset({"parent"})

    id: StrictStr
    label: StrictStr
    abbrev: StrictStr | None = None
    description: StrictStr | None = None
    polygon_mm: Annotated[
        list[PointMm], Field(min_length=MIN_POLYGON_POINTS, max_length=MAX_POLYGON_POINTS)
    ]
    centroid_mm: PointMm | None = None
    texture: StrictStr | None = None
    parent: StrictStr | None = None
    neighbors: list[Neighbor] | None = None
    source: RegionSource
    confidence: Annotated[StrictFloat, Field(ge=_CONFIDENCE_MIN, le=_CONFIDENCE_MAX)] | None = None
    verified_by_teacher: StrictBool


class RegionsFile(ContractModel):
    schema_version: Annotated[Literal[1], BeforeValidator(_not_bool)]
    figure_id: StrictStr
    title: StrictStr
    figure_type: FigureType
    grade_band: GradeBand | None = None
    page: Page
    summary: StrictStr
    textures: Annotated[list[Texture], Field(max_length=MAX_TEXTURES)]
    regions: list[Region]

    @classmethod
    def from_json_obj(cls, obj: Any) -> Self:
        """Validate a decoded JSON value (dicts and lists)."""
        return cls.model_validate(obj)

    def to_json_obj(self) -> dict[str, Any]:
        """The JSON form: unset optionals are left out, parent is always written."""
        out: dict[str, Any] = self.model_dump(mode="json", exclude_none=True)
        for dumped, region in zip(out["regions"], self.regions, strict=True):
            dumped["parent"] = region.parent
        return out


def check_references(regions_file: RegionsFile) -> list[str]:
    """Problems the schema cannot express: duplicate ids, and parents or neighbors that
    point at a region that does not exist. Empty when the file is consistent."""
    problems: list[str] = []
    seen: set[str] = set()
    for region in regions_file.regions:
        if region.id in seen:
            problems.append(f"duplicate region id {region.id}")
        seen.add(region.id)
    for region in regions_file.regions:
        if region.parent is not None and region.parent not in seen:
            problems.append(f"{region.id}: parent {region.parent} does not exist")
        if region.parent == region.id:
            problems.append(f"{region.id}: is its own parent")
        for neighbor in region.neighbors or []:
            if neighbor.id not in seen:
                problems.append(f"{region.id}: neighbor {neighbor.id} does not exist")
    return problems
