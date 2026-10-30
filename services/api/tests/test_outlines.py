"""Fix outline with no network: the outline edit and its digest, the point checks, applying a
teacher's mask to S2's output, and the spill check."""

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from app.geometry import points as gp
from app.geometry.print_marks import PrintMarks
from app.meta.types import PartPhrase, Understanding
from app.models.mask import Mask
from app.pipeline import edits as ed
from app.pipeline.outlines import (
    OutlineError,
    check_points,
    old_outline,
    spill_of,
    with_outlines,
)
from app.pipeline.s2_types import Grounded, TeacherPart


def outline(part: str = "aorta", pos: Any = ((10, 10),), neg: Any = ()) -> ed.OutlineEdit:
    return ed.OutlineEdit(
        op="outline", region="s1", part=part, positive=list(pos), negative=list(neg)
    )


def test_an_outline_edit_needs_a_positive_point_and_whole_pixels() -> None:
    assert ed.EDIT.validate_python(
        {"op": "outline", "region": "r3", "part": "aorta", "positive": [[5, 6]]}
    )
    for bad in (
        {"positive": []},
        {"positive": [[1.5, 2]]},
        {"positive": [[-1, 2]]},
        {"positive": [[1, 2]] * 21},
        {"positive": [[1, 2]], "negative": [[1, 2]] * 21},
    ):
        with pytest.raises(ValidationError):
            ed.EDIT.validate_python({"op": "outline", "region": "r3", "part": "aorta", **bad})


def test_the_s3_share_of_the_edits_is_the_outlines_only_and_the_last_per_part() -> None:
    label = ed.LabelEdit(op="label", region="r1", label="x")
    first, second = outline(pos=[(1, 1)]), outline(pos=[(2, 2)])
    assert ed.outlines([first, label, second]) == [second]
    assert ed.outlines_digest([label]) == ed.outlines_digest([])
    assert ed.outlines_digest([first]) != ed.outlines_digest([second])
    assert ed.outlines_digest([first, second]) == ed.outlines_digest([second])
    assert ed.outlines_digest([outline(neg=[(3, 3)])]) != ed.outlines_digest([outline()])


def test_apply_edits_leaves_outlines_to_before_s3() -> None:
    assert ed.apply_edits([], [outline()], {}, 0.95) == []


def scene() -> gp.Scene:
    img = np.full((40, 40, 3), 255, np.uint8)
    img[10:30, 10:30] = (200, 40, 40)
    text = np.zeros((40, 40), bool)
    text[12:14, 12:20] = True
    none = np.zeros((40, 40), bool)
    marks = PrintMarks(text=text, line=none, ink=none, words=[], segments=[])
    return gp.Scene(img, marks, gp.object_mask(img), 40.0)


def test_a_positive_click_off_the_figure_is_refused_and_one_on_text_warned() -> None:
    sc = scene()
    assert check_points(sc, [(20, 20)], [(2, 2)]) == []  # a negative point may be on the page
    assert check_points(sc, [(15, 13)], []) == ["The positive point at (15, 13) is on label text."]
    with pytest.raises(OutlineError, match="on the page"):
        check_points(sc, [(2, 2)], [])
    with pytest.raises(OutlineError, match="outside"):
        check_points(sc, [(40, 2)], [])


def mask(y0: int, y1: int) -> np.ndarray:
    m = np.zeros((40, 40), bool)
    m[y0:y1, 10:30] = True
    return m


def grounded() -> Grounded:
    sam = lambda d, label: Mask(data=d, label=label, score=0.9, source="sam")  # noqa: E731
    return Grounded(
        parts=[
            sam(mask(0, 5), "a"),
            sam(mask(5, 10), "b"),
            sam(mask(10, 15), "b"),
            sam(mask(15, 20), "c"),
        ],
        text=[],
        teacher=[TeacherPart(phrase="d", reason="spill", detail="x", suggestion=mask(20, 40))],
        facts={"a": {"points": [[{"sent": [12, 2]}]]}, "c": {"points": [[{"sent": [12, 17]}]]}},
    )


def test_an_outline_replaces_the_mask_in_place_so_later_ids_keep() -> None:
    g = with_outlines(grounded(), [("b", mask(30, 35))])
    assert [m.label for m in g.parts] == ["a", "b", "c"]
    assert g.parts[1].source == "teacher" and int(g.parts[1].data.sum()) == 100


def test_an_outline_gives_a_teacher_part_its_first_mask_at_the_end() -> None:
    g = with_outlines(grounded(), [("d", mask(30, 35))])
    assert [m.label for m in g.parts] == ["a", "b", "b", "c", "d"] and g.teacher == []


def test_the_old_outline_is_the_s2_mask_or_the_spill_suggestion() -> None:
    g = grounded()
    old_b = old_outline("b", g)
    assert old_b is not None and int(old_b.sum()) == 200
    old_d = old_outline("d", g)
    assert old_d is not None and int(old_d.sum()) == 400
    assert old_outline("e", g) is None


def test_the_spill_check_finds_other_parts_points_but_not_a_childs() -> None:
    u = Understanding(
        figure_type="other",
        title="t",
        summary="s",
        parts=[
            PartPhrase(phrase="b", print_label=""),
            PartPhrase(phrase="c", print_label="", parent="b"),
        ],
        color_carries_meaning=False,
        verdict="make_tactile",
        verdict_reason="r",
    )
    assert spill_of("b", mask(0, 20), grounded(), u) == ["a"]  # c is b's child
    assert spill_of("b", mask(5, 10), grounded(), u) == []
