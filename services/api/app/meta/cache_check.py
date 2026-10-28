"""The SAM smoke call twice through the pipeline's stage cache (the d3-8 key chain).

    LIVE=1 uv run python -m app.meta.cache_check [--record]

Ingests fixtures/heart.png (S0) into a fresh data dir, then asks Runner.find_part for the
smoke phrase twice. The first run must call SAM: one new ledger line, a miss. The second must
be answered by the cache: no new miss, one hit line. Exits 1 otherwise."""

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.meta.live import Ledger, LiveCaller
from app.meta.live_client import LiveMetaClient
from app.meta.record import Recorder
from app.meta.smoke import HEART, SAM_PHRASE
from app.pipeline.edits import EditStore
from app.pipeline.jobs import JobStore, StageOutcome
from app.pipeline.runner import Runner


def make_runner(root: Path, client: LiveMetaClient, ledger: Ledger) -> Runner:
    rules = load_tactile_rules()
    return Runner(
        client=client,
        rules=rules,
        explore=load_explore(),
        translator=Translator(rules.braille),
        jobs=JobStore(root / "jobs.sqlite"),
        edits=EditStore(root / "jobs.sqlite"),
        figures_dir=root / "figures",
        ledger=ledger,
    )


@dataclass(frozen=True)
class Run:
    outcome: StageOutcome
    masks: int
    new_lines: list[dict[str, Any]]

    @property
    def caches(self) -> list[str]:
        return [str(x["cache"]) for x in self.new_lines]


async def twice(runner: Runner, ledger: Ledger, figure_id: str) -> list[Run]:
    runs = []
    for _ in range(2):
        before = len(ledger.read())
        masks, outcome = await runner.find_part(figure_id, SAM_PHRASE)
        runs.append(Run(outcome, len(masks), ledger.read()[before:]))
    return runs


def passed(runs: list[Run]) -> bool:
    first, second = runs
    return (
        first.outcome == "ran"
        and first.caches == ["miss"]
        and second.outcome == "cached"
        and second.caches == ["hit"]
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--record", action="store_true", help="save the SAM call to fixtures/recorded/")
    args = ap.parse_args()
    rules = load_tactile_rules()
    live = LiveCaller.from_env(rules.meta, recorder=Recorder())
    client = LiveMetaClient(rules.meta, live, "cache_check" if args.record else None)
    with tempfile.TemporaryDirectory() as tmp:
        runner = make_runner(Path(tmp), client, live.ledger)
        figure_id = runner.ingest(HEART.read_bytes(), 0)[0].figure_id
        runs = asyncio.run(twice(runner, live.ledger, figure_id))
    for i, run in enumerate(runs, 1):
        print(f"run {i}:", json.dumps(asdict(run)))
    ok = passed(runs)
    print("cache check:", "PASS" if ok else "FAIL", f"(live calls {live.calls})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
