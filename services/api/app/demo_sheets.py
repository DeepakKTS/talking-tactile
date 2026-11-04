"""The two demo sheets as the question eval published them, from a fresh clone, in mock mode:
the heart (the aortic arch merge, every part checked, two teacher descriptions) and the Commons
brain (grade band 6 to 8, every part checked, two descriptions). Mock answers to typed
questions, and the question eval's replay, exist only for these sheets.

    make demo-sheets        # or: cd services/api && uv run python -m app.demo_sheets

No network and nothing spent: the pipeline answers from fixtures/recorded/. Writes into data/,
as make dev serves it. It replays the teacher's edits behind each published version 4 through
the API, publishes, and checks the result equals fixtures/qa/<figure>_v4_regions.json. A figure
whose edits already differ from those is left alone, with a message saying why."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from app.config import load_tactile_rules
from app.main import create_app
from app.meta.client import make_client
from app.paths import DATA_DIR, FIXTURES_DIR

# name: (image, upload form, the teacher's edits in order, as stored for published version 4)
SHEETS: dict[str, tuple[Path, dict[str, str], list[dict[str, Any]]]] = {
    "heart": (
        FIXTURES_DIR / "heart.png",
        {},
        [
            {"op": "merge", "region": "r1", "into": "r10"},
            {"op": "merge", "region": "r8", "into": "r10"},
            {"op": "merge", "region": "r9", "into": "r10"},
            {"op": "label", "region": "r10", "label": "aortic arch"},
            {"op": "check", "region": "r2",
             "also": ["r3", "r4", "r5", "r6", "r7", "r11", "r12", "r13", "r14"]},
            {"op": "describe", "region": "r14", "description":
             "The left ventricle pumps blood out to the whole body through the aortic arch."},
            {"op": "describe", "region": "r5",
             "description": "The right atrium collects blood coming back from the body."},
        ],
    ),
    "brain_lobes": (
        FIXTURES_DIR / "eval" / "brain_lobes.png",
        {"grade_band": "6_8"},
        [
            {"op": "check", "region": "r1", "also": ["r2", "r3", "r4", "r5"]},
            {"op": "describe", "region": "r1", "description":
             "The frontal lobe helps you plan, make choices and move your body."},
            {"op": "describe", "region": "r4",
             "description": "The occipital lobe makes sense of what your eyes see."},
        ],
    ),
}  # fmt: skip


class SheetError(Exception):
    """A demo sheet could not be made as the eval published it; the message says why."""


def fixture(name: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((FIXTURES_DIR / "qa" / f"{name}_v4_regions.json").read_text())
    return out


def eval_version(service: Any, figure_id: str, name: str) -> int:
    """The published version that is the eval's sheet: the newest whose regions.json equals the
    committed fixture. Version 4 on the machine the eval ran on; 1 after make demo-sheets."""
    want = fixture(name)
    for pub in reversed(service.publications.list(figure_id)):
        path = service.publications.path(pub, "regions.json")
        if json.loads(path.read_text("utf-8")) == want:
            return int(pub.version)
    raise SheetError(
        f"No published version of {name} is the question eval's sheet. Run make demo-sheets."
    )


async def _wait(http: httpx.AsyncClient, service: Any, fid: str) -> dict[str, Any]:
    await service.drain()
    body: dict[str, Any] = (await http.get(f"/api/figures/{fid}")).json()
    if body["job"]["status"] != "done":
        raise SheetError(f"The pipeline stopped: {body['job']}")
    return body


async def make(name: str, http: httpx.AsyncClient, service: Any) -> tuple[str, int]:
    image, form, edits = SHEETS[name]
    files = {"file": (image.name, image.read_bytes(), "application/octet-stream")}
    r = await http.post("/api/figures", files=files, data=form)
    if r.status_code not in (httpx.codes.OK, httpx.codes.ACCEPTED):
        raise SheetError(f"{name}: the upload was refused: {r.text}")
    fid = str(r.json()["figure_id"])
    await _wait(http, service, fid)
    try:
        return fid, eval_version(service, fid, name)  # already there: nothing to do
    except SheetError:
        pass
    stored = service.runner.edits
    done = [
        e.model_dump(mode="json", exclude_defaults=True)
        for e in stored.list(fid, stored.version(fid))
    ]
    if done != edits[: len(done)]:
        raise SheetError(
            f"{name} already has other edits in this data folder, so it cannot become the "
            "eval's sheet here. Run this on a fresh clone, or move data/ aside first."
        )
    for edit in edits[len(done) :]:
        body = {k: v for k, v in edit.items() if k != "region"}
        r = await http.patch(f"/api/figures/{fid}/regions/{edit['region']}", json=body)
        if r.status_code != httpx.codes.ACCEPTED:
            raise SheetError(f"{name}: an edit was refused: {r.text}")
        await _wait(http, service, fid)
    r = await http.post(f"/api/figures/{fid}/publish")
    if r.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
        raise SheetError(f"{name}: publish was refused: {r.text}")
    return fid, eval_version(service, fid, name)


async def main_async(data_dir: Path = DATA_DIR) -> list[tuple[str, str, int]]:
    rules = load_tactile_rules()
    app = create_app(data_dir=data_dir, client=make_client(True, rules.meta))
    service = app.state.figure_service()
    out = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://demo-sheets"
    ) as http:
        for name in SHEETS:
            fid, version = await make(name, http, service)
            out.append((name, fid, version))
    return out


def main() -> None:
    if os.environ.get("LIVE") == "1":
        sys.exit("demo-sheets runs in mock mode only; unset LIVE.")
    try:
        made = asyncio.run(main_async())
    except SheetError as exc:
        sys.exit(str(exc))
    print("The question eval's sheets, published. With MOCK_META=1 make dev running, open:")
    for name, fid, version in made:
        print(f"  {name}: http://localhost:5173/explore?figure={fid}&version={version}")


if __name__ == "__main__":
    main()
