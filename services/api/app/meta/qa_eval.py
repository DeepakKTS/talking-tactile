"""Explore's question eval (eval/qa/questions.jsonl) on the published heart and Commons
brain, through the same Asker as POST /api/ask.

    uv run python -m app.meta.qa_eval            # replay of the live recordings, no calls
    caffeinate -i env LIVE=1 META_RECORD=qa uv run python -m app.meta.qa_eval --live

Each question names its figure, the part under the finger and the parts touched before (by
label), the sources it accepts, the parts the answer must cite and those it may. The scorer
reports, per figure and category:
- source: the answer's source (after code's last word) is one the question accepts;
- citations: every part it must cite is cited, and nothing outside must and may;
- outside knowledge: for an answer from the figure or a teacher description, its content
  words that appear nowhere in what Spark was given (the prompt, the question) nor in a
  short list of words any answer may use. A flag is a lead for a reader, not a verdict.

The published versions are pinned (VERSION; on a fresh clone, make demo-sheets publishes the
same sheets as version 1 and the eval finds them by content), so a replay sends the same
requests the live run recorded. Writes eval/qa/RESULTS.md and eval/qa/scores.json."""

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.ask import PROMPT, TEXT_PROMPT, Asker, AskRequest, prompt_text
from app.config import load_tactile_rules
from app.demo_sheets import SheetError, eval_version
from app.main import create_app
from app.meta.client import make_client
from app.meta.mock import MockMetaClient
from app.paths import DATA_DIR, REPO_ROOT
from app.prompts import load_prompt

OUT = REPO_ROOT / "eval" / "qa"
QUESTIONS = OUT / "questions.jsonl"
FIGURES = {
    "heart": "913ba16a635188097dbb235741e05e376d23cca17bdb1789aec79a1497a67ada",
    "brain_lobes": "046e94d4f0b53298900ab96754caeb348dbc624b35841512d4e5b1198a36a699",
}
# Published Oct 30 on the point symbol floor of d5-23: every part checked, two teacher
# descriptions each.
VERSION = 4
_WORD = re.compile(r"[a-z]+")
# Words an answer may use whatever the figure: function words, positions, counting, and
# the words of the fixed sentences.
ALLOWED_WORDS = """
    a an the and or but not no yes it its this that these those there here is are was
    be can cannot can't do does did of in on at to from by with as for into onto over
    under above below left right next near beside between inside around up down top
    bottom side upper lower front back middle part parts figure picture sheet touch
    touching touched you your i me my we one two three four five six seven eight nine
    ten eleven twelve many how what which where who why when just before after only
    also each all both other called named shows show shown has have had yet ask teacher
    sure line lines raised lies sits found label labeled labelled sorry about than then
    so very more most
"""
ALLOWED = set(ALLOWED_WORDS.split())


def _words(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text.lower()):
        out.add(w)
        out.add(w[:-1] if w.endswith("s") else w)
    return out


def outside_words(answer: str, given: str) -> list[str]:
    allowed = _words(given) | ALLOWED
    return sorted(
        w
        for w in set(_WORD.findall(answer.lower()))
        if w not in allowed and w.rstrip("s") not in allowed
    )


def judge(
    q: dict[str, Any], source: str, cited: list[str]
) -> tuple[bool, bool, set[str], set[str]]:
    """Source right, citations right, and the citation sets judged. A question may list other
    acceptable outcomes in "accept" (eval/qa/README.md), each with its own sources and
    citations; the answer passes when one of them matches."""
    options = [q, *q.get("accept", [])]
    matching = [o for o in options if source in o["sources"]] or options[:1]
    for o in matching:
        must, may = set(o["cite_must"]), set(o["cite_may"])
        if must <= set(cited) <= must | may:
            return source in o["sources"], True, must, may
    o = matching[0]
    return source in o["sources"], False, set(o["cite_must"]), set(o["cite_may"])


def load_questions(path: Path = QUESTIONS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


async def run(
    live: bool, names: list[str], image: bool = True, only: str | None = None
) -> list[dict[str, Any]]:
    rules = load_tactile_rules()
    client = make_client(False, rules.meta) if live else MockMetaClient(rules.meta)
    app = create_app(data_dir=DATA_DIR, client=client)
    service = app.state.figure_service()
    asker = service.asker()
    if not image:  # the latency experiment: the figure data in words, no image
        text = load_prompt(TEXT_PROMPT)
        asker = Asker(
            service.runner.client,
            str(text.template["system"]),
            str(text.template["user"]),
            service._published_figure,
            image=False,
        )
    rows = []
    versions: dict[str, int] = {}  # the eval's sheet: version 4 where it ran, 1 after demo-sheets
    for q in load_questions():
        if q["figure"] not in names or (only is not None and q["category"] != only):
            continue
        fid = FIGURES[q["figure"]]
        if q["figure"] not in versions:
            versions[q["figure"]] = eval_version(service, fid, q["figure"])
        version = versions[q["figure"]]
        regions, _ = service._published_figure(fid, version)
        by_label = {r.label: r.id for r in regions.regions if r.touchable and "_" not in r.id}
        req = AskRequest(
            figure_id=fid,
            version=version,
            question=q["question"],
            region_id=by_label.get(q["finger"]) if q["finger"] else None,
            recent_region_ids=[by_label[x] for x in q["recent"]],
            session_id=f"qa-{q['figure']}",
        )
        row: dict[str, Any] = {"id": q["id"], "figure": q["figure"], "category": q["category"],
                               "question": q["question"]}  # fmt: skip
        try:
            a = await asker.ask(req, None)
        except Exception as exc:
            rows.append({**row, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        label = {r.id.partition("_")[0]: r.label for r in regions.regions}
        cited = [label.get(i, i) for i in a.cited_part_ids]
        ok_source, ok_cites, must, may = judge(q, a.source, cited)
        given = prompt_text(asker.user, regions, req, q["question"]) + " " + asker.system
        outside = (
            outside_words(a.answer, given) if a.source in ("figure", "teacher_description") else []
        )
        rows.append({
            **row,
            "answer": a.answer, "spark_text": a.spark.answer_text if a.spark else None,
            "source": a.source, "spark_source": a.spark.source if a.spark else None,
            "sources_ok": q["sources"] + [x for alt in q.get("accept", []) for x in alt["sources"]],
            "source_correct": ok_source,
            "cited": cited, "cite_must": sorted(must), "cite_may": sorted(may),
            "citations_correct": ok_cites,
            "outside_words": outside, "timings_ms": a.timings_ms,
            "rule_fallback": a.rule_fallback,
        })  # fmt: skip
        print(f"{row['id']} {a.source:20s} {a.answer}")
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fig in dict.fromkeys(r["figure"] for r in rows):
        mine = [r for r in rows if r["figure"] == fig]
        done = [r for r in mine if "error" not in r]
        by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for r in done:
            c = by_cat[r["category"]]
            c[0] += 1
            c[1] += r["source_correct"]
            c[2] += r["citations_correct"]
        spark = sorted(r["timings_ms"].get("spark", 0) for r in done)
        out[fig] = {
            "questions": len(mine),
            "errors": len(mine) - len(done),
            "source_correct": sum(r["source_correct"] for r in done),
            "citations_correct": sum(r["citations_correct"] for r in done),
            "outside_flags": sum(bool(r["outside_words"]) for r in done),
            "rule_fallbacks": sum(bool(r.get("rule_fallback")) for r in done),
            "by_category": {
                k: {"n": v[0], "source": v[1], "citations": v[2]} for k, v in by_cat.items()
            },
            "spark_ms_p50": spark[len(spark) // 2] if spark else None,
            "spark_ms_p95": spark[min(len(spark) - 1, int(0.95 * len(spark)))] if spark else None,
        }
    return out


def markdown(rows: list[dict[str, Any]], s: dict[str, Any], live: bool, image: bool = True) -> str:
    variant = "" if image else f" (no figure image: {TEXT_PROMPT.removesuffix('.json')})"
    out = [f"# Explore question eval{variant}", "",
           f"{'Live' if live else 'Replay of the live recordings'}; "
           f"published version {VERSION} of each "
           "figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.", ""]  # fmt: skip
    for fig, x in s.items():
        out += [f"## {fig}", "",
                f"- Questions {x['questions']}, errors {x['errors']}.",
                f"- Source correct {x['source_correct']} of {x['questions'] - x['errors']}; "
                f"citations correct {x['citations_correct']}; answers flagged for words outside "
                f"the figure {x['outside_flags']}.",
                f"- Spark time p50 {x['spark_ms_p50']} ms, p95 {x['spark_ms_p95']} ms.", "",
                "| Category | Questions | Source correct | Citations correct |",
                "|---|---|---|---|"]  # fmt: skip
        out += [
            f"| {k} | {v['n']} | {v['source']} | {v['citations']} |"
            for k, v in x["by_category"].items()
        ]
        misses = [r for r in rows if r["figure"] == fig and ("error" in r or not r["source_correct"]
                  or not r["citations_correct"] or r["outside_words"])]  # fmt: skip
        out += ["", "Misses and flags:", ""]
        if not misses:
            out.append("None.")
        for r in misses:
            if "error" in r:
                out.append(f'- {r["id"]} "{r["question"]}": error {r["error"]}')
                continue
            what = []
            if not r["source_correct"]:
                what.append(
                    f"source {r['source']} (Spark: {r['spark_source']}), "
                    f"expected {' or '.join(r['sources_ok'])}"
                )
            if not r["citations_correct"]:
                what.append(
                    f"cited {r['cited'] or 'nothing'}, must {r['cite_must'] or 'nothing'}, "
                    f"may {r['cite_may'] or 'nothing'}"
                )
            if r["outside_words"]:
                what.append(f"words outside the figure: {', '.join(r['outside_words'])}")
            out.append(f'- {r["id"]} "{r["question"]}": {"; ".join(what)}. Said: "{r["answer"]}"')
        out.append("")
    return "\n".join(line.rstrip() for line in out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="live calls (LIVE=1); default: replay")
    ap.add_argument("--no-image", action="store_true", help="no figure image; *_no_image files")
    ap.add_argument("--only", help="one category only; files named after it")
    ap.add_argument("figures", nargs="*", choices=[[], *FIGURES], help="default: both")
    args = ap.parse_args()
    names = args.figures or list(FIGURES)
    image = not args.no_image
    try:
        rows = asyncio.run(run(args.live, names, image, args.only))
    except SheetError as exc:
        sys.exit(str(exc))
    s = summary(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    tail = ("" if args.only is None else f"_{args.only}") + ("" if image else "_no_image")
    (OUT / f"scores{tail}.json").write_text(
        json.dumps(
            {"prompt": PROMPT if image else TEXT_PROMPT, "summary": s, "rows": rows}, indent=1
        )
        + "\n",
        "utf-8",
    )
    (OUT / f"RESULTS{tail}.md").write_text(markdown(rows, s, args.live, image) + "\n", "utf-8")
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
