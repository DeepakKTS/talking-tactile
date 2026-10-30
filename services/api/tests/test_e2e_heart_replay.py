"""The heart end to end through the API, on replay of the live run of Oct 30
(fixtures/recorded/pipeline_heart_*.json: 2 Spark calls, 19 SAM calls, 4 retries; three more
retries were refused by the 25-call cap). Upload, the draft regions Author shows with their
flags, publish, and the published regions.json Explore loads. That file is the fixture the
web tests read (fixtures/pipeline/heart_regions.json); the replay must give it exactly."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.cost import CostMeter
from app.meta.live import DEFAULT_BASE, Ledger, LiveCaller
from app.meta.live_client import LiveMetaClient
from app.meta.record import ReplayTransport
from app.meta.smoke import HEART
from app.models.regions import RegionsFile, check_references
from app.paths import FIXTURES_DIR, RECORDED_DIR

RULES = load_tactile_rules()
FIXTURE = FIXTURES_DIR / "pipeline" / "heart_regions.json"
SPILL = {"aorta", "mitral valve", "left ventricle", "septum"}
THIN = {"tricuspid valve", "chordae tendineae", "semilunar valves"}


def replay_client(root: Path) -> LiveMetaClient:
    files = sorted(RECORDED_DIR.glob("pipeline_heart_*.json"))
    meter = CostMeter(RULES.meta)

    def caller() -> LiveCaller:
        return LiveCaller(
            key="unused-in-replay",
            base_url=DEFAULT_BASE,
            ledger=Ledger(root / "ledger.jsonl"),
            meter=meter,
            cap=RULES.meta.live_call_cap,
            transport=ReplayTransport.from_files(files),
        )

    return CappedAt25(RULES.meta, caller)


class CappedAt25(LiveMetaClient):
    """The run was made under the 25-call cap of the time; the cap decides which retries the
    recordings hold, so the replay keeps it."""

    def cap_calls(self, cap: int) -> None:
        super().cap_calls(RULES.meta.live_call_cap)

    def for_job(self) -> "CappedAt25":
        return CappedAt25(self._rules, self._make_caller, self._record_prefix)


async def author_and_publish(root: Path) -> dict[str, Any]:
    app = create_app(data_dir=root, client=replay_client(root))
    service = app.state.figure_service()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        files = {"file": ("heart.png", HEART.read_bytes(), "image/png")}
        up = await http.post("/api/figures", files=files, data={"grade_band": "9_12"})
        assert up.status_code == 202
        fid = up.json()["figure_id"]
        await service.drain()
        status = (await http.get(f"/api/figures/{fid}")).json()
        draft = (await http.get(f"/api/figures/{fid}/regions.json")).json()
        report = (await http.get(f"/api/figures/{fid}/report.json")).json()
        pub = await http.post(f"/api/figures/{fid}/publish")
        version = pub.json()["version"]
        published = await http.get(f"/api/figures/{fid}/published/{version}/regions.json")
        return {
            "status": status,
            "draft": draft,
            "report": report,
            "publish": pub.status_code,
            "published": published.json(),
        }


def test_the_heart_through_the_api_on_replay(tmp_path: Path) -> None:
    got = asyncio.run(author_and_publish(tmp_path))
    job = got["status"]["job"]
    assert job["status"] == "done", job
    assert [s["outcome"] for s in job["stages"]] == ["ran"] * 6

    draft = RegionsFile.from_json_obj(got["draft"])
    assert draft.schema_version == 2 and check_references(draft) == []
    shown = {r.label for r in draft.regions if r.touchable}
    spill = {r.label for r in draft.regions if not r.touchable}
    assert spill == SPILL and not shown & SPILL and len(shown) == 15
    assert all(r.flags and r.flags[0].reason == "spill" for r in draft.regions if not r.touchable)
    capped = [
        r.label for r in draft.regions if not r.touchable and "cap of 25" in r.flags[0].detail
    ]  # type: ignore[index]
    assert sorted(set(capped)) == ["left ventricle", "mitral valve", "septum"]
    thin = {
        r.label
        for r in draft.regions
        if r.touchable and any(f.reason == "thin" for f in r.flags or [])
    }
    assert thin == THIN
    assert draft.needs_teacher == [] and got["report"] == []

    assert got["publish"] == 201  # flags never block publishing
    assert got["published"] == got["draft"]
    assert got["published"] == json.loads(FIXTURE.read_text("utf-8"))
