"""The SAM diagnostic (Gate A step 4.1): a control photo first, then heart.png whole and by
part in two phrasings. A control with no instances stops the run, because then the request
or the decoding is wrong, not the figure. heart.png is a colored
illustration without dark outlines. Answers with instances are decoded and checked
against what the docs say: the raster is the size of its bounds and inside the image."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from meta_sam_parser._mask_codec import _encode_raster

from app.config import load_tactile_rules
from app.meta import sam_adapter, sam_diagnostic
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from app.meta.record import ReplayTransport
from app.paths import RECORDED_DIR

RULES = load_tactile_rules()
ZERO = json.loads((RECORDED_DIR / "smoke_sam_heart_left_ventricle.json").read_text())["response"][
    "events"
]


def answer(text: str) -> list[dict[str, Any]]:
    """The recorded zero-instance stream with text put in its output lane."""
    out = []
    for e in copy.deepcopy(ZERO):
        kind = e["type"]
        if kind == "response.output_text.done":
            lane = {k: e[k] for k in ("content_index", "item_id", "output_index")}
            out.append({**lane, "type": "response.output_text.delta", "delta": text})
            e["text"] = text
        elif kind == "response.content_part.done":
            e["part"]["text"] = text
        elif kind == "response.output_item.done":
            e["item"]["content"][0]["text"] = text
        elif kind == "response.completed":
            e["response"]["output"][0]["content"][0]["text"] = text
        out.append(e)
    return out


# One instance on a 40 x 30 image: inclusive box x 10..12, y 20..21, so half-open bounds
# 10..13 by 20..22 and a 2 x 3 raster, rows [1 0 0] and [1 1 1].
RASTER = [1, 0, 0, 1, 1, 1]
ONE = (
    "<0f>0<|box;x1=10;y1=20;x2=12;y2=21;w=40;h=30;c=0.9|>"
    f"<|mask;x=0;y=0;c=0.9;data=2,3,{_encode_raster(RASTER, 3, 2)}|>"
)


def sse(events: list[dict[str, Any]]) -> httpx.Response:
    text = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})


def caller(tmp_path: Path, events: list[dict[str, Any]], sent: list[str]) -> LiveCaller:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body["input"][0]["content"][0]["text"])
        return sse(events)

    return LiveCaller(
        key="test-key",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=httpx.MockTransport(handler),
    )


def test_decoded_gives_each_instance_its_box_local_raster() -> None:
    [inst] = sam_adapter.decoded(asyncio.run(sam_adapter.parse_events(answer(ONE))))
    assert inst.object_id == "0" and inst.confidence == 0.9
    assert inst.bounds == (10, 20, 13, 22)
    assert inst.error is None and inst.raster is not None
    assert inst.raster.tolist() == [[True, False, False], [True, True, True]]


def test_zero_instances_decode_to_nothing() -> None:
    assert sam_adapter.decoded(asyncio.run(sam_adapter.parse_events(ZERO))) == []


def test_the_control_runs_first_and_the_run_fits_in_15_calls() -> None:
    cases = sam_diagnostic.CASES
    assert cases[0] == sam_diagnostic.CONTROL_CASE
    assert cases[0].image.is_file() and len(cases) <= 15
    heart = [c.phrase for c in cases if c.image == sam_diagnostic.HEART]
    assert heart[0] == "heart"
    for part in ("left ventricle", "aorta", "right atrium"):
        assert len([p for p in heart if part in p]) == 2
    assert len({c.name for c in cases}) == len(cases)


def test_a_control_with_no_instances_stops_the_run(tmp_path: Path) -> None:
    sent: list[str] = []
    live = caller(tmp_path, ZERO, sent)
    rows, stopped = asyncio.run(sam_diagnostic.run(live, record=False, out_dir=None))
    assert stopped and sent == ["banana"] and live.calls == 1
    assert rows[0]["instances"] == 0


def test_every_case_with_instances_is_decoded_and_checked(tmp_path: Path) -> None:
    sent: list[str] = []
    live = caller(tmp_path, answer(ONE), sent)
    rows, stopped = asyncio.run(sam_diagnostic.run(live, record=False, out_dir=tmp_path))
    assert not stopped and sent == [c.phrase for c in sam_diagnostic.CASES]
    for row in rows:
        assert row["instances"] == 1 and row["confidences"] == [0.9]
        [check] = row["masks"]
        assert check == {
            "object_id": "0",
            "decodes": True,
            "bounds": [10, 20, 13, 22],
            "raster_hw": [2, 3],
            "raster_is_bounds_size": True,
            "raster_scale": [1.0, 1.0],
            "inside_image": True,
            "px": 4,
        }
        assert row["cost_usd"] == RULES.meta.prices_usd[RULES.meta.models.sam].per_image
        assert (tmp_path / f"{row['case']}.png").is_file()


def test_overlay_marks_the_mask_pixels_at_their_bounds() -> None:
    inst = sam_adapter.decoded(asyncio.run(sam_adapter.parse_events(answer(ONE))))[0]
    image = np.full((30, 40, 3), 255, np.uint8)
    out = sam_diagnostic.overlay(image, [inst])
    assert (out[20, 10] != 255).any() and (out[20, 11] == 255).all()
    assert (out[21, 10:13] != 255).any(axis=1).all()


def test_a_raster_smaller_than_its_bounds_is_stretched_for_the_overlay() -> None:
    """heart.png whole, Oct 29: bounds 928 x 1423, raster 668 x 1024. The overlay must not
    assume the raster is the bounds size."""
    small = sam_adapter.Decoded("0", 0.5, (4, 2, 10, 6), np.array([[True, False]] * 2), None)
    out = sam_diagnostic.overlay(np.full((10, 12, 3), 255, np.uint8), [small])
    painted = (out != 255).any(axis=2)
    assert painted[2:6, 4:7].all() and not painted[2:6, 7:10].any()
    assert painted.sum() == 12
    [check] = [sam_diagnostic.checks(small, (10, 12))]
    assert check["raster_is_bounds_size"] is False and check["raster_scale"] == [0.5, 0.3333]


def test_a_subset_of_cases_runs_only_those(tmp_path: Path) -> None:
    sent: list[str] = []
    live = caller(tmp_path, answer(ONE), sent)
    rest = sam_diagnostic.CASES[2:]
    rows, stopped = asyncio.run(sam_diagnostic.run(live, record=False, out_dir=None, cases=rest))
    assert not stopped and sent == [c.phrase for c in rest] and len(rows) == len(rest)


def test_replay_of_the_live_diagnostic(tmp_path: Path) -> None:
    """The Oct 29 live run replayed through the same code. SAM finds the banana and the whole
    heart, one instance each, and no part of the heart in either phrasing. The banana raster
    is its bounds size; the heart raster is scaled to 1024 px on its longer side."""
    live = LiveCaller(
        key="unused-in-replay",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=ReplayTransport.from_files(
            [RECORDED_DIR / f"sam_diag_{c.name}.json" for c in sam_diagnostic.CASES]
        ),
    )
    rows, stopped = asyncio.run(sam_diagnostic.run(live, record=False, out_dir=None))
    assert not stopped and live.calls == len(sam_diagnostic.CASES)
    found = {r["case"]: r["instances"] for r in rows}
    assert found.pop("control_banana") == 1 and found.pop("heart_whole") == 1
    assert set(found.values()) == {0}
    banana, heart = (r["masks"][0] for r in rows[:2])
    assert banana["decodes"] and banana["raster_is_bounds_size"] and banana["inside_image"]
    assert banana["bounds"] == [47, 44, 978, 855] and rows[0]["confidences"][0] > 0.95
    assert heart["decodes"] and not heart["raster_is_bounds_size"] and heart["inside_image"]
    assert (heart["bounds"], heart["raster_hw"]) == ([655, 136, 1583, 1559], [1024, 668])


def test_instance_count_needs_no_decoding() -> None:
    assert sam_adapter.instance_count(asyncio.run(sam_adapter.parse_events(answer(ONE)))) == 1
    assert sam_adapter.instance_count(asyncio.run(sam_adapter.parse_events(ZERO))) == 0
