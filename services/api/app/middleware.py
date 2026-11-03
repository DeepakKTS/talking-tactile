"""ASGI middleware: a request id on every request and response with one JSON access log
line, and the body guard (UploadGuard), which refuses an oversized request body from its
Content-Length before any of it is read."""

import json
import logging
import re
import time
import uuid
from collections import deque
from collections.abc import Callable

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


# The largest body each kind of request may send. A held question is at most 15 s of 16-bit
# mono WAV at 24 kHz (apps/web/src/explore/voice.ts MAX_MS): about 720 KB.
ASK_BODY_BYTES = 2 * 1024 * 1024
JSON_BODY_BYTES = 64 * 1024
_ASK_PATHS = ("/api/ask", "/api/transcribe")


class UploadGuard:
    """Every request with a body must say its length, and the length must fit: the figure
    upload its file limit, a question ASK_BODY_BYTES, anything else (edits, fix calls)
    JSON_BODY_BYTES. Refused from the Content-Length, before any of the body is read."""

    def __init__(self, app: ASGIApp, max_bytes: int, path: str = "/api/figures") -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path = path

    def _limit(self, path: str) -> tuple[int, str]:
        if path == self.path:
            mb = self.max_bytes / (1024 * 1024)
            return self.max_bytes + _FORM_SLACK_BYTES, f"The file is over {mb:g} MB."
        if path in _ASK_PATHS:
            return ASK_BODY_BYTES, "The recording is too long."
        return JSON_BODY_BYTES, "The request is too large."

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in ("POST", "PATCH", "PUT"):
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length is None or not length.isdigit():
                await _refuse(send, 411, "length_required", "Send the request with its length.")
                return
            limit, message = self._limit(scope["path"])
            if int(length) > limit:
                await _refuse(send, 413, "too_large", message)
                return
        await self.app(scope, receive, send)


_LOOPBACK = ("127.0.0.1", "::1")
_WINDOW_S = 60.0
RATE_PER_MINUTE = 30  # questions, and fix calls, per client: a student asks far fewer
_RATE_MESSAGES = {
    "question": "Too many questions at once. Wait a moment, then ask again.",
    "fix": "Too many fix calls at once. Wait a moment, then try again.",
}


class RateLimit:
    """Per client, at most RATE_PER_MINUTE questions (/api/ask and /api/transcribe together)
    and RATE_PER_MINUTE fix calls in any minute; more is refused with 429 before the route
    runs. The client is the connecting address or, when that is this machine (the web server's
    proxy, which forwards the phone's address), the first X-Forwarded-For address."""

    def __init__(
        self,
        app: ASGIApp,
        per_minute: int = RATE_PER_MINUTE,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.now = now
        self.seen: dict[tuple[str, str], deque[float]] = {}

    @staticmethod
    def _kind(scope: Scope) -> str | None:
        if scope["type"] != "http" or scope["method"] != "POST":
            return None
        path = str(scope["path"])
        if path in _ASK_PATHS:
            return "question"
        return "fix" if path.endswith("/fix") else None

    @staticmethod
    def _client(scope: Scope) -> str:
        host = (scope.get("client") or ("", 0))[0]
        if host in _LOOPBACK:
            forwarded = dict(scope["headers"]).get(b"x-forwarded-for", b"").decode("latin-1")
            first = forwarded.split(",")[0].strip()
            if first:
                return str(first)
        return str(host)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = self._kind(scope)
        if kind is not None:
            t = self.now()
            times = self.seen.setdefault((kind, self._client(scope)), deque())
            while times and times[0] <= t - _WINDOW_S:
                times.popleft()
            if len(times) >= self.per_minute:
                await _refuse(send, 429, "rate_limited", _RATE_MESSAGES[kind])
                return
            times.append(t)
        await self.app(scope, receive, send)


async def _refuse(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "retryable": False}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
