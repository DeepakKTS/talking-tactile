"""make results: the phone measurements into the result files, the docs and the tracker.

    make results                              # or: python3 scripts/results.py
    python3 scripts/results.py --root DIR     # on a copy of the repo (the dry run does this)

Reads, from eval/gate-b/:
- touch-test-*.json: the Gate B run as the page saved it (the newest, or --touch FILE);
- latency.csv and videos.sha256: the latency film, touch to tone (scripts/latency_film.py);
- voice-latency.csv: the same film's hold-to-talk takes, release to first word (optional).

Writes eval/gate-b/RESULTS.md, replaces each marked TBD (<!-- tt:KEY -->...<!-- /tt:KEY -->)
in README.md, docs/submission/WRITEUP.md and docs/submission/VIDEO_SCRIPT.md that it has a
measurement for, and sets the tracker's metrics through scripts/tracker.py. Gate B itself is
left to you: it counts only when eval/gate-b/run.md says the protocol was met, so the command
is printed instead. Running it again replaces the same spans."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "docs/submission/WRITEUP.md", "docs/submission/VIDEO_SCRIPT.md"]
RESULTS_FILE = "eval/gate-b/RESULTS.md"


class ResultsError(Exception):
    pass


def percentile(v: list[float], p: float) -> float:
    """Nearest rank, as analyze_touch.py and the other evals report it."""
    s = sorted(v)
    return s[max(1, math.ceil(p / 100 * len(s))) - 1]


def latencies_ms(rows: list[dict[str, str]], start: str, end: str) -> list[float]:
    """Milliseconds from frame `start` to frame `end` at each row's fps. Every row must be
    filled in: a blank or backwards row is an error, not a skip."""
    out = []
    for i, r in enumerate(rows, 1):
        try:
            a, b, fps = int(r[start]), int(r[end]), float(r["fps"])
        except (KeyError, TypeError, ValueError) as e:
            raise ResultsError(f"row {i}: {start}, {end} and fps must be numbers ({e}); finish the row or delete it") from e
        if fps <= 0 or b < a:
            raise ResultsError(f"row {i}: {end} {b} is before {start} {a}, or fps {fps} is not positive")
        out.append((b - a) / fps * 1000)
    if not out:
        raise ResultsError("no rows")
    return out


def count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def summary_ms(values: list[float]) -> dict[str, float]:
    return {"n": len(values), "p50": round(percentile(values, 50)), "p95": round(percentile(values, 95)),
            "max": round(max(values))}


def replace_spans(text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Each <!-- tt:KEY -->...<!-- /tt:KEY --> span with a value gets it; the markers stay."""
    done = []

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            return m.group(0)
        done.append(key)
        return f"<!-- tt:{key} -->{values[key]}<!-- /tt:{key} -->"

    return re.sub(r"<!-- tt:([a-z-]+) -->.*?<!-- /tt:\1 -->", sub, text, flags=re.DOTALL), done


def doc_values(touch: dict | None, earcon: dict | None, voice: dict | None) -> dict[str, str]:
    v = {}
    src = f"(`{RESULTS_FILE}`)"
    if touch:
        v["gate-b"] = f"mean {touch['mean_mm']} mm, median {touch['median_mm']} mm, p95 {touch['p95_mm']} mm over {touch['n']} touches {src}"
    if earcon:
        v["earcon-device"] = f"p50 {earcon['p50']} ms, p95 {earcon['p95']} ms over {count(earcon['n'], 'entry', 'entries')} {src}"
    if voice:
        v["voice-device"] = f"p50 {voice['p50'] / 1000:.1f} s, p95 {voice['p95'] / 1000:.1f} s over {count(voice['n'], 'take', 'takes')} {src}"
    if touch:
        tone = f"; touch to tone p95 {earcon['p95']} ms" if earcon else ""
        # On lines of its own: a comment at the start of a list line would print the item raw.
        v["limits-touch"] = (f"\n- **Touch accuracy on the phone** (Gate B on the demo iPhone): mean fingertip error "
                             f"{touch['mean_mm']} mm, median {touch['median_mm']} mm, p95 {touch['p95_mm']} mm over {touch['n']} touches, against a "
                             f"target mean of 4 mm or less{tone} {src}.\n")
    return v


def load_analyzer(root: Path):
    spec = importlib.util.spec_from_file_location("analyze_touch", root / "spikes" / "tracking" / "analyze_touch.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def results_md(root: Path, touch_path: Path | None, touch: dict | None, earcon: dict | None, voice: dict | None) -> str:
    gb = root / "eval" / "gate-b"
    out = ["# Gate B and the device latency film", "",
           "Written by `scripts/results.py` (`make results`) from the files named below; run it again to reproduce.", ""]
    out += ["## Gate B: fingertip error on the 9-point sheet", ""]
    if touch and touch_path:
        digest = hashlib.sha256(touch_path.read_bytes()).hexdigest()
        run_md = (gb / "run.md").exists()
        out += [f"- File: `eval/gate-b/{touch_path.name}`, sha256 `{digest}`.",
                (f"- Touches {touch['n']}: mean {touch['mean_mm']} mm, median {touch['median_mm']} mm, p95 {touch['p95_mm']} mm, max {touch['max_mm']} mm "
                f"(target: mean 4 mm or less, p95 8 mm or less). By the numbers: {touch['gate_b']}."),
                (f"- Bias x {touch['bias_x_mm'][0]} ± {touch['bias_x_mm'][1]} mm, y {touch['bias_y_mm'][0]} ± "
                f"{touch['bias_y_mm'][1]} mm; touches without the pointing pose {touch['not_pointing']}.")]
        if touch.get("practice"):
            out.append(f"- Practice, not Gate B: {touch['practice']}.")
        per = (touch.get("page_summary") or {}).get("perTargetMeanMm")
        if per:
            out.append("- Mean error by target, mm: " + ", ".join(f"{k}: {v}" for k, v in per.items()) + ".")
        if touch.get("worst_touch"):
            w = touch["worst_touch"]
            out.append(f"- Largest error: touch {w['touch']}, on target {w['target']}, {w['mm']} mm.")
        if "scale_ratio_x_over_y" in touch:
            out.append(f"- Video {touch['video_size'][0]} x {touch['video_size'][1]}; x over y scale "
                       f"{touch['scale_ratio_x_over_y']}{' (suspect)' if touch['aspect_suspect'] else ''}.")
        out.append("- Protocol: `eval/gate-b/run.md` " + ("is written." if run_md else
                   "is missing: the run does not count as Gate B until it is written."))
    else:
        out.append("Not run yet.")
    for title, s, file, what in (
        ("Touch to tone on the iPhone (latency film)", earcon, "latency.csv", (("entry", "entries"), "frame_enter to frame_earcon")),
        ("Release to first word on the iPhone (latency film)", voice, "voice-latency.csv", (("take", "takes"), "frame_release to frame_first_word")),
    ):
        out += ["", f"## {title}", ""]
        if s:
            out += [f"- Files: `eval/gate-b/{file}`, videos in `eval/gate-b/videos.sha256`.",
                    f"- {count(s['n'], *what[0])}, {what[1]}: p50 {s['p50']} ms, p95 {s['p95']} ms, max {s['max']} ms."]
        else:
            out.append("Not measured: the latency film was cut.")
    return "\n".join(out) + "\n"


def tracker(root: Path, *args: str) -> None:
    subprocess.run([sys.executable, str(root / "scripts" / "tracker.py"), *args], check=True, cwd=root)


def run(root: Path, touch_file: Path | None = None, update_tracker: bool = True) -> dict[str, list[str]]:
    gb = root / "eval" / "gate-b"
    runs = sorted(gb.glob("touch-test-*.json"))
    touch_path = touch_file or (runs[-1] if runs else None)
    touch = earcon = voice = None
    if touch_path:
        sheet = json.loads((root / "spikes" / "tracking" / "sheet.json").read_text())
        touch = load_analyzer(root).analyze(json.loads(touch_path.read_text()), sheet["corners_mm"])
    for name, start, end in (("latency.csv", "frame_enter", "frame_earcon"), ("voice-latency.csv", "frame_release", "frame_first_word")):
        path = gb / name
        if not path.exists():
            continue
        if not (gb / "videos.sha256").exists():
            raise ResultsError(f"{name} is here but videos.sha256 is not: run scripts/latency_film.py")
        try:
            s = summary_ms(latencies_ms(read_csv(path), start, end))
        except ResultsError as e:
            raise ResultsError(f"{name}: {e}") from e
        if name == "latency.csv":
            earcon = s
        else:
            voice = s
    (gb / "RESULTS.md").write_text(results_md(root, touch_path, touch, earcon, voice))
    values = doc_values(touch, earcon, voice)
    filled: dict[str, list[str]] = {}
    for rel in DOCS:
        path = root / rel
        text, done = replace_spans(path.read_text(), values)
        path.write_text(text)
        filled[rel] = done
    if update_tracker:
        if touch:
            tracker(root, "metric", "touch-mean", str(touch["mean_mm"]), "--source", "live")
            tracker(root, "metric", "touch-p95", str(touch["p95_mm"]), "--source", "live")
        if earcon:
            tracker(root, "metric", "lat-earcon-device", str(earcon["p95"]), "--source", "live",
                    "--name", "Touch to earcon p95 on the iPhone, from the latency film (eval/gate-b/latency.csv)")
        if voice:
            tracker(root, "metric", "lat-answer-device", str(round(voice["p50"] / 1000, 2)), "--source", "live")
        tracker(root, "todo")
    if touch and touch.get("practice"):
        print(f"Not Gate B: the page marked eval/gate-b/{touch_path.name if touch_path else ''} practice ({touch['practice']}).")
    elif touch and touch_path:
        verdict = "pass" if touch["gate_b"] == "pass" else "fail"
        print(f"Gate B, once eval/gate-b/run.md says the protocol was met:\n  python3 scripts/tracker.py gate B {verdict} "
              f"--evidence \"eval/gate-b/{touch_path.name}: mean {touch['mean_mm']} mm, p95 {touch['p95_mm']} mm, "
              f"{touch['n']} touches, protocol met (run.md)\"")
    return filled


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=REPO, help="the repo to work on (default: this one)")
    ap.add_argument("--touch", type=Path, help="the Gate B JSON (default: the newest eval/gate-b/touch-test-*.json)")
    ap.add_argument("--no-tracker", action="store_true", help="leave TRACKER.html alone")
    args = ap.parse_args(argv)
    try:
        filled = run(args.root.resolve(), args.touch, not args.no_tracker)
    except ResultsError as e:
        print(f"make results: {e}", file=sys.stderr)
        return 1
    print(f"Wrote {RESULTS_FILE}.")
    for rel, keys in filled.items():
        print(f"{rel}: {', '.join(keys) if keys else 'nothing to fill'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
