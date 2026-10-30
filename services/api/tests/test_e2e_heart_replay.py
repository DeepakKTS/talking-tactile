"""The heart end to end through the API, on replay of the live runs of Oct 30: S1 from the
first run (fixtures/recorded/pipeline_heart_s1_*), S2 and the Fix outline calls from the run
under the per-job cap (pipeline_heart2_*: 19 SAM calls and 7 retries; then 3 fix calls for
the aorta and 3 for the left ventricle). Mock mode answers the heart from the same files
(fixtures/recorded/replays.json), so the replay client here is the mock.

1. Upload, the draft Author shows with its flags, publish, the published regions.json: it
   must equal fixtures/pipeline/heart_regions.json, the live draft, which the web tests read.
2. Fix outline as the live check did: three previews per part with the same masks and spill
   answers, accept, and the final draft must equal the live one,
   fixtures/pipeline/heart_fixed_draft.json. Its rules report refuses publishing (409)."""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.mock import MockMetaClient
from app.meta.smoke import HEART
from app.models.regions import RegionsFile, check_references
from app.paths import FIXTURES_DIR

RULES = load_tactile_rules()
DRAFT = json.loads((FIXTURES_DIR / "pipeline" / "heart_regions.json").read_text("utf-8"))
FIXED = json.loads((FIXTURES_DIR / "pipeline" / "heart_fixed_draft.json").read_text("utf-8"))
AORTA = [
    ([[1020, 340]], [], 136640),
    ([[1020, 340], [980, 520]], [], 136898),
    ([[1020, 340], [980, 520]], [[948, 249], [1099, 211], [1191, 233]], 178497),
]
LEFT_VENTRICLE = [
    ([[1480, 1120]], [], 1120),
    ([[1480, 1120], [1380, 1200]], [], 88949),
    ([[1480, 1120], [1380, 1200]], [[1052, 1054], [1351, 934]], 61417),
]
SPILL = {
    "aorta": [["brachiocephalic artery", "left common carotid artery", "left subclavian artery"]]
    * 2
    + [
        [
            "brachiocephalic artery",
            "left common carotid artery",
            "left pulmonary arteries",
            "left subclavian artery",
        ]
    ],
    "left ventricle": [[], ["chordae tendineae", "mitral valve"], ["chordae tendineae"]],
}


async def heart(body: Any) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp())
    app = create_app(data_dir=root, client=MockMetaClient(RULES.meta))
    service = app.state.figure_service()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        files = {"file": ("heart.png", HEART.read_bytes(), "image/png")}
        fid = (await http.post("/api/figures", files=files, data={"grade_band": "9_12"})).json()[
            "figure_id"
        ]
        await service.drain()
        out: dict[str, Any] = {"status": (await http.get(f"/api/figures/{fid}")).json()}
        await body(http, service, f"/api/figures/{fid}", out)
        return out


def test_the_heart_through_the_api_on_replay() -> None:
    async def body(http: httpx.AsyncClient, service: Any, base: str, out: dict[str, Any]) -> None:
        out["draft"] = (await http.get(f"{base}/regions.json")).json()
        out["report"] = (await http.get(f"{base}/report.json")).json()
        pub = await http.post(f"{base}/publish")
        out["publish"] = pub.status_code
        out["published"] = (
            await http.get(f"{base}/published/{pub.json()['version']}/regions.json")
        ).json()

    got = asyncio.run(heart(body))
    assert [s["outcome"] for s in got["status"]["job"]["stages"]] == ["ran"] * 6
    draft = RegionsFile.from_json_obj(got["draft"])
    assert draft.schema_version == 2 and check_references(draft) == []
    assert {r.label for r in draft.regions if not r.touchable} == {"aorta"}
    assert len({r.label for r in draft.regions if r.touchable}) == 18 and draft.needs_teacher == []
    thin = {r.label for r in draft.regions if any(f.reason == "thin" for f in r.flags or [])}
    assert thin == {"chordae tendineae", "mitral valve", "semilunar valves", "tricuspid valve"}
    assert got["report"] == [] and got["publish"] == 201  # flags never block publishing
    assert got["published"] == got["draft"] == DRAFT


def test_fix_outline_on_replay_gives_the_live_fixes() -> None:
    async def body(http: httpx.AsyncClient, service: Any, base: str, out: dict[str, Any]) -> None:
        for part, steps in (("aorta", AORTA), ("left ventricle", LEFT_VENTRICLE)):
            regions = (await http.get(f"{base}/regions.json")).json()["regions"]
            rid = sorted((r for r in regions if r["label"] == part), key=lambda r: r["touchable"])[
                0
            ]["id"]
            seen = []
            for pos, neg, _ in steps:
                v = (
                    await http.post(
                        f"{base}/regions/{rid}/fix", json={"positive": pos, "negative": neg}
                    )
                ).json()
                seen.append((v["outcome"], v["area_px"], v["spill"], v["warnings"]))
            out[part] = seen
            pos, neg, _ = steps[-1]
            accepted = await http.patch(
                f"{base}/regions/{rid}", json={"op": "outline", "positive": pos, "negative": neg}
            )
            assert accepted.status_code == 202
            await service.drain()
        out["draft"] = (await http.get(f"{base}/regions.json")).json()
        out["report"] = (await http.get(f"{base}/report.json")).json()
        out["publish"] = (await http.post(f"{base}/publish")).json()

    got = asyncio.run(heart(body))
    for part, steps in (("aorta", AORTA), ("left ventricle", LEFT_VENTRICLE)):
        assert got[part] == [
            ("ran", area, spill, []) for (_, _, area), spill in zip(steps, SPILL[part], strict=True)
        ]
    assert got["draft"] == FIXED
    fixed = RegionsFile.from_json_obj(got["draft"])
    teacher = {r.label for r in fixed.regions if r.source == "teacher"}
    assert teacher == {"aorta", "left ventricle"} and all(r.touchable for r in fixed.regions)
    assert sorted((v["rule"], v["regions"][0]) for v in got["report"]) == [
        ("point_symbol", "r11"),
        ("point_symbol", "r7_2"),
    ]
    assert got["publish"]["error"]["code"] == "rules_violated"  # the 409 rule still applies
