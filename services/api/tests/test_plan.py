"""S1's plan for touch on the sheet (app/geometry/plan.py): names to parts through edits,
line parts and what they separate, merge proposals, the silhouette's raised contour and its
gaps, the key's line entries, S3's parent hints from S2, and the rules check."""

import numpy as np
import pytest
from shapely.geometry import LineString, Polygon, box

from app.braille.models import BrailleLine, Placement
from app.config import load_tactile_rules
from app.geometry import plan
from app.geometry.layout import LayoutRegion
from app.geometry.reconcile import ReconciledPart, reconcile
from app.geometry.sheet import Sheet, SheetLine
from app.geometry.validate import validate_sheet
from app.meta.types import PartPhrase, Understanding
from app.models.mask import Mask
from app.render.regions_json import plan_fields

RULES = load_tactile_rules()
GAP = RULES.spacing.min_gap_mm
HALF = RULES.render.outline_width_mm / 2


def part(pid: str, label: str, merged: list[str] | None = None) -> ReconciledPart:
    m = Mask(data=np.ones((2, 2), bool), label=label, score=0.9, source="sam")
    return ReconciledPart(id=pid, mask=m, merged=merged or [])


def understanding(*parts: PartPhrase) -> Understanding:
    return Understanding(figure_type="labeled_diagram", title="t", summary="s",
                         parts=list(parts), color_carries_meaning=False,
                         verdict="make_tactile", verdict_reason="r", located=True)  # fmt: skip


def line(name: str, separates: tuple[str, ...] = (), parent: str = "") -> PartPhrase:
    return PartPhrase(phrase=name, print_label=name, kind="line", separates=separates,
                      parent=parent)  # fmt: skip


def region(rid: str, poly: Polygon) -> LayoutRegion:
    return LayoutRegion(id=rid, label=rid, polygon=poly, score=0.9, source="sam")


def test_phrases_map_to_parts_through_a_rename_and_a_merge() -> None:
    before = [part("r1", "pons"), part("r2", "medulla"), part("r3", "cerebellum")]
    after = [part("r1", "brainstem", merged=["medulla"]), part("r3", "cerebellum")]
    ids = plan.part_ids(["pons", "medulla", "cerebellum", "nowhere"], before, after)
    assert ids == {"pons": "r1", "medulla": "r1", "cerebellum": "r3"}


def test_a_line_separates_two_parts_on_the_sheet_or_keeps_its_parent() -> None:
    u = understanding(
        line("central sulcus", ("precentral gyrus", "postcentral gyrus")),
        line("pontine line", ("pons", "medulla"), parent="pons"),  # both in one part now
        line("groove", parent="frontal lobe"),
        line("loose"),
    )
    ids = {"precentral gyrus": "r2", "postcentral gyrus": "r3", "pons": "r5", "medulla": "r5",
           "frontal lobe": "r1"}  # fmt: skip
    labels = {"r1": "frontal lobe", "r2": "precentral gyrus", "r3": "postcentral gyrus",
              "r5": "brainstem"}  # fmt: skip
    lines = plan.sheet_lines(u, ids, labels)
    assert [(x.id, x.separates, x.between, x.parent) for x in lines] == [
        ("l1", ("r2", "r3"), ("precentral gyrus", "postcentral gyrus"), None),
        ("l2", None, ("brainstem", "brainstem"), "r5"),
        ("l3", None, None, "r1"),
        ("l4", None, None, None),
    ]
    assert [plan.key_text(x, labels) for x in lines] == [
        "central sulcus, a line between precentral gyrus and postcentral gyrus",
        "pontine line, a line between brainstem and brainstem",
        "groove, a line in frontal lobe",
        "loose, a line",
    ]


def test_a_merge_proposal_keeps_the_parts_still_apart_and_needs_two() -> None:
    ids = {"pons": "r1", "medulla": "r1", "spinal cord": "r2", "a": "r7"}
    merges = plan.sheet_merges(
        [(("pons", "medulla", "spinal cord"), "brainstem", "w"), (("a", "gone"), "x", "w")], ids
    )
    assert [(m.name, m.part_ids) for m in merges] == [("brainstem", ("r1", "r2"))]


def test_the_contour_keeps_the_minimum_gap_from_every_outline_and_braille() -> None:
    sil = box(20, 20, 120, 120)
    inner = region("r1", box(20, 40, 60, 100))  # its left edge lies on the silhouette's
    near = region("r2", box(100, 22, 110, 40))  # 2 mm under the silhouette's top edge
    rect = BrailleLine(text="x", braille="x", x_mm=60, y_mm=115, width_mm=10, height_mm=4)
    braille = Placement(region_id="r1", kind="label", inside=False, line=rect)
    pieces = plan.contour(sil, [inner, near], [braille], RULES)
    raised = [plan.band(p, RULES) for p in pieces]
    assert raised and all(b.distance(r.polygon) >= GAP - 1e-6 for b in raised
                          for r in (inner, near))  # fmt: skip
    assert all(b.distance(rect.rect) >= RULES.braille.clearance_to_line_mm - 1e-6 for b in raised)
    assert all(p.length >= RULES.spacing.point_symbol_min_mm for p in pieces)
    left_edge = LineString([(20, 20), (20, 120)])
    assert all(p.distance(left_edge.interpolate(0.5, normalized=True)) > GAP for p in pieces)


def test_a_silhouette_filled_by_its_parts_raises_no_contour() -> None:
    sil = box(0, 0, 50, 50)
    assert plan.contour(sil, [region("r1", box(1, 1, 49, 49))], [], RULES) == []


def test_s3_takes_s2s_nesting_even_under_its_own_contain_share() -> None:
    big = np.zeros((40, 40), bool)
    big[0:40, 0:30] = True
    child = np.zeros((40, 40), bool)
    child[10:20, 22:38] = True  # half of it lies outside the big mask
    masks = [Mask(data=d, label=n, score=0.9, source="sam") for d, n in ((big, "lobe"),
             (child, "gyrus"))]  # fmt: skip
    plain = reconcile(masks, [], 0.5, RULES.reconcile)
    hinted = reconcile(masks, [], 0.5, RULES.reconcile, {"gyrus": "lobe"})
    assert {p.mask.label: p.parent for p in plain.parts} == {"lobe": None, "gyrus": None}
    assert {p.mask.label: p.parent for p in hinted.parts} == {"lobe": None, "gyrus": "r1"}


def sheet(contour: list[LineString], regions: list[LayoutRegion]) -> Sheet:
    return Sheet(page="letter", grade_band=None, regions=regions, textures=[], subject="organ",
                 silhouette=box(30, 30, 150, 150), contour=contour)  # fmt: skip


def test_the_rules_check_measures_the_contour_against_every_outline() -> None:
    r = region("r1", box(40, 40, 100, 100))
    ok = sheet([LineString([(30, 30), (150, 30)])], [r])
    assert validate_sheet(ok, RULES) == []
    close = sheet([LineString([(30, 39), (150, 39)])], [r])  # 0.5 mm from r1
    (v,) = validate_sheet(close, RULES)
    assert v.rule == "min_gap" and v.regions == ["r1"] and v.measured == pytest.approx(1 - HALF)


def test_regions_json_names_only_touchable_regions() -> None:
    s = sheet([], [region("r1", box(40, 40, 60, 60))]).model_copy(
        update={
            "lines": [
                SheetLine(
                    id="l1", label="g", separates=("r1", "r2"), between=("a", "b"), parent=None
                )
            ],
            "merges": [plan.SheetMerge(name="m", part_ids=("r1", "r2"), why="w")],
        }
    )
    out = plan_fields(s, {"r1"}, 2)
    assert out["subject"].label == "organ" and len(out["subject"].polygon_mm) == 4
    (x,) = out["lines"]
    assert (x.separates, x.between, x.parent) == (None, ["a", "b"], None)
    assert "merge_proposals" not in out
    both = plan_fields(s, {"r1", "r2"}, 2)
    assert both["lines"][0].separates == ["r1", "r2"]
    assert both["merge_proposals"][0].region_ids == ["r1", "r2"]


def group(name: str, members: list[str]) -> PartPhrase:
    return PartPhrase(phrase=name, print_label=name, kind="group", members=tuple(members))


def area(name: str) -> PartPhrase:
    return PartPhrase(phrase=name, print_label=name, kind="area")


def test_each_member_on_the_sheet_carries_the_name_of_the_group_that_lists_it() -> None:
    """The flower: anther and filament in the stamen, the stamen and the petal in the
    flower. A member that is a group passes its name to its own members only."""
    u = understanding(
        group("stamen", ["anther", "filament"]),
        group("flower", ["stamen", "petal"]),
        area("anther"),
        area("filament"),
        area("petal"),
        area("sepal"),
    )
    ids = {"anther": "r1", "filament": "r2", "petal": "r3", "sepal": "r4"}
    assert plan.sheet_groups(u, ids) == {"r1": "stamen", "r2": "stamen", "r3": "flower"}


def test_s3_never_gets_a_group_even_from_s2_output_cached_with_one() -> None:
    """S2 output cached before Oct 30 holds the group's union mask, a teacher entry when no
    member had one, and members nested in it: none of them reaches S3 or the teacher."""
    from app.pipeline.s2_types import Grounded, TeacherPart  # noqa: PLC0415
    from app.pipeline.s3_reconcile import without_groups  # noqa: PLC0415

    def m(label: str) -> Mask:
        return Mask(data=np.ones((2, 2), bool), label=label, score=0.9, source="sam")

    g = Grounded(
        parts=[m("anther"), m("filament"), m("stamen")],
        text=[],
        teacher=[TeacherPart(phrase="pistil", reason="no_mask", detail="no member")],
        nested={"anther": "stamen", "microsporangium": "anther"},
    )
    u = understanding(
        group("stamen", ["anther", "filament"]), group("pistil", ["ovary"]), area("anther")
    )
    out = without_groups(g, u)
    assert [x.label for x in out.parts] == ["anther", "filament"] and out.teacher == []
    assert out.nested == {"microsporangium": "anther"}
