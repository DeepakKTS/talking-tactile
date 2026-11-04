"""Figure routes. Author: upload, status, draft outputs (plus the source image and the
rules report), edits, publish. Explore: published versions only. A figure id is checked to
be a lowercase hex sha256 before anything else looks at it. Files are served with their
media type and an ETag of their sha256."""

import hashlib
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, File, Form, Request, Response, UploadFile
from pydantic import ValidationError

from app.errors import ApiError
from app.figures import (
    DRAFT_ONLY_TYPES,
    MEDIA_TYPES,
    FigureService,
    FixPoints,
    Publication,
    job_json,
)
from app.models.regions import GradeBand, PageSize
from app.pipeline.cache import is_figure_id
from app.pipeline.edits import EDIT, AddEdit, Edit
from app.pipeline.jobs import JobOptions

router = APIRouter(prefix="/api/figures")

_REGION_OPS = {"label", "check", "describe", "merge", "delete"}


def _service(request: Request) -> FigureService:
    service: FigureService = request.app.state.figure_service()
    return service


def _fid(figure_id: str) -> str:
    if not is_figure_id(figure_id):
        raise ApiError(400, "bad_figure_id", "A figure id is 64 lowercase hex characters.")
    return figure_id


def _media_type(name: str, types: dict[str, str] = MEDIA_TYPES) -> str:
    if name not in types:
        raise ApiError(404, "not_found", f"There is no file called {name}.")
    return types[name]


def _file(
    request: Request, data: bytes, media_type: str, immutable: bool, version: int | None = None
) -> Response:
    etag = f'"{hashlib.sha256(data).hexdigest()}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache",
    }
    if version is not None:  # which version "latest" was, so Explore asks about that one
        headers["X-Published-Version"] = str(version)
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=media_type, headers=headers)


def _publication_json(pub: Publication) -> dict[str, object]:
    base = f"/api/figures/{pub.figure_id}/published/{pub.version}"
    return {
        "version": pub.version,
        "edit_version": pub.edit_version,
        "created_at": pub.created_at,
        "files": {
            name: {"url": f"{base}/{name}", "sha256": sha} for name, sha in pub.files.items()
        },
    }


@router.post("", status_code=202)
async def upload(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File()],
    page_index: Annotated[int, Form(ge=0)] = 0,
    page: Annotated[PageSize, Form()] = "letter",
    grade_band: Annotated[GradeBand | None, Form()] = None,
) -> dict[str, object]:
    service = _service(request)
    limit = int(service.runner.rules.pipeline.max_upload_mb * 1024 * 1024)
    data = await file.read(limit + 1)  # one byte over is enough for S0 to refuse it
    job, created = await service.submit(
        data, page_index, JobOptions(page=page, grade_band=grade_band)
    )
    response.status_code = 202 if created else 200
    return {"figure_id": job.figure_id, "created": created, "job": job_json(job)}


@router.get("/{figure_id}")
async def status(request: Request, figure_id: str) -> dict[str, object]:
    return _service(request).status(_fid(figure_id))


@router.patch("/{figure_id}/regions/{region_id}", status_code=202)
async def edit_region(
    request: Request, figure_id: str, region_id: str, body: Annotated[dict[str, Any], Body()]
) -> dict[str, object]:
    fid = _fid(figure_id)
    if body.get("op") == "outline":
        return await _accept_outline(request, fid, region_id, body)
    if body.get("op") not in _REGION_OPS or "region" in body:
        raise ApiError(
            422, "invalid_request", "op is one of label, check, describe, merge, delete or outline."
        )
    try:
        edit: Edit = EDIT.validate_python({**body, "region": region_id})
    except ValidationError as exc:
        raise ApiError(422, "invalid_request", _first_error(exc)) from exc
    version, job = await _service(request).edit(fid, edit)
    return {"edit_version": version, "job": job_json(job)}


def _points(body: dict[str, Any]) -> FixPoints:
    try:
        return FixPoints.model_validate({k: v for k, v in body.items() if k != "op"})
    except ValidationError as exc:
        raise ApiError(422, "invalid_request", _first_error(exc)) from exc


async def _accept_outline(
    request: Request, fid: str, region_id: str, body: dict[str, Any]
) -> dict[str, object]:
    version, job = await _service(request).fix_accept(fid, region_id, _points(body))
    return {"edit_version": version, "job": job_json(job)}


@router.post("/{figure_id}/regions/{region_id}/fix")
async def fix_preview(
    request: Request, figure_id: str, region_id: str, body: Annotated[dict[str, Any], Body()]
) -> dict[str, object]:
    """Fix outline: SAM's mask for the teacher's points, previewed. Live (LIVE=1); each call
    counts against the figure's fix cap and goes to the ledger. Accept with PATCH op outline."""
    return await _service(request).fix_preview(_fid(figure_id), region_id, _points(body))


@router.post("/{figure_id}/regions", status_code=202)
async def add_region(
    request: Request, figure_id: str, body: Annotated[dict[str, Any], Body()]
) -> dict[str, object]:
    fid = _fid(figure_id)
    try:
        edit = AddEdit.model_validate({**body, "op": "add"})
    except ValidationError as exc:
        raise ApiError(422, "invalid_request", _first_error(exc)) from exc
    version, job = await _service(request).edit(fid, edit)
    return {"edit_version": version, "job": job_json(job)}


@router.post("/{figure_id}/publish", status_code=201)
async def publish(request: Request, response: Response, figure_id: str) -> dict[str, object]:
    pub, created = await _service(request).publish(_fid(figure_id))
    response.status_code = 201 if created else 200
    return {"created": created, **_publication_json(pub)}


@router.get("/{figure_id}/published")
async def published(request: Request, figure_id: str) -> dict[str, object]:
    service = _service(request)
    latest = service.published(_fid(figure_id), None)
    versions = service.publications.list(figure_id)
    return {"latest": latest.version, "versions": [_publication_json(p) for p in versions]}


@router.get("/{figure_id}/published/{version}/{name}")
async def published_file(
    request: Request, figure_id: str, version: Literal["latest"] | int, name: str
) -> Response:
    service = _service(request)
    media_type = _media_type(name)
    if isinstance(version, int) and version < 1:
        raise ApiError(404, "not_published", f"This figure has no published version {version}.")
    pub = service.published(_fid(figure_id), None if version == "latest" else version)
    data = service.publications.path(pub, name).read_bytes()
    return _file(request, data, media_type, immutable=version != "latest", version=pub.version)


@router.get("/{figure_id}/{name}")
async def draft_file(request: Request, figure_id: str, name: str) -> Response:
    fid = _fid(figure_id)
    media_type = _media_type(name, {**MEDIA_TYPES, **DRAFT_ONLY_TYPES})
    path = _service(request).draft_file(fid, name)
    return _file(request, path.read_bytes(), media_type, immutable=False)


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first["loc"] if not str(p).endswith("Edit"))
    return f"{where}: {first['msg']}" if where else first["msg"]
