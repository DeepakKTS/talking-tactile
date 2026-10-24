"""The pipeline runner. submit runs S0 at once, so a bad upload is refused before any job
exists; run takes the job through S1 to S5.

Every stage output is cached (app/pipeline/cache.py). S1 is always read or made, since the
later stages need its title, figure type and color flag. For S2 to S5 the runner starts
after the latest stage found in the cache, and the stages before that one are skipped. A
cache entry that cannot be read is deleted and made again. The code-only stages run in a
worker thread so the event loop stays free.

    MOCK_META=1 uv run python -m app.pipeline.runner FILE [--grade k5] [--page letter]
"""

import argparse
import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar, get_args

from app.braille.louis import BrailleUnavailableError, Translator
from app.config import ExploreConfig, TactileRules, load_explore, load_tactile_rules
from app.geometry.scale import fit_to_page
from app.meta.client import MetaClient, make_client
from app.meta.cost import BudgetExceededError
from app.meta.mock import MockFixtureMissingError
from app.models.regions import GradeBand, PageSize
from app.paths import FIGURES_DIR, JOBS_DB
from app.pipeline import (
    s0_ingest,
    s1_understand,
    s2_ground,
    s3_reconcile,
    s4_layout,
    s5_render,
)
from app.pipeline.cache import FigureCache, code_digest, stage_key
from app.pipeline.jobs import JobOptions, JobRecord, JobStore, StageOutcome, StageRun

log = logging.getLogger(__name__)

__all__ = ["STAGES", "JobOptions", "Runner"]

STAGES = ("s0", "s1", "s2", "s3", "s4", "s5")
_RESUMABLE = STAGES[2:]
_MS_PER_S = 1000

_STORE: dict[str, tuple[Callable[[Any, Path], None], Callable[[Path], Any]]] = {
    "s2": (s2_ground.save, s2_ground.load),
    "s3": (s3_reconcile.save, s3_reconcile.load),
    "s4": (s4_layout.save, s4_layout.load),
    "s5": (s5_render.save, s5_render.load),
}
_ERROR_CODES: dict[type[Exception], str] = {
    MockFixtureMissingError: "no_recording",
    BudgetExceededError: "budget",
    BrailleUnavailableError: "braille_unavailable",
}

T = TypeVar("T")


class Runner:
    def __init__(
        self,
        *,
        client: MetaClient,
        rules: TactileRules,
        explore: ExploreConfig,
        translator: Translator,
        jobs: JobStore,
        figures_dir: Path = FIGURES_DIR,
    ) -> None:
        self.client = client
        self.rules = rules
        self.explore = explore
        self.translator = translator
        self.jobs = jobs
        self.figures_dir = figures_dir

    def _keys(self, figure_id: str, options: JobOptions) -> dict[str, str]:
        mode = self.client.mode
        k0 = stage_key("s0", "", figure_id=figure_id)
        k1 = stage_key(
            "s1", k0, mode=mode, version=s1_understand.VERSION, max_parts=self.rules.meta.max_parts
        )
        k2 = stage_key(
            "s2", k1, mode=mode, version=s2_ground.VERSION, text_phrase=self.rules.meta.text_phrase
        )
        free = {
            "code": code_digest(),
            "rules": self.rules.model_dump(mode="json"),
            "explore": self.explore.model_dump(mode="json"),
            "options": options.model_dump(mode="json"),
        }
        k3 = stage_key("s3", k2, **free)
        k4 = stage_key("s4", k3, **free)
        k5 = stage_key("s5", k4, **free)
        return dict(zip(STAGES, (k0, k1, k2, k3, k4, k5), strict=True))

    def output_dir(self, job: JobRecord) -> Path | None:
        """Where a finished job's tactile.svg, print.pdf, regions.json and report.json are."""
        if job.result_key is None:
            return None
        return FigureCache(self.figures_dir, job.figure_id).dir("s5", job.result_key)

    def submit(self, data: bytes, page_index: int, options: JobOptions) -> JobRecord:
        """Runs S0 and creates the job. A bad upload raises IngestError and makes no job."""
        t0 = time.perf_counter()
        ing = s0_ingest.ingest(data, page_index, self.rules.pipeline)
        cache = FigureCache(self.figures_dir, ing.figure_id)
        key = self._keys(ing.figure_id, options)["s0"]
        hit = cache.has("s0", key)
        if not hit:
            with cache.write("s0", key) as out:
                s0_ingest.save(ing, out)
        job = self.jobs.create(ing.figure_id, options)
        self._record(job.id, "s0", "cached" if hit else "ran", t0)
        return self._get(job.id)

    async def run(self, job_id: str) -> JobRecord:
        job = self._get(job_id)
        stage = "s0"
        try:
            keys = self._keys(job.figure_id, job.options)
            cache = FigureCache(self.figures_dir, job.figure_id)
            ing = s0_ingest.load(cache.dir("s0", keys["s0"]))

            stage = "s1"
            t0 = time.perf_counter()
            u = self._load(cache, "s1", keys["s1"], s1_understand.load)
            if u is None:
                u = await self._make(
                    job.id,
                    cache,
                    "s1",
                    keys["s1"],
                    s1_understand.save,
                    s1_understand.understand(self.client, ing, self.rules.meta),
                )
            else:
                self._record(job.id, "s1", "cached", t0)
            if u.verdict == "describe_only":
                self.jobs.finish(job.id, "describe_only")
                return self._get(job.id)

            h, w = ing.image.shape[:2]
            fit = fit_to_page(w, h, job.options.page, self.rules.page)
            steps: dict[str, Callable[[Any], Awaitable[Any]]] = {
                "s2": lambda _: s2_ground.ground(self.client, ing, u, self.rules.meta),
                "s3": lambda g: asyncio.to_thread(
                    s3_reconcile.reconcile_masks, g, fit, self.rules.reconcile
                ),
                "s4": lambda rec: asyncio.to_thread(
                    s4_layout.layout,
                    rec,
                    ing,
                    u,
                    fit,
                    job.options.grade_band,
                    self.rules,
                    self.explore.earcons,
                    self.translator,
                ),
                "s5": lambda c: asyncio.to_thread(
                    s5_render.render, c, u, job.figure_id, self.rules, self.explore
                ),
            }
            start, value = await self._resume(job.id, cache, keys)
            for stage in _RESUMABLE[start:]:
                value = await self._make(
                    job.id, cache, stage, keys[stage], _STORE[stage][0], steps[stage](value)
                )
            self.jobs.finish(job.id, "done", result_key=keys["s5"])
        except Exception as exc:
            code = next((c for t, c in _ERROR_CODES.items() if isinstance(exc, t)), "stage_failed")
            if code == "stage_failed":
                log.exception("job %s failed at %s", job.id, stage)
            else:
                log.warning("job %s failed at %s: %s", job.id, stage, exc)
            self.jobs.fail(job.id, stage, code, str(exc) or type(exc).__name__)
        return self._get(job.id)

    async def _resume(
        self, job_id: str, cache: FigureCache, keys: dict[str, str]
    ) -> tuple[int, Any]:
        """The index in _RESUMABLE to run from, and the cached output just before it."""
        for i in reversed(range(len(_RESUMABLE))):
            stage = _RESUMABLE[i]
            t0 = time.perf_counter()
            value = await asyncio.to_thread(self._load, cache, stage, keys[stage], _STORE[stage][1])
            if value is not None:
                for skipped in _RESUMABLE[:i]:
                    self.jobs.record_stage(
                        job_id, StageRun(stage=skipped, outcome="skipped", ms=0.0, cost_usd=0.0)
                    )
                self._record(job_id, stage, "cached", t0)
                return i + 1, value
        return 0, None

    def _load(
        self, cache: FigureCache, stage: str, key: str, load: Callable[[Path], T]
    ) -> T | None:
        if not cache.has(stage, key):
            return None
        try:
            return load(cache.dir(stage, key))
        except Exception:
            log.warning("cache entry %s is unreadable; making it again", cache.dir(stage, key))
            cache.drop(stage, key)
            return None

    async def _make(
        self,
        job_id: str,
        cache: FigureCache,
        stage: str,
        key: str,
        save: Callable[[T, Path], None],
        make: Awaitable[T],
    ) -> T:
        self.jobs.set_stage(job_id, stage)
        spent, t0 = self.client.meter.spent_usd, time.perf_counter()
        value = await make
        with cache.write(stage, key) as out:
            await asyncio.to_thread(save, value, out)
        self._record(job_id, stage, "ran", t0, self.client.meter.spent_usd - spent)
        return value

    def _record(
        self, job_id: str, stage: str, outcome: StageOutcome, t0: float, cost_usd: float = 0.0
    ) -> None:
        ms = (time.perf_counter() - t0) * _MS_PER_S
        self.jobs.record_stage(
            job_id, StageRun(stage=stage, outcome=outcome, ms=ms, cost_usd=cost_usd)
        )
        log.info("job %s %s %s in %.0f ms, $%.4f", job_id[:8], stage, outcome, ms, cost_usd)

    def _get(self, job_id: str) -> JobRecord:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(f"no job {job_id}")
        return job


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one figure through S0 to S5.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--page", choices=get_args(PageSize), default="letter")
    parser.add_argument("--grade", choices=get_args(GradeBand), default=None)
    parser.add_argument("--page-index", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rules, explore = load_tactile_rules(), load_explore()
    runner = Runner(
        client=make_client(os.environ.get("MOCK_META") == "1", rules.meta),
        rules=rules,
        explore=explore,
        translator=Translator(rules.braille),
        jobs=JobStore(JOBS_DB),
    )
    options = JobOptions(page=args.page, grade_band=args.grade)
    job = runner.submit(args.file.read_bytes(), args.page_index, options)
    job = asyncio.run(runner.run(job.id))
    print(f"{job.status}: {runner.output_dir(job) or job.error_message}")


if __name__ == "__main__":
    main()
