"""Gate A latency (step 4.2) with no network: nearest-rank percentiles, the requests the
Spark and Voice runs send, failed calls left out of the numbers, and SAM latency read from
the bake-off's results."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import load_tactile_rules
from app.meta import latency_spike as spike
from app.meta import s2_bakeoff as bake
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from app.meta.record import request_summary, sanitize
from app.paths import RECORDED_DIR

RULES = load_tactile_rules()


def test_percentiles_are_nearest_rank() -> None:
    ten = [float(v) for v in range(10, 0, -1)]
    assert (spike.percentile(ten, 50), spike.percentile(ten, 95)) == (5.0, 10.0)
    forty_four = [float(v) for v in range(1, 45)]
    assert spike.percentile(forty_four, 95) == 42.0  # ceil(0.95 * 44) = 42
    with pytest.raises(ValueError):
        spike.percentile([], 50)


def test_the_spark_run_sends_the_bakeoffs_s1_listing_request() -> None:
    body = bake.s1_list_body(RULES.meta.models, bake.HEART.read_bytes())
    recorded = json.loads((RECORDED_DIR / "bakeoff_heart_list.json").read_text())
    assert json.loads(json.dumps(sanitize(body))) == recorded["request"]["json"]
    assert body["reasoning_effort"] == "medium"


def caller(tmp_path: Path, handler: Any) -> LiveCaller:
    return LiveCaller(
        key="test-key",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=httpx.MockTransport(handler),
    )


def test_spark_runs_count_parts_and_leave_failures_out_of_the_percentiles(
    tmp_path: Path,
) -> None:
    answers = iter([200, 500, 200])
    content = json.dumps({"parts": [{"phrase": "aorta", "print_label": "Aorta"}]})

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(answers)
        if status != httpx.codes.OK:
            return httpx.Response(status, text="busy")
        usage = {"prompt_tokens": 100, "completion_tokens": 10}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}], "usage": usage}
        )

    result = asyncio.run(spike.spark(caller(tmp_path, handler), 3, record=False))
    assert [r["status"] for r in result["runs"]] == [200, 500, 200]
    assert [r.get("parts") for r in result["runs"]] == [1, None, 1]
    assert result["latency"]["n"] == 2 and result["effort"] == "medium"


def test_voice_runs_send_the_smoke_request_with_no_keywords(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request_summary(request)["multipart"]["request"])
        return httpx.Response(200, json={"transcript": "x", "audioDurationMs": 2800})

    result = asyncio.run(spike.voice(caller(tmp_path, handler), 2, record=False))
    assert len(seen) == 2 and all("keywords" not in r for r in seen)
    assert seen[0]["audioEncoding"] == "WAV" and seen[0]["mode"] == "PUSH_TO_TALK"
    assert [r["audio_duration_ms"] for r in result["runs"]] == [2800, 2800]
    assert result["latency"]["n"] == 2


def test_sam_latency_counts_only_bakeoff_answers_with_instances(tmp_path: Path) -> None:
    for i, figure in enumerate(sorted(bake.FIGURES)):
        rows = [
            {"part": "a", "latency_ms": 100.0 + i, "instances": 1},
            {"part": "b", "latency_ms": 9000.0, "instances": 0},
            {"part": "c", "grid_point": None, "instances": None},
        ]
        (tmp_path / figure).mkdir()
        (tmp_path / figure / "results.json").write_text(json.dumps({"arm_a_rows": rows}))
    result = spike.sam(tmp_path)
    assert [r["latency_ms"] for r in result["runs"]] == [100.0, 101.0, 102.0]
    assert result["latency"]["max_ms"] == 102.0


def test_sam_latency_from_the_live_bakeoff_has_all_44_answers() -> None:
    result = spike.sam()
    assert result["latency"]["n"] == 44
    assert all(r["instances"] == 1 for r in result["runs"])
