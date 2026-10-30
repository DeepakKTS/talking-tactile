"""The S2 mask scorer with no network: IoU against a passing mask, the size floors, text and
line shares, fragments, sibling overlap, the prompt points, confident fails. And the
committed bake-off eval data: scores, references and overlaps.json."""

import json
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from app.geometry.print_marks import PrintMarks
from app.meta import s2_bakeoff as bake
from app.meta import s2_grades as grades
from app.meta import s2_score as score

H = W = 200  # on a letter page, 0.8255 mm per px: a speck is under 2.9 px, a symbol 47.2 px


def box(y0: int, y1: int, x0: int, x1: int) -> npt.NDArray[np.bool_]:
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


def marks() -> PrintMarks:
    return PrintMarks(
        text=box(0, 10, 0, 50),
        line=box(100, 102, 0, 200),
        ink=box(150, 151, 0, 200),
        words=[(0, 0, 50, 10)],
        segments=[(0, 100, 199, 100)],
    )


def test_iou_and_fragments() -> None:
    assert score.iou(box(0, 10, 0, 10), box(0, 10, 5, 15)) == pytest.approx(50 / 150)
    two = box(20, 30, 20, 30) | box(60, 70, 60, 70) | box(90, 91, 90, 92)  # 2 px is a speck
    assert score.fragments(two, floor_px=2.9) == 2


def test_references_prefer_arm_a_and_need_a_pass() -> None:
    g: dict[str, Any] = {
        "grades": [
            {"part": "x", "arm": "A", "grade": "pass"},
            {"part": "x", "arm": "B", "grade": "pass"},
            {"part": "y", "arm": "A", "grade": "fail"},
            {"part": "y", "arm": "B", "grade": "pass"},
            {"part": "z", "arm": "A", "grade": "conditional"},
            {"part": "z", "arm": "B", "grade": "fail"},
        ]
    }
    a, b = box(0, 5, 0, 5), box(5, 9, 5, 9)
    refs = score.references(g, {"a": {"x": a, "y": a, "z": a}, "b": {"x": b, "y": b}})
    assert {p: r["arm"] for p, r in refs.items()} == {"x": "A", "y": "B"}
    assert refs["y"]["mask"] is b


def run() -> dict[str, Any]:
    return {
        "figure": "fake",
        "parts": ["chamber", "label", "speck", "lined", "missing"],
        "masks": {
            "chamber": box(40, 80, 40, 80) | box(120, 140, 120, 140),
            "label": box(0, 4, 0, 10),  # 40 px, under a point symbol
            "speck": box(190, 191, 190, 192),
            "lined": box(95, 105, 60, 70),
        },
        "points": {"chamber": [[60, 60]], "label": [[5, 5]], "lined": [[65, 101]]},
        "confidence": {"chamber": 0.9, "label": 0.75, "speck": 0.71, "lined": None},
    }


def test_each_number_comes_from_the_masks() -> None:
    refs = {"chamber": {"arm": "A", "mask": box(40, 80, 40, 80)}}
    s = score.score(run(), np.zeros((H, W, 3), np.uint8), marks(), refs)
    by = {r["part"]: r for r in s["parts"]}
    chamber = by["chamber"]
    assert chamber["reference"] == {"arm": "A", "iou": 0.8, "regression": False}
    assert chamber["fragments"] == 2 and not chamber["under_point_symbol"]
    assert by["label"]["text_share"] == 1.0 and by["label"]["under_point_symbol"]
    assert by["speck"]["speck"] and by["speck"]["fragments"] == 0
    assert by["lined"]["line_share"] == 0.2
    assert by["missing"]["area_px"] == 0 and by["missing"]["flags"] == ["no mask"]
    assert by["label"]["points"] == [
        {"xy": [5, 5], "on_text": True, "on_line": False, "on_ink": False}
    ]
    assert "point [65, 101] on line" in by["lined"]["flags"]
    assert s["counts"] == {
        "parts": 5,
        "no_mask": 1,
        "needs_teacher": 0,
        "regression": 0,
        "references": 1,
        "speck": 1,
        "under_point_symbol": 2,
        "on_text": 1,
        "on_line": 1,
        "fragmented": 1,
        "overlap_pairs": 0,
        "overlap_pairs_before": 0,
        "points": 3,
        "points_on_text": 1,
        "points_on_line": 1,
        "points_on_ink": 0,
    }


def test_a_mask_far_from_its_passing_mask_is_a_regression() -> None:
    refs = {"chamber": {"arm": "B", "mask": box(0, 40, 0, 40)}}
    s = score.score(run(), np.zeros((H, W, 3), np.uint8), marks(), refs)
    assert s["parts"][0]["reference"] == {"arm": "B", "iou": 0.0, "regression": True}
    assert s["parts"][0]["flags"][0] == "regression: IoU 0.0 with the passing Arm B mask"


def test_confident_fails_are_arm_a_fails_at_or_over_0_7() -> None:
    s = score.score(run(), np.zeros((H, W, 3), np.uint8), marks(), {})
    g: dict[str, Any] = {
        "grades": [
            {"part": "chamber", "arm": "A", "grade": "pass", "reason": None},
            {"part": "label", "arm": "A", "grade": "fail", "reason": "label"},
            {"part": "speck", "arm": "B", "grade": "fail", "reason": "sliver"},
            {"part": "lined", "arm": "A", "grade": "fail", "reason": "line"},
        ]
    }
    assert score.confident_fails(s, g) == [{"part": "label", "confidence": 0.75, "reason": "label"}]


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_the_committed_v1_scores_count_their_own_rows(name: str) -> None:
    s = json.loads((bake.OUT_ROOT / "scores_v1.json").read_text())["figures"][name]
    rows, c = s["parts"], s["counts"]
    assert c["parts"] == len(rows)
    assert c["speck"] == sum(r["speck"] for r in rows)
    assert c["fragmented"] == sum(1 for r in rows if score.fragmented(r))
    assert c["points_on_text"] == sum(p["on_text"] for r in rows for p in r["points"])
    g = grades.load(bake.OUT_ROOT / name)
    assert score.confident_fails(s, g) == s["confident_fails"]
    live = json.loads((bake.OUT_ROOT / name / "results.json").read_text())
    assert [r["part"] for r in rows] == [p["phrase"] for p in live["parts"]]


def test_groups_are_not_siblings_and_instances_explain_pieces() -> None:
    r = run() | {
        "kind": {"chamber": "area", "label": "group"},
        "instances": {"chamber": 2},
    }
    r["masks"]["label"] = box(40, 80, 40, 80)  # a group over its member
    s = score.score(r, np.zeros((H, W, 3), np.uint8), marks(), {})
    by = {x["part"]: x for x in s["parts"]}
    assert s["pairs"] == [] and by["chamber"]["overlaps"] == []
    assert by["chamber"]["fragments"] == 2 and not score.fragmented(by["chamber"])
    assert s["counts"]["fragmented"] == 0


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_the_committed_v2_scores_count_their_own_rows(name: str) -> None:
    s = json.loads((bake.OUT_ROOT / "scores_v2.json").read_text())["figures"][name]
    rows, c = s["parts"], s["counts"]
    assert "confident_fails" not in s  # the grades are of v1's masks
    assert c["fragmented"] == sum(1 for r in rows if score.fragmented(r))
    assert c["points"] == sum(len(r["points"]) for r in rows)
    assert c["overlap_pairs_before"] == len(s["pairs_before"])
    v2 = json.loads((bake.OUT_ROOT / name / "results_v2.json").read_text())
    assert [r["part"] for r in rows] == [r["part"] for r in v2["rows"]]
    assert [r["area_px"] for r in rows] == [r["final_px"] for r in v2["rows"]]


def test_overlap_is_reported_before_and_after_resolution() -> None:
    r = run()
    r["masks_before"] = dict(r["masks"]) | {"label": box(40, 80, 40, 80)}  # spilled on chamber
    s = score.score(r, np.zeros((H, W, 3), np.uint8), marks(), {})
    by = {x["part"]: x for x in s["parts"]}
    assert by["label"]["overlaps_before"] == ["chamber"] and by["label"]["overlaps"] == []
    assert (s["counts"]["overlap_pairs_before"], s["counts"]["overlap_pairs"]) == (1, 0)
    assert "overlapped before resolution chamber" in by["label"]["flags"]


def test_a_part_left_for_the_teacher_says_why() -> None:
    r = run() | {"teacher": {"missing": "spill, holds points of a, b"}}
    s = score.score(r, np.zeros((H, W, 3), np.uint8), marks(), {})
    by = {x["part"]: x for x in s["parts"]}
    assert by["missing"]["flags"] == ["needs teacher: spill, holds points of a, b"]
    assert s["counts"]["needs_teacher"] == 1


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_each_passing_grade_has_its_saved_reference(name: str) -> None:
    refs = score.load_references(name)
    per = grades.by_part(grades.load(bake.OUT_ROOT / name))
    passed = {
        p: next(a for a in grades.ARMS if e.get(a, {}).get("grade") == "pass")
        for p, e in per.items()
        if any(x.get("grade") == "pass" for x in e.values())
    }
    assert {p: r["arm"] for p, r in refs.items()} == passed
    assert all(r["mask"].any() for r in refs.values())


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
