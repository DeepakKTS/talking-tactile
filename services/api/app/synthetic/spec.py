"""What the synthetic figure contains. This is test data, so its numbers live here rather
than in config/: each planted problem is sized against the config limits in the tests.

Layout in figure-area mm (the figure area is the page inside the margin):

    outer chamber  ellipse, holds the inner core with wide clearance (nested part)
    right chamber  rounded rect, 15 mm right of the outer chamber
    cross vessel   bar under both chambers
    left lobe / right lobe   2.0 mm apart: closer than the minimum gap
    pore           4.0 mm across: smaller than the minimum point symbol
    stem           narrow bar at the bottom

Fill color carries meaning: one color per category, four area categories, which is
more than the three textures allowed for lower grades.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.synthetic.shapes import Shape

Rgb = tuple[int, int, int]

PAGE: Literal["letter"] = "letter"
GRADE_BAND: Literal["k5"] = "k5"
TITLE = "Synthetic test figure"
SUMMARY = "A test figure with eight parts. One part sits inside another."

OUTLINE_MM = 0.5
TEXT_HEIGHT_MM = 3.0
TEXT_PAD_MM = 0.5
OUTLINE_RGB: Rgb = (0, 0, 0)
TEXT_RGB: Rgb = (20, 20, 20)
BACKGROUND_RGB: Rgb = (255, 255, 255)

CATEGORY_RGB: dict[str, Rgb] = {
    "chamber": (240, 170, 170),
    "core": (250, 230, 140),
    "vessel": (160, 200, 240),
    "lobe": (170, 225, 170),
    "pore": (120, 80, 160),
}

PLANTED_GAP_MM = 2.0
PLANTED_POINT_MM = 4.0
LOBE_LEAK_MM = 1.5
DUPLICATE_GROW_MM = 1.0


class PartSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    label: str
    category: str
    shape: Shape
    score: float
    text_at: tuple[float, float]  # top-left of the printed label, figure-area mm
    parent: str | None = None


def _rect(x0: float, y0: float, x1: float, y1: float) -> Shape:
    return Shape(kind="rect", x0=x0, y0=y0, x1=x1, y1=y1)


_LEFT_LOBE_X1 = 80.0
_PORE_C = (120.0, 210.0)

PARTS: list[PartSpec] = [
    PartSpec(
        id="outer",
        label="outer chamber",
        category="chamber",
        shape=Shape(kind="ellipse", x0=15, y0=20, x1=85, y1=100),
        score=0.93,
        text_at=(15, 6),
    ),
    PartSpec(
        id="core",
        label="inner core",
        category="core",
        shape=Shape(kind="ellipse", x0=36, y0=46, x1=64, y1=74),
        score=0.88,
        text_at=(40, 103),
        parent="outer",
    ),
    PartSpec(
        id="right",
        label="right chamber",
        category="chamber",
        shape=Shape(kind="rounded_rect", x0=100, y0=20, x1=150, y1=100, radius=6),
        score=0.95,
        text_at=(100, 6),
    ),
    PartSpec(
        id="vessel",
        label="cross vessel",
        category="vessel",
        shape=_rect(15, 115, 150, 130),
        score=0.90,
        text_at=(60, 133),
    ),
    PartSpec(
        id="left_lobe",
        label="left lobe",
        category="lobe",
        shape=_rect(15, 145, _LEFT_LOBE_X1, 190),
        score=0.87,
        text_at=(45, 194),
    ),
    PartSpec(
        id="right_lobe",
        label="right lobe",
        category="lobe",
        shape=_rect(_LEFT_LOBE_X1 + PLANTED_GAP_MM, 145, 150, 190),
        score=0.86,
        text_at=(85, 194),
    ),
    PartSpec(
        id="pore",
        label="pore",
        category="pore",
        shape=Shape(
            kind="ellipse",
            x0=_PORE_C[0] - PLANTED_POINT_MM / 2,
            y0=_PORE_C[1] - PLANTED_POINT_MM / 2,
            x1=_PORE_C[0] + PLANTED_POINT_MM / 2,
            y1=_PORE_C[1] + PLANTED_POINT_MM / 2,
        ),
        score=0.74,
        text_at=(126, 207),
    ),
    PartSpec(
        id="stem",
        label="stem",
        category="vessel",
        shape=_rect(30, 200, 40, 225),
        score=0.81,
        text_at=(45, 212),
    ),
]

PART_BY_ID = {p.id: p for p in PARTS}

# What SAM would plausibly return. "becomes" is the part a raw mask should end up as
# after reconciliation, or None when it should be dropped.
RawFate = Literal["keep", "merge_duplicate", "drop_sliver", "text", "trim_overlap"]


class RawSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    phrase: str
    shapes: list[Shape]
    with_text_of: str | None = None  # SAM also grabbed this part's printed label
    score: float
    fate: RawFate
    becomes: str | None
    note: str


SPECK = _rect(157, 60, 158, 60.8)
SLIVER = _rect(20, 131.0, 140, 131.25)

RAW: list[RawSpec] = [
    RawSpec(id="raw_outer", phrase="outer chamber", shapes=[PART_BY_ID["outer"].shape],
            score=0.93, fate="keep", becomes="outer",
            note="covers the inner core too, so the core nests inside it"),
    RawSpec(id="raw_core", phrase="inner core", shapes=[PART_BY_ID["core"].shape],
            score=0.88, fate="keep", becomes="core", note="fully inside the outer chamber"),
    RawSpec(id="raw_right", phrase="right chamber", shapes=[PART_BY_ID["right"].shape, SPECK],
            score=0.95, fate="keep", becomes="right",
            note="has a 0.8 mm2 speck that must be removed"),
    RawSpec(id="raw_right_dup", phrase="right side chamber",
            shapes=[PART_BY_ID["right"].shape.grown(DUPLICATE_GROW_MM)],
            score=0.62, fate="merge_duplicate", becomes="right",
            note="near duplicate of the right chamber, 1 mm larger all round"),
    RawSpec(id="raw_vessel", phrase="cross vessel", shapes=[PART_BY_ID["vessel"].shape],
            with_text_of="vessel", score=0.90, fate="keep", becomes="vessel",
            note="includes its own printed label, which must be cut out"),
    RawSpec(id="raw_sliver", phrase="cross vessel", shapes=[SLIVER], score=0.31,
            fate="drop_sliver", becomes=None, note="0.25 mm thin line under the vessel"),
    RawSpec(id="raw_left_lobe", phrase="left lobe",
            shapes=[_rect(15, 145, _LEFT_LOBE_X1 + LOBE_LEAK_MM, 190)],
            score=0.87, fate="trim_overlap", becomes="left_lobe",
            note="leaks 1.5 mm into the gap; overlaps the right lobe by 1 mm"),
    RawSpec(id="raw_right_lobe", phrase="right lobe",
            shapes=[_rect(_LEFT_LOBE_X1 + PLANTED_GAP_MM - LOBE_LEAK_MM, 145, 150, 190)],
            score=0.86, fate="trim_overlap", becomes="right_lobe",
            note="leaks 1.5 mm into the gap from the other side"),
    RawSpec(id="raw_pore", phrase="pore", shapes=[PART_BY_ID["pore"].shape], score=0.74,
            fate="keep", becomes="pore", note="below the point symbol size"),
    RawSpec(id="raw_stem", phrase="stem", shapes=[PART_BY_ID["stem"].shape], score=0.81,
            fate="keep", becomes="stem", note="clean"),
]  # fmt: skip
