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
from PIL import Image

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


def test_with_clearance_a_point_beside_an_outline_moves_away_from_it(tmp_path: Path) -> None:
    image = small_figure(tmp_path).image.copy()  # black outlines 2 px wide at x 10 to 11
    image[12:98, 12:88] = (200, 200, 60)  # a filled part, so it is figure and not page
    plain, cleared = v2.scene_of(image), v2.scene_of(image, v2.CLEARANCE_PX)
    assert v2.guard_instance(plain, [(14, 60)])[0]["sent"] == [14, 60]
    g = v2.guard_instance(cleared, [(14, 60)])[0]
    assert g["on"] == ["near a mark"] and g["sent"] == [17, 60] and g["moved_px"] == 3.0
    assert (
        v2.where_on(g["on"]) == "near a mark" and v2.where_on(["text", "ink"]) == "on text and ink"
    )


def box_mask(x0: int, x1: int) -> tuple[int, int, int, int, npt.NDArray[np.bool_]]:
    return (x0, 12, x1, 98, np.ones((86, x1 - x0), bool))


def fixes_caller(tmp_path: Path, sent: list[str], answers: dict[str, httpx.Response]) -> LiveCaller:
    """SAM answers chosen by the prompt text: "left retry" when the left box's prompt has a
    negative point at the right box's point, else "left" or "right"."""
    spark = {
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
                "kind": "area",
                "members": [],
                "parent": answers.get("parent", ""),
                "instances": [{"where": "main", "points": [{"x": 750, "y": 500}]}],
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        if not request.url.path.endswith("/responses"):
            sent.append("spark")
            return chat(json.dumps(spark))
        text = body["input"][0]["content"][0]["text"]
        sent.append(text)
        if "x=30;" in text:
            return answers["left retry" if "-<|point;x=150" in text else "left"]
        return answers["right"]

    return LiveCaller(
        key="test-key",
        base_url="https://api.meta.ai/v1",
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        meter=CostMeter(RULES.meta),
        cap=RULES.meta.live_call_cap,
        transport=httpx.MockTransport(handler),
    )


def filled_figure(tmp_path: Path) -> bake.Figure:
    """The two outlined boxes with filled insides, so they are figure and not page."""
    img = small_figure(tmp_path).image.copy()
    img[12:98, 12:88] = (200, 200, 60)
    img[12:98, 112:188] = (60, 160, 200)
    path = tmp_path / "filled.png"
    Image.fromarray(img).save(path)
    return bake.load_figure("filled", path)


def fixes_run(tmp_path: Path, answers: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    fig = filled_figure(tmp_path)
    parts = [{"phrase": p, "print_label": ""} for p in ("left box", "right box")]
    sent: list[str] = []
    run = v2.ArmAv2(fixes_caller(tmp_path, sent, answers), fig, parts, {}, False, fixes=True)
    result = asyncio.run(run.run())
    return sent, {r["part"]: r for r in result["rows"]}


def test_a_spill_is_retried_once_with_the_other_parts_point_as_a_negative(tmp_path: Path) -> None:
    both, left, right = (sam_answer([box_mask(*b)]) for b in ((12, 188), (12, 88), (112, 188)))
    sent, rows = fixes_run(tmp_path, {"left": both, "left retry": left, "right": right})
    assert len(sent) == 4 and sent[-1].endswith("-<|point;x=150;y=60;w=200;h=120|>")
    assert rows["left box"]["retry"]["used"] and rows["left box"]["final_px"] == 76 * 86
    assert "spill onto right box cleared by a retry" in rows["left box"]["flags"]
    assert "retry" not in rows["right box"]


def test_a_spill_that_survives_the_retry_keeps_the_smaller_mask(tmp_path: Path) -> None:
    both, less, right = (sam_answer([box_mask(*b)]) for b in ((12, 188), (12, 170), (112, 188)))
    _, rows = fixes_run(tmp_path, {"left": both, "left retry": less, "right": right})
    left = rows["left box"]
    assert left["retry"]["used"] and left["retry"]["still_onto"] == ["right box"]
    assert left["kept_px"] == 176 * 86 and left["retry"]["kept_px"] == 158 * 86
    assert "spill onto right box" in left["flags"]


def test_a_child_inside_the_mask_is_not_a_spill(tmp_path: Path) -> None:
    both, right = sam_answer([box_mask(12, 188)]), sam_answer([box_mask(112, 188)])
    sent, rows = fixes_run(tmp_path, {"left": both, "right": right, "parent": "left box"})
    assert len(sent) == 3 and "retry" not in rows["left box"]


def test_a_mask_without_the_parts_points_leaves_the_part_for_the_teacher(tmp_path: Path) -> None:
    left, away = sam_answer([box_mask(12, 88)]), sam_answer([box_mask(160, 188)])
    _, rows = fixes_run(tmp_path, {"left": left, "right": away})
    right = rows["right box"]
    assert right["final_px"] == 0 and "needs teacher: no mask" in right["flags"]
    assert "a point of instance 1 is outside its SAM mask" in right["flags"]


def test_a_failed_sam_call_is_flagged_and_the_run_goes_on(tmp_path: Path) -> None:
    left = sam_answer([box_mask(12, 88)])
    _, rows = fixes_run(tmp_path, {"left": left, "right": httpx.Response(500, text="boom")})
    assert rows["left box"]["final_px"] == 76 * 86
    flags = rows["right box"]["flags"]
    assert (
        flags[0].startswith("SAM call failed: LiveCallError") and "needs teacher: no mask" in flags
    )


def test_equal_masks_split_by_the_nearer_prompt_point() -> None:
    a = np.zeros((20, 40), bool)
    a[:, 0:30] = True
    b = np.zeros((20, 40), bool)
    b[:, 10:40] = True  # the same size as a; columns 10 to 29 are contested
    small = np.zeros((20, 40), bool)
    small[0:5, 12:16] = True  # smaller than both: wins its 20 px outright
    final, lost, respeck, won = v2.contest_nearest(
        {"a": a, "b": b, "small": small}, {"a": [(5, 10)], "b": [(34, 10)], "small": [(13, 2)]}, 1
    )
    assert final["small"].sum() == 20
    assert final["a"][10, 19] and final["b"][10, 20]  # the midpoint of the points is 19.5
    assert won["a"] == {"b": 180} and won["b"] == {"a": 200}
    assert lost["a"] == {"b": 200, "small": 20} and lost["b"] == {"a": 180, "small": 20}
    assert won["small"] == {"a": 20, "b": 20} and respeck == {"a": 0, "b": 0, "small": 0}


def test_a_spill_after_the_retry_goes_to_the_teacher_untouchable(tmp_path: Path) -> None:
    both, less, right = (sam_answer([box_mask(*b)]) for b in ((12, 188), (12, 170), (112, 188)))
    fig = filled_figure(tmp_path)
    parts = [{"phrase": p, "print_label": ""} for p in ("left box", "right box")]
    answers = {"left": both, "left retry": less, "right": right}
    run = v2.ArmAv2(fixes_caller(tmp_path, [], answers), fig, parts, {}, False, fixes=True)
    rows = {r["part"]: r for r in asyncio.run(run.run())["rows"]}
    left = rows["left box"]
    assert left["final_px"] == 0 and "left box" not in run.final
    assert run.suggested["left box"].sum() == 158 * 86
    assert "needs teacher: spill" in left["flags"]
    assert "spill: holds points of right box; after a retry" in left["flags"]
    assert rows["right box"]["final_px"] == 76 * 86 and rows["right box"]["lost_px"] == 0


def test_oversize_masks_are_spill() -> None:
    run = v2.ArmAv2.__new__(v2.ArmAv2)
    obj = np.zeros((100, 100), bool)
    obj[:, :50] = True  # 5000 px of object
    none = np.zeros((100, 100), bool)
    marks = PrintMarks(text=none, line=none, ink=none, words=[], segments=[])
    run.scene = v2.Scene(np.zeros((100, 100, 3), np.uint8), marks, obj)
    rows: dict[str, Any] = {
        "p": {"part": "p", "kind": "thin", "parent": ""},
        "q": {"part": "q", "kind": "area", "parent": ""},
        "r": {"part": "r", "kind": "area", "parent": ""},
        "c": {"part": "c", "kind": "area", "parent": "p"},
    }
    sent = {"p": [(1, 1)], "q": [(40, 40)], "r": [(45, 45)], "c": [(30, 30)]}
    big = np.zeros((100, 100), bool)
    big[:, :52] = True  # 5200 px, 104% of the object, holds q, r and its child c
    assert run.oversize(rows["p"], big, rows, sent) == ("holds points of 2 other parts: q, r")
    one = big.copy()
    one[44:, 44:] = False  # now holds q only
    assert run.oversize(rows["p"], one, rows, sent) == (
        "covers 95% of the object area, and the part is thin"  # 4752 px
    )
    wide = np.zeros((100, 100), bool)
    wide[35:, :50] = True  # 65% of the object, holding r's point only
    assert run.oversize(rows["q"], wide, rows, sent) is None  # an area part with no parent


def test_a_point_on_the_background_is_dropped_and_its_part_goes_to_the_teacher(
    tmp_path: Path,
) -> None:
    fig = small_figure(tmp_path)  # white insides: every point there is page, not figure
    parts = [{"phrase": p, "print_label": ""} for p in ("left box", "right box")]
    sent: list[str] = []
    answers = {"left": sam_answer([box_mask(12, 88)]), "right": sam_answer([box_mask(112, 188)])}
    run = v2.ArmAv2(fixes_caller(tmp_path, sent, answers), fig, parts, {}, False, fixes=True)
    rows = {r["part"]: r for r in asyncio.run(run.run())["rows"]}
    assert sent == ["spark"] and run.final == {}
    for row in rows.values():
        assert row["instances"][0]["points"][0]["on"] == ["background"]
        assert row["flags"][0].endswith("dropped: on the background")
        assert "needs teacher: no points" in row["flags"]
        assert "needs teacher: no mask" not in row["flags"]
    plain = v2.ArmAv2(fixes_caller(tmp_path, [], answers), fig, parts, {}, False)
    assert asyncio.run(plain.run())["calls"] == 3  # v2 sends them, as it did live
