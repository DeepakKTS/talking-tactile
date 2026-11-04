"""The per-client rate limit (app/middleware.py RateLimit): questions and fix calls."""

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.middleware import RATE_PER_MINUTE, RateLimit


async def ok(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def run(limit: RateLimit, path: str, client: str = "127.0.0.1", xff: str | None = None) -> int:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    scope = {"type": "http", "method": "POST", "path": path, "headers": headers,
             "client": (client, 5)}  # fmt: skip
    got: list[int] = []

    async def send(m: dict[str, Any]) -> None:
        if m["type"] == "http.response.start":
            got.append(m["status"])

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    asyncio.run(limit(scope, receive, send))
    return got[0]


def test_questions_and_transcriptions_share_one_limit_per_client_per_minute() -> None:
    clock = [0.0]
    limit = RateLimit(ok, per_minute=3, now=lambda: clock[0])
    assert [run(limit, p) for p in ("/api/ask", "/api/transcribe", "/api/ask")] == [200] * 3
    assert run(limit, "/api/transcribe") == 429
    assert run(limit, "/api/figures/x/regions/r1/fix") == 200  # fix calls count apart
    assert run(limit, "/api/health") == 200  # nothing else is limited
    clock[0] = 60.0
    assert run(limit, "/api/ask") == 200  # a minute later


def test_uploads_have_their_own_limit_per_client_per_minute() -> None:
    clock = [0.0]
    limit = RateLimit(ok, per_minute=3, now=lambda: clock[0], uploads_per_minute=2)
    assert [run(limit, "/api/figures") for _ in range(2)] == [200, 200]
    assert run(limit, "/api/figures") == 429
    assert run(limit, "/api/ask") == 200  # questions count apart
    assert run(limit, "/api/figures/x/publish") == 200  # publish is not an upload
    clock[0] = 60.0
    assert run(limit, "/api/figures") == 200


def test_the_forwarded_address_counts_only_through_this_machine() -> None:
    limit = RateLimit(ok, per_minute=1)
    assert run(limit, "/api/ask", xff="192.168.1.20") == 200
    assert run(limit, "/api/ask", xff="192.168.1.21") == 200  # another phone
    assert run(limit, "/api/ask", xff="192.168.1.20") == 429
    # From another machine the header is ignored: it cannot claim a fresh address.
    assert run(limit, "/api/ask", client="10.0.0.9", xff="1.2.3.4") == 200
    assert run(limit, "/api/ask", client="10.0.0.9", xff="5.6.7.8") == 429


def test_the_app_refuses_the_question_past_the_limit_with_a_spoken_sentence(tmp_path: Path) -> None:
    async def body() -> list[httpx.Response]:
        app = create_app(data_dir=tmp_path, client=MockMetaClient(load_tactile_rules().meta))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            return [await http.post("/api/ask", json={}) for _ in range(RATE_PER_MINUTE + 1)]

    replies = asyncio.run(body())
    assert {r.status_code for r in replies[:-1]} == {422}  # through to the route
    assert replies[-1].status_code == 429
    assert replies[-1].json()["error"] == {
        "code": "rate_limited",
        "message": "Too many questions at once. Wait a moment, then ask again.",
        "retryable": False,
    }
