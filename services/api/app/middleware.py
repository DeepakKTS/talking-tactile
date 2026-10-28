"""ASGI middleware: a request id on every request and response with one JSON access log
line, and the upload guard, which refuses an oversized upload from its Content-Length
before any of the body is read."""

import json
import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logs import request_id

log = logging.getLogger(__name__)

_INCOMING_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
_MS_PER_S = 1000
_FORM_SLACK_BYTES = 64 * 1024  # multipart boundaries and headers around the file


class RequestContext:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _INCOMING_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id.set(rid)
        t0, status = time.perf_counter(), 0

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            ms = (time.perf_counter() - t0) * _MS_PER_S
            log.info(
                "%s %s %d in %.0f ms",
                scope["method"],
                scope["path"],
                status,
                ms,
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "ms": round(ms, 1),
                },
            )
            request_id.reset(token)


class UploadGuard:
    """POST /api/figures must say its length, and the length must fit the upload limit."""

    def __init__(self, app: ASGIApp, max_bytes: int, path: str = "/api/figures") -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == self.path:
            length = dict(scope["headers"]).get(b"content-length")
            if length is None or not length.isdigit():
                await _refuse(send, 411, "length_required", "Send the upload with its length.")
                return
            if int(length) > self.max_bytes + _FORM_SLACK_BYTES:
                mb = self.max_bytes / (1024 * 1024)
                await _refuse(send, 413, "too_large", f"The file is over {mb:g} MB.")
                return
        await self.app(scope, receive, send)


async def _refuse(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "retryable": False}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
