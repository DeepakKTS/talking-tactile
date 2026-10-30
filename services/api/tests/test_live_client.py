"""The live Meta client with no network: S1 as a listing call and a locate call merged into
the parts, SAM point prompts decoded to full-size masks, and a fresh call count per job with
one shared meter and ledger."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from meta_sam_parser._mask_codec import _encode_raster

from app.config import load_tactile_rules
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from app.meta.live_client import LiveMetaClient, merge_located
from app.meta.types import SheetContext, Understanding
from app.pipeline import s1_understand, s2_ground
from app.prompts import load_prompt
from tests.test_s2_bakeoff import chat
from tests.test_sam_diagnostic import answer, sse

RULES = load_tactile_rules()
S1 = load_prompt(s1_understand.PROMPT)
LOCATE = load_prompt(s1_understand.LOCATE_PROMPT)
S2 = load_prompt(s2_ground.PROMPT)
IMAGE = np.full((120, 200, 3), 255, np.uint8)

LISTING = {
    "figure_type": "labeled_diagram",
    "title": "Boxes",
    "summary": "Two boxes.",
    "parts": [
        {"phrase": "left box", "print_label": "left"},
        {"phrase": "right box", "print_label": ""},
        {"phrase": "boxes", "print_label": ""},
    ],
    "color_carries_meaning": False,
    "verdict": "make_tactile",
    "verdict_reason": "ok",
}
LOCATED = {
    "subject": " boxes ",
    "parts": [
        {
            "part": "left box",
            "kind": "area",
            "members": [],
            "parent": "boxes",
            "separates": [],
            "instances": [
                {"where": "main", "points": [{"x": 150, "y": 500}, {"x": 300, "y": 500}]}
            ],
        },
        {
            "part": "boxes",
            "kind": "group",
            "members": ["left box", "right box", "a part not listed"],
            "parent": "",
            "separates": [],
            "instances": [],
        },
        {
            "part": "a part not listed",
            "kind": "area",
            "members": [],
            "parent": "",
            "separates": [],
            "instances": [],
        },
    ],
    "shares_region": [],
}
SHEET = SheetContext(reader=" in grades 6 to 8", width_mm=165.1, height_mm=99.06,
                     min_part_mm=6.4, gap_mm=3.2)  # fmt: skip


def box_mask(x0: int, x1: int) -> tuple[int, int, int, int, Any]:
    return (x0, 12, x1, 98, np.ones((86, x1 - x0), bool))


def sam_answer(boxes: list[tuple[int, int, int, int, Any]]) -> httpx.Response:
    """One record per object: ids from 1, half-open bounds and a raster the bounds' size."""
    text = "<0f>" + ",".join(
        f"{i}<|box;x1={x0};y1={y0};x2={x1 - 1};y2={y1 - 1};w=200;h=120;c=0.8|>"
        f"<|mask;x=0;y=0;c=0.8;data={r.shape[0]},{r.shape[1]},"
        f"{_encode_raster(r.astype(int).ravel().tolist(), r.shape[1], r.shape[0])}|>"
        for i, (x0, y0, x1, y1, r) in enumerate(boxes, 1)
    )
    return sse(answer(text))


def client(tmp_path: Path, seen: list[dict[str, Any]]) -> tuple[LiveMetaClient, Ledger, CostMeter]:
    ledger, meter = Ledger(tmp_path / "ledger.jsonl"), CostMeter(RULES.meta)

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        seen.append(body)
        if request.url.path.endswith("/responses"):
            return sam_answer([box_mask(12, 88), box_mask(112, 188)])
        name = body["response_format"]["json_schema"]["name"]
        return chat(json.dumps(LISTING if name == "FigureUnderstanding" else LOCATED))

    def caller() -> LiveCaller:
        return LiveCaller(
            key="test-key",
            base_url="https://api.meta.ai/v1",
            ledger=ledger,
            meter=meter,
            cap=RULES.meta.live_call_cap,
            transport=httpx.MockTransport(handler),
        )

    return LiveMetaClient(RULES.meta, caller), ledger, meter


def test_s1_lists_then_locates_and_merges_by_exact_name(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    live, _, _ = client(tmp_path, seen)
    u = asyncio.run(live.understand(IMAGE, "f" * 64, S1, LOCATE, SHEET))
    assert [b["response_format"]["json_schema"]["name"] for b in seen] == [
        "FigureUnderstanding",
        "PartPoints",
    ]
    assert all(b["reasoning_effort"] == "medium" for b in seen)
    text = seen[1]["messages"][0]["content"][0]["text"]
    assert text.startswith(
        "The image is a science figure that will become a raised-line tactile graphic for a "
        "blind student in grades 6 to 8. It will print 165 mm wide and 99 mm tall. On the "
        "sheet, a part a fingertip can explore is at least 6.4 mm across, and raised outlines "
        "are at least 3.2 mm apart."
    )
    assert '"left box" (printed label "left"); "right box"; "boxes".' in text
    assert u.located and u.subject == "boxes" and u.shares_region == []
    left, right, group = u.parts
    assert (left.kind, left.parent, len(left.instances[0].points)) == ("area", "boxes", 2)
    assert right.kind is None and right.instances == ()  # not in the answer: the teacher's
    assert (group.kind, group.members) == ("group", ("left box", "right box"))
    assert live._caller.cap == 2 + 2 * 3  # set once the listing names 3 parts


def test_a_describe_only_figure_is_not_located(tmp_path: Path) -> None:
    u = Understanding.model_validate(LISTING | {"verdict": "describe_only"})
    assert not merge_located(u, {"parts": []}).parts[0].kind


def test_point_prompts_come_back_as_full_size_masks_per_object(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    live, _, _ = client(tmp_path, seen)
    objects = [([(30, 60)], [(150, 60)]), ([(150, 60)], [])]
    answer = asyncio.run(live.segment_points(IMAGE, "f" * 64, "left box", objects, S2, retry=True))
    assert [a.object_id for a in answer] == [1, 2]
    assert answer[0].mask.shape == (120, 200) and int(answer[0].mask.sum()) == 76 * 86
    assert seen[0]["input"][0]["content"][0]["text"] == (
        "<0f>1<|point;x=30;y=60;w=200;h=120|>-<|point;x=150;y=60;w=200;h=120|>,"
        "2<|point;x=150;y=60;w=200;h=120|>"
    )


def test_each_job_counts_its_own_calls_and_shares_the_meter_and_ledger(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    live, ledger, meter = client(tmp_path, seen)
    first = live.for_job()
    asyncio.run(first.understand(IMAGE, "f" * 64, S1, LOCATE, SHEET))
    second = live.for_job()
    assert isinstance(first, LiveMetaClient) and isinstance(second, LiveMetaClient)
    assert (first.calls, second.calls) == (2, 0)
    assert second.meter is meter and meter.spent_usd > 0
    assert len(ledger.path.read_text().splitlines()) == 2


PLAN_LISTING = Understanding.model_validate(
    LISTING
    | {
        "parts": [
            {"phrase": p, "print_label": p}
            for p in ("frontal lobe", "central sulcus", "parietal lobe", "pons", "medulla", "gyrus")
        ]
    }
)


def item(part: str, kind: str, **kw: Any) -> dict[str, Any]:
    point = [{"where": "main", "points": [{"x": 10, "y": 10}]}]
    return {"part": part, "kind": kind, "members": [], "parent": "", "separates": [],
            "instances": point} | kw  # fmt: skip


def test_the_plan_keeps_lines_without_points_and_checks_names_against_the_listing() -> None:
    answer = {
        "subject": "brain",
        "parts": [
            item("frontal lobe", "area"),
            item("central sulcus", "line", separates=["frontal lobe", "parietal lobe"]),
            item("parietal lobe", "area", parent="parietal lobe"),  # its own parent: dropped
            item("pons", "area"),
            item("medulla", "line", separates=["pons", "nowhere"], parent="pons"),
            item("gyrus", "area", parent="frontal lobe", separates=["pons", "medulla"]),
        ],
        "shares_region": [
            {"parts": ["pons", "medulla", "nowhere"], "name": "brainstem"},  # medulla: a line
            {"parts": ["pons", "frontal lobe", "pons"], "name": ""},
        ],
    }
    u = merge_located(PLAN_LISTING, answer)
    by = {p.phrase: p for p in u.parts}
    sulcus = by["central sulcus"]
    assert (sulcus.kind, sulcus.separates, sulcus.instances) == (
        "line",
        ("frontal lobe", "parietal lobe"),
        (),
    )
    assert by["parietal lobe"].parent == ""
    medulla = by["medulla"]  # separates an area that is not listed: a line under its parent
    assert (medulla.separates, medulla.parent, medulla.instances) == ((), "pons", ())
    gyrus = by["gyrus"]  # an area separates nothing
    assert (gyrus.parent, gyrus.separates, len(gyrus.instances)) == ("frontal lobe", (), 1)
    assert u.subject == "brain"
    assert [(s.parts, s.name) for s in u.shares_region] == [
        (("pons", "frontal lobe"), "pons and frontal lobe")]  # fmt: skip
