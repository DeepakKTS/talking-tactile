"""Job records: one row per pipeline run, one row per stage with its time, cost and whether
it ran or came from the cache."""

import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import GradeBand, PageSize
from app.pipeline import db

JobStatus = Literal["queued", "running", "done", "failed", "describe_only"]
StageOutcome = Literal["ran", "cached"]


class JobOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page: PageSize = "letter"
    grade_band: GradeBand | None = None


class StageRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    outcome: StageOutcome
    ms: float
    cost_usd: float


class JobRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    figure_id: str
    status: JobStatus
    stage: str | None  # the stage running now, or the one that failed
    options: JobOptions
    edit_version: int  # teacher edits 1 to edit_version are applied; 0 is none
    result_key: str | None  # the S5 cache key once the job is done
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    stages: list[StageRun]
    pipeline: str | None = None  # Runner.pipeline_version when it was made; None before Oct 30


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        db.init(path)

    def create(
        self, figure_id: str, options: JobOptions, edit_version: int = 0, pipeline: str = ""
    ) -> JobRecord:
        job_id, now = uuid.uuid4().hex, db.now()
        with db.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO jobs (id, figure_id, status, options, edit_version, created_at, "
                "updated_at, pipeline) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)",
                (job_id, figure_id, options.model_dump_json(), edit_version, now, now, pipeline),
            )
        return self.must_get(job_id)

    def record_stage(self, job_id: str, run: StageRun) -> None:
        with db.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stage_runs (job_id, stage, outcome, ms, cost_usd, seq) "
                "VALUES (?, ?, ?, ?, ?, (SELECT COUNT(*) FROM stage_runs WHERE job_id = ?))",
                (job_id, run.stage, run.outcome, run.ms, run.cost_usd, job_id),
            )

    def set_stage(self, job_id: str, stage: str) -> None:
        self._update(job_id, status="running", stage=stage)

    def finish(self, job_id: str, status: JobStatus, result_key: str | None = None) -> None:
        self._update(job_id, status=status, stage=None, result_key=result_key)

    def fail(self, job_id: str, stage: str | None, code: str, message: str) -> None:
        self._update(job_id, status="failed", stage=stage, error_code=code, error_message=message)

    def _update(self, job_id: str, **fields: str | None) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)  # names from this module only
        with db.connect(self.path) as conn:
            conn.execute(
                f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?",
                (*fields.values(), db.now(), job_id),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with db.connect(self.path) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            runs = conn.execute(
                "SELECT stage, outcome, ms, cost_usd FROM stage_runs WHERE job_id = ? ORDER BY seq",
                (job_id,),
            ).fetchall()
        fields = dict(row)
        options = JobOptions.model_validate_json(fields.pop("options"))
        return JobRecord(**fields, options=options, stages=[StageRun(**dict(r)) for r in runs])

    def must_get(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"no job {job_id}")
        return job

    def _latest(self, where: str, args: tuple[object, ...]) -> JobRecord | None:
        with db.connect(self.path) as conn:
            row = conn.execute(
                f"SELECT id FROM jobs WHERE {where} ORDER BY rowid DESC LIMIT 1", args
            ).fetchone()
        return None if row is None else self.get(row["id"])

    def latest_for_figure(self, figure_id: str) -> JobRecord | None:
        return self._latest("figure_id = ?", (figure_id,))

    def latest_done(self, figure_id: str, edit_version: int | None = None) -> JobRecord | None:
        if edit_version is None:
            return self._latest("figure_id = ? AND status = 'done'", (figure_id,))
        return self._latest(
            "figure_id = ? AND status = 'done' AND edit_version = ?", (figure_id, edit_version)
        )

    def find_live(
        self, figure_id: str, options: JobOptions, edit_version: int, pipeline: str = ""
    ) -> JobRecord | None:
        """The newest job for this figure, options, edits and pipeline version that has not
        failed: what a repeated upload gets back instead of a new job."""
        return self._latest(
            "figure_id = ? AND options = ? AND edit_version = ? AND pipeline = ? "
            "AND status != 'failed'",
            (figure_id, options.model_dump_json(), edit_version, pipeline),
        )
