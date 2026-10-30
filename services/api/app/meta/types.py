"""What the pipeline gets back from the Meta models, as our own types. The Spark spike's S1
schema (spikes/spark_spike.py) is the source for Understanding.

Live S1 is two Spark calls. The listing (LISTING_SCHEMA) names the parts. The locate call
(LOCATE_SCHEMA, app/prompts/s1_locate.v2.json) plans the parts for touch, as a tactile
transcriber would for the grade band and the printed size: each part's kind (an area to
touch, a line, or a group of listed parts), a group's members, the area a sub-structure
belongs to, the two areas a line separates, and every instance of an area with 1 to 3
points on the docs' 0-1000 grid. For the figure: the subject, the whole object shown, and
the areas drawn as one unbroken shape (shares_region). Mock mode answers the listing only,
so its parts have no kind and S2 finds them by phrase.

Version 1 of the locate call had kind "thin" and no lines; S1 outputs cached from it still
load."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import FigureType

Verdict = Literal["make_tactile", "split_two_sheets", "describe_only"]
PartKind = Literal["area", "thin", "line", "group"]  # thin: locate v1 only


class GridPoint(BaseModel):
    """A point on the 0-1000 grid of the image Spark was sent (docs: image-understanding)."""

    model_config = ConfigDict(frozen=True)

    x: int
    y: int


class Instance(BaseModel):
    model_config = ConfigDict(frozen=True)

    where: str  # the main drawing or an inset, in Spark's words
    points: tuple[GridPoint, ...]


class PartPhrase(BaseModel):
    model_config = ConfigDict(frozen=True)

    phrase: str  # a short noun phrase SAM can segment
    print_label: str  # the printed label that points to this part, or empty
    # From the locate call; None when the part was not located.
    kind: PartKind | None = None
    members: tuple[str, ...] = ()  # a group's listed parts
    parent: str = ""  # the listed area it belongs to, or empty
    separates: tuple[str, ...] = ()  # a line's two listed areas, or empty
    instances: tuple[Instance, ...] = ()


class SharedRegion(BaseModel):
    """Listed areas drawn as one unbroken shape, with no drawn boundary between them."""

    model_config = ConfigDict(frozen=True)

    parts: tuple[str, ...]
    name: str  # Spark's name for the combined shape


class SheetContext(BaseModel):
    """What the locate call is told about the sheet: who reads it and how big it prints."""

    model_config = ConfigDict(frozen=True)

    reader: str  # " in grades 6 to 8", or empty when no grade band was given
    width_mm: float
    height_mm: float
    min_part_mm: float
    gap_mm: float


class Understanding(BaseModel):
    """S1: what Muse Spark reads in the figure."""

    model_config = ConfigDict(frozen=True)

    figure_type: FigureType
    title: str
    summary: str
    parts: list[PartPhrase]
    color_carries_meaning: bool
    verdict: Verdict
    verdict_reason: str
    located: bool = False  # the locate call ran, so S2 grounds parts by their points
    subject: str = ""  # the whole object or objects shown, for the silhouette
    shares_region: list[SharedRegion] = []


# The S1 listing schema, from the Spark spike (spikes/spark_spike.py).
LISTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "figure_type": {
            "enum": ["labeled_diagram", "bar_chart", "line_graph", "map", "flow_diagram", "other"]
        },
        "title": {"type": "string"},
        "summary": {"type": "string", "description": "Two sentences at most. No sight words."},
        "parts": {
            "type": "array",
            "maxItems": 25,
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {
                        "type": "string",
                        "description": "Short noun phrase SAM can segment, "
                        "such as 'left ventricle'",
                    },
                    "print_label": {
                        "type": "string",
                        "description": "The exact printed label text that points to this part, "
                        "or empty",
                    },
                },
                "required": ["phrase", "print_label"],
                "additionalProperties": False,
            },
        },
        "color_carries_meaning": {"type": "boolean"},
        "verdict": {"enum": ["make_tactile", "split_two_sheets", "describe_only"]},
        "verdict_reason": {"type": "string"},
    },
    "required": [
        "figure_type",
        "title",
        "summary",
        "parts",
        "color_carries_meaning",
        "verdict",
        "verdict_reason",
    ],
    "additionalProperties": False,
}

_POINT = {
    "type": "object",
    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
    "required": ["x", "y"],
    "additionalProperties": False,
}
_INSTANCE = {
    "type": "object",
    "properties": {
        "where": {"type": "string"},
        "points": {"type": "array", "minItems": 1, "maxItems": 3, "items": _POINT},
    },
    "required": ["where", "points"],
    "additionalProperties": False,
}
_NAMES = {"type": "array", "items": {"type": "string"}}
LOCATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "string"},
                    "kind": {"enum": ["area", "line", "group"]},
                    "members": _NAMES,
                    "parent": {"type": "string"},
                    "separates": _NAMES,
                    "instances": {"type": "array", "items": _INSTANCE},
                },
                "required": ["part", "kind", "members", "parent", "separates", "instances"],
                "additionalProperties": False,
            },
        },
        "shares_region": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"parts": _NAMES, "name": {"type": "string"}},
                "required": ["parts", "name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["subject", "parts", "shares_region"],
    "additionalProperties": False,
}
