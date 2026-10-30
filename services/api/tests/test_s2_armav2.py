"""Arm A v2 of S2 with no network: the SAM request with several points and negative points,
the point guard, negative points from v1's spill, the post-processing, group unions, and a
whole run on a small figure with answers from a mock transport."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import numpy.typing as npt
from meta_sam_parser._mask_codec import _encode_raster

from app.config import load_tactile_rules
from app.geometry.print_marks import PrintMarks
from app.meta import s2_armav2 as v2
from app.meta import s2_bakeoff as bake
from app.meta import sam_adapter
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller
from tests.test_s2_bakeoff import chat, small_figure
from tests.test_sam_diagnostic import answer, sse

RULES = load_tactile_rules()


def test_one_request_names_each_instance_with_its_points_and_the_negatives() -> None:
    body = sam_adapter.objects_request_body(
        "sam-3.1", b"png", (200, 120), [([(30, 60), (60, 60)], [(150, 60)]), ([(70, 20)], [])], {}
    )
    assert body["input"][0]["content"][0]["text"] == (
        "<0f>1<|point;x=30;y=60;w=200;h=120|><|point;x=60;y=60;w=200;h=120|>"
        "-<|point;x=150;y=60;w=200;h=120|>,2<|point;x=70;y=20;w=200;h=120|>"
    )


def scene() -> v2.Scene:
    """A 60 x 60 figure: a red fill with a black text box across rows 20 to 30, and a
    blue fill from row 46."""
    img = np.full((60, 60, 3), (220, 40, 40), np.uint8)
    img[46:] = (40, 40, 220)
    text = np.zeros((60, 60), bool)
    text[20:30, 10:50] = True
    img[text] = (0, 0, 0)
    none = np.zeros((60, 60), bool)
    marks = PrintMarks(text=text, line=none, ink=img.sum(axis=2) < 64, words=[], segments=[])
    return v2.Scene(img, marks, np.ones((60, 60), bool))


def test_a_clean_point_is_sent_as_it_is() -> None:
    g = v2.guard(scene(), (30, 10), None)
    assert g == {"px": [30, 10], "on": [], "sent": [30, 10], "moved_px": 0.0, "dropped": False}


def test_a_point_on_text_moves_to_the_nearest_pixel_of_the_fill_color() -> None:
    red = np.array([220.0, 40.0, 40.0])
    g = v2.guard(scene(), (30, 21), red)
    assert g["on"] == ["text", "ink"] and g["sent"] == [30, 19] and g["moved_px"] == 2.0
    blue = v2.guard(scene(), (30, 28), np.array([40.0, 40.0, 220.0]))
    assert blue["sent"] is None and blue["dropped"]  # no blue within 15 px of row 28


def test_with_no_clean_point_the_fill_color_is_the_commonest_nearby() -> None:
    g = v2.guard_instance(scene(), [(30, 28)])[0]
    assert g["sent"] == [30, 30] and not g["dropped"]  # red sits 2 px below the text


def test_negatives_come_from_other_parts_points_inside_the_v1_mask() -> None:
    v1 = np.zeros((60, 60), bool)
    v1[:, :40] = True
    others = {"p": [(5, 5)], "q": [(30, 30), (35, 35)], "r": [(50, 50)], "s": [(12, 5)]}
    negs = v2.negatives("p", [(5, 5)], others, v1)
    assert negs == [{"of": "q", "xy": [30, 30]}]  # r is outside v1, s is within 15 px of p
    assert v2.negatives("p", [(5, 5)], others, None) == []


def test_pieces_without_a_point_and_specks_are_dropped() -> None:
    m = np.zeros((40, 40), bool)
    m[0:10, 0:10] = True  # holds the point
    m[20:30, 20:30] = True  # no point
    m[35, 35] = True
    kept, dropped = v2.keep_pieces(m, [(5, 5), (35, 35)], floor_px=3)
    assert kept.sum() == 100 and dropped == 2


def test_contested_pixels_go_to_the_smaller_mask() -> None:
    big = np.zeros((40, 40), bool)
    big[0:20, 0:20] = True
    small = np.zeros((40, 40), bool)
    small[10:30, 18:20] = True  # 40 px, 20 of them inside big
    final, lost, respeck = v2.contest({"big": big, "small": small}, floor_px=3)
    assert final["small"].sum() == 40 and final["big"].sum() == 380
    assert lost == {"small": {}, "big": {"small": 20}} and respeck == {"small": 0, "big": 0}


def test_group_members_open_up_nested_groups() -> None:
    info: dict[str, dict[str, Any]] = {
        "flower": {"kind": "group", "members": ["pistil", "petal", "ghost"]},
        "pistil": {"kind": "group", "members": ["ovary", "style"]},
        "ovary": {"kind": "area", "members": []},
        "style": {"kind": "thin", "members": []},
        "petal": {"kind": "area", "members": []},
    }
    assert v2.members_of("flower", info, {"flower"}) == ["ovary", "style", "petal"]


def sam_answer(boxes: list[tuple[int, int, int, int, npt.NDArray[np.bool_]]]) -> httpx.Response:
    """One record per object: ids from 1, half-open bounds and a raster the bounds' size."""
    text = "<0f>" + ",".join(
        f"{i}<|box;x1={x0};y1={y0};x2={x1 - 1};y2={y1 - 1};w=200;h=120;c=0.8|>"
        f"<|mask;x=0;y=0;c=0.8;data={r.shape[0]},{r.shape[1]},"
        f"{_encode_raster(r.astype(int).ravel().tolist(), r.shape[1], r.shape[0])}|>"
        for i, (x0, y0, x1, y1, r) in enumerate(boxes, 1)
    )
    return sse(answer(text))


SPARK = {
    "parts": [
        {
            "part": "left box",
            "kind": "area",
            "members": [],
            "parent": "",
            "instances": [{"where": "main", "points": [{"x": 150, "y": 500}]}],
        },
        {
            "part": "right box",
            "kind": "thin",
            "members": [],
            "parent": "",
            "instances": [{"where": "main", "points": [{"x": 750, "y": 500}]}],
        },
        {
            "part": "boxes",
            "kind": "group",
            "members": ["left box", "right box", "ghost"],
            "parent": "",
            "instances": [],
        },
    ]
}


def mock_caller(tmp_path: Path, sent: list[str]) -> LiveCaller:
    left = np.ones((86, 76), bool)
    left[:, 30:34] = False  # two pieces; the point (30, 60) is in the first
    right = np.ones((86, 158), bool)  # x 30 to 187: over the left box's first piece too
    answers = iter([sam_answer([(12, 12, 88, 98, left)]), sam_answer([(30, 12, 188, 98, right)])])

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        if request.url.path.endswith("/responses"):
            sent.append(body["input"][0]["content"][0]["text"])
            return next(answers)
        sent.append(body["response_format"]["json_schema"]["name"])
        return chat(json.dumps(SPARK))

    return LiveCaller(
        key="test-key",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=httpx.MockTransport(handler),
    )


def test_a_whole_run_guards_segments_contests_and_unions(tmp_path: Path) -> None:
    fig = small_figure(tmp_path)
    parts = [{"phrase": p, "print_label": ""} for p in ("left box", "right box", "boxes")]
    v1_left = np.zeros((120, 200), bool)
    v1_left[10:100, 10:190] = True  # v1 spilled over both boxes
    sent: list[str] = []
    run = v2.ArmAv2(mock_caller(tmp_path, sent), fig, parts, {"left box": v1_left}, False)
    result = asyncio.run(run.run())
    assert sent == [
        "PartPoints",
        "<0f>1<|point;x=30;y=60;w=200;h=120|>-<|point;x=150;y=60;w=200;h=120|>",
        "<0f>1<|point;x=150;y=60;w=200;h=120|>",
    ]
    rows = {r["part"]: r for r in result["rows"]}
    left, right, group = rows["left box"], rows["right box"], rows["boxes"]
    assert left["instances"][0]["pieces_dropped"] == 1 and left["kept_px"] == 30 * 86
    assert right["lost_to"] == {"left box": 12 * 86} and left["lost_px"] == 0
    assert right["final_px"] == (158 - 12) * 86
    assert "thin: kept for the record, sheet use decided later" in right["flags"]
    assert group["final_px"] == left["final_px"] + right["final_px"]
    assert group["unknown_members"] == ["ghost"] and "sam" not in group
    assert result["calls"] == 3
    out = tmp_path / "out"
    v2.save_views(fig, result, run.final, {"left box": v1_left}, {}, out)
    v2.write_sheet(result, {}, out)
    page = (out / "v2.html").read_text()
    assert page.count("<td></td><td></td></tr>") == 3 and "v2 grade" in page
    assert "—" not in page
    assert (out / "img" / "v2sheet_v2_left_box.jpg").is_file()


def test_the_prompt_lists_every_part_and_its_label() -> None:
    text = v2.v2_prompt(
        [{"phrase": "ovary", "print_label": "ovary"}, {"phrase": "x", "print_label": ""}]
    )
    assert '"ovary" (printed label "ovary"); "x".' in text
    assert "0 to 1000 grid" in text and "never put a point on label text" in text.lower()


def test_each_v2_figure_fits_under_the_cap() -> None:
    for name in bake.FIGURES:
        result = json.loads((bake.OUT_ROOT / name / "results.json").read_text())
        assert 1 + len(result["parts"]) <= RULES.meta.live_call_cap
