"""Fix outline through the API with no network, on the synthetic figure in points mode (the
fake live client of test_runner_points): preview, the cache, refused points, accept as an
edit that re-runs S3 and later only, and publish with the part touchable."""

import asyncio
import json
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np

from app.main import create_app
from app.models.regions import RegionsFile
from app.paths import FIXTURES_DIR
from tests.test_runner_points import MASKS, FakeLive, W

FIGURE = (FIXTURES_DIR / "synthetic" / "figure.png").read_bytes()


def inside(phrase: str) -> list[int]:
    d = cv2.distanceTransform(MASKS[phrase].astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(d.argmax()), d.shape)
    return [int(x), int(y)]


async def session(root: Path, client: FakeLive, body: Any) -> dict[str, Any]:
    app = create_app(data_dir=root, client=client)  # type: ignore[arg-type]
    service = app.state.figure_service()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        fid = (
            await http.post("/api/figures", files={"file": ("f.png", FIGURE, "image/png")})
        ).json()["figure_id"]
        await service.drain()
        out: dict[str, Any] = {"fid": fid}
        await body(http, service, fid, out)
        return out


def run(root: Path, client: FakeLive, body: Any) -> dict[str, Any]:
    return asyncio.run(session(root, client, body))


def test_preview_cache_accept_and_publish_a_spill_part(tmp_path: Path) -> None:
    client = FakeLive()
    point = inside("right chamber")

    async def body(http: httpx.AsyncClient, service: Any, fid: str, out: dict[str, Any]) -> None:
        base = f"/api/figures/{fid}"
        draft = (await http.get(f"{base}/regions.json")).json()
        (spill,) = [r for r in draft["regions"] if not r["touchable"]]
        assert spill["label"] == "right chamber"
        sid = spill["id"]
        empty = (await http.post(f"{base}/regions/{sid}/fix", json={"positive": []})).json()
        assert empty["outcome"] is None and empty["image"].startswith("data:image/png;base64,")
        assert (empty["width"], empty["part"]) == (W, "right chamber")
        off = await http.post(f"{base}/regions/{sid}/fix", json={"positive": [[2, 2]]})
        assert off.status_code == 422 and off.json()["error"]["code"] == "point_refused"
        first = (await http.post(f"{base}/regions/{sid}/fix", json={"positive": [point]})).json()
        assert first["outcome"] == "ran" and first["spill"] == [] and first["area_px"] > 0
        assert first["latency_ms"] is not None and first["call_cap"] == 30 and client.cap == 30
        again = (await http.post(f"{base}/regions/{sid}/fix", json={"positive": [point]})).json()
        assert again["outcome"] == "cached"
        assert client.calls.count("fix right chamber") == 1
        accepted = await http.patch(
            f"{base}/regions/{sid}", json={"op": "outline", "positive": [point]}
        )
        assert accepted.status_code == 202
        await service.drain()
        out["status"] = (await http.get(base)).json()
        out["draft"] = (await http.get(f"{base}/regions.json")).json()
        pub = await http.post(f"{base}/publish")
        assert pub.status_code == 201
        out["published"] = (await http.get(f"{base}/published/1/regions.json")).json()

    got = run(tmp_path, client, body)
    outcomes = {s["stage"]: s["outcome"] for s in got["status"]["job"]["stages"]}
    assert outcomes == {
        "s0": "cached",
        "s1": "cached",
        "s2": "cached",
        "s3": "ran",
        "s4": "ran",
        "s5": "ran",
    }
    assert client.calls.count("fix right chamber") == 1  # accepting used the previewed answer
    f = RegionsFile.from_json_obj(got["published"])
    chamber = [r for r in f.regions if r.label == "right chamber"]
    assert chamber and all(r.touchable and r.source == "teacher" for r in chamber)
    assert all(r.touchable for r in f.regions)
    assert got["published"] == got["draft"]


def test_fixing_a_touchable_part_keeps_the_other_regions_ids(tmp_path: Path) -> None:
    client = FakeLive()

    async def body(http: httpx.AsyncClient, service: Any, fid: str, out: dict[str, Any]) -> None:
        base = f"/api/figures/{fid}"
        before = (await http.get(f"{base}/regions.json")).json()
        lobe = next(r for r in before["regions"] if r["label"] == "left lobe")
        r = await http.patch(
            f"{base}/regions/{lobe['id']}",
            json={"op": "outline", "positive": [inside("left lobe")]},
        )
        assert r.status_code == 202
        await service.drain()
        after = (await http.get(f"{base}/regions.json")).json()
        out["before"], out["after"], out["lobe"] = before, after, lobe["id"]

    got = run(tmp_path, client, body)
    ids = lambda f: {r["label"]: r["id"] for r in f["regions"] if r["touchable"]}  # noqa: E731
    assert ids(got["after"]) == ids(got["before"])
    lobe = next(r for r in got["after"]["regions"] if r["id"] == got["lobe"])
    assert lobe["source"] == "teacher"


def test_a_part_added_by_name_or_an_unknown_region_cannot_be_fixed(tmp_path: Path) -> None:
    async def body(http: httpx.AsyncClient, service: Any, fid: str, out: dict[str, Any]) -> None:
        r = await http.post(f"/api/figures/{fid}/regions/t9/fix", json={"positive": [[10, 10]]})
        out["code"] = (r.status_code, r.json()["error"]["code"])
        r = await http.patch(
            f"/api/figures/{fid}/regions/r1", json={"op": "outline", "positive": []}
        )
        out["empty"] = (r.status_code, r.json()["error"]["code"])

    got = run(tmp_path, FakeLive(), body)
    assert got["code"] == (422, "edit_invalid")
    assert got["empty"] == (422, "invalid_request")


def test_mock_mode_without_recordings_says_fix_needs_live_mode(tmp_path: Path) -> None:
    from app.meta.mock import MockMetaClient  # noqa: PLC0415
    from tests.test_runner import RULES  # noqa: PLC0415

    async def body(http: httpx.AsyncClient, service: Any, fid: str, out: dict[str, Any]) -> None:
        regions = (await http.get(f"/api/figures/{fid}/regions.json")).json()["regions"]
        rid = regions[0]["id"]
        r = await http.post(
            f"/api/figures/{fid}/regions/{rid}/fix", json={"positive": [inside("left lobe")]}
        )
        out["fix"] = (r.status_code, r.json()["error"]["code"])

    got = run(tmp_path, MockMetaClient(RULES.meta), body)  # type: ignore[arg-type]
    assert got["fix"] == (503, "fix_unavailable")
    assert json.dumps(got)  # the answer is plain JSON
