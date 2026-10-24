"""The figure API in mock mode, through the ASGI app: upload, status, draft files, teacher
edits, publish and published files, plus the middleware (request id, error envelope,
upload guard, CORS, JSON logs)."""

import asyncio
import hashlib
import io
import json
import logging
import stat
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app.config import load_tactile_rules
from app.figures import FigureService
from app.logs import JsonFormatter, request_id
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.paths import FIXTURES_DIR

RULES = load_tactile_rules()
SYNTHETIC_PNG = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()
MB = 1024 * 1024
FINISHED = {"done", "failed", "describe_only"}
WEB = "http://localhost:5173"


class Api:
    def __init__(self, http: httpx.AsyncClient, service: FigureService, client: MockMetaClient):
        self.http = http
        self.service = service
        self.client = client

    async def upload(self, data: bytes = SYNTHETIC_PNG, name: str = "figure.png",
                     **form: str) -> httpx.Response:  # fmt: skip
        files = {"file": (name, data, "application/octet-stream")}
        return await self.http.post("/api/figures", files=files, data={"grade_band": "k5", **form})

    async def wait(self, fid: str) -> dict[str, Any]:
        """Status once the newest job for the figure has finished."""
        await self.service.drain()
        body: dict[str, Any] = (await self.http.get(f"/api/figures/{fid}")).json()
        assert body["job"]["status"] in FINISHED, body
        return body

    def understand_calls(self) -> int:
        return sum(c.call == "understand" for c in self.client.calls)


@asynccontextmanager
async def api_for(root: Path) -> AsyncIterator[Api]:
    client = MockMetaClient(RULES.meta)
    app = create_app(data_dir=root, client=client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        api = Api(http, app.state.figure_service(), client)
        try:
            yield api
        finally:
            await api.service.drain()


def run(root: Path, body: Callable[[Api], Awaitable[None]]) -> None:
    async def go() -> None:
        async with api_for(root) as api:
            await body(api)

    asyncio.run(go())


def assert_envelope(r: httpx.Response, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/json")
    err = r.json()["error"]
    assert err["code"] == code
    assert isinstance(err["message"], str) and err["message"]
    assert isinstance(err["retryable"], bool)


def sha_etag(data: bytes) -> str:
    return f'"{hashlib.sha256(data).hexdigest()}"'


def outcomes(status: dict[str, Any]) -> dict[str, str]:
    return {s["stage"]: s["outcome"] for s in status["job"]["stages"]}


def test_upload_edit_publish_and_fetch(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        r = await api.upload()
        assert r.status_code == 202, r.text
        assert r.json()["created"] is True
        assert len(r.headers["x-request-id"]) >= 8
        fid = r.json()["figure_id"]
        status = await api.wait(fid)
        assert status["job"]["status"] == "done"
        assert status["edit_version"] == 0
        assert status["published"] == []

        # Draft files for the teacher's review.
        r = await api.http.get(f"/api/figures/{fid}/regions.json")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/json"
        assert r.headers["etag"] == sha_etag(r.content)
        again = await api.http.get(f"/api/figures/{fid}/regions.json",
                                   headers={"If-None-Match": r.headers["etag"]})  # fmt: skip
        assert again.status_code == 304
        draft = r.json()
        assert {x["id"] for x in draft["regions"]} >= {"r1", "r2", "r7", "r8", "r9"}
        assert not any(x["verified_by_teacher"] for x in draft["regions"])

        # Explore sees nothing until the teacher publishes.
        assert_envelope(await api.http.get(f"/api/figures/{fid}/published"), 404, "not_published")
        r = await api.http.get(f"/api/figures/{fid}/published/latest/regions.json")
        assert_envelope(r, 404, "not_published")

        # Teacher edits, each a new version that re-runs S4 and S5 only.
        edits: list[tuple[str, str, dict[str, Any]]] = [
            ("patch", "/regions/r1", {"op": "label", "label": "outer wall"}),
            ("patch", "/regions/r2", {"op": "describe", "description": "The core."}),
            ("patch", "/regions/r8", {"op": "merge", "into": "r7"}),
            ("patch", "/regions/r9", {"op": "delete"}),
            ("post", "/regions", {"name": "pore"}),
        ]
        for n, (method, path, payload) in enumerate(edits, start=1):
            r = await api.http.request(method.upper(), f"/api/figures/{fid}{path}", json=payload)
            assert r.status_code == 202, r.text
            assert r.json()["edit_version"] == n
        status = await api.wait(fid)
        assert status["job"]["status"] == "done", status
        assert status["job"]["edit_version"] == len(edits)
        assert outcomes(status) == {"s0": "cached", "s1": "cached", "s2": "cached",
                                    "s3": "cached", "s4": "ran", "s5": "ran"}  # fmt: skip
        assert api.understand_calls() == 1

        # Edits live in SQLite only: each Meta and S3 stage still has its one cache entry.
        figure = tmp_path / "figures" / fid
        for stage in ("s0", "s1", "s2", "s3"):
            assert len(list((figure / stage).iterdir())) == 1, stage

        edited = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        regions = {x["id"]: x for x in edited["regions"]}
        assert regions["r1"]["label"] == "outer wall"
        assert regions["r1"]["verified_by_teacher"] is True
        assert regions["r2"]["description"] == "The core."
        assert "r8" not in regions
        assert regions["r7"]["verified_by_teacher"] is True
        assert "r9" not in regions
        assert regions["t1"]["label"] == "pore"
        assert regions["t1"]["verified_by_teacher"] is True

        # Publish a locked version, then fetch it the way Explore does.
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert r.status_code == 201, r.text
        pub = r.json()
        assert pub["version"] == 1
        assert pub["edit_version"] == len(edits)
        for name, media in [("regions.json", "application/json"),
                            ("tactile.svg", "image/svg+xml"),
                            ("print.pdf", "application/pdf")]:  # fmt: skip
            r = await api.http.get(pub["files"][name]["url"])
            assert r.status_code == 200, name
            assert r.headers["content-type"].startswith(media), name
            assert r.headers["etag"] == sha_etag(r.content) == f'"{pub["files"][name]["sha256"]}"'
            assert "immutable" in r.headers["cache-control"]
            path = tmp_path / "published" / fid / "1" / name
            assert not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        r = await api.http.get(f"/api/figures/{fid}/published/1/regions.json")
        assert r.json() == edited
        r = await api.http.get(f"/api/figures/{fid}/published/1/print.pdf")
        assert r.content.startswith(b"%PDF")

        # Publishing the same output again keeps version 1; Explore's index shows it.
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert r.status_code == 200
        assert r.json()["version"] == 1
        index = (await api.http.get(f"/api/figures/{fid}/published")).json()
        assert index["latest"] == 1
        assert [v["version"] for v in index["versions"]] == [1]
        r = await api.http.get(f"/api/figures/{fid}/published/latest/tactile.svg")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        assert (await api.http.get(f"/api/figures/{fid}")).json()["published"] == [1]

    run(tmp_path, body)


def test_a_new_edit_after_publishing_makes_version_two(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).json()["version"] == 1
        r = await api.http.patch(f"/api/figures/{fid}/regions/r3", json={"op": "delete"})
        assert r.status_code == 202
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).json()["version"] == 2
        v1 = (await api.http.get(f"/api/figures/{fid}/published/1/regions.json")).json()
        v2 = (await api.http.get(f"/api/figures/{fid}/published/2/regions.json")).json()
        assert "r3" in {x["id"] for x in v1["regions"]}
        assert "r3" not in {x["id"] for x in v2["regions"]}

    run(tmp_path, body)


def test_publish_waits_for_pending_edits(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        async with api.service._run[fid]:  # hold the pipeline so the edit stays pending
            r = await api.http.patch(f"/api/figures/{fid}/regions/r1",
                                     json={"op": "label", "label": "shell"})  # fmt: skip
            assert r.status_code == 202
            assert_envelope(await api.http.post(f"/api/figures/{fid}/publish"), 409, "not_ready")
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201

    run(tmp_path, body)


def test_a_duplicate_upload_returns_the_existing_job(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        first = await api.upload()
        await api.wait(first.json()["figure_id"])
        second = await api.upload(name="renamed.png")
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["figure_id"] == first.json()["figure_id"]
        assert second.json()["job"]["id"] == first.json()["job"]["id"]
        assert api.understand_calls() == 1
        other = await api.upload(grade_band="9_12")  # other options are another job
        assert other.status_code == 202
        assert other.json()["job"]["id"] != first.json()["job"]["id"]

    run(tmp_path, body)


def test_a_concurrent_double_submit_runs_the_pipeline_once(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        a, b = await asyncio.gather(api.upload(), api.upload())
        assert sorted([a.status_code, b.status_code]) == [200, 202]
        assert a.json()["job"]["id"] == b.json()["job"]["id"]
        status = await api.wait(a.json()["figure_id"])
        assert status["job"]["status"] == "done"
        assert api.understand_calls() == 1
        segments = [c.phrase for c in api.client.calls if c.call == "segment"]
        assert len(segments) == len(set(segments))

    run(tmp_path, body)


@pytest.mark.parametrize(
    "path",
    [
        "/api/figures/not-a-hash",
        "/api/figures/" + "A" * 64,
        "/api/figures/" + "a" * 63,
        "/api/figures/" + "a" * 65,
        "/api/figures/%2e%2e/regions.json",
        "/api/figures/..%5C..%5Cetc%5Cpasswd/regions.json",
        "/api/figures/%2e%2e/published/1/regions.json",
        "/api/figures/..%2F..%2Fetc%2Fpasswd",
        "/api/figures/..%2F..%2Fetc%2Fpasswd/regions.json",
        "/api/figures/%00" + "a" * 63,
    ],
)
def test_a_bad_figure_id_never_reaches_a_path(tmp_path: Path, path: str) -> None:
    async def body(api: Api) -> None:
        r = await api.http.get(path)
        assert r.status_code in {400, 404}, r.text
        assert r.json()["error"]["code"] in {"bad_figure_id", "not_found"}
        for method, suffix in [("PATCH", "/regions/r1"), ("POST", "/publish")]:
            r = await api.http.request(method, path + suffix, json={"op": "delete"})
            assert r.status_code in {400, 404, 405}, r.text
        assert not (tmp_path / "figures").exists()

    run(tmp_path, body)


def test_a_malformed_id_is_a_400_and_an_unknown_one_a_404(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        assert_envelope(await api.http.get("/api/figures/xyz"), 400, "bad_figure_id")
        assert_envelope(await api.http.get("/api/figures/%2e%2e/tactile.svg"), 400, "bad_figure_id")
        unknown = "0" * 64
        assert_envelope(await api.http.get(f"/api/figures/{unknown}"), 404, "not_found")
        assert_envelope(await api.http.get(f"/api/figures/{unknown}/regions.json"), 404,
                        "not_found")  # fmt: skip
        r = await api.http.patch(f"/api/figures/{unknown}/regions/r1", json={"op": "delete"})
        assert_envelope(r, 404, "not_found")

    run(tmp_path, body)


def test_an_oversized_upload_is_refused(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        limit = int(RULES.pipeline.max_upload_mb * MB)
        r = await api.upload(b"\x89PNG\r\n\x1a\n" + bytes(limit + MB))
        assert_envelope(r, 413, "too_large")  # by the guard, from Content-Length
        r = await api.upload(b"\x89PNG\r\n\x1a\n" + bytes(limit))
        assert_envelope(r, 413, "too_large")  # just over: inside the form slack, refused by S0
        assert not (tmp_path / "figures").exists()

    run(tmp_path, body)


@pytest.mark.parametrize(
    "data",
    [b"GIF89a" + bytes(100), b"hello, this is text", b"", b"\x89PNG\r\n\x1a\n not really"],
)
def test_a_wrong_or_broken_file_is_refused(tmp_path: Path, data: bytes) -> None:
    async def body(api: Api) -> None:
        r = await api.upload(data)
        assert r.status_code in {415, 422}, r.text
        code = r.json()["error"]["code"]
        assert code == ("unreadable" if data.startswith(b"\x89PNG") else "unsupported_type")
        assert not (tmp_path / "figures").exists()

    run(tmp_path, body)


def test_a_pdf_page_out_of_range_is_refused(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        buf = io.BytesIO()
        Image.open(io.BytesIO(SYNTHETIC_PNG)).convert("RGB").save(buf, "PDF")
        r = await api.upload(buf.getvalue(), name="figure.pdf", page_index="3")
        assert_envelope(r, 422, "bad_page")

    run(tmp_path, body)


def test_bad_edits_are_refused_and_not_stored(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        base = f"/api/figures/{fid}"
        cases = [
            ("PATCH", "/regions/r99", {"op": "label", "label": "x"}, "edit_invalid"),
            ("PATCH", "/regions/r1", {"op": "merge", "into": "r1"}, "edit_invalid"),
            ("PATCH", "/regions/r1", {"op": "add", "name": "x"}, "invalid_request"),
            ("PATCH", "/regions/r1", {"op": "label", "label": ""}, "invalid_request"),
            ("PATCH", "/regions/r1", {"op": "label", "label": "x", "region": "r2"},
             "invalid_request"),
            ("PATCH", "/regions/bad.id", {"op": "delete"}, "invalid_request"),
            ("POST", "/regions", {"name": "mitochondria"}, "edit_invalid"),
            ("POST", "/regions", {}, "invalid_request"),
        ]  # fmt: skip
        for method, path, payload, code in cases:
            r = await api.http.request(method, base + path, json=payload)
            assert_envelope(r, 422, code)
        assert (await api.http.get(base)).json()["edit_version"] == 0

    run(tmp_path, body)


def test_cors_allows_only_the_local_web_origin(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        preflight = {"Access-Control-Request-Method": "POST"}
        ok = await api.http.options("/api/figures", headers={"Origin": WEB, **preflight})
        assert ok.status_code == 200
        assert ok.headers["access-control-allow-origin"] == WEB
        evil = {"Origin": "https://evil.example", **preflight}
        bad = await api.http.options("/api/figures", headers=evil)  # fmt: skip
        assert bad.status_code == 400
        assert "access-control-allow-origin" not in bad.headers
        simple = await api.http.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in simple.headers

    run(tmp_path, body)


def test_every_response_has_a_request_id_and_errors_one_envelope(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        r = await api.http.get("/api/health", headers={"X-Request-ID": "abcdef12-3456"})
        assert r.headers["x-request-id"] == "abcdef12-3456"
        r = await api.http.get("/api/health", headers={"X-Request-ID": "bad id\n"})
        assert r.headers["x-request-id"] != "bad id\n"
        assert_envelope(await api.http.get("/api/nothing-here"), 404, "not_found")
        r = await api.http.post("/api/figures", data={"grade_band": "k5"})
        assert_envelope(r, 422, "invalid_request")
        assert "x-request-id" in r.headers

    run(tmp_path, body)


def test_live_mode_without_a_client_says_what_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOCK_META", raising=False)

    async def go() -> None:
        app = create_app(data_dir=tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            files = {"file": ("f.png", SYNTHETIC_PNG, "image/png")}
            r = await http.post("/api/figures", files=files)
            assert_envelope(r, 503, "unavailable")
            assert "MOCK_META=1" in r.json()["error"]["message"]
            assert (await http.get("/api/health")).status_code == 200

    asyncio.run(go())


def test_logs_are_json_with_the_request_id_and_stage_fields() -> None:
    token = request_id.set("req-1234abcd")
    try:
        record = logging.LogRecord("app.pipeline.runner", logging.INFO, __file__, 1,
                                   "job %s s4 ran", ("abc",), None)  # fmt: skip
        record.__dict__.update({"stage": "s4", "ms": 12.5, "cost_usd": 0.0, "job_id": "abc"})
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id.reset(token)
    assert line["msg"] == "job abc s4 ran"
    assert line["request_id"] == "req-1234abcd"
    assert line["level"] == "info"
    assert (line["stage"], line["ms"], line["cost_usd"], line["job_id"]) == ("s4", 12.5, 0.0, "abc")


def test_pipeline_logs_carry_the_upload_request_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def body(api: Api) -> None:
        r = await api.http.post(
            "/api/figures",
            files={"file": ("f.png", SYNTHETIC_PNG, "image/png")},
            headers={"X-Request-ID": "upload-req-0001"},
        )
        await api.wait(r.json()["figure_id"])

    with caplog.at_level(logging.INFO, logger="app"):
        run(tmp_path, body)
    stage_logs = [rec for rec in caplog.records if getattr(rec, "stage", None) == "s5"]
    assert stage_logs
    formatted = json.loads(JsonFormatter().format(stage_logs[-1]))
    assert formatted["request_id"] == "upload-req-0001"
    assert formatted["ms"] > 0
    assert "cost_usd" in formatted


def test_concurrent_publishes_and_edits_take_distinct_versions(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        base = f"/api/figures/{fid}"
        a, b = await asyncio.gather(api.http.post(f"{base}/publish"),
                                    api.http.post(f"{base}/publish"))  # fmt: skip
        assert sorted([a.status_code, b.status_code]) == [200, 201]
        assert a.json()["version"] == b.json()["version"] == 1
        edits = await asyncio.gather(
            api.http.patch(f"{base}/regions/r1", json={"op": "label", "label": "shell"}),
            api.http.patch(f"{base}/regions/r2", json={"op": "label", "label": "kernel"}),
        )
        assert sorted(r.json()["edit_version"] for r in edits) == [1, 2]
        status = await api.wait(fid)
        assert status["job"]["edit_version"] == 2
        labels = {x["id"]: x["label"] for x in
                  (await api.http.get(f"{base}/regions.json")).json()["regions"]}  # fmt: skip
        assert (labels["r1"], labels["r2"]) == ("shell", "kernel")

    run(tmp_path, body)
