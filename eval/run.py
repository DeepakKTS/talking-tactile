"""make eval: reruns the replay scorers, checks they reproduce the committed results, and writes
eval/RESULTS.md, an index of every suite with its file. No live call, nothing spent.

- Part plan: app.meta.plan_eval on a fresh pipeline cache; eval/plan/ must come back unchanged.
- Questions: app.meta.qa_eval on replay; its scores must match eval/qa/scores.json apart from
  timings (a replay is fast; the live timings stay). The committed files are put back as they
  were. It needs the eval's sheets in data/ (make demo-sheets on a fresh clone).
- Touch, device latency: measured on the iPhone only (eval/gate-b/RESULTS.md, by make
  results); not measured until that file exists.

A suite that cannot run says so, never a number."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "services" / "api"
OUT = ROOT / "eval" / "RESULTS.md"
QA = ROOT / "eval" / "qa"


def _api(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["uv", "run", "python", "-c", code], cwd=API, capture_output=True, text=True)


def _no_timings(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _no_timings(v) for k, v in o.items() if k != "timings_ms" and not k.startswith("spark_ms")}
    if isinstance(o, list):
        return [_no_timings(x) for x in o]
    return o


def _sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    name = ""
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
        out[name] = out.get(name, "") + line + "\n"
    return out


def plan() -> str:
    path = ROOT / "eval" / "plan" / "RESULTS.md"
    kept = {p: p.read_bytes() for p in path.parent.glob("*") if p.is_file()}
    work = tempfile.mkdtemp(prefix="plan_eval_")
    try:
        r = _api(f"import pathlib, app.meta.plan_eval as p; p.WORK = pathlib.Path({work!r}); p.main()")
        if r.returncode != 0:
            return f"did not run: {(r.stderr.strip().splitlines() or [str(r.returncode)])[-1]}"
        if path.read_bytes() == kept[path]:
            return "reproduced exactly"
        # Without the private test figure (not distributed), the shared tables differ; each
        # public figure's own section must still be the same.
        before, now = _sections(kept[path].decode("utf-8")), _sections(path.read_text("utf-8"))
        public = ("heart", "flower", "japan_regions", "brain_lobes")
        if "private" not in now and all(before.get(f) == now.get(f) for f in public):
            return "reproduced for every public figure (the private test figure is not here)"
        return "CHANGED: a public figure's section differs"
    finally:
        for p, data in kept.items():
            p.write_bytes(data)


def questions() -> str:
    kept = {p: p.read_bytes() for p in QA.glob("*") if p.is_file()}
    committed = json.loads((QA / "scores.json").read_text("utf-8"))
    try:
        r = _api("import sys, app.meta.qa_eval as q; sys.argv = ['qa_eval']; q.main()")
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or [str(r.returncode)])[-1]
            return f"did not run: {last}"
        now = json.loads((QA / "scores.json").read_text("utf-8"))
        same = _no_timings(now) == _no_timings(committed)
        return "reproduced (apart from timings)" if same else "CHANGED: the replay scores differ"
    finally:
        for p, data in kept.items():
            p.write_bytes(data)


def touch() -> str:
    res = ROOT / "eval" / "gate-b" / "RESULTS.md"
    return "measured: eval/gate-b/RESULTS.md" if res.exists() else "not measured yet (Gate B on the iPhone)"


def main() -> None:
    rows = [
        ("Part plan and S2 against graded references", "eval/plan/RESULTS.md", plan()),
        ("Questions: source and citations", "eval/qa/RESULTS.md", questions()),
        ("Voice: transcribe and release to first word", "eval/qa/VOICE.md", "live only; not rerun here"),
        ("Touch accuracy and device latency", "eval/gate-b/", touch()),
        ("Users: blind students or teachers", "none", "not tested yet"),
    ]
    lines = ["# Eval results", "", "Written by make eval (eval/run.py). Replays only, no live call.", "",
             "| Suite | File | Status |", "|---|---|---|"]
    lines += [f"| {name} | `{path}` | {status} |" for name, path, status in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text("utf-8"))
    sys.exit(1 if any("CHANGED" in s for _, _, s in rows) else 0)


if __name__ == "__main__":
    main()
