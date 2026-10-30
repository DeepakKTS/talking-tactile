"""No retention (Oct 30): a question through POST /api/ask leaves no audio, no transcript and
no question text on disk (the data dir, the job database, the cost ledger, temporary files)
or in the logs. The answer still carries the transcript back to Explore.

The live client runs for real, with a fake network transport, so its ledger lines and the
route's request handling are the ones a class would get."""

import asyncio
import io
import json
import logging
import tempfile
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from app.meta.live_client import LiveMetaClient
from app.models.regions import RegionsFile
from app.paths import FIXTURES_DIR

RULES = load_tactile_rules()
FID = "a" * 64
QUESTION = "Where does the quokkamarmot hide"
HEARD = "what does the zebrafinch outer chamber do"
GOLDEN = RegionsFile.from_json_obj(
    json.loads((FIXTURES_DIR / "regions" / "golden.json").read_text())
)
PCM = bytes(range(7, 251)) * 40  # a pattern no file would hold by chance


def wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(PCM)
    return buf.getvalue()


def meta(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/asr/transcribe"):
        return httpx.Response(200, json={"transcript": HEARD, "audioDurationMs": 300})
    answer = {
        "answer_text": "This is the outer chamber.",
        "source": "figure",
        "cited_part_ids": ["r1"],
    }
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })  # fmt: skip


def everything_written(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


def test_a_question_leaves_no_audio_transcript_or_question_text_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    data, temp = tmp_path / "data", tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))  # uploads that spill land here
    ledger = Ledger(tmp_path / "ledger.jsonl")

    def caller() -> LiveCaller:
        return LiveCaller(key="k", base_url="https://api.meta.ai/v1", ledger=ledger,
                          meter=CostMeter(RULES.meta), cap=RULES.meta.live_call_cap,
                          transport=httpx.MockTransport(meta))  # fmt: skip

    async def body() -> list[dict[str, Any]]:
        app = create_app(data_dir=data, client=LiveMetaClient(RULES.meta, caller))
        service = app.state.figure_service()
        service._published_figure = lambda fid, v: (GOLDEN, b"\x89PNG")
        out = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            spoken = await http.post("/api/ask", files={"audio": ("q.wav", wav(), "audio/wav")},
                                     data={"request": json.dumps({"figure_id": FID})})  # fmt: skip
            typed = await http.post("/api/ask", json={"figure_id": FID, "question": QUESTION})
            for r in (spoken, typed):
                assert r.status_code == 200, r.text
                out.append(r.json())
        return out

    with caplog.at_level(logging.DEBUG):
        spoken, typed = asyncio.run(body())
    assert spoken["transcript"] == HEARD and typed["transcript"] == QUESTION  # back to Explore
    assert ledger.path.exists() and len(ledger.path.read_text().splitlines()) == 3  # calls logged
    written = everything_written(tmp_path)
    for secret in (HEARD.encode(), QUESTION.encode(), PCM[:200], b"quokka", b"zebrafinch"):
        assert secret not in written, f"{secret[:20]!r} was written to disk"
    logged = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    for word in (HEARD, QUESTION, "quokka", "zebrafinch"):
        assert word not in logged, f"{word} was logged"
    assert caplog.records  # the request logs were captured, so the check means something
