"""One SAM call cached on the pipeline's key chain (d3-8). Runner.find_part takes the path a
part a teacher adds by name takes: the S0 image and one phrase, keyed on the S0 key and
digest, the S2 prompt and the client's cache tag. The second run is a hit, and a runner given
a ledger writes it there as a hit, never as a new miss."""

import asyncio
from pathlib import Path

import pytest

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.meta.cache_check import Run, make_runner, passed, twice
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from app.meta.live_client import LiveMetaClient
from app.meta.mock import MockMetaClient
from app.meta.record import ReplayTransport
from app.meta.smoke import HEART
from app.models.image import RGB
from app.models.mask import Mask
from app.paths import FIXTURES_DIR, RECORDED_DIR
from app.pipeline.edits import EditStore
from app.pipeline.jobs import JobStore
from app.pipeline.runner import JobOptions, NotReadyError, Runner
from app.prompts import Prompt
from tests.recorded_png import mac_png

RULES = load_tactile_rules()
SYNTHETIC_PNG = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()
PHRASE = "left lobe"


class _Counting(MockMetaClient):
    segments = 0

    async def segment(self, image: RGB, figure_id: str, phrase: str, prompt: Prompt) -> list[Mask]:
        self.segments += 1
        return await super().segment(image, figure_id, phrase, prompt)


def make(root: Path, client: MockMetaClient, ledger: Ledger | None = None) -> Runner:
    return Runner(
        client=client,
        rules=RULES,
        explore=load_explore(),
        translator=Translator(RULES.braille),
        jobs=JobStore(root / "jobs.sqlite"),
        edits=EditStore(root / "jobs.sqlite"),
        figures_dir=root / "figures",
        ledger=ledger,
    )


def test_find_part_calls_sam_once_then_hits_the_cache(tmp_path: Path) -> None:
    client = _Counting(RULES.meta)
    runner = make(tmp_path, client)
    fid = runner.ingest(SYNTHETIC_PNG, 0)[0].figure_id
    first, ran = asyncio.run(runner.find_part(fid, PHRASE))
    again, cached = asyncio.run(runner.find_part(fid, PHRASE))
    assert (ran, cached) == ("ran", "cached")
    assert client.segments == 1
    assert first and [m.label for m in again] == [m.label for m in first]
    assert all((a.data == b.data).all() for a, b in zip(first, again, strict=True))


def test_a_hit_is_a_ledger_line_marked_hit_and_never_a_miss(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    runner = make(tmp_path, _Counting(RULES.meta), ledger)
    fid = runner.ingest(SYNTHETIC_PNG, 0)[0].figure_id
    asyncio.run(runner.find_part(fid, PHRASE))
    assert ledger.read() == []  # the mock makes no live call, so nothing is a miss
    asyncio.run(runner.find_part(fid, PHRASE))
    [line] = ledger.read()
    assert (line["cache"], line["caller"], line["model"]) == ("hit", "added", RULES.meta.models.sam)
    assert line["usage"] is None and line["cost_usd"] == 0
    assert PHRASE in line["input"]


def test_without_a_ledger_nothing_is_written(tmp_path: Path) -> None:
    runner = make(tmp_path, _Counting(RULES.meta))
    fid = runner.ingest(SYNTHETIC_PNG, 0)[0].figure_id
    asyncio.run(runner.find_part(fid, PHRASE))
    asyncio.run(runner.find_part(fid, PHRASE))
    assert not (tmp_path / "ledger.jsonl").exists()


def test_find_part_needs_the_figure_ingested_first(tmp_path: Path) -> None:
    runner = make(tmp_path, _Counting(RULES.meta))
    with pytest.raises(NotReadyError):
        asyncio.run(runner.find_part("0" * 64, PHRASE))


def test_a_cached_s1_and_s2_are_ledger_hits_when_given_a_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    runner = make(tmp_path, _Counting(RULES.meta), ledger)
    for _ in range(2):
        job = runner.submit(SYNTHETIC_PNG, 0, JobOptions(grade_band="k5"))
        asyncio.run(runner.run(job.id))
    hits = [(x["caller"], x["model"], x["cache"]) for x in ledger.read()]
    assert hits == [("s1", RULES.meta.models.spark, "hit"), ("s2", RULES.meta.models.sam, "hit")]


@mac_png
def test_replay_of_the_live_cache_check(tmp_path: Path) -> None:
    """The Oct 27 live run (app/meta/cache_check.py) replayed: the real SAM answer on heart.png
    after S0, zero instances, then a cache hit with no second call."""
    ledger = Ledger(tmp_path / "ledger.jsonl")
    caller = LiveCaller(
        key="unused-in-replay",
        base_url="https://api.meta.ai/v1",
        ledger=ledger,
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=ReplayTransport.from_files([RECORDED_DIR / "cache_check_left_ventricle.json"]),
    )
    runner = make_runner(tmp_path, LiveMetaClient(RULES.meta, lambda: caller), ledger)
    fid = runner.ingest(HEART.read_bytes(), 0)[0].figure_id
    runs: list[Run] = asyncio.run(twice(runner, ledger, fid))
    assert [(r.outcome, r.masks, r.caches) for r in runs] == [
        ("ran", 0, ["miss"]),
        ("cached", 0, ["hit"]),
    ]
    assert passed(runs) and caller.calls == 1
