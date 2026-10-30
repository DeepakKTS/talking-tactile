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
FlagReason = Literal["spill", "thin", "under_point_symbol"]
TeacherReason = Literal["no_points", "no_mask", "dropped"]

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


class Flag(ContractModel):
    reason: FlagReason
    detail: StrictStr


class TeacherEntry(ContractModel):
    """A listed part with no shape to touch."""

    id: StrictStr
    label: StrictStr
    reason: TeacherReason
    detail: StrictStr


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
    touchable: StrictBool
    flags: list[Flag] | None = None


class Subject(ContractModel):
    """The whole object shown, and its silhouette."""

    label: StrictStr
    polygon_mm: Annotated[
        list[PointMm], Field(min_length=MIN_POLYGON_POINTS, max_length=MAX_POLYGON_POINTS)
    ]


class Line(ContractModel):
    """A part that is a line: spoken at the border it separates, never touched."""

    _nullable: ClassVar[frozenset[str]] = frozenset({"parent"})

    id: StrictStr
    label: StrictStr
    separates: Annotated[list[StrictStr], Field(min_length=2, max_length=2)] | None = None
    between: Annotated[list[StrictStr], Field(min_length=2, max_length=2)] | None = None
    parent: StrictStr | None = None


class MergeProposal(ContractModel):
    name: StrictStr
    region_ids: Annotated[list[StrictStr], Field(min_length=2)]
    why: StrictStr


class RegionsFile(ContractModel):
    schema_version: Annotated[Literal[3], BeforeValidator(_not_bool)]
    figure_id: StrictStr
    title: StrictStr
    figure_type: FigureType
    grade_band: GradeBand | None = None
    page: Page
    summary: StrictStr
    textures: Annotated[list[Texture], Field(max_length=MAX_TEXTURES)]
    regions: list[Region]
    subject: Subject | None = None
    lines: list[Line] | None = None
    merge_proposals: list[MergeProposal] | None = None
    needs_teacher: list[TeacherEntry] | None = None

    @classmethod
    def from_json_obj(cls, obj: Any) -> Self:
        """Validate a decoded JSON value (dicts and lists)."""
        return cls.model_validate(obj)

    def to_json_obj(self) -> dict[str, Any]:
        """The JSON form: unset optionals are left out, a region's parent is always written."""
        out: dict[str, Any] = self.model_dump(mode="json", exclude_none=True)
        for dumped, region in zip(out["regions"], self.regions, strict=True):
            dumped["parent"] = region.parent
        return out


def check_references(regions_file: RegionsFile) -> list[str]:
    """Problems the schema cannot express: duplicate ids (regions, lines and needs_teacher
    share them), parents that do not exist, and neighbors, the regions a line separates and
    the regions of a merge proposal that are not touchable regions. Empty when the file is
    consistent."""
    problems: list[str] = []
    seen: set[str] = set()
    ids = (
        [r.id for r in regions_file.regions]
        + [x.id for x in regions_file.lines or []]
        + [t.id for t in regions_file.needs_teacher or []]
    )
    for rid in ids:
        if rid in seen:
            problems.append(f"duplicate region id {rid}")
        seen.add(rid)
    touchable = {r.id for r in regions_file.regions if r.touchable}
    for region in regions_file.regions:
        if region.parent is not None and region.parent not in seen:
            problems.append(f"{region.id}: parent {region.parent} does not exist")
        if region.parent == region.id:
            problems.append(f"{region.id}: is its own parent")
        for neighbor in region.neighbors or []:
            if neighbor.id not in seen:
                problems.append(f"{region.id}: neighbor {neighbor.id} does not exist")
            elif neighbor.id not in touchable:
                problems.append(f"{region.id}: neighbor {neighbor.id} is not touchable")
    return problems + _plan_references(regions_file, touchable)


def _plan_references(regions_file: RegionsFile, touchable: set[str]) -> list[str]:
    problems: list[str] = []
    regions = {r.id for r in regions_file.regions}
    for line in regions_file.lines or []:
        for rid in line.separates or []:
            if rid not in touchable:
                problems.append(f"{line.id}: separates {rid}, which is not a touchable region")
        if line.parent is not None and line.parent not in regions:
            problems.append(f"{line.id}: parent {line.parent} does not exist")
    for m in regions_file.merge_proposals or []:
        for rid in m.region_ids:
            if rid not in touchable:
                problems.append(f"merge {m.name}: {rid} is not a touchable region")
    return problems
