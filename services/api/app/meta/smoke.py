"""One live call per model, the key check for tracker d1-3: Muse Spark on a short text prompt,
SAM 3.1 on fixtures/heart.png, and Muse Voice Transcribe on a clip under 5 seconds.

    LIVE=1 uv run python -m app.meta.smoke [--record]

Stops at the first failure with no retry, and prints the error with the key redacted. Each
call writes its ledger line; --record also saves it under fixtures/recorded/smoke_*.json.
Request shapes are the ones the spikes took from the docs (spikes/*.md)."""

import argparse
import asyncio
import json
import math
import sys
import wave
from pathlib import Path
from typing import Any

from app.config import MetaModels, load_tactile_rules
from app.meta import sam_adapter
from app.meta.live import LiveCaller, LiveCallError, LiveResult, spark_units
from app.meta.record import Files, Recorder
from app.paths import FIXTURES_DIR
from app.pipeline import s2_ground
from app.prompts import load_prompt

HEART = FIXTURES_DIR / "heart.png"
CLIP = FIXTURES_DIR / "audio" / "question_aorta_ventricle.wav"
SPARK_PROMPT = "In one short sentence, name the four chambers of the human heart."
SAM_PHRASE = "left ventricle"
CALLER = "smoke"


def spark_body(models: MetaModels) -> dict[str, Any]:
    return {
        "model": models.spark,
        "messages": [{"role": "user", "content": SPARK_PROMPT}],
        "reasoning_effort": "low",
    }


def voice_files(models: MetaModels, wav: bytes) -> Files:
    req = {
        "model": models.voice,
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
        "languageBias": ["English"],
    }
    return {
        "request": (None, json.dumps(req), "application/json"),
        "audio": (CLIP.name, wav, "audio/wav"),
    }


def wav_seconds(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def shape(value: Any, depth: int = 0) -> Any:
    """Keys and types of a response, with long lists and strings cut down."""
    if isinstance(value, dict):
        return {k: shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        head = [shape(v, depth + 1) for v in value[:2]]
        return [*head, f"... {len(value)} items"] if len(value) > 2 else head  # noqa: PLR2004
    if isinstance(value, str):
        return f"str({len(value)})" if len(value) > 60 else value  # noqa: PLR2004
    return type(value).__name__ if depth else value


async def spark_text(live: LiveCaller, models: MetaModels, record: bool) -> LiveResult:
    return await live.post_json(
        "/chat/completions",
        spark_body(models),
        caller=CALLER,
        model=models.spark,
        describe=f"text prompt: {SPARK_PROMPT}",
        units=spark_units,
        record_as="smoke_spark_text" if record else None,
    )


async def sam_segment(live: LiveCaller, models: MetaModels, record: bool) -> LiveResult:
    return await live.post_sse(
        "/responses",
        sam_adapter.request_body(
            models.sam, HEART.read_bytes(), load_prompt(s2_ground.PROMPT).template, SAM_PHRASE
        ),
        caller=CALLER,
        model=models.sam,
        describe=f"fixtures/heart.png 2048x1612, phrase: {SAM_PHRASE}",
        units=lambda _usage: {"images": 1},
        record_as="smoke_sam_heart_left_ventricle" if record else None,
    )


async def voice_transcribe(live: LiveCaller, models: MetaModels, record: bool) -> LiveResult:
    seconds = wav_seconds(CLIP)
    billed = float(math.ceil(seconds))  # billed in whole seconds (spikes/muse-voice.md)
    return await live.post_multipart(
        "/asr/transcribe",
        voice_files(models, CLIP.read_bytes()),
        caller=CALLER,
        model=models.voice,
        describe=f"fixtures/audio/{CLIP.name}, {seconds:.2f} s, 16 kHz WAV",
        units=lambda _usage: {"audio_seconds": billed},
        record_as="smoke_voice_transcribe" if record else None,
    )


def report(name: str, res: LiveResult, extra: Any = None) -> None:
    print(f"== {name}: HTTP {res.status}, {res.latency_ms} ms")
    print("ledger:", json.dumps(res.ledger_line))
    print("shape:", json.dumps(shape(res.body), indent=1))
    if extra is not None:
        print("parsed:", json.dumps(extra, indent=1))


async def run(live: LiveCaller, models: MetaModels, record: bool) -> None:
    res = await spark_text(live, models, record)
    report("spark", res)
    res = await sam_segment(live, models, record)
    report("sam", res, sam_adapter.instances(await sam_adapter.parse_events(res.body)))
    res = await voice_transcribe(live, models, record)
    report("voice", res)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--record", action="store_true", help="save each call to fixtures/recorded/")
    args = ap.parse_args()
    rules = load_tactile_rules()
    live = LiveCaller.from_env(rules.meta, recorder=Recorder())
    try:
        asyncio.run(run(live, rules.meta.models, args.record))
    except LiveCallError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"spent ${live.meter.spent_usd:.5f} on {live.calls} calls")


if __name__ == "__main__":
    main()
