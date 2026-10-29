"""Gate A latency, step 4.2: p50 and p95 per model, for the parts that do not wait on S2.

    LIVE=1 uv run python -m app.meta.latency_spike spark [--runs 10] [--record]
    LIVE=1 uv run python -m app.meta.latency_spike voice [--runs 10] [--record]
    uv run python -m app.meta.latency_spike sam

spark: the S1 listing call on heart.png at reasoning effort medium, the request the bake-off
made (s2_bakeoff.s1_list_body). voice: the file endpoint on the synthetic clip, the smoke
call's request, with no keywords. sam: no calls; the SAM point-prompt answers recorded by
the Oct 29 bake-off, read from eval/s2-bakeoff/*/results.json, counting only answers with
at least one instance.

Each run is timed from request to full answer (for SAM, the end of the stream). Percentiles
are nearest rank, as in spikes/meta_common.py, so p95 of 10 runs is the slowest one. A
failed call is kept with its status and left out of the percentiles. Writes
spikes/results/latency_MODEL.json."""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.meta import s2_bakeoff as bake
from app.meta.live import LiveCaller, LiveCallError, LiveResult, spark_units
from app.meta.record import Recorder
from app.meta.smoke import CLIP, HEART, voice_files, wav_seconds
from app.paths import REPO_ROOT

CALLER = "latency_spike"
OUT_DIR = REPO_ROOT / "spikes" / "results"
RUNS = 10


def percentile(values: list[float], pct: float) -> float:
    """Nearest rank: the smallest value with at least pct percent of values at or below it."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    return s[max(1, math.ceil(pct / 100 * len(s))) - 1]


def summary(ms: list[float]) -> dict[str, Any]:
    return {
        "n": len(ms),
        "p50_ms": percentile(ms, 50),
        "p95_ms": percentile(ms, 95),
        "min_ms": min(ms),
        "max_ms": max(ms),
    }


def part_count(body: Any) -> int | None:
    try:
        return len(json.loads(body["choices"][0]["message"]["content"])["parts"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def finish(model: str, rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    ok = [r["latency_ms"] for r in rows if r.get("status") == httpx.codes.OK]
    return {"model": model, "latency": summary(ok) if ok else None, **extra, "runs": rows}


async def timed(run: int, call: Awaitable[LiveResult]) -> tuple[dict[str, Any], LiveResult | None]:
    """One call: its row so far and its body, or the row with the failure and no body."""
    try:
        res = await call
    except LiveCallError as exc:
        return {"run": run, "status": exc.status}, None
    except httpx.HTTPError as exc:
        return {"run": run, "status": None, "error": type(exc).__name__}, None
    row = {
        "run": run,
        "status": res.status,
        "latency_ms": res.latency_ms,
        "cost_usd": res.ledger_line["cost_usd"],
    }
    return row, res


async def spark(live: LiveCaller, runs: int, record: bool) -> dict[str, Any]:
    models = load_tactile_rules().meta.models
    body = bake.s1_list_body(models, HEART.read_bytes())
    rows = []
    for i in range(1, runs + 1):
        row, res = await timed(
            i,
            live.post_json(
                "/chat/completions",
                body,
                caller=CALLER,
                model=models.spark,
                describe=f"fixtures/heart.png 2048x1612, S1 listing, run {i}",
                units=spark_units,
                record_as=f"latency_spark_list_{i:02d}" if record else None,
            ),
        )
        if res is not None:
            row |= {"parts": part_count(res.body), "usage": res.usage}
        rows.append(row)
    return finish(models.spark, rows, request="S1 listing, heart.png", effort=bake.EFFORT)


async def voice(live: LiveCaller, runs: int, record: bool) -> dict[str, Any]:
    models = load_tactile_rules().meta.models
    wav = CLIP.read_bytes()
    seconds = wav_seconds(CLIP)
    billed = float(math.ceil(seconds))  # billed in whole seconds (spikes/muse-voice.md)
    rows = []
    for i in range(1, runs + 1):
        row, res = await timed(
            i,
            live.post_multipart(
                "/asr/transcribe",
                voice_files(models, wav),
                caller=CALLER,
                model=models.voice,
                describe=f"fixtures/audio/{CLIP.name}, {seconds:.2f} s, no keywords, run {i}",
                units=lambda _usage: {"audio_seconds": billed},
                record_as=f"latency_voice_{i:02d}" if record else None,
            ),
        )
        if res is not None:
            row |= {"audio_duration_ms": res.body.get("audioDurationMs")}
        rows.append(row)
    return finish(
        models.voice, rows, request=f"file endpoint, {CLIP.name}, {seconds:.2f} s, no keywords"
    )


def sam(root: Path = bake.OUT_ROOT) -> dict[str, Any]:
    """The bake-off's SAM point-prompt latencies, from its results files. No calls."""
    rows = []
    for figure in sorted(bake.FIGURES):
        result = json.loads((root / figure / "results.json").read_text(encoding="utf-8"))
        rows += [
            {
                "figure": figure,
                "part": r["part"],
                "status": httpx.codes.OK,
                "latency_ms": r["latency_ms"],
                "instances": r["instances"],
            }
            for r in result["arm_a_rows"]
            if r.get("instances")
        ]
    return finish(
        load_tactile_rules().meta.models.sam,
        rows,
        request="point prompts from the Oct 29 S2 bake-off, answers with at least one instance",
    )


def write(name: str, result: dict[str, Any], out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"latency_{name}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model", choices=["spark", "voice", "sam"])
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--record", action="store_true", help="save each call to fixtures/recorded/")
    args = ap.parse_args()
    if args.model == "sam":
        result = sam()
    else:
        live = LiveCaller.from_env(load_tactile_rules().meta, recorder=Recorder())
        if args.runs > live.cap:
            sys.exit(f"{args.runs} runs is over the cap of {live.cap} calls per run.")
        run = spark if args.model == "spark" else voice
        result = asyncio.run(run(live, args.runs, args.record))
        print(f"spent ${live.meter.spent_usd:.5f} on {live.calls} calls")
    print(f"{args.model}: {json.dumps(result['latency'])}")
    print(f"wrote {write(args.model, result).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
