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
from app.geometry import boundaries
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

    def cap_calls(self, cap: int) -> None:
        self.cap = cap

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
            ("left", False): [box(12, 160)],  # holds the right box's point (150, 60)
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
            ("left", False): [box(12, 160)],  # 63% of right: a spill, not nesting
            ("left", True): [box(12, 155)],
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
    assert t.suggestion is not None and int(t.suggestion.sum()) == 143 * 86


def test_a_failed_retry_keeps_the_mask_as_spill() -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 160)],
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


def test_a_group_gets_no_call_no_mask_and_never_needs_the_teacher() -> None:
    """A group is never drawn: its members are drawn as themselves (Oct 30)."""
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): [box(112, 188)]})
    u = understanding(
        part("left", 150), part("right", 750), part("both", 0, "group", members=["left", "right"])
    )
    g = ground(sam, u)
    assert [m.label for m in g.parts] == ["left", "right"] and len(sam.calls) == 2
    assert g.teacher == [] and "both" not in g.flags


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
            ("left", False): [box(12, 160)],  # 63% of right: a spill, not nesting
            ("left", True): [box(12, 155)],
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


def test_s2_sets_the_job_cap_from_the_number_of_parts() -> None:
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): [box(112, 188)]})
    ground(sam, understanding(part("left", 150), part("right", 750)))
    assert sam.cap == 2 + 2 * 2


@pytest.mark.parametrize(("parts", "cap"), [(0, 2), (3, 8), (19, 40), (29, 60), (40, 60)])
def test_the_job_cap_is_two_spark_calls_and_two_per_part_up_to_60(parts: int, cap: int) -> None:
    from app.meta.client import job_cap  # noqa: PLC0415

    assert job_cap(parts, RULES.meta) == cap


# The plan for touch (S1 locate v2): lines, nesting, shared regions and the silhouette.


class SubjectSam(FakeSam):
    """FakeSam that also answers the subject's phrase call, or raises."""

    def __init__(self, answers: dict[tuple[str, bool], Any], subject: Any) -> None:
        super().__init__(answers)
        self.subject = subject
        self.phrases: list[tuple[str, str]] = []

    async def segment(
        self, image: Any, figure_id: str, phrase: str, prompt: Any, what: str = ""
    ) -> list[Any]:
        self.phrases.append((phrase, what))
        if isinstance(self.subject, Exception):
            raise self.subject
        from app.models.mask import Mask as PartMask  # noqa: PLC0415

        return [PartMask(data=m, label=phrase, score=0.9, source="sam") for m in self.subject]


def line(name: str, separates: Sequence[str] = (), parent: str = "") -> PartPhrase:
    return PartPhrase(
        phrase=name, print_label=name, kind="line", separates=tuple(separates), parent=parent
    )


def planned(*parts: PartPhrase, subject: str = "", shared: Sequence[Any] = ()) -> Understanding:
    from app.meta.types import SharedRegion  # noqa: PLC0415

    return understanding(*parts).model_copy(
        update={
            "subject": subject,
            "shares_region": [SharedRegion(parts=tuple(p), name=n) for p, n in shared],
        }
    )


def test_a_line_gets_no_call_no_mask_and_never_needs_the_teacher() -> None:
    sam = FakeSam({("left", False): [box(12, 88)], ("right", False): [box(112, 188)]})
    u = planned(part("left", 150), line("border", ["left", "right"]), part("right", 750))
    g = ground(sam, u)
    assert [c[0] for c in sam.calls] == ["left", "right"]
    assert [m.label for m in g.parts] == ["left", "right"]
    assert g.teacher == [] and "border" not in g.flags


def test_a_lines_points_never_count_as_spill() -> None:
    """Spark gave the line a point by mistake; it is not sent and spills nothing."""
    bad = line("border", ["left", "right"]).model_copy(
        update={"instances": (Instance(where="main", points=(GridPoint(x=150, y=500),)),)}
    )
    sam = FakeSam({("left", False): [box(12, 88)]})
    g = ground(sam, planned(part("left", 150), bad))
    assert [c[0] for c in sam.calls] == ["left"] and g.teacher == []


def test_a_mask_mostly_inside_a_larger_one_is_its_nested_child_whatever_spark_said() -> None:
    """Spark gave right no parent; 95% of its mask lies inside left's, so it is left's
    child: its point is no spill for left, and left's outline keeps right's pixels."""
    sam = FakeSam({("left", False): [box(12, 188)], ("right", False): [box(110, 192)]})
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert g.nested == {"right": "left"} and g.teacher == []
    assert all(not retry for _, retry, _ in sam.calls)
    masks = {m.label: m.data for m in g.parts}
    assert int(masks["right"].sum()) == 82 * 86  # the smaller keeps every pixel it claimed
    assert int(masks["left"].sum()) == 176 * 86  # the parent's outline holds its child
    assert g.facts["right"]["inside_of"] == {"left": round(78 / 82, 4)}


def test_a_mask_under_the_nesting_share_is_still_spill() -> None:
    sam = FakeSam(
        {
            ("left", False): [box(12, 182)],  # 70 of right's 76 columns: 92%
            ("left", True): [box(12, 170)],
            ("right", False): [box(112, 188)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750)))
    assert g.nested == {} and teacher(g)["left"][0] == "spill"


def stem(crease: bool = False) -> Ingested:
    """One shape, x 10 to 189, in one fill with a 2 px outline; with crease, a line drawn
    from the top edge two thirds of the way down at x 100, open at its lower end."""
    ing = figure()
    img = np.full((H, W, 3), 255, np.uint8)
    img[12:98, 12:188] = (240, 200, 120)
    img[10:12, 10:190] = img[98:100, 10:190] = 0
    img[10:100, 10:12] = img[10:100, 188:190] = 0
    if crease:
        img[12:70, 99:101] = 0
    return ing.model_copy(update={"image": img})


def test_near_identical_masks_with_no_drawn_boundary_are_a_merge_proposal_not_a_split() -> None:
    """medulla and spinal cord, Oct 30: SAM gives both the whole stem, and the figure draws
    no line between them. Neither is spill. They are not split by their points, which would
    draw a line the figure does not: a merge is proposed, and the smaller mask takes the
    contested pixels, as any contested pixels."""
    sam = FakeSam({("pons", False): [box(12, 188)], ("medulla", False): [box(14, 188)]})
    g = ground(sam, understanding(part("pons", 150), part("medulla", 750)), stem(crease=True))
    assert g.teacher == [] and g.nested == {} and all(not r for _, r, _ in sam.calls)
    masks = {m.label: m.data for m in g.parts}
    assert int(masks["medulla"].sum()) == 174 * 86  # all it claimed
    assert int(masks["pons"].sum()) == 2 * 86  # what only pons claimed: no line at the points
    (m,) = g.merges
    assert (m.parts, m.name) == (("pons", "medulla"), "pons and medulla")
    assert m.why == "their outlines overlap almost entirely" and m.left_out == ()


def test_near_identical_masks_across_a_drawn_boundary_send_the_smaller_to_the_teacher() -> None:
    """pons and cerebellum, Oct 30: SAM gives both the same outline, but the figure draws a
    line between them. Not split, not merged: the smaller needs the teacher, its mask a
    suggestion, and its point is no spill for the larger, so no retry is asked for."""
    sam = FakeSam({("cerebellum", False): [box(12, 188)], ("pons", False): [box(14, 188)]})
    g = ground(sam, understanding(part("cerebellum", 150), part("pons", 750)))
    assert all(not retry for _, retry, _ in sam.calls) and g.merges == []
    (t,) = g.teacher
    assert (t.phrase, t.reason) == ("pons", "same_outline")
    assert t.detail == "same outline as cerebellum; " + boundaries.LINE
    assert t.suggestion is not None and int(t.suggestion.sum()) == 174 * 86
    assert [m.label for m in g.parts] == ["cerebellum"]


def test_parts_spark_marked_as_one_shape_are_no_spill_and_keep_sparks_name() -> None:
    sam = FakeSam({("pons", False): [box(12, 160)], ("medulla", False): [box(112, 188)]})
    u = planned(
        part("pons", 150), part("medulla", 750), shared=[(("pons", "medulla"), "brainstem")]
    )
    g = ground(sam, u, stem(crease=True))  # the crease is open: one drawn region
    assert g.teacher == [] and all(not retry for _, retry, _ in sam.calls)
    (m,) = g.merges
    assert (m.parts, m.name) == (("pons", "medulla"), "brainstem")


def test_a_member_spark_marked_that_the_image_separates_is_left_out_of_the_merge() -> None:
    """Spark marked left, right and mid as one shape; the figure draws left and right as two
    boxes, and mid lies in the right box. left is left out, with the reason, and its point
    counts as spill again: right's mask, holding it, is asked for once more."""
    sam = FakeSam(
        {
            ("left", False): [box(12, 88)],
            ("right", False): [box(25, 188)],  # over 83% of left: not nested
            ("right", True): [box(112, 188)],
            ("mid", False): [box(150, 188)],
        }
    )
    u = planned(
        part("left", 150),
        part("right", 650),
        part("mid", 850),
        shared=[(("left", "right", "mid"), "boxes")],
    )
    g = ground(sam, u)
    (m,) = g.merges
    assert (m.parts, m.name) == (("right", "mid"), "boxes")
    assert m.left_out == (("left", "not merged with right: " + boundaries.LINE),)
    assert ("right", True, [[(30, 60)]]) in sam.calls and g.teacher == []
    assert "not merged with right: " + boundaries.LINE in g.flags["left"]


def test_the_subjects_largest_piece_is_the_silhouette() -> None:
    whole = box(5, 195, 5, 115)
    speck = box(0, 3, 0, 3)
    sam = SubjectSam({("left", False): [box(12, 88)]}, [whole, speck])
    g = ground(sam, planned(part("left", 150), subject="boxes"))
    assert sam.phrases == [("boxes", "s2_subject")]
    assert g.silhouette is not None and int(g.silhouette.sum()) == 190 * 110
    assert g.facts[s2_points.SUBJECT] == {"phrase": "boxes", "instances": 2, "px": 190 * 110}


@pytest.mark.parametrize("answer", [LiveCallCapError("cap"), []])
def test_a_failed_or_empty_silhouette_never_blocks_the_job(answer: Any) -> None:
    sam = SubjectSam({("left", False): [box(12, 88)]}, answer)
    g = ground(sam, planned(part("left", 150), subject="boxes"))
    assert g.silhouette is None and [m.label for m in g.parts] == ["left"]


def test_no_subject_no_silhouette_call() -> None:
    sam = SubjectSam({("left", False): [box(12, 88)]}, [box(5, 195)])
    g = ground(sam, planned(part("left", 150)))
    assert sam.phrases == [] and g.silhouette is None


def test_nesting_merges_and_the_silhouette_survive_the_cache(tmp_path: Any) -> None:
    sam = SubjectSam(
        {("left", False): [box(12, 188)], ("right", False): [box(110, 192)]}, [box(5, 195)]
    )
    g = ground(sam, planned(part("left", 150), part("right", 750), subject="boxes"))
    s2_ground.save(g, tmp_path)
    back = s2_ground.load(tmp_path)
    assert back.nested == g.nested == {"right": "left"} and back.merges == g.merges
    assert back.silhouette is not None and (back.silhouette == g.silhouette).all()


def test_relate_picks_the_smallest_container_and_shared_pairs_do_not_nest() -> None:
    big, mid, small = box(0, 200, 0, 120), box(10, 100), box(20, 40)
    r = pm.relate({"big": big, "mid": mid, "small": small, "twin": box(10, 101)})
    assert r.nested["small"] == "mid" and r.nested["mid"] == "big"
    assert {"mid", "twin"} in r.shared and "twin" not in r.nested.values()


def test_resolve_keeps_a_nested_childs_pixels_in_its_parent() -> None:
    parent, child = box(0, 100), box(40, 60)
    final, lost, won, _ = pm.resolve(
        {"parent": parent, "child": child},
        {"parent": [(10, 50)], "child": [(50, 50)]},
        1,
        nested={"child": "parent"},
    )
    assert (final["parent"] == parent).all() and (final["child"] == child).all()
    assert lost["parent"] == {} and won["parent"] == {}


def test_nesting_is_tested_again_on_the_mask_a_retry_keeps() -> None:
    """The heart's septum, Oct 30: its first mask took most of the heart. left lies wholly
    inside it, so left's point is no spill; right's does count, so the wall is asked again,
    and the strip that comes back holds neither box: nothing is recorded as nested."""
    sam = FakeSam(
        {
            ("left", False): [box(12, 60)],
            ("right", False): [box(112, 188)],
            ("wall", False): [box(0, 160, 0, 120)],  # all of left, 63% of right
            ("wall", True): [box(64, 100)],
        }
    )
    g = ground(sam, understanding(part("left", 150), part("right", 750), part("wall", 375)))
    assert ("wall", True, [[(150, 60)]]) in sam.calls  # right's point only
    assert g.nested == {} and g.teacher == []
    assert g.facts["left"]["inside_of"] == {"wall": 1.0}  # the first masks, as eval data
    assert [m.label for m in g.parts] == ["left", "right", "wall"]
