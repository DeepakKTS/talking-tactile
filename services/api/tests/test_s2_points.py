"""S2 by points (Arm A v2f) with no network: the guard, SAM calls at bounded concurrency,
the spill retry, the oversize rule, spill masks left to the teacher, contested pixels,
group unions, and every listed part accounted for."""

import asyncio
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from app.config import load_tactile_rules
from app.geometry import part_masks as pm
from app.geometry import points as gp
from app.meta.client import ObjectMask
from app.meta.cost import CostMeter
from app.meta.live import LiveCallCapError
from app.meta.types import GridPoint, Instance, PartPhrase, Understanding
from app.pipeline import s2_ground, s2_points
from app.pipeline.s0_ingest import Ingested
from app.prompts import load_prompt

RULES = load_tactile_rules()
PROMPT = load_prompt(s2_ground.PROMPT)
W, H = 200, 120
Mask = npt.NDArray[np.bool_]


def figure(white: bool = False) -> Ingested:
    """Two boxes on white with 2 px black outlines: left x 10 to 89, right x 110 to 189."""
    img = np.full((H, W, 3), 255, np.uint8)
    for x0, x1, fill in ((10, 90, (200, 200, 60)), (110, 190, (60, 160, 200))):
        if not white:
            img[12:98, x0 + 2 : x1 - 2] = fill
        img[10:12, x0:x1] = img[98:100, x0:x1] = 0
        img[10:100, x0 : x0 + 2] = img[10:100, x1 - 2 : x1] = 0
    return Ingested(
        image=img,
        figure_id="f" * 64,
        source_type="png",
        page_index=0,
        original_size=(W, H),
        deskewed=False,
        sharpness=1.0,
    )


def box(x0: int, x1: int, y0: int = 12, y1: int = 98) -> Mask:
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


def part(
    name: str, x: int, kind: str = "area", parent: str = "", members: Sequence[str] = ()
) -> PartPhrase:
    instances = (
        () if kind == "group" else (Instance(where="main", points=(GridPoint(x=x, y=500),)),)
    )
    return PartPhrase(
        phrase=name,
        print_label="",
        kind=kind,  # type: ignore[arg-type]
        parent=parent,
        members=tuple(members),
        instances=instances,
    )


def understanding(*parts: PartPhrase) -> Understanding:
    return Understanding(
        figure_type="labeled_diagram",
        title="Boxes",
        summary="Two boxes.",
        parts=list(parts),
        color_carries_meaning=False,
        verdict="make_tactile",
        verdict_reason="test",
        located=True,
    )


class FakeSam:
    """Answers each (part, retry) with masks, one per object, or raises what it is given."""

    mode = "live"
    cache_tag = "fake"

    def __init__(self, answers: dict[tuple[str, bool], Any]) -> None:
        self.answers = answers
        self.meter = CostMeter(RULES.meta)
        self.calls: list[tuple[str, bool, list[Any]]] = []
        self.running = 0
        self.most = 0

    def for_job(self) -> "FakeSam":
        return self

    async def segment_points(
        self, image: Any, figure_id: str, part: str, objects: Any, prompt: Any, retry: bool = False
    ) -> list[ObjectMask]:
        self.calls.append((part, retry, [list(neg) for _, neg in objects]))
        self.running += 1
        self.most = max(self.most, self.running)
        await asyncio.sleep(0.01)
        self.running -= 1
        answer = self.answers[(part, retry)]
        if isinstance(answer, Exception):
            raise answer
        return [ObjectMask(i, 0.8, m) for i, m in enumerate(answer, 1)]


def ground(client: FakeSam, u: Understanding, ing: Ingested | None = None) -> s2_ground.Grounded:
    return asyncio.run(s2_ground.ground(client, ing or figure(), u, PROMPT, RULES))  # type: ignore[arg-type]


def teacher(g: s2_ground.Grounded) -> dict[str, tuple[str, str]]:
    return {t.phrase: (t.reason, t.detail) for t in g.teacher}


def test_two_clean_parts_become_two_masks_and_text_is_found_in_code() -> None:
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): [box(112, 188)]})
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert [m.label for m in g.parts] == ["left", "right"]
    assert [int(m.data.sum()) for m in g.parts] == [76 * 86, 76 * 86]
    assert g.teacher == [] and g.text == []  # no print text on this figure
    assert [c[:2] for c in sam.calls] == [("left", False), ("right", False)]


def test_a_point_on_the_background_is_dropped_and_the_part_needs_the_teacher() -> None:
    sam = FakeSam({})
    g = ground(sam, understanding(part("left", 150)), figure(white=True))
    assert sam.calls == [] and g.parts == []
    assert teacher(g) == {"left": ("no_points", "every point was dropped by the guard")}
    assert g.flags["left"][0] == "point [30, 60] dropped: on the background"


def test_a_part_spark_did_not_locate_needs_the_teacher() -> None:
    unlocated = PartPhrase(phrase="ghost", print_label="")
    sam = FakeSam({("left", False): [box(12, 88)]})
    g = ground(sam, understanding(part("left", 150), unlocated))
    assert teacher(g) == {"ghost": ("no_points", "Spark did not locate this part")}


def test_a_spill_cleared_by_the_retry_is_used() -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 188)],  # holds the right box's point (150, 60)
            ("left", True): [box(12, 88)],
            ("right", False): [box(112, 188)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert ("left", True, [[(150, 60)]]) in sam.calls
    assert "spill onto right cleared by a retry" in g.flags["left"]
    assert int(g.parts[0].data.sum()) == 76 * 86 and g.teacher == []


def test_a_spill_that_survives_goes_to_the_teacher_as_an_untouchable_suggestion() -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 188)],
            ("left", True): [box(12, 170)],
            ("right", False): [box(112, 188)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert [m.label for m in g.parts] == ["right"]
    assert int(g.parts[0].data.sum()) == 76 * 86  # the spill took no pixel from it
    (t,) = g.teacher
    assert (t.phrase, t.reason, t.detail) == (
        "left",
        "spill",
        "holds points of right after a retry",
    )
    assert t.suggestion is not None and int(t.suggestion.sum()) == 158 * 86


def test_a_failed_retry_keeps_the_mask_as_spill() -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 188)],
            ("left", True): LiveCallCapError("cap"),
            ("right", False): [box(112, 188)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert teacher(g)["left"] == (
        "spill",
        "holds points of right; the retry call failed: LiveCallCapError: cap",
    )


def test_a_child_inside_the_mask_is_no_spill() -> None:
    sam = FakeSam({("left", False): [box(12, 188)], ("right", False): [box(112, 188)]})
    g = ground(sam, understanding(part("left", 150), part("right", 750, parent="left")))
    assert all(not retry for _, retry, _ in sam.calls) and g.teacher == []
    right = next(m for m in g.parts if m.label == "right")
    assert int(right.data.sum()) == 76 * 86  # the smaller mask wins the shared pixels


def test_a_thin_part_over_half_the_figure_is_spill_by_the_oversize_rule() -> None:
    ing = figure()
    big = box(0, 200, 0, 120)  # 100% of the figure; holds no other part's point
    sam = FakeSam({("stalk", False): [big]})
    g = ground(sam, understanding(part("stalk", 150, kind="thin")), ing)
    reason, detail = teacher(g)["stalk"]
    assert (
        reason == "spill" and detail.startswith("covers ") and detail.endswith("the part is thin")
    )
    assert "thin" in g.flags["stalk"]


def test_a_failed_first_call_leaves_the_part_to_the_teacher_and_the_run_goes_on() -> None:
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): LiveCallCapError("cap")})
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert [m.label for m in g.parts] == ["left"]
    assert teacher(g)["right"] == ("no_mask", "SAM call failed: LiveCallCapError: cap")


def test_a_mask_without_the_parts_point_leaves_it_to_the_teacher() -> None:
    sam = FakeSam({("left", False): [box(60, 88)]})  # the point is at x 30
    g = ground(sam, understanding(part("left", 150)))
    assert teacher(g)["left"] == ("no_mask", "SAM's mask holds none of the part's points")


def test_a_group_is_the_union_of_its_members_with_no_call() -> None:
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): [box(112, 188)]})
    u = understanding(
        part("left", 150), part("right", 750), part("both", 0, "group", members=["left", "right"])
    )
    g = ground(sam, u)
    both = next(m for m in g.parts if m.label == "both")
    assert int(both.data.sum()) == 2 * 76 * 86 and len(sam.calls) == 2


def test_sam_calls_run_at_most_sam_concurrency_at_a_time() -> None:
    names = [f"p{i}" for i in range(9)]
    answers = {(n, False): [box(12, 88)] for n in names}
    sam = FakeSam(answers)
    parts = [part(n, 150 + i) for i, n in enumerate(names)]
    ground(sam, understanding(*parts))
    assert sam.most == RULES.meta.sam_concurrency == 4


def test_mock_parts_without_points_are_found_by_phrase() -> None:
    """Mock mode is unchanged: an S1 that did not locate goes to the phrase path."""

    class Phrases(FakeSam):
        async def segment(self, image: Any, figure_id: str, phrase: str, prompt: Any) -> list[Any]:
            self.calls.append((phrase, False, []))
            return []

    sam = Phrases({})
    u = understanding(PartPhrase(phrase="left", print_label="")).model_copy(
        update={"located": False}
    )
    ground(sam, u)
    assert [c[0] for c in sam.calls] == ["left", RULES.meta.text_phrase]


def test_grounded_with_flags_and_suggestions_survives_the_cache(tmp_path: Any) -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 188)],
            ("left", True): [box(12, 170)],
            ("right", False): [box(112, 188)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750, kind="thin")))
    s2_ground.save(g, tmp_path)
    back = s2_ground.load(tmp_path)
    assert back.flags == g.flags and back.facts == g.facts
    assert [(t.phrase, t.reason, t.detail) for t in back.teacher] == [
        (t.phrase, t.reason, t.detail) for t in g.teacher
    ]
    assert back.teacher[0].suggestion is not None
    assert (back.teacher[0].suggestion == g.teacher[0].suggestion).all()


@pytest.mark.parametrize(
    ("v", "size", "px"),
    [(0, 2048, 0), (500, 2048, 1024), (333, 1183, 393), (1001, 2048, 2047), (-3, 2048, 0)],
)
def test_grid_values_map_to_integer_pixels(v: int, size: int, px: int) -> None:
    assert s2_points.grid_to_px(v, size) == px


def test_equal_masks_split_by_the_nearer_prompt_point() -> None:
    a = np.zeros((20, 40), bool)
    a[:, 0:30] = True
    b = np.zeros((20, 40), bool)
    b[:, 10:40] = True  # the same size as a; columns 10 to 29 are contested
    small = np.zeros((20, 40), bool)
    small[0:5, 12:16] = True  # smaller than both: wins its 20 px outright
    final, lost, won, respeck = pm.resolve(
        {"a": a, "b": b, "small": small}, {"a": [(5, 10)], "b": [(34, 10)], "small": [(13, 2)]}, 1
    )
    assert final["small"].sum() == 20
    assert final["a"][10, 19] and final["b"][10, 20]  # the midpoint of the points is 19.5
    assert won["a"] == {"b": 180} and won["b"] == {"a": 200}
    assert lost["a"] == {"b": 200, "small": 20} and won["small"] == {"a": 20, "b": 20}
    assert respeck == {"a": 0, "b": 0, "small": 0}


def test_the_guard_moves_a_point_off_an_outline_by_the_clearance() -> None:
    scene = gp.scene_of(figure().image, 40.0)
    g = gp.guard_instance(scene, [(14, 60)])[0]  # 2 px inside the left box's outline
    assert g["on"] == [gp.NEAR] and g["sent"] == [17, 60] and g["moved_px"] == 3.0
