"""The cross-site guard (app/middleware.py CrossSiteGuard): a page on another site cannot make a
browser start uploads, questions, edits or publishes here; reads and the app's own pages pass.
A typed question must be JSON, so a cross-site text/plain form post is not a question either."""

import asyncio
from pathlib import Path

import httpx
import pytest

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.mock import MockMetaClient

FID = "a" * 64
QUESTION = b'{"figure_id": "' + FID.encode() + b'", "question": "What is this?"}'


def send(tmp_path: Path, method: str, url: str, headers: dict[str, str],
         content: bytes = b"{}") -> httpx.Response:  # fmt: skip
    async def body() -> httpx.Response:
        app = create_app(data_dir=tmp_path, client=MockMetaClient(load_tactile_rules().meta))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            return await http.request(method, url, content=content, headers=headers)

    return asyncio.run(body())


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "/api/figures"),
        ("POST", "/api/ask"),
        ("POST", "/api/transcribe"),
        ("POST", f"/api/figures/{FID}/publish"),
        ("PATCH", f"/api/figures/{FID}/regions/r1"),
        ("POST", f"/api/figures/{FID}/regions/r1/fix"),
    ],
)
def test_a_change_from_another_site_is_refused_before_the_route(
    tmp_path: Path, method: str, url: str
) -> None:
    r = send(tmp_path, method, url, {"Sec-Fetch-Site": "cross-site", "Content-Type": "text/plain"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cross_site"


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none", None])
def test_the_apps_own_pages_and_clients_without_the_header_pass(
    tmp_path: Path, site: str | None
) -> None:
    headers = {"Content-Type": "application/json"}
    if site is not None:
        headers["Sec-Fetch-Site"] = site
    r = send(tmp_path, "POST", "/api/ask", headers, QUESTION)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_published"


def test_reads_from_another_site_pass_and_cors_hides_them(tmp_path: Path) -> None:
    r = send(tmp_path, "GET", "/api/health", {"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers


def test_a_typed_question_must_be_json(tmp_path: Path) -> None:
    r = send(tmp_path, "POST", "/api/ask", {"Content-Type": "text/plain"}, QUESTION)
    assert r.status_code == 415 and r.json()["error"]["code"] == "invalid_request"
