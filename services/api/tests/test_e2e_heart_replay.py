"""The heart end to end through the API, on replay of the live runs of Oct 30 with S1's plan
for touch: S1 from fixtures/recorded/plan_heart_s1_*, S2 from plan2_heart_* (15 area calls,
3 retries and the subject's phrase call), and the Fix outline calls from the earlier run
under the per-job cap (pipeline_heart2_fix_*: 3 for the aorta and 3 for the left
ventricle; a fix call is matched on its points alone). Mock mode answers the heart from the
same files (fixtures/recorded/replays.json), so the replay client here is the mock.

1. Upload with no grade band, as the live run did; the draft Author shows must equal
   fixtures/pipeline/heart_regions.json, which the web tests read.
   Its rules report is empty since Oct 30: the aorta's speck and the second left pulmonary
   vein symbol are repairs (S4 leaves out a part's pieces under the point symbol floor when
   it keeps one valid piece, and a part's point symbols closer than the gap), so it publishes.
2. Fix outline: three previews per part with the recorded masks and today's spill answers,
   accept, and the final draft must equal fixtures/pipeline/heart_fixed_draft.json. It
   publishes."""

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
SPILL = {  # the aortic branches share the aorta's region, so they are no spill for it
    "aorta": [[], [], ["left pulmonary arteries"]],
    "left ventricle": [[], ["septum"], []],
}


async def heart(body: Any) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp())
    app = create_app(data_dir=root, client=MockMetaClient(RULES.meta))
    service = app.state.figure_service()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        files = {"file": ("heart.png", HEART.read_bytes(), "image/png")}
        fid = (await http.post("/api/figures", files=files)).json()["figure_id"]
        await service.drain()
        out: dict[str, Any] = {"status": (await http.get(f"/api/figures/{fid}")).json()}
        await body(http, service, f"/api/figures/{fid}", out)
        return out


def test_the_heart_through_the_api_on_replay() -> None:
    async def body(http: httpx.AsyncClient, service: Any, base: str, out: dict[str, Any]) -> None:
        out["draft"] = (await http.get(f"{base}/regions.json")).json()
        out["report"] = (await http.get(f"{base}/report.json")).json()
        out["publish"] = (await http.post(f"{base}/publish")).status_code

    got = asyncio.run(heart(body))
    assert [s["outcome"] for s in got["status"]["job"]["stages"]] == ["ran"] * 6
    draft = RegionsFile.from_json_obj(got["draft"])
    assert draft.schema_version == 3 and check_references(draft) == []
    assert not any(r.touchable for r in draft.regions)  # nothing checked by the teacher yet
    spill = {r.label for r in draft.regions if r.flags and r.flags[0].reason == "spill"}
    assert spill == {"septum"} and draft.needs_teacher == []
    assert len({r.label for r in draft.regions} - spill) == 14
    lines = {x.label: (x.between, x.separates, x.parent) for x in draft.lines or []}
    assert lines == {  # separates and parent name touchable regions only: none yet
        "tricuspid valve": (["right atrium", "right ventricle"], None, None),
        "chordae tendineae": (None, None, None),
        "semilunar valves": (["left ventricle", "aorta"], None, None),
        "mitral valve": (["left atrium", "left ventricle"], None, None),
    }
    assert [(m.name, m.region_ids) for m in draft.merge_proposals or []] == [
        ("aortic arch", ["r1", "r8", "r9", "r10"])
    ]
    assert draft.subject is not None and draft.subject.label == "heart"
    assert got["report"] == [] and got["publish"] == 201
    assert got["draft"] == DRAFT


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
    assert teacher == {"aorta", "left ventricle"}
    assert {r.label for r in fixed.regions if r.touchable} == {"aorta", "left ventricle"}
    assert got["report"] == [] and got["publish"]["version"] == 1
