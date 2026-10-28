"""S3 reconcile rules on Masks: text removal, specks, slivers, near duplicates, nesting,
partial overlaps. Small hand-built cases, a property test, then the synthetic figure."""

import itertools

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.config import Reconcile, load_tactile_rules
from app.geometry.reconcile import ReconciledPart, reconcile
from app.models.mask import BoolImage, Mask
from app.synthetic.load import SyntheticFigure, load_synthetic

RULES = load_tactile_rules().reconcile
# Unit cases use 1 mm pixels; these limits keep the arithmetic readable.
UNIT = Reconcile(duplicate_iou=0.8, contain_fraction=0.95, speck_max_area_mm2=3.0,
                 sliver_max_width_mm=2.0)  # fmt: skip
H, W = 40, 60


def box(x0: int, y0: int, x1: int, y1: int) -> BoolImage:
    data = np.zeros((H, W), dtype=bool)
    data[y0:y1, x0:x1] = True
    return data


def mask(data: BoolImage, label: str, score: float = 0.9) -> Mask:
    return Mask(data=data, label=label, score=score, source="sam")


def by_label(parts: list[ReconciledPart]) -> dict[str, ReconciledPart]:
    return {p.mask.label: p for p in parts}


def run(masks: list[Mask], text: list[Mask] | None = None, rules: Reconcile = UNIT):
    return reconcile(masks, text or [], mm_per_px=1.0, rules=rules)


def test_ids_follow_input_order() -> None:
    out = run([mask(box(0, 0, 10, 10), "a"), mask(box(20, 0, 30, 10), "b")])
    assert [(p.id, p.mask.label) for p in out.parts] == [("r1", "a"), ("r2", "b")]


def test_text_pixels_are_removed() -> None:
    out = run([mask(box(0, 0, 20, 10), "a")], text=[mask(box(10, 0, 20, 10), "text label")])
    assert np.array_equal(out.parts[0].mask.data, box(0, 0, 10, 10))


def test_specks_are_removed_but_the_part_stays() -> None:
    data = box(0, 0, 10, 10) | box(30, 30, 31, 32)  # 2 px speck, limit 3 mm2
    out = run([mask(data, "a")])
    assert np.array_equal(out.parts[0].mask.data, box(0, 0, 10, 10))


def test_a_part_that_is_only_specks_is_dropped() -> None:
    out = run([mask(box(0, 0, 1, 2), "dust")])
    assert out.parts == []
    assert [(d.label, d.reason) for d in out.dropped] == [("dust", "empty")]


def test_slivers_are_dropped_and_thick_parts_kept() -> None:
    out = run([mask(box(0, 0, 50, 1), "line"), mask(box(0, 10, 50, 13), "bar")])
    assert [p.mask.label for p in out.parts] == ["bar"]
    assert [(d.label, d.reason) for d in out.dropped] == [("line", "sliver")]


def test_near_duplicates_keep_the_higher_score() -> None:
    a = mask(box(0, 0, 20, 20), "chamber", 0.7)
    b = mask(box(0, 0, 20, 21), "big chamber", 0.9)  # IoU 400/420 = 0.95
    out = run([a, b])
    assert [p.mask.label for p in out.parts] == ["big chamber"]
    assert out.parts[0].merged == ["chamber"]
    assert [(d.label, d.reason) for d in out.dropped] == [("chamber", "duplicate of big chamber")]


def test_overlap_below_the_duplicate_threshold_is_not_merged() -> None:
    a = mask(box(0, 0, 20, 20), "a", 0.9)
    b = mask(box(0, 4, 20, 24), "b", 0.8)  # IoU 320/480 = 0.67
    out = run([a, b])
    assert len(out.parts) == 2


def test_contained_part_becomes_a_child_of_the_smallest_container() -> None:
    outer = mask(box(0, 0, 50, 40), "outer")
    middle = mask(box(10, 10, 40, 30), "middle")
    inner = mask(box(20, 15, 30, 25), "inner")
    parts = by_label(run([inner, outer, middle]).parts)
    assert parts["outer"].parent is None
    assert parts["middle"].parent == parts["outer"].id
    assert parts["inner"].parent == parts["middle"].id
    # A parent keeps its full area; the child is drawn inside it.
    assert np.array_equal(parts["outer"].mask.data, box(0, 0, 50, 40))


def test_mostly_contained_part_nests_at_the_threshold() -> None:
    big = mask(box(0, 0, 40, 40), "big")
    small = mask(box(30, 10, 41, 20), "small")  # 100 of 110 px inside: 0.91
    parts = by_label(run([big, small]).parts)
    assert parts["small"].parent is None
    loose = Reconcile(**{**UNIT.model_dump(), "contain_fraction": 0.9})
    parts = by_label(run([big, small], rules=loose).parts)
    assert parts["small"].parent == parts["big"].id


def test_partial_overlap_goes_to_the_smaller_part() -> None:
    big = mask(box(0, 0, 30, 20), "big")  # 600 px
    small = mask(box(25, 0, 40, 20), "small")  # 300 px, 100 px shared
    parts = by_label(run([big, small]).parts)
    assert np.array_equal(parts["small"].mask.data, box(25, 0, 40, 20))
    assert np.array_equal(parts["big"].mask.data, box(0, 0, 25, 20))


def test_partial_overlap_between_equal_parts_goes_to_the_higher_score() -> None:
    a = mask(box(0, 0, 20, 20), "a", 0.6)
    b = mask(box(15, 0, 35, 20), "b", 0.8)
    parts = by_label(run([a, b]).parts)
    assert np.array_equal(parts["b"].mask.data, box(15, 0, 35, 20))
    assert np.array_equal(parts["a"].mask.data, box(0, 0, 15, 20))


def test_trimming_that_leaves_a_speck_removes_it() -> None:
    big = mask(box(0, 0, 30, 20) | box(30, 0, 31, 2), "big")  # a 2 px tail
    small = mask(box(29, 0, 45, 20), "small")
    parts = by_label(run([big, small]).parts)
    assert not parts["big"].mask.data[:, 29:].any()


def test_masks_of_different_sizes_are_refused() -> None:
    with pytest.raises(ValueError, match="size"):
        run([mask(box(0, 0, 5, 5), "a"), Mask(data=np.ones((5, 5), bool), label="b", score=1,
                                                source="sam")])  # fmt: skip


@st.composite
def random_masks(draw: st.DrawFn) -> list[Mask]:
    n = draw(st.integers(1, 6))
    out = []
    for i in range(n):
        x0 = draw(st.integers(0, W - 4))
        y0 = draw(st.integers(0, H - 4))
        x1 = draw(st.integers(x0 + 1, W))
        y1 = draw(st.integers(y0 + 1, H))
        score = draw(st.floats(0, 1))
        out.append(mask(box(x0, y0, x1, y1), f"m{i}", score))
    return out


@settings(max_examples=300, deadline=None)
@given(random_masks())
def test_reconcile_invariants(masks: list[Mask]) -> None:
    out = run(masks)
    by_id = {p.id: p for p in out.parts}
    inputs = {f"r{i + 1}": m for i, m in enumerate(masks)}
    for p in out.parts:
        assert p.mask.area_px > 0
        assert not (p.mask.data & ~inputs[p.id].data).any(), "reconcile never adds pixels"
        if p.parent is not None:
            assert p.parent in by_id
    assert len(out.parts) + len(out.dropped) == len(masks)

    def ancestors(pid: str) -> set[str]:
        seen: set[str] = set()
        while (parent := by_id[pid].parent) is not None:
            assert parent not in seen, "parent chain has a cycle"
            seen.add(parent)
            pid = parent
        return seen

    for a, b in itertools.combinations(out.parts, 2):
        related = a.id in ancestors(b.id) or b.id in ancestors(a.id)
        if not related:
            assert not (a.mask.data & b.mask.data).any(), "unrelated parts must not overlap"


@pytest.fixture(scope="module")
def fig() -> SyntheticFigure:
    return load_synthetic()


@pytest.fixture(scope="module")
def synthetic_result(fig: SyntheticFigure):
    parts = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    return reconcile(parts, text, mm_per_px=1 / fig.truth.px_per_mm, rules=RULES)


def test_synthetic_parts_come_out_once_each(fig: SyntheticFigure, synthetic_result) -> None:
    labels = sorted(p.mask.label for p in synthetic_result.parts)
    assert labels == sorted(p.label for p in fig.truth.parts)


def test_synthetic_cleanups_restore_the_truth(fig: SyntheticFigure, synthetic_result) -> None:
    parts = by_label(synthetic_result.parts)
    for part in fig.truth.parts:
        if part.id in {"left_lobe", "right_lobe"}:
            continue
        got = parts[part.label].mask.data
        assert np.array_equal(got, fig.truth_masks[part.id].data), part.label


def test_synthetic_overlap_goes_to_the_smaller_lobe(fig: SyntheticFigure, synthetic_result) -> None:
    parts = by_label(synthetic_result.parts)
    raw_l, raw_r = fig.raw_masks["raw_left_lobe"].data, fig.raw_masks["raw_right_lobe"].data
    assert raw_l.sum() < raw_r.sum()
    assert np.array_equal(parts["left lobe"].mask.data, raw_l)
    assert np.array_equal(parts["right lobe"].mask.data, raw_r & ~raw_l)


def test_synthetic_nesting_and_drops(synthetic_result) -> None:
    parts = by_label(synthetic_result.parts)
    assert parts["inner core"].parent == parts["outer chamber"].id
    assert all(p.parent is None for p in synthetic_result.parts if p.mask.label != "inner core")
    assert parts["right chamber"].merged == ["right side chamber"]
    reasons = sorted((d.label, d.reason) for d in synthetic_result.dropped)
    assert reasons == [("cross vessel", "sliver"),
                       ("right side chamber", "duplicate of right chamber")]  # fmt: skip
