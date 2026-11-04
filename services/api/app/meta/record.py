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
import io
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.paths import RECORDED_DIR

_DATA_URI = re.compile(r"data:([^;,]*)(;base64)?,(.*)", re.S)
_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")
NO_RECORDING = 599  # what ReplayTransport answers for a request it has no recording of

Files = Mapping[str, tuple[str | None, bytes | str, str]]


# The same pixels make other PNG bytes on Linux than on the Mac the recordings were made on
# (Pillow's builds compress differently), so a PNG's digest alone finds no recording there.
# png_pixels.json maps a hash of the decoded pixels to the digest the recordings hold; it is
# made on a Mac by app.meta.png_pixels. ReplayTransport tries the plain digest first and the
# mapped one only when no recording matches, so on the Mac nothing changes.
PNG_PIXELS = RECORDED_DIR / "png_pixels.json"
_pixel_digests: dict[str, list[str]] | None = None
_pixel_keys: dict[str, str | None] = {}  # PNG sha256 -> pixel key, so each PNG decodes once
CAPTURE_ENV = "TT_PNG_CAPTURE"  # a file: app.meta.png_pixels collects every PNG digest here


def pixel_key(png: bytes) -> str | None:
    """sha256 of the decoded image: its mode, size and raw pixels; None if it is not a PNG."""
    sha = hashlib.sha256(png).hexdigest()
    if sha not in _pixel_keys:
        try:
            with Image.open(io.BytesIO(png)) as im:
                im.load()
                head = f"{im.mode} {im.size[0]}x{im.size[1]} ".encode()
                _pixel_keys[sha] = hashlib.sha256(head + im.tobytes()).hexdigest()
        except (OSError, ValueError):
            _pixel_keys[sha] = None
    return _pixel_keys[sha]


def _recorded_digests() -> dict[str, list[str]]:
    global _pixel_digests  # noqa: PLW0603 - loaded once, on first use
    if _pixel_digests is None:
        _pixel_digests = (
            json.loads(PNG_PIXELS.read_text(encoding="utf-8")) if PNG_PIXELS.exists() else {}
        )
    return _pixel_digests


def _digest(kind: str, data: bytes, mapped: bool = False) -> str:
    """A data part as a recording names it. mapped: a PNG by the digest png_pixels.json gives
    its pixels, when exactly one is listed."""
    plain = f"<data {kind} sha256={hashlib.sha256(data).hexdigest()} bytes={len(data)}>"
    if kind != "image/png":
        return plain
    if (out := os.environ.get(CAPTURE_ENV)) and (key := pixel_key(data)) is not None:
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps({"pixels": key, "digest": plain}) + "\n")
    if not mapped:
        return plain
    key = pixel_key(data)
    candidates = _recorded_digests().get(key, []) if key is not None else []
    return candidates[0] if len(candidates) == 1 else plain


def sanitize(value: Any, mapped: bool = False) -> Any:
    """The value with each data: URI replaced by its type, sha256 and size."""
    if isinstance(value, str):
        m = _DATA_URI.fullmatch(value)
        if m is None:
            return value
        raw = base64.b64decode(m.group(3)) if m.group(2) else m.group(3).encode()
        return _digest(m.group(1) or "application/octet-stream", raw, mapped)
    if isinstance(value, dict):
        return {k: sanitize(v, mapped) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, mapped) for v in value]
    return value


def _part(content: bytes | str, ctype: str, mapped: bool) -> Any:
    data = content.encode() if isinstance(content, str) else content
    if ctype == "application/json":
        return sanitize(json.loads(data), mapped)
    return _digest(ctype, data, mapped)


def request_summary(request: httpx.Request, mapped: bool = False) -> dict[str, Any]:
    """What a recording holds for this request, from the request httpx would send. mapped: each
    PNG by its pixels (png_pixels.json), for a replay whose PNG bytes differ from the Mac's."""
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
            parts[name] = _part(payload, p.get_content_type(), mapped)
        return {"multipart": parts}
    return {"json": sanitize(json.loads(request.content), mapped) if request.content else None}


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
        # The request as sent first; then, on a miss, with each PNG found by its pixels.
        summary = request_summary(request)
        tries = [summary]
        if _recorded_digests() and (mapped := request_summary(request, mapped=True)) != summary:
            tries.append(mapped)
        for want in tries:
            for rec in self.recordings:
                req = rec["request"]
                if (
                    req["method"] == request.method
                    and request.url.path.endswith(req["path"])
                    and {k: req.get(k) for k in want} == want
                ):
                    return _respond(rec["response"])
        return httpx.Response(
            NO_RECORDING, text=f"no recording for {request.method} {request.url.path}"
        )
