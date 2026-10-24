"""What the figure routes call: submitting uploads, teacher edits, publishing, and finding
the files to serve.

Every figure has one admission lock. Submit, edit and publish decide under it, so two
requests for the same figure cannot both start a pipeline run or both take the same
version number. Runs of one figure also queue behind each other on a second lock, which
admission never waits on, so a request is not held up by a running pipeline.

Publishing copies regions.json, tactile.svg and print.pdf into
data/published/<figure_id>/<n>/, read-only and never overwritten. Explore loads these. A
version is published only when the tactile rules report written with those exact files has
no violation; there is no override."""

import asyncio
import hashlib
import json
import shutil
import stat
import uuid
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.errors import ApiError
from app.geometry.validate import Violation
from app.pipeline import db
from app.pipeline.edits import Edit, EditError, EditStore
from app.pipeline.jobs import JobOptions, JobRecord, JobStore
from app.pipeline.runner import NotReadyError, Runner
from app.pipeline.s5_render import PDF_FILE, REGIONS_FILE, REPORT_FILE, SVG_FILE

MEDIA_TYPES = {
    REGIONS_FILE: "application/json",
    SVG_FILE: "image/svg+xml",
    PDF_FILE: "application/pdf",
}
_RETRYABLE_JOB_ERRORS = {"stage_failed"}
_READ_ONLY = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Publication(BaseModel):
    model_config = ConfigDict(frozen=True)

    figure_id: str
    version: int
    job_id: str
    edit_version: int
    files: dict[str, str]  # file name -> sha256
    created_at: str


class PublishStore:
    def __init__(self, db_path: Path, root: Path) -> None:
        self.db_path = db_path
        self.root = root
        db.init(db_path)

    def list(self, figure_id: str) -> list[Publication]:
        with db.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM publications WHERE figure_id = ? ORDER BY version", (figure_id,)
            ).fetchall()
        return [Publication(**{**dict(r), "files": json.loads(r["files"])}) for r in rows]

    def get(self, figure_id: str, version: int | None) -> Publication | None:
        """One version, or the newest when version is None."""
        pubs = self.list(figure_id)
        if version is None:
            return pubs[-1] if pubs else None
        return next((p for p in pubs if p.version == version), None)

    def path(self, pub: Publication, name: str) -> Path:
        return self.root / pub.figure_id / str(pub.version) / name

    def publish(self, job: JobRecord, source: Path) -> Publication:
        """Copies the job's outputs into the next numbered version, read-only."""
        latest = self.get(job.figure_id, None)
        version = 1 if latest is None else latest.version + 1
        final = self.root / job.figure_id / str(version)
        if final.exists():
            raise FileExistsError(f"published version {version} already exists")
        tmp = final.parent / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir(parents=True)
        try:
            for name in MEDIA_TYPES:
                shutil.copyfile(source / name, tmp / name)
                (tmp / name).chmod(_READ_ONLY)
            files = {name: file_digest(tmp / name) for name in MEDIA_TYPES}
            tmp.rename(final)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        pub = Publication(
            figure_id=job.figure_id,
            version=version,
            job_id=job.id,
            edit_version=job.edit_version,
            files=files,
            created_at=db.now(),
        )
        with db.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO publications (figure_id, version, job_id, edit_version, files, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    pub.figure_id,
                    pub.version,
                    pub.job_id,
                    pub.edit_version,
                    json.dumps(pub.files),
                    pub.created_at,
                ),
            )
        return pub


def job_json(job: JobRecord) -> dict[str, object]:
    error = None
    if job.error_code is not None:
        error = {
            "code": job.error_code,
            "message": job.error_message,
            "retryable": job.error_code in _RETRYABLE_JOB_ERRORS,
        }
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "options": job.options.model_dump(mode="json"),
        "edit_version": job.edit_version,
        "stages": [s.model_dump() for s in job.stages],
        "error": error,
    }


def check_report(out: Path, edit_version: int) -> None:
    """Raises a 409 unless the rules report next to these outputs is present and empty."""
    try:
        raw = json.loads((out / REPORT_FILE).read_text("utf-8"))
        report = [Violation.model_validate(v) for v in raw]
    except (OSError, ValueError) as exc:
        raise ApiError(
            409,
            "rules_unchecked",
            "This version has no tactile rules report, so it cannot be published.",
        ) from exc
    if not report:
        return
    n = len(report)
    raise ApiError(
        409,
        "rules_violated",
        f"This version breaks {n} tactile rule{'s' if n > 1 else ''}. Fix "
        f"{'them' if n > 1 else 'it'} with an edit, then publish again.",
        extra={
            "edit_version": edit_version,
            "violations": [
                {"regions": v.regions, "rule": v.rule, "measured": v.measured, "limit": v.limit}
                for v in report
            ],
        },
    )


class FigureService:
    def __init__(self, runner: Runner, publications: PublishStore) -> None:
        self.runner = runner
        self.jobs: JobStore = runner.jobs
        self.edits: EditStore = runner.edits
        self.publications = publications
        self._admit: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._run: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Task[JobRecord]] = set()

    def _start(self, job: JobRecord) -> None:
        task = asyncio.create_task(self._run_job(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_job(self, job: JobRecord) -> JobRecord:
        async with self._run[job.figure_id]:
            return await self.runner.run(job.id)

    async def drain(self) -> None:
        """Waits for every pipeline run started so far."""
        while self._tasks:
            await asyncio.gather(*self._tasks)

    async def submit(
        self, data: bytes, page_index: int, options: JobOptions
    ) -> tuple[JobRecord, bool]:
        """The job for this image and options, and whether it is new. The same image again
        gets the job it already has unless that job failed."""
        ing, s0 = await asyncio.to_thread(self.runner.ingest, data, page_index)
        fid = ing.figure_id
        async with self._admit[fid]:
            edit_version = self.edits.version(fid)
            live = self.jobs.find_live(fid, options, edit_version)
            if live is not None:
                return live, False
            job = self.runner.create_job(fid, options, edit_version, s0)
            self._start(job)
            return job, True

    def status(self, figure_id: str) -> dict[str, object]:
        job = self.jobs.latest_for_figure(figure_id)
        if job is None:
            raise ApiError(404, "not_found", "There is no figure with that id.")
        return {
            "figure_id": figure_id,
            "job": job_json(job),
            "edit_version": self.edits.version(figure_id),
            "published": [p.version for p in self.publications.list(figure_id)],
        }

    def draft_file(self, figure_id: str, name: str) -> Path:
        """The newest finished output, for the teacher's review."""
        self._known(figure_id)
        job = self.jobs.latest_done(figure_id)
        out = None if job is None else self.runner.output_dir(job)
        if out is None:
            raise ApiError(409, "not_ready", "The figure is still being processed.", True)
        return out / name

    def _known(self, figure_id: str) -> None:
        if self.jobs.latest_for_figure(figure_id) is None:
            raise ApiError(404, "not_found", "There is no figure with that id.")

    async def edit(self, figure_id: str, edit: Edit) -> tuple[int, JobRecord]:
        """Checks the edit against the current parts, stores it as the next version and
        starts a run that applies it."""
        self._known(figure_id)
        async with self._admit[figure_id]:
            base = self.jobs.latest_done(figure_id)
            if base is None:
                raise ApiError(409, "not_ready", "The figure is still being processed.", True)
            prior = self.edits.list(figure_id, self.edits.version(figure_id))
            try:
                await self.runner.check_edits(base, [*prior, edit])
            except EditError as exc:
                raise ApiError(422, "edit_invalid", str(exc)) from exc
            except NotReadyError as exc:
                raise ApiError(409, "not_ready", str(exc), True) from exc
            version = self.edits.append(figure_id, edit)
            job = self.runner.create_job(figure_id, base.options, version)
            self._start(job)
            return version, job

    async def publish(self, figure_id: str) -> tuple[Publication, bool]:
        """A locked version of the output that has every edit so far, and whether it is
        new. Publishing the same output again returns the version it already has. Refused
        with each violation when that output breaks a tactile rule."""
        self._known(figure_id)
        async with self._admit[figure_id]:
            job = self.jobs.latest_done(figure_id, self.edits.version(figure_id))
            out = None if job is None else self.runner.output_dir(job)
            if job is None or out is None:
                raise ApiError(409, "not_ready", "The latest edits are still being applied.", True)
            latest = self.publications.get(figure_id, None)
            if latest is not None and latest.job_id == job.id:
                return latest, False
            check_report(out, job.edit_version)
            return await asyncio.to_thread(self.publications.publish, job, out), True

    def published(self, figure_id: str, version: int | None) -> Publication:
        pub = self.publications.get(figure_id, version)
        if pub is None:
            what = (
                "This figure has no published version."
                if version is None
                else (f"This figure has no published version {version}.")
            )
            raise ApiError(404, "not_published", what)
        return pub
