"""The body guard (app/middleware.py UploadGuard): every request body says its length and fits
its limit, refused before any of it is read."""

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.middleware import ASK_BODY_BYTES, JSON_BODY_BYTES

FID = "a" * 64


def post(tmp_path: Path, method: str, url: str, content: bytes) -> httpx.Response:
    async def body() -> httpx.Response:
        app = create_app(data_dir=tmp_path, client=MockMetaClient(load_tactile_rules().meta))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            return await http.request(
                method, url, content=content, headers={"Content-Type": "application/json"}
            )

    return asyncio.run(body())


def test_an_edit_or_fix_body_over_64_kb_is_refused(tmp_path: Path) -> None:
    big = b"{" + b" " * (JSON_BODY_BYTES + 10) + b"}"
    for method, url in (
        ("PATCH", f"/api/figures/{FID}/regions/r1"),
        ("POST", f"/api/figures/{FID}/regions/r1/fix"),
    ):
        r = post(tmp_path, method, url, big)
        assert r.status_code == 413
        assert r.json()["error"] == {
            "code": "too_large",
            "message": "The request is too large.",
            "retryable": False,
        }


def test_a_question_over_2_mb_is_refused_and_one_under_reaches_the_route(tmp_path: Path) -> None:
    r = post(tmp_path, "POST", "/api/ask", b"x" * (ASK_BODY_BYTES + 1))
    assert (r.status_code, r.json()["error"]["message"]) == (413, "The recording is too long.")
    r = post(tmp_path, "POST", "/api/transcribe", b"x" * (ASK_BODY_BYTES + 1))
    assert r.status_code == 413
    r = post(tmp_path, "POST", "/api/ask", b"{}")
    assert r.status_code == 422  # through the guard, refused by the route


def test_a_publish_with_no_body_passes_the_guard(tmp_path: Path) -> None:
    r = post(tmp_path, "POST", f"/api/figures/{FID}/publish", b"")
    assert r.status_code == 404  # the figure is unknown: the guard let it through


def test_a_body_without_a_length_is_refused() -> None:
    app = create_app(client=MockMetaClient(load_tactile_rules().meta))
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/ask", "raw_path": b"/api/ask",
             "headers": [(b"content-type", b"application/json")], "query_string": b"",
             "http_version": "1.1", "scheme": "http", "server": ("t", 80), "client": ("c", 1),
             "root_path": ""}  # fmt: skip
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 411
