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
from shapely.geometry import Point

from app.config import TactileRules, load_tactile_rules
from app.figures import NOTHING_TOUCHABLE, FigureService
from app.geometry.sheet import Sheet
from app.geometry.validate import Violation, validate_sheet
from app.logs import JsonFormatter, request_id
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.paths import FIXTURES_DIR
from app.pipeline import s5_render

RULES = load_tactile_rules()
SYNTHETIC_PNG = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()
SYNTHETIC_REGIONS = {
    r["id"]: r
    for r in json.loads((FIXTURES_DIR / "synthetic" / "regions.json").read_text())["regions"]
}
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

    async def check_all(self, fid: str) -> dict[str, Any]:
        """The teacher marks every part checked, as Mark all parts checked does: one edit.
        Publish refuses a sheet with nothing touchable."""
        draft = (await self.http.get(f"/api/figures/{fid}/regions.json")).json()
        ids = list(dict.fromkeys(r["id"].split("_")[0] for r in draft["regions"]))
        r = await self.http.patch(
            f"/api/figures/{fid}/regions/{ids[0]}", json={"op": "check", "also": ids[1:]}
        )
        assert r.status_code == 202, r.text
        return await self.wait(fid)

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
        await api.check_all(fid)
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


def test_an_upload_after_a_pipeline_change_is_a_new_job_from_the_cached_meta_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A code change moves the pipeline version: the same image again starts a new job, and
    S1 and S2, whose keys do not hold the code, come from the cache with no Meta call."""

    async def body(api: Api) -> None:
        first = await api.upload()
        fid = first.json()["figure_id"]
        await api.wait(fid)
        calls = len(api.client.calls)
        monkeypatch.setattr("app.pipeline.runner.code_digest", lambda: "changed")
        second = await api.upload()
        assert second.status_code == 202 and second.json()["created"] is True
        assert second.json()["job"]["id"] != first.json()["job"]["id"]
        done = await api.wait(fid)
        outcomes = {s["stage"]: s["outcome"] for s in done["job"]["stages"]}
        assert outcomes == {"s0": "cached", "s1": "cached", "s2": "cached",
                            "s3": "ran", "s4": "ran", "s5": "ran"}  # fmt: skip
        assert len(api.client.calls) == calls
        third = await api.upload()  # the same pipeline again: that job
        assert third.json()["created"] is False
        assert third.json()["job"]["id"] == second.json()["job"]["id"]

    run(tmp_path, body)


def test_a_version_2_job_database_is_migrated_and_its_jobs_are_not_reused(tmp_path: Path) -> None:
    """The dev database from before Oct 30: its tables and rows stay; its jobs have no
    pipeline version, so an upload of the same figure starts a new one."""
    import sqlite3  # noqa: PLC0415

    from app.pipeline.jobs import JobOptions, JobStore  # noqa: PLC0415

    path = tmp_path / "jobs.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, figure_id TEXT NOT NULL, status TEXT NOT "
            "NULL, stage TEXT, options TEXT NOT NULL, edit_version INTEGER NOT NULL, result_key "
            "TEXT, error_code TEXT, error_message TEXT, created_at TEXT NOT NULL, updated_at "
            "TEXT NOT NULL);"
            "INSERT INTO jobs VALUES ('old', '" + "f" * 64 + "', 'done', NULL, "
            "'{\"page\":\"letter\",\"grade_band\":null}', 0, 'k', NULL, NULL, 't', 't');"
            "PRAGMA user_version = 2;"
        )
    store = JobStore(path)
    old = store.get("old")
    assert old is not None and old.status == "done" and old.pipeline is None
    assert store.find_live("f" * 64, JobOptions(), 0, "now") is None
    new = store.create("f" * 64, JobOptions(), 0, "now")
    assert store.find_live("f" * 64, JobOptions(), 0, "now") == new


def test_a_part_is_touchable_only_once_the_teacher_checks_it(tmp_path: Path) -> None:
    """Touch requires the teacher's check (Oct 30): a fresh draft has no touchable part;
    one check edit can name many regions; neighbors name touchable regions only."""
    from app.models.regions import RegionsFile, check_references  # noqa: PLC0415

    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        draft = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        assert not any(r["touchable"] or r["verified_by_teacher"] for r in draft["regions"])
        assert all(not r.get("neighbors") for r in draft["regions"])
        r = await api.http.patch(f"/api/figures/{fid}/regions/r1",
                                 json={"op": "check", "also": ["r2", "r9"]})  # fmt: skip
        assert r.status_code == 202, r.text
        await api.wait(fid)
        after = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        touch = {x["id"].partition("_")[0] for x in after["regions"] if x["touchable"]}
        assert touch == {"r1", "r2", "r9"}
        assert all(x["verified_by_teacher"] == x["touchable"] for x in after["regions"])
        for x in after["regions"]:
            assert {n["id"].partition("_")[0] for n in x.get("neighbors", [])} <= touch
        assert check_references(RegionsFile.from_json_obj(after)) == []
        bad = await api.http.patch(f"/api/figures/{fid}/regions/r1",
                                   json={"op": "check", "also": ["r99"]})  # fmt: skip
        assert_envelope(bad, 422, "edit_invalid")
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201
        # Author's overlap warnings are a draft file for the teacher, never published.
        warned = await api.http.get(f"/api/figures/{fid}/warnings.json")
        assert warned.status_code == 200 and isinstance(warned.json(), list)
        pub = (await api.http.get(f"/api/figures/{fid}/published")).json()
        assert "warnings.json" not in json.dumps(pub)

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
        await api.check_all(fid)
        base = f"/api/figures/{fid}"
        a, b = await asyncio.gather(api.http.post(f"{base}/publish"),
                                    api.http.post(f"{base}/publish"))  # fmt: skip
        assert sorted([a.status_code, b.status_code]) == [200, 201]
        assert a.json()["version"] == b.json()["version"] == 1
        edits = await asyncio.gather(
            api.http.patch(f"{base}/regions/r1", json={"op": "label", "label": "shell"}),
            api.http.patch(f"{base}/regions/r2", json={"op": "label", "label": "kernel"}),
        )
        assert sorted(r.json()["edit_version"] for r in edits) == [2, 3]  # 1 is the check
        status = await api.wait(fid)
        assert status["job"]["edit_version"] == 3
        labels = {x["id"]: x["label"] for x in
                  (await api.http.get(f"{base}/regions.json")).json()["regions"]}  # fmt: skip
        assert (labels["r1"], labels["r2"]) == ("shell", "kernel")

    run(tmp_path, body)


PLANTED = "too close"


@pytest.fixture
def planted_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    """S5's rules check also reports a gap violation on any part labelled PLANTED, the way it
    would if layout had missed one. A teacher fixes it by relabelling the part."""
    real = s5_render.validate_sheet

    def check(sheet: Sheet, rules: TactileRules) -> list[Violation]:
        planted = [
            Violation(
                rule="min_gap",
                regions=[r.id],
                measured=2.01,
                limit=rules.spacing.min_gap_mm,
                message=f"{r.id} is 2.01 mm from its neighbor",
            )
            for r in sheet.regions
            if r.label == PLANTED
        ]
        return real(sheet, rules) + planted

    monkeypatch.setattr(s5_render, "validate_sheet", check)


@pytest.mark.usefixtures("planted_violation")
def test_publish_refuses_a_version_that_breaks_a_rule(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        r = await api.http.patch(f"/api/figures/{fid}/regions/r3",
                                 json={"op": "label", "label": PLANTED})  # fmt: skip
        assert r.status_code == 202
        await api.wait(fid)
        draft = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        assert {x["id"]: x["label"] for x in draft["regions"]}["r3"] == PLANTED

        for attempt in ({}, {"force": True}, {"override": True}):  # there is no override
            r = await api.http.post(f"/api/figures/{fid}/publish", json=attempt)
            assert_envelope(r, 409, "rules_violated")
            err = r.json()["error"]
            assert err["retryable"] is False
            assert err["edit_version"] == 1
            assert err["violations"] == [{"regions": ["r3"], "rule": "min_gap", "measured": 2.01,
                                          "limit": RULES.spacing.min_gap_mm}]  # fmt: skip
        status = (await api.http.get(f"/api/figures/{fid}")).json()
        assert status["published"] == []
        assert not (tmp_path / "published" / fid).exists()

        # The fixing edit makes a new version, and that version publishes.
        r = await api.http.patch(f"/api/figures/{fid}/regions/r3",
                                 json={"op": "label", "label": "left lobe"})  # fmt: skip
        assert r.status_code == 202
        await api.wait(fid)
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert r.status_code == 201, r.text
        assert r.json()["version"] == 1
        assert r.json()["edit_version"] == 2
        pub = (await api.http.get(f"/api/figures/{fid}/published/1/regions.json")).json()
        assert {x["id"]: x["label"] for x in pub["regions"]}["r3"] == "left lobe"

    run(tmp_path, body)


@pytest.mark.usefixtures("planted_violation")
def test_publish_checks_the_report_of_the_exact_version(tmp_path: Path) -> None:
    """A clean version 1 is published; an edit that breaks a rule cannot replace it, and
    Explore keeps getting version 1."""

    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.check_all(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201
        await api.http.patch(f"/api/figures/{fid}/regions/r3",
                                 json={"op": "label", "label": PLANTED})  # fmt: skip
        await api.wait(fid)
        assert_envelope(await api.http.post(f"/api/figures/{fid}/publish"), 409, "rules_violated")
        index = (await api.http.get(f"/api/figures/{fid}/published")).json()
        assert index["latest"] == 1
        latest = (await api.http.get(f"/api/figures/{fid}/published/latest/regions.json")).json()
        assert PLANTED not in {x["label"] for x in latest["regions"]}

    run(tmp_path, body)


def test_a_version_with_no_report_is_never_published(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        job = api.service.jobs.latest_done(fid)
        assert job is not None
        out = api.service.runner.output_dir(job)
        assert out is not None
        (out / s5_render.REPORT_FILE).unlink()
        assert_envelope(await api.http.post(f"/api/figures/{fid}/publish"), 409, "rules_unchecked")
        assert (await api.http.get(f"/api/figures/{fid}")).json()["published"] == []

    run(tmp_path, body)


@pytest.mark.usefixtures("planted_violation")
def test_explore_can_never_load_an_unpublished_version(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        names = ("regions.json", "tactile.svg", "print.pdf")

        def explore_urls(versions: tuple[str, ...]) -> list[str]:
            return [f"/api/figures/{fid}/published/{v}/{n}" for v in versions for n in names]

        # Nothing published: every Explore path is a 404, even though a draft exists.
        assert (await api.http.get(f"/api/figures/{fid}/regions.json")).status_code == 200
        assert_envelope(await api.http.get(f"/api/figures/{fid}/published"), 404, "not_published")
        for url in explore_urls(("latest", "0", "1", "2", "-1")):
            assert_envelope(await api.http.get(url), 404, "not_published")

        # A refused version stays invisible to Explore.
        await api.http.patch(f"/api/figures/{fid}/regions/r3",
                             json={"op": "label", "label": PLANTED})  # fmt: skip
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 409
        for url in explore_urls(("latest", "1")):
            assert_envelope(await api.http.get(url), 404, "not_published")

        # After a fix and a publish, Explore sees version 1 only, and newer drafts never leak.
        await api.http.patch(f"/api/figures/{fid}/regions/r3",
                             json={"op": "label", "label": "left lobe"})  # fmt: skip
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201
        await api.http.patch(f"/api/figures/{fid}/regions/r1",
                             json={"op": "label", "label": "draft only"})  # fmt: skip
        await api.wait(fid)
        draft = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        assert "draft only" in {x["label"] for x in draft["regions"]}
        for v in ("latest", "1"):
            r = await api.http.get(f"/api/figures/{fid}/published/{v}/regions.json")
            assert "draft only" not in {x["label"] for x in r.json()["regions"]}
        for url in explore_urls(("2",)):
            assert_envelope(await api.http.get(url), 404, "not_published")

    run(tmp_path, body)


def test_the_teacher_gets_the_source_image_and_the_draft_rules_report(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.check_all(fid)
        r = await api.http.get(f"/api/figures/{fid}/source.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        with Image.open(io.BytesIO(r.content)) as img:
            assert img.size == Image.open(io.BytesIO(SYNTHETIC_PNG)).size
        r = await api.http.get(f"/api/figures/{fid}/report.json")
        assert r.status_code == 200
        assert r.json() == []

        # Neither is part of a published version, and Explore cannot ask for them there.
        pub = (await api.http.post(f"/api/figures/{fid}/publish")).json()
        assert set(pub["files"]) == {"regions.json", "tactile.svg", "print.pdf"}
        for name in ("source.png", "report.json"):
            r = await api.http.get(f"/api/figures/{fid}/published/1/{name}")
            assert_envelope(r, 404, "not_found")

    run(tmp_path, body)


@pytest.mark.usefixtures("planted_violation")
def test_the_draft_report_lists_what_publish_would_refuse(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.http.patch(f"/api/figures/{fid}/regions/r3",
                             json={"op": "label", "label": PLANTED})  # fmt: skip
        await api.wait(fid)
        report = (await api.http.get(f"/api/figures/{fid}/report.json")).json()
        assert [(v["rule"], v["regions"]) for v in report] == [("min_gap", ["r3"])]
        refused = (await api.http.post(f"/api/figures/{fid}/publish")).json()["error"]
        assert [(v["rule"], v["regions"]) for v in refused["violations"]] == [("min_gap", ["r3"])]

    run(tmp_path, body)


@pytest.fixture
def merge_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    """S5's rules check also reports a gap violation on any part other than the right lobe
    that reaches over the right lobe's spot, as merging the right lobe into its neighbor
    does. Layout repairs every real gap a merge makes on the synthetic figure, so the
    violation is planted, but it follows the merged geometry, not a label."""
    real = s5_render.validate_sheet
    spot = Point(SYNTHETIC_REGIONS["r8"]["centroid_mm"])

    def check(sheet: Sheet, rules: TactileRules) -> list[Violation]:
        planted = [
            Violation(
                rule="min_gap",
                regions=[r.id],
                measured=1.5,
                limit=rules.spacing.min_gap_mm,
                message=f"{r.id} is 1.5 mm from its neighbor",
            )
            for r in sheet.regions
            if r.id != "r8" and r.polygon.contains(spot)
        ]
        return real(sheet, rules) + planted

    monkeypatch.setattr(s5_render, "validate_sheet", check)


@pytest.mark.usefixtures("merge_violation")
def test_a_merge_that_breaks_a_rule_is_refused_naming_the_merged_part(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        assert (await api.http.get(f"/api/figures/{fid}/report.json")).json() == []

        r = await api.http.patch(
            f"/api/figures/{fid}/regions/r8", json={"op": "merge", "into": "r7"}
        )
        assert r.status_code == 202
        status = await api.wait(fid)
        assert status["edit_version"] == 1
        draft = {
            x["id"]: x
            for x in (await api.http.get(f"/api/figures/{fid}/regions.json")).json()["regions"]
        }
        assert "r8" not in draft
        assert (draft["r7"]["label"], draft["r7"]["verified_by_teacher"]) == ("left lobe", True)

        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert_envelope(r, 409, "rules_violated")
        err = r.json()["error"]
        assert err["edit_version"] == 1
        assert err["violations"] == [{"regions": ["r7"], "rule": "min_gap", "measured": 1.5,
                                      "limit": RULES.spacing.min_gap_mm}]  # fmt: skip
        assert (await api.http.get(f"/api/figures/{fid}")).json()["published"] == []
        assert_envelope(await api.http.get(f"/api/figures/{fid}/published/latest/regions.json"),
                        404, "not_published")  # fmt: skip

    run(tmp_path, body)


@pytest.mark.usefixtures("planted_violation")
def test_deleting_a_part_recomputes_the_report_for_the_new_version(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.http.patch(
            f"/api/figures/{fid}/regions/r3", json={"op": "label", "label": PLANTED}
        )
        await api.wait(fid)
        job1 = api.service.jobs.latest_done(fid)
        assert job1 is not None and job1.edit_version == 1
        report1 = api.service.runner.output_dir(job1)
        assert report1 is not None
        assert [
            v["regions"] for v in (await api.http.get(f"/api/figures/{fid}/report.json")).json()
        ] == [["r3"]]
        assert_envelope(await api.http.post(f"/api/figures/{fid}/publish"), 409, "rules_violated")

        r = await api.http.patch(f"/api/figures/{fid}/regions/r3", json={"op": "delete"})
        assert r.status_code == 202
        status = await api.wait(fid)
        assert status["edit_version"] == 2
        job2 = api.service.jobs.latest_done(fid)
        assert job2 is not None and job2.edit_version == 2
        report2 = api.service.runner.output_dir(job2)
        assert report2 is not None and report2 != report1

        # Version 2 has its own report, made by its own S5 run; version 1's still lists r3.
        assert outcomes(status)["s5"] == "ran"
        assert json.loads((report2 / s5_render.REPORT_FILE).read_text()) == []
        assert [
            v["regions"] for v in json.loads((report1 / s5_render.REPORT_FILE).read_text())
        ] == [["r3"]]
        assert (await api.http.get(f"/api/figures/{fid}/report.json")).json() == []
        draft = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        assert "r3" not in {x["id"] for x in draft["regions"]}

        await api.check_all(fid)  # edit 3: publish needs a touchable part
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert r.status_code == 201, r.text
        assert (r.json()["version"], r.json()["edit_version"]) == (1, 3)

    run(tmp_path, body)


def test_draft_only_files_never_reach_a_published_version(tmp_path: Path) -> None:
    """The source image and the rules report are for the teacher's review. No published
    version serves them, holds them on disk, or points at them from regions.json."""

    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.check_all(fid)
        source = (await api.http.get(f"/api/figures/{fid}/source.png")).content
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201
        await api.http.patch(
            f"/api/figures/{fid}/regions/r1", json={"op": "label", "label": "chamber"}
        )
        await api.wait(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201

        for v in ("1", "2", "latest", "3", "0"):
            for name in ("source.png", "report.json"):
                r = await api.http.get(f"/api/figures/{fid}/published/{v}/{name}")
                assert r.status_code in (403, 404), (v, name, r.status_code)
                assert r.headers["content-type"].startswith("application/json")
                assert source not in r.content

        index = (await api.http.get(f"/api/figures/{fid}/published")).json()
        assert [set(p["files"]) for p in index["versions"]] == [
            {"regions.json", "tactile.svg", "print.pdf"}
        ] * 2
        on_disk = [p for p in (tmp_path / "published" / fid).rglob("*") if p.is_file()]
        assert on_disk
        assert not {p.name for p in on_disk} & {"source.png", "report.json"}
        assert all(p.read_bytes() != source for p in on_disk)
        for v in ("1", "2"):
            text = (await api.http.get(f"/api/figures/{fid}/published/{v}/regions.json")).text
            assert "source.png" not in text and "report.json" not in text
            assert "rules" not in json.loads(text) and "violations" not in text

    run(tmp_path, body)


def test_the_planted_violations_never_fire_in_production(tmp_path: Path) -> None:
    """planted_violation and merge_violation are test fixtures that wrap S5's rules check.
    Nothing outside this file defines them. Without them S5 runs the real check, and the
    same merge and the same label give an empty report and a version that publishes."""
    assert s5_render.validate_sheet is validate_sheet

    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        await api.http.patch(f"/api/figures/{fid}/regions/r8", json={"op": "merge", "into": "r7"})
        await api.wait(fid)
        await api.http.patch(
            f"/api/figures/{fid}/regions/r3", json={"op": "label", "label": PLANTED}
        )
        status = await api.wait(fid)
        assert status["edit_version"] == 2
        draft = (await api.http.get(f"/api/figures/{fid}/regions.json")).json()
        labels = {x["id"]: x["label"] for x in draft["regions"]}
        assert "r8" not in labels and labels["r3"] == PLANTED
        assert (await api.http.get(f"/api/figures/{fid}/report.json")).json() == []
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert r.status_code == 201, r.text

    run(tmp_path, body)


def test_publish_is_refused_until_a_part_is_checked(tmp_path: Path) -> None:
    async def body(api: Api) -> None:
        fid = (await api.upload()).json()["figure_id"]
        await api.wait(fid)
        r = await api.http.post(f"/api/figures/{fid}/publish")
        assert_envelope(r, 409, "nothing_touchable")
        assert r.json()["error"]["message"] == NOTHING_TOUCHABLE
        assert (await api.http.get(f"/api/figures/{fid}")).json()["published"] == []
        await api.check_all(fid)
        assert (await api.http.post(f"/api/figures/{fid}/publish")).status_code == 201

    run(tmp_path, body)
