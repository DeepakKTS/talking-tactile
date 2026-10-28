"""Replay variants of the live caller tests, on real Meta responses recorded by the smoke run
(fixtures/recorded/smoke_*.json, Oct 27). The requests are built by the same smoke code and
must match the recordings exactly, image and audio digests included. The hand-written
responses in test_live_ledger.py stay for the error cases."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.config import load_tactile_rules
from app.meta import sam_adapter, smoke
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller, LiveResult
from app.meta.record import ReplayTransport
from app.paths import RECORDED_DIR

RULES = load_tactile_rules()
MODELS = RULES.meta.models


def recorded(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((RECORDED_DIR / f"{name}.json").read_text())
    return data


def replayer(tmp_path: Path, name: str) -> LiveCaller:
    return LiveCaller(
        key="unused-in-replay",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=ReplayTransport.from_files([RECORDED_DIR / f"{name}.json"]),
    )


def test_spark_text_replays_with_its_real_usage_and_price(tmp_path: Path) -> None:
    live = replayer(tmp_path, "smoke_spark_text")
    res: LiveResult = asyncio.run(smoke.spark_text(live, MODELS, record=False))
    assert res.status == 200
    answer = res.body["choices"][0]["message"]["content"]
    for chamber in ("right atrium", "left atrium", "right ventricle", "left ventricle"):
        assert chamber in answer
    usage = recorded("smoke_spark_text")["response"]["json"]["usage"]
    assert res.ledger_line["usage"] == usage
    want = CostMeter(RULES.meta).price(
        MODELS.spark,
        input_tokens=usage["prompt_tokens"],
        cached_tokens=usage["prompt_tokens_details"]["cached_tokens"],
        output_tokens=usage["completion_tokens"],
    )
    assert res.ledger_line["cost_usd"] == pytest.approx(want)


def test_sam_zero_matches_replays_as_a_complete_empty_result(tmp_path: Path) -> None:
    """The live call found no instance of "left ventricle" on heart.png: no text deltas, an
    empty output_text.done, status completed. That is a result, not an error."""
    live = replayer(tmp_path, "smoke_sam_heart_left_ventricle")
    res = asyncio.run(smoke.sam_segment(live, MODELS, record=False))
    types = [e["type"] for e in res.body]
    assert types[-1] == "response.completed"
    assert "response.output_text.delta" not in types
    assert res.body[-1]["response"]["status"] == "completed"
    assert sam_adapter.instances(asyncio.run(sam_adapter.parse_events(res.body))) == []
    assert res.usage["images_processed"] == 1
    assert res.ledger_line["cost_usd"] == pytest.approx(RULES.meta.prices_usd[MODELS.sam].per_image)


def test_voice_transcribe_replays_the_real_transcript(tmp_path: Path) -> None:
    live = replayer(tmp_path, "smoke_voice_transcribe")
    res = asyncio.run(smoke.voice_transcribe(live, MODELS, record=False))
    assert res.body["transcript"] == "Where is the order? What does the left ventricle do?"
    assert res.body["audioDurationMs"] == 2800
    assert res.usage is None  # the file endpoint returns no usage object
    assert res.ledger_line["cost_usd"] == pytest.approx(3 * 0.18 / 3600)


def test_replay_matches_the_exact_image_and_audio(tmp_path: Path) -> None:
    """A different image would not match the SAM recording."""
    sam_req = recorded("smoke_sam_heart_left_ventricle")["request"]
    url = sam_req["json"]["input"][0]["content"][1]["image_url"]
    assert url.startswith("<data image/png sha256=")
    assert f"bytes={smoke.HEART.stat().st_size}>" in url
    audio = recorded("smoke_voice_transcribe")["request"]["multipart"]["audio"]
    assert f"bytes={smoke.CLIP.stat().st_size}>" in audio
