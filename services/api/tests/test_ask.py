"""Explore's questions (app/ask.py, POST /api/ask) with a fake Meta client: the prompt is the
published figure in words, code has the last word on Spark's answer, audio is checked and
transcribed with the figure's names as hints, and a session has a question cap."""

import asyncio
import io
import json
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import ask
from app.ask import Asker, AskRequest, SessionCap, SparkAnswer
from app.config import load_tactile_rules
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.models.regions import RegionsFile
from app.paths import FIXTURES_DIR
from app.prompts import load_prompt

GOLDEN = RegionsFile.from_json_obj(
    json.loads((FIXTURES_DIR / "regions" / "golden.json").read_text())
)
FID = "a" * 64
PROMPT = load_prompt(ask.PROMPT)


def wav(rate: int = 16000, channels: int = 1, seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(rate * seconds) * channels)
    return buf.getvalue()


class FakeClient:
    def __init__(self, answer: dict[str, Any], transcript: str = "what is this") -> None:
        self.answer_json, self.transcript = answer, transcript
        self.asked: list[dict[str, Any]] = []
        self.heard: list[list[str]] = []

    def for_job(self) -> "FakeClient":
        return self

    def cap_calls(self, cap: int) -> None:
        self.cap = cap

    async def transcribe(self, figure_id: str, data: bytes, keywords: list[str]) -> str:
        self.heard.append(list(keywords))
        return self.transcript

    async def answer(self, figure_id: str, png: bytes, system: str, user: str,
                     schema: dict[str, Any], what: str) -> dict[str, Any]:  # fmt: skip
        self.asked.append({"system": system, "user": user, "schema": schema, "what": what})
        return self.answer_json


def asker(client: FakeClient, cap: int = 50) -> Asker:
    return Asker(client, PROMPT.template["system"], PROMPT.template["user"],
                 lambda fid, v: (GOLDEN, b"png"), SessionCap(cap))  # fmt: skip


def req(**kw: Any) -> AskRequest:
    return AskRequest(figure_id=FID, **{"question": "What is this?", **kw})


def test_the_prompt_is_the_published_figure_in_words_with_the_touch_context() -> None:
    text = ask.prompt_text(
        PROMPT.template["user"],
        GOLDEN,
        req(region_id="r2", recent_region_ids=["r3"]),
        "What is this?",
    )
    assert f"Figure title: {GOLDEN.title}" in text
    assert (
        "- r1: outer chamber. Next to: r2 core (inside it), r3 right vessel (to the right)." in text
    )
    assert "- r2: core. " in text and "Inside outer chamber." in text
    assert "Part of the vessels." in text
    assert (
        "The student's finger is on: r2 core" in text
        and "Touched just before: r3 right vessel" in text
    )
    assert 'question, as heard: "What is this?"' in text


@pytest.mark.parametrize(
    ("source", "said"),
    [("off_figure", ask.OFF_FIGURE), ("unsure", ask.UNSURE)],
)
def test_off_figure_and_unsure_get_fixed_wording_that_sends_the_student_to_the_teacher(
    source: str, said: str
) -> None:
    spark = SparkAnswer(answer_text="The heart pumps blood.", source=source, cited_part_ids=["r1"])
    assert ask.final(spark, GOLDEN) == (said, source, [])


def test_code_keeps_two_sentences_known_ids_and_no_dashes() -> None:
    spark = SparkAnswer(answer_text="It is the core — inside. Next is r1. Third one.",
                        source="figure", cited_part_ids=["r2", "r99", "r2_2"])  # fmt: skip
    assert ask.final(spark, GOLDEN) == ("It is the core, inside. Next is r1.", "figure", ["r2"])


def test_a_teacher_description_answer_must_cite_a_described_part() -> None:
    spark = SparkAnswer(
        answer_text="It does x.", source="teacher_description", cited_part_ids=["r4"]
    )
    assert ask.final(spark, GOLDEN)[1] == "unsure"


def test_keywords_are_the_figures_part_line_and_group_names_once_each() -> None:
    names = ask.keywords(GOLDEN)
    assert "outer chamber" in names and "vessels" in names
    assert len(names) == len(set(names))
    assert all(x.label in names for x in GOLDEN.lines or [])


@pytest.mark.parametrize(
    ("rate", "channels", "ok"),
    [(16000, 1, True), (24000, 1, True), (44100, 1, False), (16000, 2, False)],
)
def test_audio_must_be_mono_16_bit_wav_at_16_or_24_khz(rate: int, channels: int, ok: bool) -> None:
    if ok:
        assert ask.check_wav(wav(rate, channels)) == pytest.approx(0.5)
    else:
        with pytest.raises(ask.WavError):
            ask.check_wav(wav(rate, channels))
    with pytest.raises(ask.WavError):
        ask.check_wav(b"RIFF not a wave")


def test_a_spoken_question_is_transcribed_with_hints_then_answered() -> None:
    client = FakeClient(
        {"answer_text": "This is the core.", "source": "figure", "cited_part_ids": ["r2"]}
    )
    out = asyncio.run(asker(client).ask(req(question=""), wav()))
    assert client.heard == [ask.keywords(GOLDEN)] and client.asked[0]["what"] == "what is this"
    assert (out.transcript, out.answer, out.source, out.cited_part_ids) == (
        "what is this",
        "This is the core.",
        "figure",
        ["r2"],
    )
    assert (
        set(out.timings_ms) == {"transcribe", "spark", "server"}
        and client.cap == ask.CALLS_PER_QUESTION
    )


def test_nothing_heard_asks_again_without_calling_spark() -> None:
    client = FakeClient({}, transcript="  ")
    out = asyncio.run(asker(client).ask(req(question=""), wav()))
    assert out.answer == ask.NOT_HEARD and client.asked == []


def test_a_session_stops_at_its_question_cap() -> None:
    client = FakeClient({"answer_text": "Yes.", "source": "figure", "cited_part_ids": []})
    a = asker(client, cap=2)
    asyncio.run(a.ask(req(session_id="s1"), None))
    asyncio.run(a.ask(req(session_id="s1"), None))
    with pytest.raises(ask.QuestionCapError):
        asyncio.run(a.ask(req(session_id="s1"), None))
    asyncio.run(a.ask(req(session_id="s2"), None))  # another session


def test_the_route_answers_typed_and_spoken_questions_and_says_what_went_wrong(
    tmp_path: Path,
) -> None:
    client = FakeClient(
        {"answer_text": "This is the core.", "source": "figure", "cited_part_ids": ["r2"]}
    )

    async def body() -> None:
        app = create_app(data_dir=tmp_path, client=MockMetaClient(load_tactile_rules().meta))
        service = app.state.figure_service
        service().asker = lambda: asker(client)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            typed = await http.post(
                "/api/ask", json={"figure_id": FID, "question": "What is this?", "region_id": "r2"}
            )
            assert typed.status_code == 200 and typed.json()["answer"] == "This is the core."
            spoken = await http.post("/api/ask", files={"audio": ("q.wav", wav(), "audio/wav")},
                                     data={"request": json.dumps({"figure_id": FID})})  # fmt: skip
            assert spoken.status_code == 200 and spoken.json()["transcript"] == "what is this"
            bad = await http.post("/api/ask", files={"audio": ("q.wav", wav(44100), "audio/wav")},
                                  data={"request": json.dumps({"figure_id": FID})})  # fmt: skip
            assert (bad.status_code, bad.json()["error"]["code"]) == (422, "audio_invalid")
            empty = await http.post("/api/ask", json={"figure_id": FID, "question": " "})
            assert empty.status_code == 422

    asyncio.run(body())
