"""Record and replay real Meta responses, under fixtures/recorded/.

A recording keeps the request as sent minus anything secret or bulky: no headers at all (so
no auth), the key redacted as a backstop, and every data: URI or binary upload replaced by
"<data TYPE sha256=... bytes=N>". The response is kept whole: status, content type, and the
JSON body or the stream's events. ReplayTransport matches a request on method, path and the
same sanitized body, and serves the saved response through the real LiveCaller code."""

import base64
import datetime as dt
import email
import email.message
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx

from app.paths import RECORDED_DIR

_DATA_URI = re.compile(r"data:([^;,]*)(;base64)?,(.*)", re.S)
_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")
NO_RECORDING = 599  # what ReplayTransport answers for a request it has no recording of

Files = Mapping[str, tuple[str | None, bytes | str, str]]


def _digest(kind: str, data: bytes) -> str:
    return f"<data {kind} sha256={hashlib.sha256(data).hexdigest()} bytes={len(data)}>"


def sanitize(value: Any) -> Any:
    """The value with each data: URI replaced by its type, sha256 and size."""
    if isinstance(value, str):
        m = _DATA_URI.fullmatch(value)
        if m is None:
            return value
        raw = base64.b64decode(m.group(3)) if m.group(2) else m.group(3).encode()
        return _digest(m.group(1) or "application/octet-stream", raw)
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def _part(content: bytes | str, ctype: str) -> Any:
    data = content.encode() if isinstance(content, str) else content
    if ctype == "application/json":
        return sanitize(json.loads(data))
    return _digest(ctype, data)


def request_summary(request: httpx.Request) -> dict[str, Any]:
    """What a recording holds for this request, from the request httpx would send."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        msg = email.message_from_bytes(
            b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + request.content
        )
        parts: dict[str, Any] = {}
        for p in msg.get_payload():
            assert isinstance(p, email.message.Message)
            name = p.get_param("name", header="content-disposition")
            payload = p.get_payload(decode=True)
            assert isinstance(name, str) and isinstance(payload, bytes)
            parts[name] = _part(payload, p.get_content_type())
        return {"multipart": parts}
    return {"json": sanitize(json.loads(request.content)) if request.content else None}


class Recorder:
    def __init__(self, root: Path = RECORDED_DIR) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        if _NAME.fullmatch(name) is None:
            raise ValueError(f"recording name {name!r}: use lowercase letters, digits, _ . -")
        return self.root / f"{name}.json"

    def check_free(self, name: str) -> None:
        """Called before the live call, so a name clash never costs a call."""
        if self.path(name).exists():
            raise FileExistsError(f"{self.path(name)} exists; recordings are never overwritten")

    def save(
        self,
        name: str,
        *,
        model: str,
        request: httpx.Request,
        path: str,
        response: dict[str, Any],
        redact: Callable[[str], str],
    ) -> Path:
        out = self.path(name)
        obj = {
            "recorded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "model": model,
            "request": {"method": request.method, "path": path, **request_summary(request)},
            "response": response,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as f:
            f.write(redact(json.dumps(obj, indent=1, ensure_ascii=False)) + "\n")
        return out


def _respond(saved: dict[str, Any]) -> httpx.Response:
    if "events" in saved:
        sse = "".join(f"data: {json.dumps(e)}\n\n" for e in saved["events"]) + "data: [DONE]\n\n"
        return httpx.Response(
            saved["status"], text=sse, headers={"content-type": "text/event-stream"}
        )
    return httpx.Response(saved["status"], json=saved["json"])


class ReplayTransport(httpx.MockTransport):
    """Serves recordings. Never reaches the network."""

    def __init__(self, recordings: Iterable[dict[str, Any]]) -> None:
        self.recordings = list(recordings)
        super().__init__(self._handle)

    @classmethod
    def from_files(cls, paths: Iterable[Path]) -> "ReplayTransport":
        return cls(json.loads(p.read_text(encoding="utf-8")) for p in paths)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        summary = request_summary(request)
        for rec in self.recordings:
            req = rec["request"]
            if (
                req["method"] == request.method
                and request.url.path.endswith(req["path"])
                and {k: req.get(k) for k in summary} == summary
            ):
                return _respond(rec["response"])
        return httpx.Response(
            NO_RECORDING, text=f"no recording for {request.method} {request.url.path}"
        )
