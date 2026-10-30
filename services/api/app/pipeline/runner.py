"""The pipeline runner. ingest runs S0 at once, so a bad upload is refused before any job
exists; run takes a job through S1 to S5.

Stage keys (app/pipeline/cache.py) chain: each one hashes the previous key, the digests of
the upstream outputs the stage reads, and the stage's own inputs. The Meta stages key on
their prompt file, response schema and the client's cache tag, which in mock mode covers
the fixture files. The code-only stages key on the source, config and job options; S4 and
S5 also on the teacher's edit layer. A stage found in the cache is not loaded unless a later
stage has to run from it. The code-only stages run in a worker thread so the event loop
stays free.

    MOCK_META=1 uv run python -m app.pipeline.runner FILE [--grade k5] [--page letter]
"""

import argparse
import asyncio
import logging
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, get_args

import numpy as np

from app.braille.louis import BrailleUnavailableError, Translator
from app.config import ExploreConfig, TactileRules, load_explore, load_tactile_rules
from app.geometry.reconcile import Reconciled, ReconciledPart
from app.geometry.scale import PageFit, fit_to_page
from app.meta.client import MetaClient, make_client
from app.meta.cost import BudgetExceededError
from app.meta.live import Ledger
from app.meta.live_client import SPARK_EFFORT
from app.meta.mock import MockFixtureMissingError
from app.meta.types import Understanding
from app.models.mask import BoolImage, Mask
from app.models.regions import GradeBand, PageSize
from app.paths import FIGURES_DIR, JOBS_DB
from app.pipeline import (
    s0_ingest,
    s1_understand,
    s2_ground,
    s2_points,
    s3_reconcile,
    s4_layout,
    s5_render,
)
from app.pipeline.cache import FigureCache, code_digest, load_mask, save_mask, stage_key
from app.pipeline.edits import (
    Edit,
    EditError,
    EditStore,
    added_names,
    annotations,
    apply_edits,
    edits_digest,
    outlines,
    outlines_digest,
)
from app.pipeline.jobs import JobOptions, JobRecord, JobStore, StageOutcome, StageRun
from app.pipeline.outlines import keep as keep_outline
from app.pipeline.outlines import with_outlines
from app.pipeline.s2_types import Grounded
from app.prompts import PROMPTS_DIR, load_prompt

log = logging.getLogger(__name__)

__all__ = ["STAGES", "JobOptions", "NotReadyError", "Runner"]

STAGES = ("s0", "s1", "s2", "s3", "s4", "s5")
_CONSUMES: dict[str, tuple[str, ...]] = {
    "s1": ("s0",),
    "s2": ("s0", "s1"),
    "s3": ("s0", "s1", "s2"),  # S1 for the groups, which are never drawn
    "s4": ("s0", "s1", "s2", "s3"),  # S2 for the silhouette and the merge proposals
    "s5": ("s0", "s1", "s2", "s3", "s4"),  # S2 and S3 for the parts left to the teacher
}
_LOAD: dict[str, Callable[[Path], Any]] = {
    "s0": s0_ingest.load,
    "s1": s1_understand.load,
    "s2": s2_ground.load,
    "s3": s3_reconcile.load,
    "s4": s4_layout.load,
    "s5": s5_render.load,
}
_SAVE: dict[str, Callable[[Any, Path], None]] = {
    "s1": s1_understand.save,
    "s2": s2_ground.save,
    "s3": s3_reconcile.save,
    "s4": s4_layout.save,
    "s5": s5_render.save,
}
_ADDED = "added"  # cache stage for SAM answers to parts a teacher adds by name
_OUTLINE = "outline"  # cache stage for SAM answers to a teacher's points (Fix outline)
Point = tuple[int, int]
_META_STAGES = ("s1", "s2")  # stages whose cached output spares Meta calls
_MS_PER_S = 1000
_ERROR_CODES: dict[type[Exception], str] = {
    MockFixtureMissingError: "no_recording",
    BudgetExceededError: "budget",
    BrailleUnavailableError: "braille_unavailable",
    EditError: "edit_conflict",
}


class NotReadyError(Exception):
    """The figure has not been through the stages this needs."""


class _Walk:
    """One pass along the key chain for a job: keys, verified digests and loaded outputs."""

    def __init__(self, cache: FigureCache) -> None:
        self.cache = cache
        self.keys: dict[str, str] = {}
        self.digests: dict[str, str] = {}
        self.values: dict[str, Any] = {}

    async def value(self, stage: str) -> Any:
        if stage not in self.values:
            entry = self.cache.dir(stage, self.keys[stage])
            self.values[stage] = await asyncio.to_thread(_LOAD[stage], entry)
        return self.values[stage]


class Runner:
    def __init__(  # noqa: PLR0913  keyword-only dependencies, each one injected by tests
        self,
        *,
        client: MetaClient,
        rules: TactileRules,
        explore: ExploreConfig,
        translator: Translator,
        jobs: JobStore,
        edits: EditStore,
        figures_dir: Path = FIGURES_DIR,
        prompts_dir: Path = PROMPTS_DIR,
        ledger: Ledger | None = None,
    ) -> None:
        self.client = client
        self.ledger = ledger  # given in live mode: a cache hit that spares a Meta call is logged
        self.rules = rules
        self.explore = explore
        self.translator = translator
        self.jobs = jobs
        self.edits = edits
        self.figures_dir = figures_dir
        self.s1_prompt = load_prompt(s1_understand.PROMPT, prompts_dir)
        self.s1_locate = load_prompt(s1_understand.LOCATE_PROMPT, prompts_dir)
        self.s2_prompt = load_prompt(s2_ground.PROMPT, prompts_dir)

    # Keys

    def _inputs(
        self, stage: str, options: JobOptions, edits: str, outlined: str = ""
    ) -> dict[str, object]:
        meta = self.rules.meta
        if stage == "s1":
            return {
                "client": self.client.cache_tag,
                "prompt": self.s1_prompt.digest,
                "locate": self.s1_locate.digest,
                "schema": s1_understand.SCHEMA_DIGEST,
                "effort": SPARK_EFFORT,
                "max_parts": meta.max_parts,
                # The locate call plans for the reader and the printed size.
                "options": options.model_dump(mode="json"),
                "spacing": self.rules.spacing.model_dump(mode="json"),
                "page": self.rules.page.model_dump(mode="json"),
            }
        sam = {
            "client": self.client.cache_tag,
            "prompt": self.s2_prompt.digest,
            "schema": s2_ground.SCHEMA_DIGEST,
        }
        if stage == "s2":
            return {
                **sam,
                "text_phrase": meta.text_phrase,
                "points": s2_points.SETTINGS,
                "job_calls": meta.job_calls.model_dump(mode="json"),  # the cap decides retries
                "fill_delta": self.rules.layout.color_group_max_delta,
                "speck_mm2": self.rules.reconcile.speck_max_area_mm2,
                "page": self.rules.page.model_dump(mode="json"),
            }
        free: dict[str, object] = {
            "code": code_digest(),
            "rules": self.rules.model_dump(mode="json"),
            "explore": self.explore.model_dump(mode="json"),
            "options": options.model_dump(mode="json"),
        }
        if stage == "s3":
            return {**free, **sam, "outlines": outlined}  # a teacher's outline is a SAM call
        if stage == "s4":
            return {**free, **sam, "edits": edits}  # an added part is a SAM call
        if stage == "s5":
            return {**free, "edits": edits}
        return free

    def _key(self, walk: _Walk, stage: str, options: JobOptions, edits: str, outlined: str) -> str:
        previous = walk.keys[STAGES[STAGES.index(stage) - 1]]
        upstream = {m: walk.digests[m] for m in _CONSUMES[stage]}
        inputs = self._inputs(stage, options, edits, outlined)
        return stage_key(stage, previous, upstream=upstream, **inputs)

    @staticmethod
    def _key0(figure_id: str) -> str:
        return stage_key("s0", "", figure_id=figure_id)

    # Jobs

    def output_dir(self, job: JobRecord) -> Path | None:
        """Where a finished job's tactile.svg, print.pdf, regions.json and report.json are."""
        if job.result_key is None:
            return None
        return FigureCache(self.figures_dir, job.figure_id).dir("s5", job.result_key)

    def source_image(self, figure_id: str) -> Path:
        """S0's normalized image of the figure, which every job of it starts from."""
        cache = FigureCache(self.figures_dir, figure_id)
        return cache.dir("s0", self._key0(figure_id)) / s0_ingest.IMAGE_FILE

    def ingest(self, data: bytes, page_index: int) -> tuple[s0_ingest.Ingested, StageRun]:
        """S0, saved to the cache. A bad upload raises IngestError."""
        t0 = time.perf_counter()
        ing = s0_ingest.ingest(data, page_index, self.rules.pipeline)
        cache = FigureCache(self.figures_dir, ing.figure_id)
        key = self._key0(ing.figure_id)
        hit = cache.digest("s0", key) is not None
        if not hit:
            with cache.write("s0", key) as out:
                s0_ingest.save(ing, out)
        return ing, _stage_run("s0", "cached" if hit else "ran", t0)

    def create_job(
        self, figure_id: str, options: JobOptions, edit_version: int, s0: StageRun | None = None
    ) -> JobRecord:
        job = self.jobs.create(figure_id, options, edit_version)
        if s0 is not None:
            self.jobs.record_stage(job.id, s0)
            _log_stage(job.id, s0)
        return self.jobs.must_get(job.id)

    def submit(self, data: bytes, page_index: int, options: JobOptions) -> JobRecord:
        ing, s0 = self.ingest(data, page_index)
        return self.create_job(ing.figure_id, options, self.edits.version(ing.figure_id), s0)

    async def run(self, job_id: str) -> JobRecord:
        job = self.jobs.must_get(job_id)
        client = self.client.for_job()  # live: the call cap counts per job
        stage = "s0"
        try:
            edits = self.edits.list(job.figure_id, job.edit_version)
            t0 = time.perf_counter()
            walk = await self._start(job)
            if not any(s.stage == "s0" for s in job.stages):
                self._record(job.id, "s0", "cached", t0)
            for stage in STAGES[1:]:
                await self._step(walk, stage, job, edits, client)
                if stage == "s1":
                    u: Understanding = await walk.value("s1")
                    if u.verdict == "describe_only":
                        self.jobs.finish(job.id, "describe_only")
                        return self.jobs.must_get(job.id)
            self.jobs.finish(job.id, "done", result_key=walk.keys["s5"])
        except Exception as exc:
            code = next((c for t, c in _ERROR_CODES.items() if isinstance(exc, t)), "stage_failed")
            where = {"job_id": job.id, "stage": stage}
            if code == "stage_failed":
                log.exception("job %s failed at %s", job.id, stage, extra=where)
            else:
                log.warning("job %s failed at %s: %s", job.id, stage, exc, extra=where)
            self.jobs.fail(job.id, stage, code, str(exc) or type(exc).__name__)
        return self.jobs.must_get(job.id)

    async def _start(self, job: JobRecord) -> _Walk:
        return await self._walk_s0(job.figure_id)

    async def _walk_s0(self, figure_id: str) -> _Walk:
        walk = _Walk(FigureCache(self.figures_dir, figure_id))
        walk.keys["s0"] = self._key0(figure_id)
        digest = await asyncio.to_thread(walk.cache.digest, "s0", walk.keys["s0"])
        if digest is None:
            raise NotReadyError("The uploaded figure is missing from the cache. Upload it again.")
        walk.digests["s0"] = digest
        return walk

    def _hit(self, caller: str, describe: str) -> None:
        if self.ledger is None:
            return
        models = self.rules.meta.models
        self.ledger.hit(caller, models.spark if caller == "s1" else models.sam, describe)

    async def _step(
        self, walk: _Walk, stage: str, job: JobRecord, edits: Sequence[Edit], client: MetaClient
    ) -> None:
        t0 = time.perf_counter()
        key = self._key(walk, stage, job.options, edits_digest(edits), outlines_digest(edits))
        walk.keys[stage] = key
        digest = await asyncio.to_thread(walk.cache.digest, stage, key)
        if digest is not None:
            walk.digests[stage] = digest
            self._record(job.id, stage, "cached", t0)
            if stage in _META_STAGES:
                self._hit(stage, f"{stage} stage output, figure {job.figure_id[:12]}")
            return
        self.jobs.set_stage(job.id, stage)
        spent = client.meter.spent_usd
        value = await self._make(walk, stage, job, edits, client)
        with walk.cache.write(stage, key) as out:
            await asyncio.to_thread(_SAVE[stage], value, out)
        digest = await asyncio.to_thread(walk.cache.digest, stage, key)
        if digest is None:
            raise RuntimeError(f"the {stage} cache entry is unreadable right after writing")
        walk.digests[stage] = digest
        walk.values[stage] = value
        self._record(job.id, stage, "ran", t0, client.meter.spent_usd - spent)

    async def _fit(self, walk: _Walk, options: JobOptions) -> PageFit:
        ing: s0_ingest.Ingested = await walk.value("s0")
        h, w = ing.image.shape[:2]
        return fit_to_page(w, h, options.page, self.rules.page)

    async def _make(
        self, walk: _Walk, stage: str, job: JobRecord, edits: Sequence[Edit], client: MetaClient
    ) -> Any:
        v = walk.value
        if stage == "s1":
            ing = await v("s0")
            fit = await self._fit(walk, job.options)
            sheet = s1_understand.sheet_context(ing, fit, job.options.grade_band, self.rules)
            return await s1_understand.understand(
                client, ing, self.s1_prompt, self.s1_locate, sheet, self.rules
            )
        if stage == "s2":
            return await s2_ground.ground(
                client, await v("s0"), await v("s1"), self.s2_prompt, self.rules
            )
        if stage == "s3":
            fit = await self._fit(walk, job.options)
            grounded = await self._grounded(walk, edits, client)
            return await asyncio.to_thread(
                s3_reconcile.reconcile_masks, grounded, fit, self.rules.reconcile
            )
        if stage == "s4":
            fit = await self._fit(walk, job.options)
            parts = await self._edited_parts(walk, edits, client)
            rec: Reconciled = await v("s3")
            u: Understanding = await v("s1")
            plan = s4_layout.sheet_plan(u, await v("s2"), rec.parts, parts)
            return await asyncio.to_thread(
                s4_layout.layout,
                parts,
                await v("s0"),
                u,
                fit,
                job.options.grade_band,
                self.rules,
                self.explore.earcons,
                self.translator,
                sheet_plan=plan,
            )
        fit = await self._fit(walk, job.options)
        grounded = await self._grounded(walk, edits, client)  # outlines come from the cache
        teacher = await asyncio.to_thread(
            s5_render.teacher_info, grounded, await v("s3"), fit, self.rules
        )
        return await asyncio.to_thread(
            s5_render.render,
            await v("s4"),
            await v("s1"),
            job.figure_id,
            annotations(edits),
            self.rules,
            self.explore,
            teacher,
        )

    # Teacher edits

    async def _edited_parts(
        self, walk: _Walk, edits: Sequence[Edit], client: MetaClient
    ) -> list[ReconciledPart]:
        rec: Reconciled = await walk.value("s3")
        added = await self._added(walk, added_names(edits), client)
        return apply_edits(rec.parts, edits, added, self.rules.reconcile.contain_fraction)

    async def _added(
        self, walk: _Walk, names: Sequence[str], client: MetaClient
    ) -> dict[str, list[Mask]]:
        """SAM's answer for each part a teacher added by name, cached like S2's answers."""
        return {name: (await self._added_one(walk, name, client))[0] for name in names}

    async def _added_one(
        self, walk: _Walk, name: str, client: MetaClient
    ) -> tuple[list[Mask], StageOutcome]:
        sam = {
            "client": self.client.cache_tag,
            "prompt": self.s2_prompt.digest,
            "schema": s2_ground.SCHEMA_DIGEST,
            "text_phrase": self.rules.meta.text_phrase,
        }
        key = stage_key(
            _ADDED, walk.keys["s0"], upstream={"s0": walk.digests["s0"]}, name=name, **sam
        )
        if await asyncio.to_thread(walk.cache.digest, _ADDED, key) is not None:
            found = await asyncio.to_thread(s2_ground.load, walk.cache.dir(_ADDED, key))
            self._hit(_ADDED, f"part by name, figure {walk.cache.root.name[:12]}, phrase: {name}")
            return found.parts, "cached"
        ing: s0_ingest.Ingested = await walk.value("s0")
        masks = await client.segment(ing.image, ing.figure_id, name, self.s2_prompt)
        found = s2_ground.Grounded(parts=masks, text=[])
        with walk.cache.write(_ADDED, key) as entry:
            await asyncio.to_thread(s2_ground.save, found, entry)
        return found.parts, "ran"

    async def find_part(self, figure_id: str, name: str) -> tuple[list[Mask], StageOutcome]:
        """SAM's answer for one part name on the figure's S0 image, through the same cache a
        part added by a teacher uses. Says whether SAM ran or the cache answered."""
        return await self._added_one(await self._walk_s0(figure_id), name, self.client.for_job())

    async def check_edits(self, job: JobRecord, edits: Sequence[Edit]) -> None:
        """Replays the edits on the S3 parts the job used. Raises EditError when one cannot
        be applied, and NotReadyError when the job has not been through S3."""
        walk = await self._through_s3(job)
        await self._edited_parts(walk, edits, self.client.for_job())

    async def _through_s3(self, job: JobRecord) -> _Walk:
        """The walk to the job's own S3 output, with the outlines it ran with."""
        walk = await self._start(job)
        outlined = outlines_digest(self.edits.list(job.figure_id, job.edit_version))
        for stage in ("s1", "s2", "s3"):
            walk.keys[stage] = self._key(walk, stage, job.options, "", outlined)
            digest = await asyncio.to_thread(walk.cache.digest, stage, walk.keys[stage])
            if digest is None:
                raise NotReadyError("The figure is still being processed. Try again shortly.")
            walk.digests[stage] = digest
        return walk

    async def fix_context(
        self, job: JobRecord
    ) -> tuple[s0_ingest.Ingested, Understanding, Grounded, Reconciled]:
        """What Fix outline needs from a finished job: the image, S1, S2 with the job's
        outlines applied, and S3."""
        walk = await self._through_s3(job)
        g = await self._grounded(walk, self.edits.list(job.figure_id, job.edit_version), None)
        return await walk.value("s0"), await walk.value("s1"), g, await walk.value("s3")

    async def outline_mask(
        self, figure_id: str, part: str, positive: Sequence[Point], negative: Sequence[Point],
        client: MetaClient,
    ) -> tuple[BoolImage, StageOutcome]:  # fmt: skip
        """SAM's mask for a teacher's points, cached by the points: a preview pays for the
        call, and accepting it does not pay again."""
        return await self._outline_mask(
            await self._walk_s0(figure_id), part, positive, negative, client
        )

    async def _outline_mask(
        self, walk: _Walk, part: str, positive: Sequence[Point], negative: Sequence[Point],
        client: MetaClient | None,
    ) -> tuple[BoolImage, StageOutcome]:  # fmt: skip
        key = stage_key(
            _OUTLINE,
            walk.keys["s0"],
            upstream={"s0": walk.digests["s0"]},
            positive=[list(p) for p in positive],
            negative=[list(p) for p in negative],
            client=self.client.cache_tag,
            prompt=self.s2_prompt.digest,
            floor=self.rules.reconcile.speck_max_area_mm2,
        )
        entry = walk.cache.dir(_OUTLINE, key)
        if await asyncio.to_thread(walk.cache.digest, _OUTLINE, key) is not None:
            self._hit("fix", f"outline, figure {walk.cache.root.name[:12]}, part: {part}")
            return await asyncio.to_thread(load_mask, entry / "mask.png"), "cached"
        if client is None:
            raise NotReadyError(f"The outline for {part} is not in the cache.")
        ing: s0_ingest.Ingested = await walk.value("s0")
        answer = await client.segment_points(
            ing.image, ing.figure_id, part, [(positive, negative)], self.s2_prompt, kind="fix"
        )
        mask = np.zeros(ing.image.shape[:2], bool)
        for a in answer:
            mask |= a.mask
        kept = keep_outline(mask, positive, s2_points.speck_floor_px(ing.image, self.rules))
        with walk.cache.write(_OUTLINE, key) as out:
            await asyncio.to_thread(save_mask, out / "mask.png", kept)
        return kept, "ran"

    async def _grounded(
        self, walk: _Walk, edits: Sequence[Edit], client: MetaClient | None
    ) -> Grounded:
        """S2's output with the teacher's outlines in place, less S1's groups."""
        g = s3_reconcile.without_groups(await walk.value("s2"), await walk.value("s1"))
        outlined = []
        for e in outlines(edits):
            pos = [(x, y) for x, y in e.positive]
            neg = [(x, y) for x, y in e.negative]
            mask, _ = await self._outline_mask(walk, e.part, pos, neg, client)
            if mask.any():
                outlined.append((e.part, mask))
        return with_outlines(g, outlined) if outlined else g

    def _record(
        self, job_id: str, stage: str, outcome: StageOutcome, t0: float, cost_usd: float = 0.0
    ) -> None:
        run = _stage_run(stage, outcome, t0, cost_usd)
        self.jobs.record_stage(job_id, run)
        _log_stage(job_id, run)


def _log_stage(job_id: str, run: StageRun) -> None:
    fields = {"job_id": job_id, "stage": run.stage, "outcome": run.outcome,
              "ms": round(run.ms, 1), "cost_usd": run.cost_usd}  # fmt: skip
    log.info("job %s %s %s in %.0f ms, $%.4f", job_id[:8], run.stage, run.outcome, run.ms,
             run.cost_usd, extra=fields)  # fmt: skip


def _stage_run(stage: str, outcome: StageOutcome, t0: float, cost_usd: float = 0.0) -> StageRun:
    ms = (time.perf_counter() - t0) * _MS_PER_S
    return StageRun(stage=stage, outcome=outcome, ms=ms, cost_usd=cost_usd)


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
        edits=EditStore(JOBS_DB),
    )
    options = JobOptions(page=args.page, grade_band=args.grade)
    job = runner.submit(args.file.read_bytes(), args.page_index, options)
    job = asyncio.run(runner.run(job.id))
    print(f"{job.status}: {runner.output_dir(job) or job.error_message}")


if __name__ == "__main__":
    main()
