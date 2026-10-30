"""The tactile-aware part plan (S1 locate v2, Oct 30) on every eval figure, from live
recordings: no live call, nothing spent.

    uv run python -m app.meta.plan_eval

Each figure was run live once through the pipeline (META_RECORD=plan_NAME, or private_brain
for the uploaded brain, which is not openly licensed). Heart and flower ran S2 live a second
time (plan2_NAME) once NEST_INSIDE moved to 0.95, which changed two retries' negatives.
Here the whole pipeline runs again in mock mode on those recordings, so any change to S2
to S5 is measured on the same answers.
A request the recordings do not hold (a retry the live run did not make) fails like a
live call would, and shows as such.

Per figure: the plan (areas, lines and what each separates, groups, the subject), what is
touchable, what needs the teacher and why, nesting, merge proposals, and the silhouette.
For heart, flower and Japan, the S2 scorer (app/meta/s2_score.py) against the graded
references, beside v2f's scores: each reference part held, regressed, improved, or still
regressed. Also every pair of first masks with one 25% or more inside the other, the data
NEST_INSIDE is chosen from.

Writes eval/plan/RESULTS.md and eval/plan/scores.json; the uploaded brain's numbers go in
them, but nothing drawn from its image. The pipeline's cache is data/plan_eval/."""

import argparse
import asyncio
import itertools
import json
from pathlib import Path
from typing import Any

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.geometry import part_masks as pm
from app.geometry import print_marks
from app.meta import s2_score
from app.meta.mock import MockMetaClient
from app.models.regions import GradeBand, RegionsFile
from app.paths import DATA_DIR, FIXTURES_DIR, RECORDED_DIR, REPO_ROOT
from app.pipeline import s2_points
from app.pipeline.edits import EditStore
from app.pipeline.jobs import JobOptions, JobStore
from app.pipeline.outlines import prompt_points
from app.pipeline.runner import Runner
from app.pipeline.s0_ingest import ingest

OUT = REPO_ROOT / "eval" / "plan"
WORK = DATA_DIR / "plan_eval"
INDEX = RECORDED_DIR / "private_plan_replays.json"  # git-ignored: it names private recordings
V2F = REPO_ROOT / "eval" / "s2-bakeoff" / "scores_v2f.json"

# name: (image, recording prefixes, grade band, graded references)
_EVAL = FIXTURES_DIR / "eval"
FIGURES: dict[str, tuple[Path, list[str], GradeBand | None, bool]] = {
    "heart": (FIXTURES_DIR / "heart.png", ["plan_heart_s1_", "plan2_heart_"], None, True),
    "flower": (_EVAL / "flower.png", ["plan_flower_s1_", "plan2_flower_"], None, True),
    "japan_regions": (_EVAL / "japan_regions.png", ["plan_japan_"], None, True),
    "brain_upload": (
        FIXTURES_DIR / "private" / "brain_upload.png",
        ["private_brain_"],
        "6_8",
        False,
    ),
    "brain_lobes": (_EVAL / "brain_lobes.png", ["plan_brain_lobes_"], "6_8", False),
}
BINS = (0.25, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0001)


def write_index(names: list[str]) -> None:
    rules = load_tactile_rules()
    figures = {}
    for name in names:
        path, prefixes, _, _ = FIGURES[name]
        fid = ingest(path.read_bytes(), 0, rules.pipeline).figure_id
        figures[fid] = {"name": name, "prefixes": prefixes}
    INDEX.write_text(json.dumps({"description": __doc__.splitlines()[0], "figures": figures}))


def runner() -> Runner:
    rules = load_tactile_rules()
    WORK.mkdir(parents=True, exist_ok=True)
    db = WORK / "jobs.sqlite"
    return Runner(
        client=MockMetaClient(rules.meta, replays=INDEX),
        rules=rules,
        explore=load_explore(),
        translator=Translator(rules.braille),
        jobs=JobStore(db),
        edits=EditStore(db),
        figures_dir=WORK / "figures",
    )


async def run_one(r: Runner, name: str) -> dict[str, Any]:
    path, _, grade, graded = FIGURES[name]
    job = r.submit(path.read_bytes(), 0, JobOptions(grade_band=grade))
    job = await r.run(job.id)
    if job.status != "done":
        return {"figure": name, "status": job.status, "error": job.error_message}
    ing, u, g, _ = await r.fix_context(job)
    out = r.output_dir(job)
    assert out is not None
    regions = RegionsFile.from_json_obj(json.loads((out / "regions.json").read_text("utf-8")))
    report = json.loads((out / "report.json").read_text("utf-8"))
    kinds = {p.phrase: p.kind for p in u.parts}
    areas = [p.phrase for p in u.parts if p.kind not in ("line", "group")]
    touch_parts = {x.label for x in g.parts if kinds.get(x.label) != "group"}
    row: dict[str, Any] = {
        "figure": name,
        "status": "done",
        "grade_band": grade,
        "subject": u.subject,
        "listed": len(u.parts),
        "areas": areas,
        "groups": [p.phrase for p in u.parts if p.kind == "group"],
        "lines": [
            {"line": p.phrase, "separates": list(p.separates), "parent": p.parent}
            for p in u.parts
            if p.kind == "line"
        ],
        "unlocated": [p.phrase for p in u.parts if p.kind is None],
        "spark_shared": [{"parts": list(s.parts), "name": s.name} for s in u.shares_region],
        "touchable_areas": [a for a in areas if a in touch_parts],
        "needs_you": [
            {"part": t.phrase, "reason": t.reason, "detail": t.detail} for t in g.teacher
        ],
        "nested": g.nested,
        "merges": [m.model_dump(mode="json") for m in g.merges],
        "silhouette": g.facts.get(s2_points.SUBJECT),
        "regions_json": {
            "touchable": len({x.id.split("_")[0] for x in regions.regions if x.touchable}),
            "lines": [x.model_dump(mode="json", exclude_none=True) for x in regions.lines or []],
            "merge_proposals": len(regions.merge_proposals or []),
            "subject_drawn": regions.subject is not None,
            "needs_teacher": len(regions.needs_teacher or []),
        },
        "contour_pieces": _contour(out),
        "rules_report": len(report),
        "pairs": _pairs(g.facts, u),
        "live_calls": r.client.live_calls,
    }
    if graded:
        row["score"] = _score(name, ing.image, u, g)
    return row


def _contour(out: Path) -> dict[str, float]:
    svg = (out / "tactile.svg").read_text("utf-8")
    return {"pieces": svg.count('data-kind="silhouette"')}


def _pairs(facts: dict[str, Any], u: Any) -> list[dict[str, Any]]:
    """Every first-mask pair with one mask RECORD_SHARE or more inside the other."""
    parents = {p.phrase: p.parent for p in u.parts}
    out = []
    for part, f in facts.items():
        if part == s2_points.SUBJECT:
            continue
        for other, share in (f.get("inside_of") or {}).items():
            iou = (f.get("iou") or {}).get(other, 0.0)
            spark = "parent" if parents.get(part) == other else ""
            out.append({"part": part, "inside": other, "share": share, "iou": iou, "spark": spark})
    return sorted(out, key=lambda x: -x["share"])


def _score(name: str, image: Any, u: Any, g: Any) -> dict[str, Any]:
    masks = {m.label: m.data for m in g.parts}
    conf = {}
    for p in u.parts:
        c = [x for x in g.facts.get(p.phrase, {}).get("confidence", []) if x is not None]
        conf[p.phrase] = max(c) if c else None
    run = {
        "figure": name,
        "parts": [p.phrase for p in u.parts if p.kind != "line"],
        "masks": masks,
        "points": {k: [list(p) for p in v] for k, v in prompt_points(g).items()},
        "confidence": conf,
        "kind": {p.phrase: p.kind for p in u.parts},
        "instances": {p.phrase: max(1, len(p.instances)) for p in u.parts},
        "teacher": {t.phrase: f"{t.reason}, {t.detail}" for t in g.teacher},
    }
    s = s2_score.score(run, image, print_marks.find(image), s2_score.load_references(name))
    v2f = {r["part"]: r for r in json.loads(V2F.read_text("utf-8"))["figures"][name]["parts"]}
    refs = s2_score.load_references(name)
    rows = {r["part"]: r for r in s["parts"]}
    compare = []
    for part, ref in refs.items():
        before = v2f.get(part)
        was = None if before is None else before["reference"]["regression"]
        now, how = _match(part, ref["mask"], masks, list(rows))
        if now is None:
            compare.append({"part": part, "v2f_iou": _iou(before), "iou": None, "now": None,
                            "match": how, "verdict": "not listed now"})  # fmt: skip
            continue
        m = masks.get(now)
        got = 0.0 if m is None else round(s2_score.iou(m, ref["mask"]), 3)
        reg = got < s2_score.REGRESSION_IOU
        verdict = {
            (False, False): "held",
            (False, True): "regressed",
            (True, False): "improved",
            (True, True): "still regressed",
        }[(bool(was), reg)]
        compare.append({"part": part, "v2f_iou": _iou(before), "iou": got, "now": now,
                        "match": how, "verdict": verdict, "flags": rows[now]["flags"]})  # fmt: skip
    return {"counts": s["counts"], "summary": s2_score.summary(s), "references": compare}


def _words(name: str) -> set[str]:
    return set(name.lower().split()) - {"region", "area", "island", "islands", "the", "of"}


def _match(part: str, ref: Any, masks: dict[str, Any], listed: list[str]) -> tuple[str | None, str]:
    """The part listed now that stands for a reference part: the same name; else one
    sharing a word of its name; else the mask with the best IoU with the reference."""
    if part in listed:
        return part, "name"
    by_word = [q for q in listed if _words(q) & _words(part)]
    if len(by_word) == 1:
        return by_word[0], "word"
    scored = sorted(((s2_score.iou(m, ref), q) for q, m in masks.items()), reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1], f"mask IoU {scored[0][0]:.3f}"
    return None, "none"


def _iou(row: dict[str, Any] | None) -> float | None:
    return None if row is None else row["reference"]["iou"]


def nesting_table(rows: list[dict[str, Any]]) -> str:
    pairs = [(r["figure"], p) for r in rows for p in r.get("pairs", [])]
    counts = []
    for lo, hi in itertools.pairwise(BINS):
        n = sum(1 for _, p in pairs if lo <= p["share"] < hi)
        counts.append(f"| {lo:.2f} to {min(hi, 1.0):.2f} | {n} |")
    lines = [
        "| Share inside | Pairs |",
        "|---|---|",
        *counts,
        "",
        "| Figure | Part | Inside | Share | IoU | Spark |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {f} | {p['part']} | {p['inside']} | {p['share']:.3f} | {p['iou']:.3f} | {p['spark']} |"
        for f, p in pairs
        if p["share"] >= BINS[2]
    ]
    return "\n".join(lines)


def markdown(rows: list[dict[str, Any]]) -> str:
    out = [
        "# Tactile-aware part plan, from the live recordings",
        "",
        f"S2 settings: nest inside {pm.NEST_INSIDE}, shared IoU {pm.SHARED_IOU}. "
        "Written by app/meta/plan_eval.py.",
    ]
    for r in rows:
        out += ["", f"## {r['figure']}", ""]
        if r["status"] != "done":
            out.append(f"Run {r['status']}: {r.get('error')}")
            continue
        rj = r["regions_json"]
        needs = "; ".join(f"{n['part']} ({n['reason']}: {n['detail']})" for n in r["needs_you"])
        lines = "; ".join(
            f"{x['line']}" + (f" between {' and '.join(x['separates'])}" if x["separates"] else
                              f" in {x['parent'] or 'nothing'}")
            for x in r["lines"]
        )  # fmt: skip
        merges = "; ".join(f"{', '.join(m['parts'])} as '{m['name']}' ({m['why']})"
                           for m in r["merges"])  # fmt: skip
        sil = r["silhouette"] or {}
        out += [
            f"- Subject: {r['subject'] or 'none'}. Grade band: {r['grade_band'] or 'none'}.",
            f"- Listed {r['listed']}: areas {len(r['areas'])}, lines {len(r['lines'])}, "
            f"groups {len(r['groups'])}, not located {len(r['unlocated'])}.",
            f"- Touchable areas: {len(r['touchable_areas'])} of {len(r['areas'])}. "
            f"Touchable parts in regions.json: {rj['touchable']}.",
            f"- Needs you: {len(r['needs_you'])}. {needs}",
            f"- Lines: {lines or 'none'}.",
            f"- Nested by geometry: "
            f"{', '.join(f'{c} in {p}' for c, p in r['nested'].items()) or 'none'}.",
            f"- Merge proposals: {len(r['merges'])}. {merges}",
            f"- Silhouette: SAM {sil.get('instances', 0)} instance(s), {sil.get('px', 0)} px"
            f"{', error ' + sil['error'] if 'error' in sil else ''}; in regions.json: "
            f"{rj['subject_drawn']}, {r['contour_pieces']['pieces']} raised contour piece(s).",
            f"- Rules report: {r['rules_report']} violation(s). Replayed calls: {r['live_calls']}.",
        ]
        if "score" in r:
            sc = r["score"]
            out += ["", sc["summary"], "",
                    "| Reference part | Listed now as | Matched by | v2f IoU | IoU now | Verdict |",
                    "|---|---|---|---|---|---|"]  # fmt: skip
            out += [f"| {c['part']} | {c['now'] or ''} | {c['match']} | {c['v2f_iou']} | "
                    f"{c['iou']} | {c['verdict']} |" for c in sc["references"]]  # fmt: skip
    out += ["", "## First-mask pairs, for NEST_INSIDE", "", nesting_table(rows), ""]
    return "\n".join(out)


async def main_async(names: list[str]) -> list[dict[str, Any]]:
    r = runner()
    return [await run_one(r, n) for n in names]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("figures", nargs="*", choices=[[], *FIGURES], help="default: all present")
    asked = ap.parse_args().figures or list(FIGURES)
    names = [n for n in asked if FIGURES[n][0].is_file()]
    write_index(names)
    rows = asyncio.run(main_async(names))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scores.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")
    (OUT / "RESULTS.md").write_text(markdown(rows), "utf-8")
    print(markdown(rows))


if __name__ == "__main__":
    main()
