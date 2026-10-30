"""Author's overlap warning (app/geometry/overlap.py): an outline covering the drawn region
of another part's prompt point, never a gate."""

import numpy as np
import numpy.typing as npt

from app.config import load_tactile_rules
from app.geometry import points as gp
from app.geometry.boundaries import Drawn
from app.geometry.overlap import overlaps
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import fit_to_page
from app.meta.types import PartPhrase, Understanding
from app.models.mask import Mask

RULES = load_tactile_rules()
W, H = 200, 120


def outlined(img: npt.NDArray[np.uint8], x0: int, x1: int) -> None:
    img[10:12, x0:x1] = img[98:100, x0:x1] = 0
    img[10:100, x0 : x0 + 2] = img[10:100, x1 - 2 : x1] = 0


def two_boxes() -> npt.NDArray[np.uint8]:
    img = np.full((H, W, 3), 255, np.uint8)
    img[12:98, 12:88] = (240, 200, 120)
    img[12:98, 112:188] = (120, 200, 240)
    outlined(img, 10, 90)
    outlined(img, 110, 190)
    return img


def box(x0: int, x1: int) -> npt.NDArray[np.bool_]:
    m = np.zeros((H, W), bool)
    m[12:98, x0:x1] = True
    return m


def part(pid: str, label: str, data: npt.NDArray[np.bool_]) -> ReconciledPart:
    return ReconciledPart(id=pid, mask=Mask(data=data, label=label, score=0.9, source="sam"))


def plan(*names: str, parent: dict[str, str] | None = None) -> Understanding:
    parts = [
        PartPhrase(phrase=n, print_label=n, kind="area", parent=(parent or {}).get(n, ""))
        for n in names
    ]
    return Understanding(figure_type="labeled_diagram", title="t", summary="s", parts=parts,
                         color_carries_meaning=False, verdict="make_tactile",
                         verdict_reason="r", located=True)  # fmt: skip


def run(parts: list[ReconciledPart], u: Understanding, img: npt.NDArray[np.uint8]) -> list[str]:
    scene = gp.scene_of(img, 0.0)
    drawn = Drawn(img, scene.marks, scene.obj)
    pts = {"left": [(50, 55)], "right": [(150, 55)]}
    fit = fit_to_page(W, H, "letter", RULES.page)
    return [f"{w.part}: {w.text}" for w in overlaps(parts, parts, u, pts, {}, drawn, fit, RULES)]


def test_an_outline_over_the_drawn_region_of_another_parts_point_is_warned() -> None:
    parts = [part("r1", "left", box(12, 188)), part("r2", "right", box(112, 188))]
    assert run(parts, plan("left", "right"), two_boxes()) == [
        "left: This outline also covers the area where right is"
    ]


def test_outlines_inside_their_own_drawn_regions_are_not_warned() -> None:
    parts = [part("r1", "left", box(12, 88)), part("r2", "right", box(112, 188))]
    assert run(parts, plan("left", "right"), two_boxes()) == []


def test_a_nested_childs_region_is_its_parents_own() -> None:
    parts = [part("r1", "left", box(12, 188)), part("r2", "right", box(112, 188))]
    assert run(parts, plan("left", "right", parent={"right": "left"}), two_boxes()) == []


def test_a_merged_part_owns_the_points_of_what_was_merged_into_it() -> None:
    before = [part("r1", "left", box(12, 88)), part("r2", "right", box(112, 188))]
    merged = before[0].model_copy(
        update={
            "mask": Mask(data=box(12, 188), label="both", score=0.9, source="sam"),
            "merged": ["right"],
        }
    )
    scene = gp.scene_of(two_boxes(), 0.0)
    drawn = Drawn(two_boxes(), scene.marks, scene.obj)
    pts = {"left": [(50, 55)], "right": [(150, 55)]}
    fit = fit_to_page(W, H, "letter", RULES.page)
    assert overlaps([merged], before, plan("left", "right"), pts, {}, drawn, fit, RULES) == []


def test_in_one_shaded_region_parts_whose_fills_differ_are_not_warned() -> None:
    """The Blausen lobes: shaded into each other, one drawn region, told apart by color."""
    img = np.full((H, W, 3), 255, np.uint8)
    t = np.linspace(0, 1, 176)[None, :, None]
    img[12:98, 12:188] = np.rint((1 - t) * np.array((182, 69, 64)) + t * np.array((111, 144, 175)))
    outlined(img, 10, 190)
    parts = [part("r1", "left", box(12, 188)), part("r2", "right", box(112, 188))]
    assert run(parts, plan("left", "right"), img) == []
