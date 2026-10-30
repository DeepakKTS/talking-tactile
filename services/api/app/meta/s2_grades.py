"""Human grades for the S2 bake-off masks, kept in eval/s2-bakeoff/FIGURE/grades.json.

A grades file holds the figure, the source of the grades, the parts left ungraded, and one
entry per graded part per arm: part (the phrase as Spark listed it), arm (A or B), grade
(pass, conditional or fail), reason (one of REASONS, or null when the grader gave none) and
a note in the grader's words. Nothing here grades a mask; it reads and checks what a person
wrote."""

import json
from pathlib import Path
from typing import Any

GRADES = ("pass", "conditional", "fail")
REASONS = ("sliver", "label", "line", "noise", "spill", "whole", "missing", "partial", "wrong")
ARMS = ("A", "B")


def path(out_dir: Path) -> Path:
    return out_dir / "grades.json"


def load(out_dir: Path) -> dict[str, Any]:
    return dict(json.loads(path(out_dir).read_text(encoding="utf-8")))


def problems(grades: dict[str, Any], parts: list[str]) -> list[str]:
    """What is wrong with a grades file, given the figure's listed parts. Empty is valid."""
    out = []
    seen: set[tuple[str, str]] = set()
    for e in grades["grades"]:
        key = (e["part"], e["arm"])
        if e["part"] not in parts:
            out.append(f"unknown part {e['part']!r}")
        if e["arm"] not in ARMS:
            out.append(f"{key}: arm {e['arm']!r}")
        if e["grade"] not in GRADES:
            out.append(f"{key}: grade {e['grade']!r}")
        if e["reason"] is not None and e["reason"] not in REASONS:
            out.append(f"{key}: reason {e['reason']!r}")
        if key in seen:
            out.append(f"{key}: graded twice")
        seen.add(key)
    for part in grades["ungraded"]:
        if part not in parts:
            out.append(f"unknown ungraded part {part!r}")
        if any(e["part"] == part for e in grades["grades"]):
            out.append(f"{part!r} is both graded and ungraded")
    return out


def by_part(grades: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{part: {arm: entry}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for e in grades["grades"]:
        out.setdefault(e["part"], {})[e["arm"]] = e
    return out


def tally(grades: dict[str, Any]) -> dict[str, Any]:
    """Per arm, how many pass, conditional and fail; and, counting only pass as a pass, how
    many graded parts passed in both arms, A only, B only or neither."""
    per = by_part(grades)
    arms = {
        arm: {g: sum(1 for p in per.values() if arm in p and p[arm]["grade"] == g) for g in GRADES}
        for arm in ARMS
    }
    passed = {
        part: tuple(a.get(arm, {}).get("grade") == "pass" for arm in ARMS)
        for part, a in per.items()
    }
    strict = {
        "both": sum(1 for v in passed.values() if v == (True, True)),
        "a_only": sum(1 for v in passed.values() if v == (True, False)),
        "b_only": sum(1 for v in passed.values() if v == (False, True)),
        "neither": sum(1 for v in passed.values() if v == (False, False)),
    }
    return {"graded": len(per), "arms": arms, "strict": strict}
