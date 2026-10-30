"""Grading aids for the S2 bake-off sheets, with no network: the object area, overlapping
pairs, the per-part flags, the focus view and the graded sheet."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from app.meta import s2_bakeoff as bake
from app.meta import s2_grading as grading

SEA = (42, 122, 177)


def box(h: int, w: int, y0: int, y1: int, x0: int, x1: int) -> npt.NDArray[np.bool_]:
    m = np.zeros((h, w), bool)
    m[y0:y1, x0:x1] = True
    return m


def test_object_area_is_what_differs_from_the_border_color() -> None:
    img = np.full((60, 80, 3), SEA, np.uint8)
    img[10:30, 10:40] = (230, 200, 120)  # land
    img[40:42, 50:70] = (60, 140, 190)  # within 40 of the sea: not object
    assert grading.object_mask(img).sum() == 20 * 30


def test_pairs_overlap_when_they_share_more_than_20_percent_of_the_smaller_mask() -> None:
    a = box(40, 40, 0, 10, 0, 10)  # 100 px
    b = box(40, 40, 7, 17, 0, 10)  # shares 30 px with a
    c = box(40, 40, 16, 26, 0, 10)  # shares 10 px with b
    pairs = grading.overlap_pairs({"a": a, "b": b, "c": c})
    assert pairs == [{"parts": ["a", "b"], "overlap_px": 30, "of_smaller": 0.3}]


def fake_result() -> dict[str, Any]:
    parts = ["inside", "outside", "whole", "unnamed", "bad ids"]
    a_rows = [
        {"part": p, "confidences": [0.5 + i / 10], "point_px": [1, 1], "point_in_mask": True}
        for i, p in enumerate(parts)
    ]
    a_rows[1]["point_in_mask"] = False
    b_rows: list[dict[str, Any]] = [
        {"part": "inside", "region_ids": [1], "invalid_ids": [], "mask_px": 4},
        {"part": "outside", "region_ids": [1, 2], "invalid_ids": [], "mask_px": 16},
        {"part": "whole", "region_ids": [3], "invalid_ids": [], "mask_px": 5},
        {"part": "unnamed", "region_ids": None},
        {"part": "bad ids", "region_ids": [99], "invalid_ids": [99], "mask_px": 0},
    ]
    return {
        "figure": "fake",
        "parts": [{"phrase": p, "print_label": ""} for p in parts],
        "arm_a_rows": a_rows,
        "arm_b_rows": b_rows,
    }


def fake_masks() -> dict[str, dict[str, npt.NDArray[np.bool_]]]:
    return {
        "a": {
            "inside": box(20, 20, 0, 2, 0, 2),
            "outside": box(20, 20, 10, 12, 10, 12),
            "whole": box(20, 20, 0, 12, 0, 12),  # 144 px of 200, over both others
        },
        "b": {
            "inside": box(20, 20, 0, 2, 0, 2),
            "outside": box(20, 20, 0, 4, 0, 4),  # contains inside
            "whole": box(20, 20, 15, 16, 0, 5),
        },
    }


def test_each_flag_comes_from_the_data() -> None:
    g = grading.grade(fake_result(), fake_masks(), object_px=200)
    by = {p["part"]: p for p in g["parts"]}
    assert by["outside"]["a"]["point_outside"] and not by["inside"]["a"]["point_outside"]
    assert by["whole"]["a"]["whole_object"] and by["whole"]["a"]["of_object"] == 0.72
    assert by["inside"]["a"]["overlaps"] == ["whole"]
    assert by["inside"]["b"]["overlaps"] == ["outside"]
    assert by["unnamed"]["b"]["no_regions"] and by["bad ids"]["b"]["no_regions"]
    assert by["unnamed"]["a"]["area_px"] is None and by["whole"]["a"]["confidence"] == 0.7
    assert g["counts"] == {
        "a_point_outside": 1,
        "a_whole_object": 1,
        "a_overlap_pairs": 2,  # whole contains inside and outside
        "b_whole_object": 0,
        "b_overlap_pairs": 1,
        "b_no_regions": 2,
    }
    assert g["summary"].startswith("fake, 5 parts. Arm A: point outside its mask 1,")


def test_the_focus_view_fades_the_figure_and_outlines_the_mask() -> None:
    img = np.full((100, 100, 3), 100, np.uint8)
    view = np.asarray(grading.focus_view(img, box(100, 100, 40, 60, 40, 60), [50, 50]))
    assert abs(int(view[5, 5, 0]) - round(100 * 0.3 + 255 * 0.7)) <= 1  # faded
    assert tuple(view[45, 45]) == (100, 100, 100)  # the mask at full strength
    outline = {tuple(int(c) for c in view[42, x]) for x in (38, 39)}  # off the crosshair
    assert len(outline) == 1 and outline.pop() in grading.OUTLINE_COLORS  # 2 px, outside
    assert abs(int(view[42, 37, 0]) - 208) <= 1
    assert tuple(view[50, 50]) == (100, 100, 100)  # the crosshair leaves its center clear
    assert tuple(view[50, 60]) == (0, 0, 0)  # and draws its arms in black


def test_the_graded_sheet_has_the_view_flags_and_sorting_and_no_grades(tmp_path: Path) -> None:
    result = fake_result() | {"image": "fake.png", "size": [20, 20]}
    g = grading.grade(result, fake_masks(), object_px=200)
    bake.write_sheet(result, tmp_path, g)
    page = (tmp_path / "index.html").read_text()
    steps = json.loads(page.split("const STEPS = ")[1].split(";\nlet at")[0])
    assert [s["part"] for s in steps] == ["inside", "outside", "whole", "unnamed", "bad ids"]
    assert "FLAG: point not inside its own mask" in steps[1]["a_facts"]
    assert steps[3]["b_facts"] == ["region ids []", "no mask", "FLAG: no regions assigned"]
    assert 'id="sort"' in page and "ArrowRight" in page and 'data-conf="0.7"' in page
    assert page.count("<td></td><td></td></tr>") == 5  # pass/fail left blank
    assert "—" not in page


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_the_committed_overlaps_file_counts_its_own_rows(name: str) -> None:
    g = json.loads((bake.OUT_ROOT / "overlaps.json").read_text())["figures"][name]
    parts = g["parts"]
    assert g["counts"] == {
        "a_point_outside": sum(p["a"]["point_outside"] for p in parts),
        "a_whole_object": sum(p["a"]["whole_object"] for p in parts),
        "a_overlap_pairs": len(g["pairs"]["a"]),
        "b_whole_object": sum(p["b"]["whole_object"] for p in parts),
        "b_overlap_pairs": len(g["pairs"]["b"]),
        "b_no_regions": sum(p["b"]["no_regions"] for p in parts),
    }
    live = json.loads((bake.OUT_ROOT / name / "results.json").read_text())
    outside = {r["part"] for r in live["arm_a_rows"] if r.get("point_in_mask") is False}
    assert {p["part"] for p in parts if p["a"]["point_outside"]} == outside
