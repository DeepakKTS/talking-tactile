"""The live caller: one ledger line per call with the usage object exactly as returned, a
per-run cap on calls, and the key kept out of every error, ledger line and file. The
transport is an httpx.MockTransport, so nothing here reaches the network."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import load_tactile_rules
from app.meta.cost import CostMeter
from app.meta.live import (
    Ledger,
    LiveCallCapError,
    LiveCaller,
    LiveCallError,
    LiveConfigError,
    LiveDisabledError,
    load_key,
    spark_units,
)

RULES = load_tactile_rules()
KEY = "LLM_fake_key_for_tests_0123456789"
SPARK = RULES.meta.models.spark
SAM = RULES.meta.models.sam


def caller(tmp_path: Path, handler: Any, cap: int = 25) -> LiveCaller:
    return LiveCaller(
        key=KEY,
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=cap,
        transport=httpx.MockTransport(handler),
    )


def lines(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "ledger.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


USAGE = {
    "prompt_tokens": 20,
    "completion_tokens": 8,
    "prompt_tokens_details": {"cached_tokens": 4},
    "some_field_we_never_named": {"x": 1},
}


def ok_chat(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = {"choices": [{"message": {"content": "Four chambers."}}], "usage": USAGE}
    return httpx.Response(200, json=body)


def test_a_call_writes_one_ledger_line_with_the_usage_exactly_as_returned(
    tmp_path: Path,
) -> None:
    live = caller(tmp_path, ok_chat)
    res = asyncio.run(
        live.post_json(
            "/chat/completions",
            {"model": SPARK, "messages": []},
            caller="smoke",
            model=SPARK,
            describe="short text prompt",
            units=spark_units,
        )
    )
    assert res.status == 200 and res.body["usage"] == USAGE
    [line] = lines(tmp_path)
    assert set(line) == {
        "ts",
        "caller",
        "model",
        "input",
        "cache",
        "status",
        "latency_ms",
        "usage",
        "cost_usd",
    }
    assert (line["caller"], line["model"], line["input"], line["cache"]) == (
        "smoke",
        SPARK,
        "short text prompt",
        "miss",
    )
    assert line["usage"] == USAGE
    want = CostMeter(RULES.meta).price(SPARK, input_tokens=20, cached_tokens=4, output_tokens=8)
    assert line["cost_usd"] == pytest.approx(want)
    assert live.meter.spent_usd == pytest.approx(want)


def test_a_response_without_usage_logs_null_and_no_guessed_cost(tmp_path: Path) -> None:
    live = caller(tmp_path, lambda r: httpx.Response(200, json={"choices": []}))
    asyncio.run(
        live.post_json(
            "/chat/completions", {}, caller="t", model=SPARK, describe="x", units=spark_units
        )
    )
    [line] = lines(tmp_path)
    assert line["usage"] is None and line["cost_usd"] is None


def test_a_streamed_call_takes_usage_from_the_completed_event(tmp_path: Path) -> None:
    usage = {"input_tokens": 3, "output_tokens": 50, "unknown": True}
    events = [
        {"type": "response.output_text.delta", "delta": "<0f>"},
        {"type": "response.completed", "response": {"usage": usage}},
    ]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    live = caller(tmp_path, handler)
    res = asyncio.run(
        live.post_sse(
            "/responses",
            {},
            caller="smoke",
            model=SAM,
            describe="heart.png, aorta",
            units=lambda u: {"images": 1},
        )
    )
    assert res.body == events
    [line] = lines(tmp_path)
    assert line["usage"] == usage
    assert line["cost_usd"] == pytest.approx(RULES.meta.prices_usd[SAM].per_image or 0)


def test_the_run_stops_at_the_cap_before_sending(tmp_path: Path) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return ok_chat(request)

    live = caller(tmp_path, handler, cap=2)

    async def go() -> None:
        for _ in range(2):
            await live.post_json("/chat/completions", {}, caller="t", model=SPARK, describe="x")
        with pytest.raises(LiveCallCapError, match="2"):
            await live.post_json("/chat/completions", {}, caller="t", model=SPARK, describe="x")

    asyncio.run(go())
    assert len(sent) == 2 and len(lines(tmp_path)) == 2


def test_the_default_cap_is_25_from_config(tmp_path: Path) -> None:
    assert RULES.meta.live_call_cap == 25
    env = tmp_path / ".env"
    env.write_text("MODEL_API_KEY" + f"={KEY}\n")
    live = LiveCaller.from_env(RULES.meta, env_file=env, ledger_path=tmp_path / "l.jsonl")
    assert live.cap == 25
    assert live.base_url == "https://api.meta.ai/v1"


def test_an_error_is_logged_and_raised_with_the_key_redacted(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": f"bad key Bearer {KEY}"})

    live = caller(tmp_path, handler, cap=1)
    with pytest.raises(LiveCallError) as err:
        asyncio.run(live.post_json("/chat/completions", {}, caller="t", model=SPARK, describe="x"))
    assert err.value.status == 401
    assert KEY not in str(err.value) and "<redacted>" in str(err.value)
    [line] = lines(tmp_path)
    assert line["status"] == 401 and line["usage"] is None
    assert KEY not in (tmp_path / "ledger.jsonl").read_text()
    with pytest.raises(LiveCallCapError):  # a failed call still counts toward the cap
        asyncio.run(live.post_json("/chat/completions", {}, caller="t", model=SPARK, describe="x"))


def test_the_real_network_needs_live_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE", raising=False)
    live = LiveCaller(
        key=KEY,
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=25,
    )
    with pytest.raises(LiveDisabledError, match="LIVE=1"):
        asyncio.run(live.post_json("/chat/completions", {}, caller="t", model=SPARK, describe="x"))
    assert lines(tmp_path) == []


def test_load_key_never_puts_the_value_in_an_error(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    with pytest.raises(LiveConfigError, match="MODEL_API_KEY"):
        load_key(env)
    env.write_text("MODEL_API_KEY" + "=\n")
    with pytest.raises(LiveConfigError, match="empty"):
        load_key(env)
    env.write_text("MODEL_API_KEY" + f'="{KEY}"\nOTHER=1\n')
    assert load_key(env) == KEY


def test_every_configured_model_has_a_price() -> None:
    models = RULES.meta.models
    for model in (models.spark, models.sam, models.voice):
        assert model in RULES.meta.prices_usd
