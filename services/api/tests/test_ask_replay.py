"""POST /api/ask on replay of the live runs of Oct 30 (fixtures/recorded/qa2_ask_* and
qa_ask_transcribe_*): the question eval's 61 answers on published version 4 of the heart and
the Commons brain (fixtures/qa/*_v4_regions.json), the transcribe clips, and the route. Nothing
reaches the network: a request the recordings do not hold fails."""

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
from app.meta.mock import MockMetaClient
from app.models.regions import RegionsFile
from app.paths import FIXTURES_DIR, REPO_ROOT
from app.pipeline import s0_ingest
from app.prompts import load_prompt

RULES = load_tactile_rules()
PROMPT = load_prompt(ask.PROMPT)
LIVE = {
    r["id"]: r for r in json.loads((REPO_ROOT / "eval" / "qa" / "scores.json").read_text())["rows"]
}
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
@pytest.mark.parametrize(
    "q", [q for q in qa_eval.load_questions() if q["id"] in LIVE], ids=lambda q: q["id"]
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
