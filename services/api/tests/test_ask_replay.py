"""POST /api/ask on replay of the live runs (fixtures/recorded/qa7_ask_*, Nov 3, answer
prompt v2; qa_ask_transcribe_*, Oct 30): the question eval's 73 answers on published version 4
of the heart and the Commons brain (fixtures/qa/*_v4_regions.json), the transcribe clips, and
the route. Nothing reaches the network: a request the recordings do not hold fails."""

import asyncio
import json
import tempfile
from functools import cache
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import ask
from app.config import load_tactile_rules
from app.main import create_app
from app.meta import qa_eval
from app.meta.mock import MockFixtureMissingError, MockMetaClient
from app.models.regions import RegionsFile
from app.paths import FIXTURES_DIR, REPO_ROOT
from app.pipeline import s0_ingest
from app.prompts import load_prompt
from tests.recorded_png import mac_pixels, mac_png

RULES = load_tactile_rules()
PROMPT = load_prompt(ask.PROMPT)
SCORES = json.loads((REPO_ROOT / "eval" / "qa" / "scores.json").read_text())
LIVE = {r["id"]: r for r in SCORES["rows"]}
# Recordings answer the prompt they were made with; after a prompt change they wait for the
# next live run (app/meta/qa_eval.py --live), which writes its prompt into scores.json.
RECORDED_PROMPT = SCORES.get("prompt", "ask_answer.v1.json")
stale = pytest.mark.skipif(
    RECORDED_PROMPT != ask.PROMPT,
    reason=f"answers recorded with {RECORDED_PROMPT}, the prompt is now {ask.PROMPT}",
)
IMAGES = {
    "heart": FIXTURES_DIR / "heart.png",
    "brain_lobes": FIXTURES_DIR / "eval" / "brain_lobes.png",
}
NAMES = {fid: name for name, fid in qa_eval.FIGURES.items()}


@cache
def figure(fid: str) -> tuple[RegionsFile, bytes]:
    """Published version 4 and the image S0 makes, byte for byte what the live run sent."""
    name = NAMES[fid]
    regions = RegionsFile.from_json_obj(
        json.loads((FIXTURES_DIR / "qa" / f"{name}_v4_regions.json").read_text("utf-8"))
    )
    out = Path(tempfile.mkdtemp())
    s0_ingest.save(s0_ingest.ingest(IMAGES[name].read_bytes(), 0, RULES.pipeline), out)
    return regions, (out / s0_ingest.IMAGE_FILE).read_bytes()


def asker() -> ask.Asker:
    return ask.Asker(MockMetaClient(RULES.meta), PROMPT.template["system"],
                     PROMPT.template["user"], lambda fid, v: figure(fid))  # fmt: skip


def request(q: dict[str, Any]) -> ask.AskRequest:
    fid = qa_eval.FIGURES[q["figure"]]
    regions, _ = figure(fid)
    by_label = {r.label: r.id for r in regions.regions if r.touchable and "_" not in r.id}
    return ask.AskRequest(
        figure_id=fid, version=qa_eval.VERSION, question=q["question"],
        region_id=by_label.get(q["finger"]) if q["finger"] else None,
        recent_region_ids=[by_label[x] for x in q["recent"]], session_id=f"replay-{q['id']}",
    )  # fmt: skip


# The questions the recorded live run answered (scores.json); the image experiment's are apart.
# Each request holds the figure's PNG as encoded on macOS (tests/recorded_png.py).
@mac_png
@stale
@pytest.mark.parametrize(
    "q",
    [
        pytest.param(q, marks=mac_pixels if q["figure"] == "brain_lobes" else ())
        for q in qa_eval.load_questions()
        if q["id"] in LIVE
    ],
    ids=lambda q: q["id"],
)
def test_every_eval_question_gets_its_live_answer_back(q: dict[str, Any]) -> None:
    got = asyncio.run(asker().ask(request(q), None))
    live = LIVE[q["id"]]
    regions, _ = figure(qa_eval.FIGURES[q["figure"]])
    label = {r.id.partition("_")[0]: r.label for r in regions.regions}
    assert (got.answer, got.source) == (live["answer"], live["source"])
    assert [label[i] for i in got.cited_part_ids] == live["cited"]


@pytest.mark.parametrize(
    ("clip", "hints", "heard"),
    [
        ("question_left_ventricle", False, "What does the left ventricle do?"),
        ("question_left_ventricle", True, "What does the the left ventricle do?"),
        ("question_superior_vena_cava", True, "where is the superior vena cava?"),
        ("question_left_pulmonary_veins", True, "What is next to the left pulmonary veins?"),
    ],
)
def test_the_transcribe_clips_replay_with_and_without_keywords(
    clip: str, hints: bool, heard: str
) -> None:
    fid = qa_eval.FIGURES["heart"]
    wav = (FIXTURES_DIR / "audio" / f"{clip}.wav").read_bytes()
    words = ask.keywords(figure(fid)[0]) if hints else []
    assert asyncio.run(MockMetaClient(RULES.meta).transcribe(fid, wav, words)) == heard


@stale
def test_the_route_answers_from_the_figure_and_deflects_off_it(tmp_path: Path) -> None:
    async def body() -> list[dict[str, Any]]:
        app = create_app(data_dir=tmp_path, client=MockMetaClient(RULES.meta))
        service = app.state.figure_service()
        service._published_figure = lambda fid, v: figure(fid)
        fid = qa_eval.FIGURES["heart"]
        out = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            for question in (
                "What does the left ventricle do?",
                "What does the right ventricle do?",
            ):
                r = await http.post(
                    "/api/ask", json={"figure_id": fid, "version": 3, "question": question}
                )
                assert r.status_code == 200, r.text
                out.append(r.json())
            missing = await http.post(
                "/api/ask", json={"figure_id": fid, "question": "Not recorded?"}
            )
            assert (missing.status_code, missing.json()["error"]["message"]) == (502, ask.FAILED)
        return out

    described, off = asyncio.run(body())
    assert described["source"] == "teacher_description"
    assert (
        described["answer"]
        == "The left ventricle pumps blood out to the whole body through the aortic arch."
    )
    assert (off["source"], off["answer"], off["cited_part_ids"]) == (
        "off_figure",
        ask.OFF_FIGURE,
        [],
    )


def ask_on(question: str, finger: str | None, recent: list[str]) -> ask.Answer:
    q = {"id": "fallback", "figure": "heart", "question": question, "finger": finger,
         "recent": recent}  # fmt: skip
    return asyncio.run(asker().ask(request(q), None))


def test_mock_answers_a_finger_free_question_wherever_the_finger_is() -> None:
    """The demo's offline fallback: h15 was recorded with no part under the finger; asked with
    a finger on the right atrium after the aortic arch, the same recorded answer comes back."""
    got = ask_on("What does the left ventricle do?", "right atrium", ["aortic arch"])
    assert (got.answer, got.source) == (LIVE["h15"]["answer"], LIVE["h15"]["source"])


def test_mock_never_serves_an_answer_tied_to_another_finger_position() -> None:
    """h01 "What is this?" was recorded on the right atrium; on the left ventricle there is
    no recording, and the fallback must not answer "the right atrium"."""
    with pytest.raises(MockFixtureMissingError):
        ask_on("What is this?", "left ventricle", [])
