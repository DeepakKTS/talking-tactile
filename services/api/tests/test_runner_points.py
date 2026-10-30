"""The pipeline with S1 and S2 by points (live mode's path) on the synthetic figure, with a
fake live client: regions.json v2 carries the flags, a spill is an untouchable suggestion, a
part with no shape is in needs_teacher, and the cache keys cover the new inputs."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from app.meta.client import ObjectMask
from app.meta.cost import CostMeter
from app.meta.types import GridPoint, Instance, PartPhrase, Understanding
from app.models.regions import RegionsFile, check_references
from app.pipeline import s2_points
from app.pipeline.jobs import JobOptions, JobRecord
from app.pipeline.runner import STAGES, Runner
from app.prompts import PROMPTS_DIR
from app.synthetic.load import load_synthetic
from tests.test_runner import RULES, make_runner, outcomes, ran_from, submit_and_run

FIG = load_synthetic()
H, W = FIG.image.shape[:2]
MASKS = {m.label: m.data for m in FIG.truth_masks.values()}
PARENT = {"inner core": "outer chamber"}


def spill() -> np.ndarray:
    """The box around the right chamber and the right lobe, filled: one piece holding both
    parts' points. A spill that is not connected would already go with the piece rule."""
    both = MASKS["right chamber"] | MASKS["right lobe"]
    rows, cols = np.nonzero(both)
    out = np.zeros_like(both)
    out[rows.min() : rows.max() + 1, cols.min() : cols.max() + 1] = True
    return out


SPILL = spill()


def inside_point(phrase: str) -> GridPoint:
    """The pixel deepest inside the part, less its children, on the 0-1000 grid."""
    m = MASKS[phrase].copy()
    for child, parent in PARENT.items():
        if parent == phrase:
            m &= ~MASKS[child]
    d = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(d.argmax()), d.shape)
    return GridPoint(x=int(x) * 1000 // W + 1, y=int(y) * 1000 // H + 1)


class FakeLive:
    """S1 locates every part but the pore; SAM answers with the true mask, except the right
    chamber, whose mask spills over the right lobe on both calls (SPILL)."""

    mode = "live"
    cache_tag = "fake-live"

    def __init__(self) -> None:
        self.meter = CostMeter(RULES.meta)
        self.calls: list[str] = []

    def for_job(self) -> "FakeLive":
        return self

    async def understand(
        self, image: Any, figure_id: str, prompt: Any, locate: Any
    ) -> Understanding:
        self.calls.append("understand")
        parts = []
        for phrase in MASKS:
            if phrase == "pore":
                parts.append(PartPhrase(phrase=phrase, print_label=""))
                continue
            parts.append(
                PartPhrase(
                    phrase=phrase,
                    print_label="",
                    kind="thin" if phrase == "stem" else "area",
                    parent=PARENT.get(phrase, ""),
                    instances=(Instance(where="main", points=(inside_point(phrase),)),),
                )
            )
        await asyncio.sleep(0)
        return Understanding(
            figure_type="labeled_diagram",
            title=FIG.truth.title,
            summary=FIG.truth.summary,
            parts=parts,
            color_carries_meaning=False,
            verdict="make_tactile",
            verdict_reason="test",
            located=True,
        )

    async def segment_points(
        self, image: Any, figure_id: str, part: str, objects: Any, prompt: Any, retry: bool = False
    ) -> list[ObjectMask]:
        self.calls.append(f"{part}{' retry' if retry else ''}")
        mask = MASKS[part]
        if part == "right chamber":
            mask = SPILL
        await asyncio.sleep(0)
        return [ObjectMask(1, 0.9, mask)]

    async def segment(self, *args: Any) -> list[Any]:
        raise AssertionError("no phrase call in points mode")


def run_points(
    root: Path, client: FakeLive | None = None, prompts: Path = PROMPTS_DIR
) -> tuple[Runner, JobRecord]:
    runner = make_runner(root, client or FakeLive(), prompts)  # type: ignore[arg-type]
    return runner, submit_and_run(runner, JobOptions(grade_band="k5"))


@pytest.fixture(scope="module")
def done(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Runner, JobRecord, FakeLive]:
    root = tmp_path_factory.mktemp("points")
    client = FakeLive()
    runner, job = run_points(root, client)
    return root, runner, job, client


def regions(runner: Runner, job: JobRecord) -> RegionsFile:
    out = runner.output_dir(job)
    assert out is not None
    return RegionsFile.from_json_obj(json.loads((out / "regions.json").read_text("utf-8")))


def test_the_job_finishes_and_calls_sam_once_per_located_part_plus_the_retry(
    done: tuple[Path, Runner, JobRecord, FakeLive],
) -> None:
    _, _, job, client = done
    assert job.status == "done", job.error_message
    assert client.calls[0] == "understand"
    assert sorted(client.calls[1:]) == sorted(
        [p for p in MASKS if p != "pore"] + ["right chamber retry"]
    )


def test_regions_json_marks_what_a_student_can_touch(
    done: tuple[Path, Runner, JobRecord, FakeLive],
) -> None:
    _, runner, job, _ = done
    f = regions(runner, job)
    assert f.schema_version == 2 and check_references(f) == []
    touch = {r.label for r in f.regions if r.touchable}
    assert "right chamber" not in touch and {"outer chamber", "inner core", "stem"} <= touch
    (sug,) = [r for r in f.regions if not r.touchable]
    assert sug.label == "right chamber" and sug.id.startswith("s")
    assert sug.flags is not None and sug.flags[0].reason == "spill"
    assert sug.flags[0].detail == "holds points of right lobe after a retry"
    assert sug.neighbors is None and all(
        sug.id not in [n.id for n in r.neighbors or []] for r in f.regions
    )
    stem = next(r for r in f.regions if r.label == "stem")
    assert [fl.reason for fl in stem.flags or []][:1] == ["thin"]
    assert [(t.label, t.reason) for t in f.needs_teacher or []] == [("pore", "no_points")]


def test_the_report_has_no_violation_for_the_undrawn_suggestion(
    done: tuple[Path, Runner, JobRecord, FakeLive],
) -> None:
    _, runner, job, _ = done
    out = runner.output_dir(job)
    assert out is not None
    report = json.loads((out / "report.json").read_text("utf-8"))
    assert [v for v in report if v["rule"] == "svg_ids"] == []


def test_a_new_locate_prompt_runs_s1_and_everything_after(
    done: tuple[Path, Runner, JobRecord, FakeLive], tmp_path: Path
) -> None:
    root = done[0]
    prompts = tmp_path / "prompts"
    shutil.copytree(PROMPTS_DIR, prompts)
    locate = prompts / "s1_locate.v1.json"
    locate.write_text(locate.read_text("utf-8").replace("1 to 3 points", "1 to 2 points"), "utf-8")
    _, job = run_points(root, prompts=prompts)
    assert outcomes(job) == ran_from("s1")


def test_a_new_s2_setting_runs_s2_and_after_but_not_s1(
    done: tuple[Path, Runner, JobRecord, FakeLive], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = done[0]
    monkeypatch.setitem(s2_points.SETTINGS, "method", "arm-a-v2f.test")
    _, job = run_points(root)
    assert outcomes(job) == ran_from("s2")


def test_the_same_job_again_is_served_from_the_cache(
    done: tuple[Path, Runner, JobRecord, FakeLive],
) -> None:
    client = FakeLive()
    _, job = run_points(done[0], client)
    assert outcomes(job) == ran_from(None) and client.calls == []
    assert STAGES[-1] == "s5"
