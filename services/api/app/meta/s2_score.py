"""S2 mask scorer: numbers per part from a run's masks, with no live calls.

    uv run python -m app.meta.s2_score v1|v2|v2f

v1 is the bake-off's Arm A, its masks replayed from fixtures/recorded/bakeoff_*.json; v2 is
Arm A v2 (app/meta/s2_armav2.py), replayed from fixtures/recorded/armav2_*.json; v2f is
v2 with the fixes (point clearance, empty-mask rule, spill retry), replayed from
armav2f_*.json, for the figures it ran on. Writes
eval/s2-bakeoff/scores_RUN.json and scores_RUN.md. Nothing here grades a mask.

Per part:
- reference: for a part graded pass in the review, the IoU of this run's mask with the
  passing mask (Arm A's if A passed, else Arm B's); under REGRESSION_IOU is a regression.
- too small: under S3's speck floor (reconcile.speck_max_area_mm2, 2 mm2) is a speck. Under
  the area of a point symbol is a proposal: a disk spacing.point_symbol_min_mm wide, 32.2 mm2.
  That 6.4 mm is sourced in the spacing rules (1/4 inch, APH "Planning and Designing Quality
  Tactile Graphics"; RULES.md 3.4), not in S3's rules, which have no area floor but the
  speck. PLAN.md S4 turns parts under the point symbol size into point symbols.
- text and line: the share of the mask on label text and on leader lines, found in code
  (app/geometry/print_marks.py). Over ON_MARKS is flagged.
- fragments: 8-connected pieces at or over the speck floor; flagged when there are more
  pieces than instances (v2 lists each instance; v1 has one), never for a group.
- sibling overlap: as in overlaps.json, another part of the run covering more than 20% of the
  smaller mask. Groups are left out: a group's mask is its members'. Reported before and
  after v2 gives contested pixels to the smaller mask; before is the real spill measure.
  v1 has no such step, so its before and after are the same masks.
- points: whether each prompt point is on text, a leader line or ink.
Sizes are on a letter page, as S3 would print the figure."""

import argparse
import asyncio
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from app.config import load_tactile_rules
from app.geometry import print_marks
from app.geometry.scale import fit_to_page
from app.meta import s2_armav2
from app.meta import s2_bakeoff as bake
from app.meta import s2_grades as grades
from app.meta import s2_grading as grading
from app.pipeline.cache import load_mask

Mask = npt.NDArray[np.bool_]

REGRESSION_IOU = 0.8
ON_MARKS = 0.1
CONFIDENT = 0.7


def iou(a: Mask, b: Mask) -> float:
    union = int((a | b).sum())
    return int((a & b).sum()) / union if union else 0.0


def fragments(mask: Mask, floor_px: float) -> int:
    n, _, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= floor_px)


def point_on(point: list[int], marks: print_marks.PrintMarks) -> dict[str, Any]:
    x, y = point
    return {
        "xy": [x, y],
        "on_text": bool(marks.text[y, x]),
        "on_line": bool(marks.line[y, x]),
        "on_ink": bool(marks.ink[y, x]),
    }


def references(g: dict[str, Any], v1: dict[str, dict[str, Mask]]) -> dict[str, dict[str, Any]]:
    """{part: {"arm", "mask"}} for each part graded pass: Arm A's mask if A passed, else B's."""
    out = {}
    for part, arms in grades.by_part(g).items():
        for arm in grades.ARMS:
            m = v1[arm.lower()].get(part)
            if arms.get(arm, {}).get("grade") == "pass" and m is not None:
                out[part] = {"arm": arm, "mask": m}
                break
    return out


def load_references(name: str) -> dict[str, dict[str, Any]]:
    """The passing masks saved as eval data, eval/s2-bakeoff/FIGURE/reference/: written once
    from the v1 replays while Arm B's code still existed, so Arm B's passes stay usable."""
    d = bake.OUT_ROOT / name / "reference"
    index = json.loads((d / "index.json").read_text(encoding="utf-8"))
    return {p: {"arm": i["arm"], "mask": load_mask(d / i["file"])} for p, i in index.items()}


def page_scale(image: npt.NDArray[np.uint8]) -> float:
    rules = load_tactile_rules()
    h, w = image.shape[:2]
    return fit_to_page(w, h, bake.PAGE, rules.page).mm_per_px


def floors_mm2() -> tuple[float, float]:
    rules = load_tactile_rules()
    return rules.reconcile.speck_max_area_mm2, math.pi * (
        rules.spacing.point_symbol_min_mm / 2
    ) ** 2


def score(
    run: dict[str, Any],
    image: npt.NDArray[np.uint8],
    marks: print_marks.PrintMarks,
    refs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """run: figure, parts (phrases in order), masks {part: mask}, points {part: [[x, y]]},
    confidence {part: float or None} and, for v2, kind {part: str}."""
    mm = page_scale(image)
    speck_mm2, symbol_mm2 = floors_mm2()
    floor_px = speck_mm2 / mm**2
    masks: dict[str, Mask] = run["masks"]
    kinds = run.get("kind", {})
    pairs = sibling_pairs(masks, kinds)
    pairs_before = sibling_pairs(run.get("masks_before", masks), kinds)
    rows = []
    for part in run["parts"]:
        m = masks.get(part, np.zeros(image.shape[:2], bool))
        area = int(m.sum())
        area_mm2 = area * mm**2
        ref = refs.get(part)
        text_px = int((m & marks.text).sum())
        line_px = int((m & marks.line).sum())
        row: dict[str, Any] = {
            "part": part,
            "kind": run.get("kind", {}).get(part),
            "confidence": run["confidence"].get(part),
            "area_px": area,
            "area_mm2": round(area_mm2, 1),
            "speck": 0 < area_mm2 < speck_mm2,
            "under_point_symbol": 0 < area_mm2 < symbol_mm2,
            "text_share": round(text_px / area, 3) if area else None,
            "line_share": round(line_px / area, 3) if area else None,
            "fragments": fragments(m, floor_px) if area else 0,
            "instances": run.get("instances", {}).get(part, 1),
            "reference": None if ref is None else reference(m, ref),
            "overlaps": partners(pairs, part),
            "overlaps_before": partners(pairs_before, part),
            "points": [point_on(p, marks) for p in run["points"].get(part, [])],
            "teacher": run.get("teacher", {}).get(part),
        }
        row["flags"] = flags(row)
        rows.append(row)
    counts = {
        "parts": len(rows),
        "no_mask": sum(1 for r in rows if not r["area_px"]),
        "needs_teacher": sum(1 for r in rows if r["teacher"]),
        "regression": sum(1 for r in rows if r["reference"] and r["reference"]["regression"]),
        "references": sum(1 for r in rows if r["reference"]),
        "speck": sum(r["speck"] for r in rows),
        "under_point_symbol": sum(r["under_point_symbol"] for r in rows),
        "on_text": sum(1 for r in rows if (r["text_share"] or 0) > ON_MARKS),
        "on_line": sum(1 for r in rows if (r["line_share"] or 0) > ON_MARKS),
        "fragmented": sum(1 for r in rows if fragmented(r)),
        "overlap_pairs": len(pairs),
        "overlap_pairs_before": len(pairs_before),
        "points": sum(len(r["points"]) for r in rows),
        "points_on_text": sum(p["on_text"] for r in rows for p in r["points"]),
        "points_on_line": sum(p["on_line"] for r in rows for p in r["points"]),
        "points_on_ink": sum(p["on_ink"] for r in rows for p in r["points"]),
    }
    return {
        "figure": run["figure"],
        "mm_per_px": round(mm, 5),
        "speck_floor_px": round(floor_px, 1),
        "point_symbol_px": round(symbol_mm2 / mm**2, 1),
        "parts": rows,
        "pairs": pairs,
        "pairs_before": pairs_before,
        "counts": counts,
    }


def sibling_pairs(masks: dict[str, Mask], kinds: dict[str, str]) -> list[dict[str, Any]]:
    return grading.overlap_pairs(
        {p: m for p, m in masks.items() if m.any() and kinds.get(p) != "group"}
    )


def partners(pairs: list[dict[str, Any]], part: str) -> list[str]:
    return [q for pr in pairs for q in pr["parts"] if part in pr["parts"] and q != part]


def reference(mask: Mask, ref: dict[str, Any]) -> dict[str, Any]:
    v = round(iou(mask, ref["mask"]), 3)
    return {"arm": ref["arm"], "iou": v, "regression": v < REGRESSION_IOU}


def fragmented(row: dict[str, Any]) -> bool:
    """More pieces than instances; a group's pieces are its members'."""
    return bool(row["kind"] != "group" and row["fragments"] > max(1, row["instances"]))


def flags(row: dict[str, Any]) -> list[str]:
    out = []
    if row.get("teacher"):
        out.append("needs teacher: " + row["teacher"])
    elif not row["area_px"]:
        out.append("no mask")
    ref = row["reference"]
    if ref and ref["regression"]:
        out.append(f"regression: IoU {ref['iou']} with the passing Arm {ref['arm']} mask")
    if row["speck"]:
        out.append("speck")
    elif row["under_point_symbol"]:
        out.append("under a point symbol's area")
    if (row["text_share"] or 0) > ON_MARKS:
        out.append(f"{row['text_share']:.0%} on text")
    if (row["line_share"] or 0) > ON_MARKS:
        out.append(f"{row['line_share']:.0%} on leader lines")
    if fragmented(row):
        out.append(f"{row['fragments']} fragments")
    if row["overlaps_before"] != row["overlaps"]:
        out.append("overlapped before resolution " + ", ".join(row["overlaps_before"]))
    if row["overlaps"]:
        out.append("overlaps " + ", ".join(row["overlaps"]))
    for p in row["points"]:
        on = [k[3:] for k in ("on_text", "on_line", "on_ink") if p[k]]
        if on:
            out.append(f"point {p['xy']} on {' and '.join(on)}")
    return out


def confident_fails(scored: dict[str, Any], g: dict[str, Any]) -> list[dict[str, Any]]:
    """Arm A masks graded fail whose SAM confidence is CONFIDENT or higher."""
    per = grades.by_part(g)
    out = []
    for r in scored["parts"]:
        e = per.get(r["part"], {}).get("A")
        conf = r["confidence"]
        if e and e["grade"] == "fail" and conf is not None and conf >= CONFIDENT:
            out.append({"part": r["part"], "confidence": r["confidence"], "reason": e["reason"]})
    return out


def v1_run(name: str, result: dict[str, Any], masks: dict[str, Mask]) -> dict[str, Any]:
    rows = {r["part"]: r for r in result["arm_a_rows"]}
    conf = {}
    for part, r in rows.items():
        c = [x for x in r.get("confidences") or [] if x is not None]
        conf[part] = max(c) if c else None
    return {
        "figure": name,
        "parts": [p["phrase"] for p in result["parts"]],
        "masks": masks,
        "points": {p: [r["point_px"]] for p, r in rows.items() if r.get("point_px")},
        "confidence": conf,
    }


def table(scored: dict[str, Any], g: dict[str, Any] | None) -> str:
    per = grades.by_part(g) if g else {}
    head = (
        "| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = []
    for i, r in enumerate(scored["parts"], 1):
        grade = per.get(r["part"], {}).get("A", {}).get("grade", "")
        conf = "" if r["confidence"] is None else f"{r['confidence']:.2f}"
        ref = r["reference"]
        ref_iou = "" if ref is None else f"{ref['iou']} ({ref['arm']})"
        cells = [
            str(i),
            r["part"],
            grade,
            r["kind"] or "",
            conf,
            str(r["area_mm2"]),
            str(r["fragments"]),
            pct(r["text_share"]),
            pct(r["line_share"]),
            ref_iou,
            "; ".join(r["flags"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return head + "\n".join(lines) + "\n"


def pct(v: float | None) -> str:
    return "" if v is None else f"{v:.0%}"


async def v1_runs() -> dict[
    str, tuple[npt.NDArray[np.uint8], dict[str, Any], dict[str, dict[str, Mask]]]
]:
    out = {}
    for name in sorted(bake.FIGURES):
        fig, masks = await grading.replay_masks(name)
        result = json.loads((bake.OUT_ROOT / name / "results.json").read_text(encoding="utf-8"))
        out[name] = (fig.image, v1_run(name, result, masks["a"]), masks)
    return out


def write(run_name: str, scored: dict[str, dict[str, Any]], tables: list[str]) -> Path:
    speck_mm2, symbol_mm2 = floors_mm2()
    rules = {
        "regression_iou": REGRESSION_IOU,
        "speck_mm2": speck_mm2,
        "point_symbol_mm2": round(symbol_mm2, 1),
        "on_marks_share": ON_MARKS,
        "confident": CONFIDENT,
        "overlap": grading.OVERLAP,
        "page": bake.PAGE,
    }
    path = bake.OUT_ROOT / f"scores_{run_name}.json"
    path.write_text(json.dumps({"rules": rules, "figures": scored}, indent=1) + "\n", "utf-8")
    md = bake.OUT_ROOT / f"scores_{run_name}.md"
    md.write_text("\n".join(tables), "utf-8")
    return path


def teacher(flags: list[str]) -> str | None:
    """Why a v2f part needs the teacher: "spill" with its reason, or "no mask"."""
    for f in flags:
        if f.startswith("spill: "):
            return "spill, " + f.removeprefix("spill: ")
    for reason in ("no points", "no mask"):
        if f"needs teacher: {reason}" in flags:
            return reason
    return None


def v2_run(
    name: str, result: dict[str, Any], final: dict[str, Mask], kept: dict[str, Mask]
) -> dict[str, Any]:
    """A v2 result as the scorer reads it: the points are the ones sent to SAM."""
    rows = result["rows"]
    conf: dict[str, float | None] = {}
    for r in rows:
        c = [i["confidence"] for i in r["instances"] if i.get("confidence") is not None]
        conf[r["part"]] = max(c) if c else None
    return {
        "figure": name,
        "parts": [r["part"] for r in rows],
        "masks": final,
        "points": {
            r["part"]: [g["sent"] for i in r["instances"] for g in i["points"] if g["sent"]]
            for r in rows
        },
        "confidence": conf,
        "kind": {r["part"]: r["kind"] for r in rows},
        "instances": {r["part"]: sum(1 for i in r["instances"] if i.get("kept_px")) for r in rows},
        "masks_before": kept,
        "teacher": {r["part"]: teacher(r["flags"]) for r in rows if teacher(r["flags"])},
    }


async def v2_runs(
    v1: dict[str, tuple[npt.NDArray[np.uint8], dict[str, Any], dict[str, dict[str, Mask]]]],
    fixes: bool = False,
) -> dict[str, tuple[npt.NDArray[np.uint8], dict[str, Any], dict[str, dict[str, Mask]]]]:
    """v2, or with fixes v2f, replayed: v2f only for the figures it ran live on."""
    out = {}
    for name, (image, _, masks) in v1.items():
        rec = s2_armav2.prefix(fixes)
        if fixes and not (bake.OUT_ROOT / name / "results_v2f.json").exists():
            continue
        run, result = await s2_armav2.run_figure(
            s2_armav2.replayer(name, rec), name, False, "none", fixes
        )
        out[name] = (image, v2_run(name, result, run.final, run.kept), masks)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", choices=["v1", "v2", "v2f"])
    args = ap.parse_args()
    runs = asyncio.run(v1_runs())
    if args.run != "v1":
        runs = asyncio.run(v2_runs(runs, fixes=args.run == "v2f"))
    scored, tables = {}, [f"# S2 scores, {args.run}\n"]
    for name, (image, run, _) in runs.items():
        g = grades.load(bake.OUT_ROOT / name)
        s = score(run, image, print_marks.find(image), load_references(name))
        if args.run == "v1":  # the grades are of the v1 masks
            s["confident_fails"] = confident_fails(s, g)
        scored[name] = s
        tables.append(f"## {name}\n\n{summary(s)}\n\n{table(s, g)}")
        print(f"{name}: {summary(s)}")
    print(f"wrote {bake.shown(write(args.run, scored, tables))}")


def summary(s: dict[str, Any]) -> str:
    c = s["counts"]
    fails = s.get("confident_fails")
    graded = (
        "" if fails is None else f" Graded fail at confidence {CONFIDENT} or higher: {len(fails)}."
    )
    return (
        f"{c['parts']} parts, no mask {c['no_mask']}, needs teacher {c['needs_teacher']}, "
        f"regressions {c['regression']} of "
        f"{c['references']} references, specks {c['speck']}, under a point symbol "
        f"{c['under_point_symbol']}, on text {c['on_text']}, on leader lines {c['on_line']}, "
        f"fragmented {c['fragmented']}, overlapping pairs {c['overlap_pairs_before']} before "
        f"resolution and {c['overlap_pairs']} after. Points "
        f"{c['points']}: on text {c['points_on_text']}, on lines {c['points_on_line']}, on ink "
        f"{c['points_on_ink']}.{graded}"
    )


if __name__ == "__main__":
    main()
