"""The committed S2 bake-off grades: every file is valid against its figure's listed parts,
and its tally is the one the grader reported."""

import json
from typing import Any

import pytest

from app.meta import s2_bakeoff as bake
from app.meta import s2_grades as grades

GRADED = sorted(p.parent.name for p in bake.OUT_ROOT.glob("*/grades.json"))


def parts_of(name: str) -> list[str]:
    result = json.loads((bake.OUT_ROOT / name / "results.json").read_text())
    return [p["phrase"] for p in result["parts"]]


def test_there_are_grades() -> None:
    assert "heart" in GRADED


@pytest.mark.parametrize("name", GRADED)
def test_each_grades_file_is_valid(name: str) -> None:
    g = grades.load(bake.OUT_ROOT / name)
    assert g["figure"] == name
    assert g["source"] == "Deepak and Claude review, 2026-10-29"
    assert grades.problems(g, parts_of(name)) == []
    graded = {e["part"] for e in g["grades"]}
    assert graded | set(g["ungraded"]) == set(parts_of(name))
    assert all({e["arm"] for e in g["grades"] if e["part"] == p} == {"A", "B"} for p in graded)


def test_problems_are_found() -> None:
    bad: dict[str, Any] = {
        "ungraded": ["x", "a"],
        "grades": [
            {"part": "a", "arm": "A", "grade": "pass", "reason": None},
            {"part": "a", "arm": "A", "grade": "ok", "reason": "smudge"},
            {"part": "z", "arm": "C", "grade": "fail", "reason": "spill"},
        ],
    }
    assert grades.problems(bad, ["a", "b"]) == [
        "('a', 'A'): grade 'ok'",
        "('a', 'A'): reason 'smudge'",
        "('a', 'A'): graded twice",
        "unknown part 'z'",
        "('z', 'C'): arm 'C'",
        "unknown ungraded part 'x'",
        "'a' is both graded and ungraded",
    ]


def test_the_heart_tally_is_the_graders() -> None:
    """14 shown: both 1, A only 3 plus 3 conditional, B only 0, neither 7."""
    t = grades.tally(grades.load(bake.OUT_ROOT / "heart"))
    assert t["graded"] == 14
    # Strict counts only pass, so neither holds the grader's 7 and the 3 conditional in A.
    assert t["strict"] == {"both": 1, "a_only": 3, "b_only": 0, "neither": 10}
    assert t["arms"]["A"] == {"pass": 4, "conditional": 3, "fail": 7}
    assert t["arms"]["B"] == {"pass": 1, "conditional": 0, "fail": 13}
