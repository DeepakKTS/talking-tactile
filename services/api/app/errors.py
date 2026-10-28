"""One error envelope for every failure: {"error": {"code", "message", "retryable"}}, plus
any fields an error adds, such as the violations that stop a publish."""

import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.pipeline.s0_ingest import IngestError

log = logging.getLogger(__name__)

_INGEST_STATUS = {"too_large": 413, "unsupported_type": 415}
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}
_STATUS_UNPROCESSABLE = 422
_STATUS_INTERNAL = 500


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        retryable: bool = False,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.extra = dict(extra or {})


def envelope(
    status: int,
    code: str,
    message: str,
    retryable: bool = False,
    extra: Mapping[str, object] | None = None,
) -> JSONResponse:
    body = {"error": {**(extra or {}), "code": code, "message": message, "retryable": retryable}}
    return JSONResponse(body, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return envelope(exc.status, exc.code, exc.message, exc.retryable, exc.extra)

    @app.exception_handler(IngestError)
    async def ingest_error(_: Request, exc: IngestError) -> JSONResponse:
        return envelope(_INGEST_STATUS.get(exc.code, _STATUS_UNPROCESSABLE), exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid')}" if where else "The request is invalid."
        return envelope(_STATUS_UNPROCESSABLE, "invalid_request", message)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return envelope(_STATUS_INTERNAL, "internal", "Something went wrong.", retryable=True)
