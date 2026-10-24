"""The SQLite file that holds jobs, teacher edits and published versions. A connection per
call, so stages running in worker threads can record too."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2  # bump with any change below; an older file is refused, not migrated

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  figure_id TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT,
  options TEXT NOT NULL,
  edit_version INTEGER NOT NULL,
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
CREATE TABLE IF NOT EXISTS edits (
  figure_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  edit TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (figure_id, version)
);
CREATE TABLE IF NOT EXISTS publications (
  figure_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  job_id TEXT NOT NULL REFERENCES jobs (id),
  edit_version INTEGER NOT NULL,
  files TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (figure_id, version)
);
"""


class DatabaseVersionError(Exception):
    """The file was made by an older schema."""


def now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """One transaction: committed when the block ends, rolled back on an error."""
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.row_factory = sqlite3.Row
        yield db


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        empty = db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0
        if not empty and version != SCHEMA_VERSION:
            raise DatabaseVersionError(
                f"{path} has schema {version}, this code needs {SCHEMA_VERSION}. "
                "Move it aside to start a new one."
            )
        db.executescript(_SCHEMA)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
