"""Job records in SQLite: one row per pipeline run, one row per stage with its time, cost and
whether it ran, came from the cache, or was not needed. A connection per call, so the
runner can record from worker threads."""

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import GradeBand, PageSize

JobStatus = Literal["queued", "running", "done", "failed", "describe_only"]
# skipped: a later stage came from the cache, so this one was not needed
StageOutcome = Literal["ran", "cached", "skipped"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  figure_id TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT,
  options TEXT NOT NULL,
  result_key TEXT,
  error_code TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_by_figure ON jobs (figure_id);
CREATE TABLE IF NOT EXISTS stage_runs (
  job_id TEXT NOT NULL REFERENCES jobs (id),
  stage TEXT NOT NULL,
  outcome TEXT NOT NULL,
  ms REAL NOT NULL,
  cost_usd REAL NOT NULL,
  seq INTEGER NOT NULL,
  PRIMARY KEY (job_id, stage)
);
"""


class JobOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    result_key: str | None  # the S5 cache key once the job is done
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    stages: list[StageRun]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def create(self, figure_id: str, options: JobOptions) -> JobRecord:
        job_id, now = uuid.uuid4().hex, _now()
        with self._db() as db:
            db.execute(
                "INSERT INTO jobs (id, figure_id, status, options, created_at, updated_at) "
                "VALUES (?, ?, 'queued', ?, ?, ?)",
                (job_id, figure_id, options.model_dump_json(), now, now),
            )
        return self._must_get(job_id)

    def record_stage(self, job_id: str, run: StageRun) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO stage_runs (job_id, stage, outcome, ms, cost_usd, seq) "
                "VALUES (?, ?, ?, ?, ?, "
                "(SELECT COUNT(*) FROM stage_runs WHERE job_id = ?))",
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
        with self._db() as db:
            db.execute(
                f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?",
                (*fields.values(), _now(), job_id),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            runs = db.execute(
                "SELECT stage, outcome, ms, cost_usd FROM stage_runs WHERE job_id = ? ORDER BY seq",
                (job_id,),
            ).fetchall()
        fields = dict(row)
        options = JobOptions.model_validate_json(fields.pop("options"))
        return JobRecord(**fields, options=options, stages=[StageRun(**dict(r)) for r in runs])

    def _must_get(self, job_id: str) -> JobRecord:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def latest_for_figure(self, figure_id: str) -> JobRecord | None:
        with self._db() as db:
            row = db.execute(
                "SELECT id FROM jobs WHERE figure_id = ? ORDER BY rowid DESC LIMIT 1",
                (figure_id,),
            ).fetchone()
        return None if row is None else self.get(row["id"])
