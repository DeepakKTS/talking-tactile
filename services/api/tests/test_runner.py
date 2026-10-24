"""The pipeline runner in mock mode: S0 to S5 in order, the per-stage cache, and the SQLite
job records."""

import asyncio
import json
import shutil
from pathlib import Path

import cv2
import jsonschema
import numpy as np
import pytest

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.meta.mock import MockMetaClient
from app.meta.types import Understanding
from app.models.image import RGB
from app.models.mask import Mask
from app.paths import FIXTURES_DIR, REGIONS_SCHEMA
from app.pipeline.jobs import JobRecord, JobStore
from app.pipeline.runner import STAGES, JobOptions, Runner
from app.pipeline.s0_ingest import IngestError

RULES = load_tactile_rules()
EXPLORE = load_explore()
SYNTHETIC_PNG = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()
OUTPUTS = ("tactile.svg", "print.pdf", "regions.json", "report.json")


def make_runner(root: Path, client: MockMetaClient | None = None) -> Runner:
    return Runner(
        client=client or MockMetaClient(RULES.meta),
        rules=RULES,
        explore=EXPLORE,
        translator=Translator(RULES.braille),
        jobs=JobStore(root / "jobs.sqlite"),
        figures_dir=root / "figures",
    )


def submit_and_run(runner: Runner, options: JobOptions | None = None) -> JobRecord:
    job = runner.submit(SYNTHETIC_PNG, 0, options or JobOptions(grade_band="k5"))
    return asyncio.run(runner.run(job.id))


def outcomes(job: JobRecord) -> dict[str, str]:
    return {s.stage: s.outcome for s in job.stages}


@pytest.fixture(scope="module")
def first(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, JobRecord]:
    root = tmp_path_factory.mktemp("pipeline")
    return root, submit_and_run(make_runner(root))


@pytest.fixture
def warm(first: tuple[Path, JobRecord], tmp_path: Path) -> Path:
    """A copy of the cache and job database after one full run, for tests that change it."""
    shutil.copytree(first[0], tmp_path, dirs_exist_ok=True)
    return tmp_path


def test_a_fresh_upload_runs_every_stage(first: tuple[Path, JobRecord]) -> None:
    root, job = first
    assert job.status == "done", job.error_message
    assert [s.stage for s in job.stages] == list(STAGES)
    assert set(outcomes(job).values()) == {"ran"}
    assert all(s.ms > 0 for s in job.stages)
    out = make_runner(root).output_dir(job)
    assert out is not None
    for name in OUTPUTS:
        assert (out / name).stat().st_size > 0
    regions = json.loads((out / "regions.json").read_text(encoding="utf-8"))
    jsonschema.validate(regions, json.loads(REGIONS_SCHEMA.read_text(encoding="utf-8")))
    assert regions["figure_id"] == job.figure_id
    assert regions["grade_band"] == "k5"
    assert json.loads((out / "report.json").read_text(encoding="utf-8")) == []


def test_the_same_upload_again_costs_no_meta_calls(
    warm: Path, first: tuple[Path, JobRecord]
) -> None:
    client = MockMetaClient(RULES.meta)
    runner = make_runner(warm, client)
    job = submit_and_run(runner)
    assert job.status == "done"
    assert job.figure_id == first[1].figure_id
    assert outcomes(job) == {
        "s0": "cached",
        "s1": "cached",
        "s2": "skipped",
        "s3": "skipped",
        "s4": "skipped",
        "s5": "cached",
    }
    assert client.calls == []
    assert runner.output_dir(job) == runner.output_dir(first[1])


def test_new_options_reuse_the_meta_stages(warm: Path) -> None:
    client = MockMetaClient(RULES.meta)
    job = submit_and_run(make_runner(warm, client), JobOptions(grade_band="9_12"))
    assert job.status == "done"
    assert outcomes(job)["s1"] == "cached"
    assert outcomes(job)["s2"] == "cached"
    assert outcomes(job)["s5"] == "ran"
    assert client.calls == []


def test_a_missing_render_resumes_from_the_saved_layout(
    warm: Path, first: tuple[Path, JobRecord]
) -> None:
    runner = make_runner(warm)
    old = runner.output_dir(first[1])
    assert old is not None
    before = {name: (old / name).read_bytes() for name in ("tactile.svg", "regions.json")}
    shutil.rmtree(old)
    job = submit_and_run(runner)
    assert outcomes(job)["s4"] == "cached"
    assert outcomes(job)["s5"] == "ran"
    new = runner.output_dir(job)
    assert new is not None
    for name, data in before.items():
        assert (new / name).read_bytes() == data, name


def test_a_missing_layout_resumes_from_the_saved_masks(
    warm: Path, first: tuple[Path, JobRecord]
) -> None:
    runner = make_runner(warm)
    old = runner.output_dir(first[1])
    assert old is not None
    regions = (old / "regions.json").read_bytes()
    figure = warm / "figures" / first[1].figure_id
    for stage in ("s3", "s4", "s5"):
        shutil.rmtree(figure / stage)
    job = submit_and_run(runner)
    assert outcomes(job) == {
        "s0": "cached",
        "s1": "cached",
        "s2": "cached",
        "s3": "ran",
        "s4": "ran",
        "s5": "ran",
    }
    new = runner.output_dir(job)
    assert new is not None
    assert (new / "regions.json").read_bytes() == regions


def test_a_damaged_cache_entry_is_rebuilt(warm: Path, first: tuple[Path, JobRecord]) -> None:
    runner = make_runner(warm)
    old = runner.output_dir(first[1])
    assert old is not None
    (old / "regions.json").write_text("{not json", encoding="utf-8")
    job = submit_and_run(runner)
    assert job.status == "done"
    assert outcomes(job)["s5"] == "ran"
    assert json.loads((old / "regions.json").read_text(encoding="utf-8"))["figure_id"]


def test_jobs_survive_a_restart(first: tuple[Path, JobRecord]) -> None:
    root, job = first
    store = JobStore(root / "jobs.sqlite")
    assert store.get(job.id) == job
    assert store.latest_for_figure(job.figure_id) is not None
    assert store.get("no-such-job") is None


def test_the_latest_job_for_a_figure_is_the_newest(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    a = store.create("f" * 64, JobOptions())
    b = store.create("f" * 64, JobOptions(grade_band="k5"))
    latest = store.latest_for_figure("f" * 64)
    assert latest is not None
    assert latest.id == b.id != a.id
    assert latest.status == "queued"


def test_a_bad_upload_makes_no_job(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(IngestError) as caught:
        runner.submit(b"GIF89a not supported", 0, JobOptions())
    assert caught.value.code == "unsupported_type"
    assert not (tmp_path / "figures").exists() or not any((tmp_path / "figures").iterdir())


def _sharp_figure() -> bytes:
    img = np.full((600, 800, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (400, 400), (200, 60, 60), -1)
    cv2.circle(img, (600, 300), 120, (60, 60, 200), -1)
    ok, png = cv2.imencode(".png", img)
    assert ok
    return png.tobytes()


def test_an_image_with_no_recording_fails_at_s1(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    job = runner.submit(_sharp_figure(), 0, JobOptions())
    done = asyncio.run(runner.run(job.id))
    assert done.status == "failed"
    assert done.stage == "s1"
    assert done.error_code == "no_recording"
    assert outcomes(done) == {"s0": "ran"}
    assert runner.output_dir(done) is None


class _DescribeOnly(MockMetaClient):
    async def understand(self, image: RGB, figure_id: str) -> Understanding:
        u = await super().understand(image, figure_id)
        return u.model_copy(update={"verdict": "describe_only"})


def test_describe_only_stops_before_segmenting(tmp_path: Path) -> None:
    client = _DescribeOnly(RULES.meta)
    job = submit_and_run(make_runner(tmp_path, client))
    assert job.status == "describe_only"
    assert outcomes(job) == {"s0": "ran", "s1": "ran"}
    assert [c.call for c in client.calls] == ["understand"]


class _Counting(MockMetaClient):
    def __init__(self) -> None:
        super().__init__(RULES.meta)
        self.in_flight = 0
        self.most = 0

    async def segment(self, image: RGB, figure_id: str, phrase: str) -> list[Mask]:
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return await super().segment(image, figure_id, phrase)


def test_segmenting_keeps_to_the_sam_concurrency(tmp_path: Path) -> None:
    client = _Counting()
    job = submit_and_run(make_runner(tmp_path, client))
    assert job.status == "done"
    phrases = [c.phrase for c in client.calls if c.call == "segment"]
    assert RULES.meta.text_phrase in phrases
    assert len(phrases) == len(set(phrases)) > RULES.meta.sam_concurrency
    assert client.most == RULES.meta.sam_concurrency
