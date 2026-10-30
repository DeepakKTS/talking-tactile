"""The pipeline runner in mock mode: S0 to S5 in order, the per-stage cache, and the SQLite
job records. The cache tests each change one thing a stage depends on and check that the
stage, and everything after it, runs again instead of serving a stale hit."""

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
from app.meta.types import SheetContext, Understanding
from app.models.image import RGB
from app.models.mask import Mask
from app.paths import FIXTURES_DIR, REGIONS_SCHEMA
from app.pipeline.cache import FigureCache
from app.pipeline.edits import EditStore
from app.pipeline.jobs import JobRecord, JobStore
from app.pipeline.runner import STAGES, JobOptions, Runner
from app.pipeline.s0_ingest import IngestError
from app.prompts import PROMPTS_DIR, Prompt
from app.synthetic.generate import OUT_DIR as SYNTHETIC_DIR

RULES = load_tactile_rules()
EXPLORE = load_explore()
SYNTHETIC_PNG = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()
OUTPUTS = ("tactile.svg", "print.pdf", "regions.json", "report.json")


def make_runner(
    root: Path, client: MockMetaClient | None = None, prompts: Path = PROMPTS_DIR
) -> Runner:
    return Runner(
        client=client or MockMetaClient(RULES.meta),
        rules=RULES,
        explore=EXPLORE,
        translator=Translator(RULES.braille),
        jobs=JobStore(root / "jobs.sqlite"),
        edits=EditStore(root / "jobs.sqlite"),
        figures_dir=root / "figures",
        prompts_dir=prompts,
    )


def submit_and_run(runner: Runner, options: JobOptions | None = None) -> JobRecord:
    job = runner.submit(SYNTHETIC_PNG, 0, options or JobOptions(grade_band="k5"))
    return asyncio.run(runner.run(job.id))


def outcomes(job: JobRecord) -> dict[str, str]:
    return {s.stage: s.outcome for s in job.stages}


def ran_from(stage: str | None) -> dict[str, str]:
    """Every stage before `stage` cached, it and every later one ran. None: all cached."""
    cut = len(STAGES) if stage is None else STAGES.index(stage)
    return {s: "cached" if i < cut else "ran" for i, s in enumerate(STAGES)}


def regions_of(runner: Runner, job: JobRecord) -> dict[str, object]:
    out = runner.output_dir(job)
    assert out is not None
    regions: dict[str, object] = json.loads((out / "regions.json").read_text(encoding="utf-8"))
    return regions


@pytest.fixture(scope="module")
def first(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, JobRecord]:
    root = tmp_path_factory.mktemp("pipeline")
    return root, submit_and_run(make_runner(root))


@pytest.fixture
def warm(first: tuple[Path, JobRecord], tmp_path: Path) -> Path:
    """A copy of the cache and job database after one full run, for tests that change it."""
    shutil.copytree(first[0], tmp_path, dirs_exist_ok=True)
    return tmp_path


def copy_prompts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    prompts = tmp_path_factory.mktemp("prompts")
    shutil.copytree(PROMPTS_DIR, prompts, dirs_exist_ok=True)
    return prompts


def test_a_fresh_upload_runs_every_stage(first: tuple[Path, JobRecord]) -> None:
    root, job = first
    assert job.status == "done", job.error_message
    assert outcomes(job) == ran_from("s0")
    assert [s.stage for s in job.stages] == list(STAGES)
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
    assert outcomes(job) == ran_from(None)
    assert client.calls == []
    assert runner.output_dir(job) == runner.output_dir(first[1])


def test_new_options_plan_again_from_s1(warm: Path) -> None:
    """S1 plans the parts for the reader and the printed size, so a new grade band or page
    runs S1 onward."""
    client = MockMetaClient(RULES.meta)
    job = submit_and_run(make_runner(warm, client), JobOptions(grade_band="9_12"))
    assert job.status == "done"
    assert outcomes(job) == ran_from("s1")
    assert [c.call for c in client.calls][:1] == ["understand"]


def test_a_figure_with_no_grade_band_leaves_it_out(warm: Path) -> None:
    runner = make_runner(warm)
    job = submit_and_run(runner, JobOptions())
    assert job.status == "done", job.error_message
    assert "grade_band" not in regions_of(runner, job)


def test_a_missing_render_runs_from_the_saved_layout(
    warm: Path, first: tuple[Path, JobRecord]
) -> None:
    runner = make_runner(warm)
    old = runner.output_dir(first[1])
    assert old is not None
    before = {name: (old / name).read_bytes() for name in ("tactile.svg", "regions.json")}
    shutil.rmtree(old)
    job = submit_and_run(runner)
    assert outcomes(job) == ran_from("s5")
    new = runner.output_dir(job)
    assert new is not None
    for name, data in before.items():
        assert (new / name).read_bytes() == data, name


def test_a_missing_layout_runs_from_the_saved_masks(
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
    assert outcomes(job) == ran_from("s3")
    new = runner.output_dir(job)
    assert new is not None
    assert (new / "regions.json").read_bytes() == regions


def test_a_damaged_cache_entry_is_rebuilt(warm: Path, first: tuple[Path, JobRecord]) -> None:
    runner = make_runner(warm)
    old = runner.output_dir(first[1])
    assert old is not None
    good = (old / "regions.json").read_bytes()
    (old / "regions.json").write_text("{}", encoding="utf-8")  # valid JSON, wrong content
    job = submit_and_run(runner)
    assert job.status == "done"
    assert outcomes(job) == ran_from("s5")
    assert (old / "regions.json").read_bytes() == good


# Each of these passes only if the key covers the thing changed; a key without it serves
# the stale entry and the outcomes come back all cached.


def test_editing_the_s1_prompt_runs_s1_again(
    warm: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    prompts = copy_prompts(tmp_path_factory)
    s1 = prompts / "s1_understand.v1.json"
    s1.write_text(s1.read_text(encoding="utf-8").replace("You read", "You  read", 1), "utf-8")
    client = MockMetaClient(RULES.meta)
    job = submit_and_run(make_runner(warm, client, prompts))
    assert outcomes(job) == ran_from("s1")
    assert client.calls[0].call == "understand"
    again = submit_and_run(make_runner(warm, MockMetaClient(RULES.meta), prompts))
    assert outcomes(again) == ran_from(None)


def test_editing_the_s2_request_runs_s2_and_not_s1(
    warm: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    prompts = copy_prompts(tmp_path_factory)
    s2 = prompts / "s2_ground.v1.json"
    s2.write_text(s2.read_text(encoding="utf-8").replace('"true"', '"false"'), "utf-8")
    job = submit_and_run(make_runner(warm, MockMetaClient(RULES.meta), prompts))
    assert outcomes(job) == ran_from("s2")


class _Retitled(MockMetaClient):
    async def understand(
        self, image: RGB, figure_id: str, prompt: Prompt, locate: Prompt, sheet: SheetContext
    ) -> Understanding:
        u = await super().understand(image, figure_id, prompt, locate, sheet)
        return u.model_copy(update={"title": "A different title"})


def test_a_new_s1_answer_runs_every_later_stage(warm: Path, first: tuple[Path, JobRecord]) -> None:
    """S1 is made again under the same key (its entry is gone) and answers differently. The
    later keys follow S1's output, so nothing downstream is served stale."""
    shutil.rmtree(warm / "figures" / first[1].figure_id / "s1")
    runner = make_runner(warm, _Retitled(RULES.meta))
    job = submit_and_run(runner)
    assert outcomes(job) == ran_from("s1")
    assert regions_of(runner, job)["title"] == "A different title"


def test_editing_a_mock_fixture_runs_the_meta_stages_again(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    shutil.copytree(SYNTHETIC_DIR, fixtures)
    first = submit_and_run(make_runner(tmp_path, MockMetaClient(RULES.meta, fixtures)))
    assert first.status == "done"
    truth = fixtures / "truth.json"
    obj = json.loads(truth.read_text(encoding="utf-8"))
    obj["summary"] = "An edited summary."
    truth.write_text(json.dumps(obj, indent=1), "utf-8")
    runner = make_runner(tmp_path, MockMetaClient(RULES.meta, fixtures))
    job = submit_and_run(runner)
    assert outcomes(job) == ran_from("s1")
    assert regions_of(runner, job)["summary"] == "An edited summary."


def test_the_cache_refuses_a_figure_id_that_is_not_a_sha256(tmp_path: Path) -> None:
    for bad in ["../" * 3 + "etc", "A" * 64, "a" * 63, "a" * 64 + "/x", "", "..", "a" * 65]:
        with pytest.raises(ValueError, match="64 lowercase hex"):
            FigureCache(tmp_path, bad)
    FigureCache(tmp_path, "0" * 64)


# Jobs


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
    assert store.find_live("f" * 64, JobOptions(), 0) == a
    assert store.find_live("f" * 64, JobOptions(), 1) is None


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
    async def understand(
        self, image: RGB, figure_id: str, prompt: Prompt, locate: Prompt, sheet: SheetContext
    ) -> Understanding:
        u = await super().understand(image, figure_id, prompt, locate, sheet)
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

    async def segment(self, image: RGB, figure_id: str, phrase: str, prompt: Prompt) -> list[Mask]:
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return await super().segment(image, figure_id, phrase, prompt)


def test_segmenting_keeps_to_the_sam_concurrency(tmp_path: Path) -> None:
    client = _Counting()
    job = submit_and_run(make_runner(tmp_path, client))
    assert job.status == "done"
    phrases = [c.phrase for c in client.calls if c.call == "segment"]
    assert RULES.meta.text_phrase in phrases
    assert len(phrases) == len(set(phrases)) > RULES.meta.sam_concurrency
    assert client.most == RULES.meta.sam_concurrency
