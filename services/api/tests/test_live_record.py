"""Record and replay. A successful live call can be saved under fixtures/recorded/ with no auth
header and no key, and with image or audio payloads replaced by their sha256 and size.
ReplayTransport serves a saved call back to the same request through the same LiveCaller
code, with no network."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import load_tactile_rules
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller, LiveCallError
from app.meta.record import Recorder, ReplayTransport, sanitize

RULES = load_tactile_rules()
KEY = "LLM_fake_key_for_record_tests_42"
SPARK = RULES.meta.models.spark
SAM = RULES.meta.models.sam
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8
DATA_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


def make(
    tmp_path: Path, transport: httpx.MockTransport, recorder: Recorder | None = None
) -> LiveCaller:
    return LiveCaller(
        key=KEY,
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=25,
        transport=transport,
        recorder=recorder,
    )


def chat(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"echo": json.loads(request.content)["messages"], "usage": {}})


def test_a_recording_has_no_key_no_auth_and_no_raw_image(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "recorded")
    answer = httpx.Response(200, json={"choices": [], "usage": {}})
    live = make(tmp_path, httpx.MockTransport(lambda r: answer), rec)
    body = {
        "model": SPARK,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "image_url", "image_url": {"url": DATA_URI}},
                ],
            }
        ],
    }
    asyncio.run(
        live.post_json(
            "/chat/completions", body, caller="t", model=SPARK, describe="x", record_as="spark_case"
        )
    )
    path = tmp_path / "recorded" / "spark_case.json"
    text = path.read_text()
    assert KEY not in text and "uthorization" not in text and "Bearer" not in text
    assert DATA_URI not in text
    saved = json.loads(text)
    assert saved["request"]["path"] == "/chat/completions"
    assert saved["model"] == SPARK and saved["response"]["status"] == 200
    url = saved["request"]["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert url == sanitize(DATA_URI)
    assert url.startswith("<data image/png sha256=") and f"bytes={len(PNG)}" in url


def test_a_json_call_replays_through_the_same_caller(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "recorded")
    body = {"model": SPARK, "messages": [{"role": "user", "content": DATA_URI}]}
    first = asyncio.run(
        make(tmp_path, httpx.MockTransport(chat), rec).post_json(
            "/chat/completions", body, caller="t", model=SPARK, describe="x", record_as="c"
        )
    )
    replay = ReplayTransport.from_files([tmp_path / "recorded" / "c.json"])
    again = asyncio.run(
        make(tmp_path, replay).post_json(
            "/chat/completions", body, caller="t", model=SPARK, describe="x"
        )
    )
    assert again.body == first.body


def test_a_stream_replays_event_for_event(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = [
        {"type": "response.output_text.delta", "delta": "<0f>"},
        {"type": "response.completed", "response": {"usage": {"n": 1}}},
    ]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    live = make(
        tmp_path,
        httpx.MockTransport(
            lambda r: httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        ),
        Recorder(tmp_path / "recorded"),
    )
    body = {"model": SAM, "input": [{"content": [{"type": "input_image", "image_url": DATA_URI}]}]}
    asyncio.run(
        live.post_sse("/responses", body, caller="t", model=SAM, describe="x", record_as="sam_case")
    )
    replay = ReplayTransport.from_files([tmp_path / "recorded" / "sam_case.json"])
    again = asyncio.run(
        make(tmp_path, replay).post_sse("/responses", body, caller="t", model=SAM, describe="x")
    )
    assert again.body == events and again.usage == {"n": 1}


def test_multipart_audio_is_saved_as_a_digest_and_replays(tmp_path: Path) -> None:
    wav = b"RIFF" + bytes(4000)
    live = make(
        tmp_path,
        httpx.MockTransport(
            lambda r: httpx.Response(200, json={"transcript": "where is the aorta"})
        ),
        Recorder(tmp_path / "recorded"),
    )
    files = {
        "request": (None, json.dumps({"model": "m"}), "application/json"),
        "audio": ("q.wav", wav, "audio/wav"),
    }
    asyncio.run(
        live.post_multipart(
            "/asr/transcribe", files, caller="t", model="m", describe="x", record_as="voice_case"
        )
    )
    saved = json.loads((tmp_path / "recorded" / "voice_case.json").read_text())
    parts = saved["request"]["multipart"]
    assert parts["request"] == {"model": "m"}
    assert parts["audio"].startswith("<data audio/wav sha256=") and "bytes=4004" in parts["audio"]
    replay = ReplayTransport.from_files([tmp_path / "recorded" / "voice_case.json"])
    again = asyncio.run(
        make(tmp_path, replay).post_multipart(
            "/asr/transcribe", files, caller="t", model="m", describe="x"
        )
    )
    assert again.body == {"transcript": "where is the aorta"}


def test_a_request_with_no_recording_is_refused(tmp_path: Path) -> None:
    replay = ReplayTransport([])
    with pytest.raises(LiveCallError, match="no recording"):
        asyncio.run(
            make(tmp_path, replay).post_json(
                "/chat/completions", {"x": 1}, caller="t", model=SPARK, describe="x"
            )
        )


def test_a_failed_call_is_not_recorded(tmp_path: Path) -> None:
    live = make(
        tmp_path,
        httpx.MockTransport(lambda r: httpx.Response(500, text="oops")),
        Recorder(tmp_path / "recorded"),
    )
    with pytest.raises(LiveCallError):
        asyncio.run(
            live.post_json(
                "/chat/completions", {}, caller="t", model=SPARK, describe="x", record_as="bad"
            )
        )
    assert not (tmp_path / "recorded" / "bad.json").exists()


def test_a_recording_never_overwrites_an_existing_one(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "recorded")
    live = make(tmp_path, httpx.MockTransport(chat), rec)
    body = {"messages": ["a"]}
    asyncio.run(
        live.post_json(
            "/chat/completions", body, caller="t", model=SPARK, describe="x", record_as="once"
        )
    )
    with pytest.raises(FileExistsError):
        asyncio.run(
            live.post_json(
                "/chat/completions", body, caller="t", model=SPARK, describe="x", record_as="once"
            )
        )
