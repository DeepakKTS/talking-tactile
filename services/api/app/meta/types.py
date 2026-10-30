"""What the pipeline gets back from the Meta models, as our own types. The Spark spike's S1
schema (spikes/spark_spike.py) is the source for Understanding.

Live S1 is two Spark calls. The listing (LISTING_SCHEMA) names the parts. The locate call
(LOCATE_SCHEMA, app/prompts/s1_locate.v1.json) gives each part a kind, a group's members,
the part it sits inside, and every instance with 1 to 3 points on the docs' 0-1000 grid.
Mock mode answers the listing only, so its parts have no kind and S2 finds them by phrase."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import FigureType

Verdict = Literal["make_tactile", "split_two_sheets", "describe_only"]
PartKind = Literal["area", "thin", "group"]


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
    parent: str = ""  # the listed part it sits inside, or empty
    instances: tuple[Instance, ...] = ()


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
LOCATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "string"},
                    "kind": {"enum": ["area", "thin", "group"]},
                    "members": {"type": "array", "items": {"type": "string"}},
                    "parent": {"type": "string"},
                    "instances": {"type": "array", "items": _INSTANCE},
                },
                "required": ["part", "kind", "members", "parent", "instances"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["parts"],
    "additionalProperties": False,
}
