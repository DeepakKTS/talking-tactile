"""The S2 bake-off's Arm A (Gate A step 4.1b) with no network: Spark's 0-1000 grid points
mapped to source pixels, the SAM point prompt, a run on a small figure with answers from a
mock transport, and the live runs replayed. Arm B's code is gone; its results stay as data."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from PIL import Image

from app.config import load_tactile_rules
from app.meta import s2_bakeoff as bake
from app.meta import sam_adapter
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from tests.test_sam_diagnostic import ONE, answer, sse

RULES = load_tactile_rules()


def test_grid_values_map_to_integer_source_pixels() -> None:
    assert bake.to_px(0, 2048) == 0
    assert bake.to_px(500, 2048) == 1024
    assert bake.to_px(333, 1183) == 393  # floor(333 * 1183 / 1000) = floor(393.9)
    assert bake.to_px(1000, 2048) == 2047
    assert bake.to_px(1001, 2048) == 2047
    assert bake.to_px(-3, 2048) == 0


def test_points_come_from_the_first_json_array_and_only_for_listed_parts() -> None:
    content = (
        "Here you go:\n```json\n"
        '[{"object_name": "aorta", "x": 410, "y": 120},'
        ' {"object_name": "moon", "x": 1, "y": 1},'
        ' {"object_name": "aorta", "x": 9, "y": 9}]\n```'
    )
    assert bake.parse_points(content, ["aorta", "septum"]) == {"aorta": (410.0, 120.0)}
    assert bake.parse_points("I cannot see it.", ["aorta"]) == {}


def test_the_points_prompt_is_the_docs_point_mode() -> None:
    text = bake.points_prompt(["left ventricle", "aorta"])
    assert text.startswith('Point to each of the following objects in the image: "left ventricle"')
    assert "0-1000 range" in text and "omit it" in text


def test_a_point_prompt_names_one_object_in_source_pixels_and_no_phrase() -> None:
    body = sam_adapter.point_request_body("sam-3.1", b"png", (2048, 1612), (1300, 1100), {"a": "b"})
    text, image = body["input"][0]["content"]
    assert text == {"type": "input_text", "text": "<0f>1<|point;x=1300;y=1100;w=2048;h=1612|>"}
    assert image["image_url"].startswith("data:image/png;base64,")
    assert body["stream"] is True and body["metadata"] == {"a": "b"}


def small_figure(tmp_path: Path) -> bake.Figure:
    """Two outlined boxes on white, 200 x 120, saved as a PNG."""
    img = np.full((120, 200, 3), 255, np.uint8)
    for x0, x1 in ((10, 90), (110, 190)):
        img[10:12, x0:x1] = img[98:100, x0:x1] = 0
        img[10:100, x0 : x0 + 2] = img[10:100, x1 - 2 : x1] = 0
    path = tmp_path / "boxes.png"
    Image.fromarray(img).save(path)
    return bake.load_figure("boxes", path)


def chat(content: str) -> httpx.Response:
    usage = {"prompt_tokens": 100, "completion_tokens": 10}
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}}], "usage": usage}
    )


def mock_caller(tmp_path: Path, parts: list[str], seen: list[str]) -> LiveCaller:
    understanding = {
        "figure_type": "labeled_diagram",
        "title": "Boxes",
        "summary": "Two boxes.",
        "parts": [{"phrase": p, "print_label": p} for p in parts],
        "color_carries_meaning": False,
        "verdict": "make_tactile",
        "verdict_reason": "ok",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        if request.url.path.endswith("/responses"):
            seen.append(body["input"][0]["content"][0]["text"])
            return sse(answer(ONE))
        fmt = body.get("response_format", {}).get("json_schema", {}).get("name")
        seen.append(fmt or "points")
        if fmt == "FigureUnderstanding":
            return chat(json.dumps(understanding))
        return chat(json.dumps([{"object_name": "left box", "x": 250, "y": 500}]))

    return LiveCaller(
        key="test-key",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=httpx.MockTransport(handler),
    )


def test_a_run_lists_points_and_segments_each_part_spark_pointed_to(tmp_path: Path) -> None:
    seen: list[str] = []
    live = mock_caller(tmp_path, ["left box", "right box"], seen)
    run = bake.Bakeoff(live, small_figure(tmp_path))
    result = asyncio.run(run.run())
    # list, points, one SAM call for the one part Spark pointed to
    assert seen == ["FigureUnderstanding", "points", "<0f>1<|point;x=50;y=60;w=200;h=120|>"]
    a = {r["part"]: r for r in result["arm_a_rows"]}
    assert a["right box"] == {
        "part": "right box",
        "grid_point": None,
        "point_px": None,
        "instances": None,
    }
    assert a["left box"]["point_px"] == [50, 60] and a["left box"]["instances"] == 1
    assert a["left box"]["masks"][0]["raster_is_bounds_size"] is True
    assert list(run.masks) == ["left box"] and result["calls"] == 3


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_each_bakeoff_figure_is_in_the_repo(name: str) -> None:
    assert bake.FIGURES[name].is_file()


LIVE_ONLY = {"latency_ms", "cost_usd", "usage"}


def measured(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows as results.json holds them (tuples become lists), live timings left out."""
    out: list[dict[str, Any]] = json.loads(json.dumps(rows))
    return [{k: v for k, v in r.items() if k not in LIVE_ONLY} for r in out]


@pytest.mark.parametrize("name", sorted(bake.FIGURES))
def test_replay_of_the_live_bakeoff_gives_arm_a_as_measured(name: str) -> None:
    """The Oct 29 live runs, replayed: every request matches its recording (image digests
    included), and the points, instances and masks come out as in results.json."""
    live_result = json.loads((bake.OUT_ROOT / name / "results.json").read_text())
    _, result, masks = asyncio.run(bake.replay_arm_a(name))
    assert result["parts"] == live_result["parts"]
    assert measured(result["arm_a_rows"]) == measured(live_result["arm_a_rows"])
    assert result["calls"] == 2 + sum(1 for r in live_result["arm_a_rows"] if r["point_px"])
    assert set(masks) == {r["part"] for r in live_result["arm_a_rows"] if r.get("instances")}
