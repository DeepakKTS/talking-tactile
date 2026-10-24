"""S4 layout fixes: point symbols, gap enforcement by shrinking, textures within the limit."""

import itertools

import numpy as np
import pytest
import shapely
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon, box

from app.config import load_explore, load_tactile_rules
from app.geometry.layout import (
    LayoutRegion,
    enforce_gaps,
    make_point_symbols,
    regions_from_parts,
    size_mm,
)
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.geometry.textures import assign_textures, group_by_color
from app.synthetic.load import SyntheticFigure, load_synthetic

RULES = load_tactile_rules()
EARCONS = load_explore().earcons
G = RULES.spacing.min_gap_mm
POINT = RULES.spacing.point_symbol_min_mm
TOL = RULES.layout.gap_simplify_tolerance_mm


def region(rid: str, poly: Polygon, parent: str | None = None, kind: str = "area") -> LayoutRegion:
    return LayoutRegion(id=rid, label=rid, polygon=poly, parent=parent, kind=kind,  # type: ignore[arg-type]
                        score=0.9, source="sam")  # fmt: skip


def by_id(regions: list[LayoutRegion]) -> dict[str, LayoutRegion]:
    return {r.id: r for r in regions}


# Point symbols


def test_size_is_the_longest_side_of_the_rotated_bounding_box() -> None:
    assert size_mm(box(0, 0, 4, 10)) == pytest.approx(10)
    diamond = shapely.affinity.rotate(box(0, 0, 4, 4), 45)
    assert size_mm(diamond) == pytest.approx(4)


def test_small_parts_become_point_symbols_and_large_ones_stay() -> None:
    small = region("s", box(10, 10, 14, 13))
    large = region("l", box(30, 30, 60, 60))
    out = by_id(make_point_symbols([small, large], RULES.spacing, RULES.layout))
    assert out["l"].polygon.equals(large.polygon)
    assert out["l"].kind == "area"
    point = out["s"]
    assert point.kind == "point"
    assert len(point.polygon.exterior.coords) - 1 == RULES.layout.point_symbol_vertices
    # At least the minimum across in every direction, centered inside the old part.
    assert 2 * point.polygon.centroid.distance(point.polygon.exterior) >= POINT - 1e-9
    assert small.polygon.contains(point.polygon.centroid)
    assert point.notes and "point symbol" in point.notes[0]


# Gaps


def test_two_close_parts_end_up_a_full_gap_apart_and_only_the_larger_shrinks() -> None:
    a = region("a", box(0, 0, 50, 40))
    b = region("b", box(52, 0, 100, 40))  # 2 mm apart, b smaller
    out, unresolved = enforce_gaps([a, b], G, RULES.layout)
    got = by_id(out)
    assert unresolved == []
    assert got["a"].polygon.distance(got["b"].polygon) >= G
    assert got["b"].polygon.equals(b.polygon)
    assert got["a"].polygon.buffer(-1e-9).within(a.polygon)
    lost = a.polygon.area - got["a"].polygon.area
    assert lost == pytest.approx((G + 2 * TOL - 2) * 40, rel=0.05)
    assert any("gap" in n for n in got["a"].notes)


def test_parts_already_far_apart_are_untouched() -> None:
    a, b = region("a", box(0, 0, 10, 10)), region("b", box(20, 0, 30, 10))
    out, _ = enforce_gaps([a, b], G, RULES.layout)
    assert [r.polygon.equals(o.polygon) for r, o in zip(out, [a, b], strict=True)] == [True, True]


def test_a_child_near_the_parent_outline_shrinks_inward() -> None:
    parent = region("p", box(0, 0, 60, 60))
    child = region("c", box(1, 20, 20, 40), parent="p")
    out, unresolved = enforce_gaps([parent, child], G, RULES.layout)
    got = by_id(out)
    assert unresolved == []
    assert got["p"].polygon.equals(parent.polygon)
    assert got["c"].polygon.within(parent.polygon)
    assert got["c"].polygon.distance(parent.polygon.exterior) >= G


def test_a_point_symbol_never_shrinks_the_area_does() -> None:
    area = region("a", box(0, 0, 40, 40))
    pt = make_point_symbols([region("p", box(41, 18, 43, 20))], RULES.spacing, RULES.layout)[0]
    out, unresolved = enforce_gaps([area, pt], G, RULES.layout)
    got = by_id(out)
    assert unresolved == []
    assert got["p"].polygon.equals(pt.polygon)
    assert got["a"].polygon.distance(got["p"].polygon) >= G


def test_two_point_symbols_too_close_are_reported_not_moved() -> None:
    pts = make_point_symbols(
        [region("p", box(10, 10, 12, 12)), region("q", box(14, 10, 16, 12))],
        RULES.spacing, RULES.layout,
    )  # fmt: skip
    out, unresolved = enforce_gaps(pts, G, RULES.layout)
    assert unresolved == [("p", "q")]
    assert [r.polygon.equals(p.polygon) for r, p in zip(out, pts, strict=True)] == [True, True]


def test_a_cut_that_splits_a_part_keeps_the_largest_piece() -> None:
    u_shape = region("u", Polygon([(0, 0), (60, 0), (60, 40), (40, 40), (40, 10), (20, 10),
                                   (20, 40), (0, 40)]))  # fmt: skip
    plug = region("plug", box(21, 11, 39, 60))  # fills the notch, then overlaps below
    out, _ = enforce_gaps([u_shape, plug], G, RULES.layout)
    got = by_id(out)
    assert got["u"].polygon.geom_type == "Polygon"
    assert got["u"].polygon.distance(got["plug"].polygon) >= G


@st.composite
def scattered_boxes(draw: st.DrawFn) -> list[LayoutRegion]:
    n = draw(st.integers(2, 6))
    out = []
    for i in range(n):
        x = draw(st.floats(0, 150))
        y = draw(st.floats(0, 150))
        w = draw(st.floats(POINT + 4, 40))
        h = draw(st.floats(POINT + 4, 40))
        out.append(region(f"r{i}", box(x, y, x + w, y + h)))
    return out


@settings(max_examples=150, deadline=None)
@given(scattered_boxes())
def test_gap_enforcement_only_shrinks_and_leaves_every_gap_clear(
    regions: list[LayoutRegion],
) -> None:
    # Overlapping inputs cannot come out of reconcile; separate them the same way first.
    flat: list[LayoutRegion] = []
    for r in regions:
        poly = r.polygon
        for f in flat:
            poly = poly.difference(f.polygon)
        if poly.geom_type == "Polygon" and poly.area > 1:
            flat.append(r.model_copy(update={"polygon": poly}))
    out, unresolved = enforce_gaps(flat, G, RULES.layout)
    assert unresolved == []
    original = by_id(flat)
    for r in out:
        assert r.polygon.is_valid and not r.polygon.is_empty
        assert r.polygon.within(original[r.id].polygon.buffer(TOL + 1e-6)), "shrink, never move"
        assert len(r.notes) == len(set(r.notes))
    for a, b in itertools.combinations(out, 2):
        assert a.polygon.distance(b.polygon) >= G - 1e-6


# Textures


def test_textures_go_to_the_largest_groups_up_to_the_limit() -> None:
    regions = [
        region("big1", box(0, 0, 50, 50)), region("big2", box(60, 0, 100, 50)),
        region("mid", box(0, 60, 40, 100)), region("small", box(50, 60, 60, 70)),
        region("tiny", box(70, 60, 75, 65)),
    ]  # fmt: skip
    groups = {"big1": 0, "big2": 0, "mid": 1, "small": 2, "tiny": 3}
    out, textures = assign_textures(regions, groups, limit=3, order=RULES.textures.order,
                                    earcons=EARCONS)  # fmt: skip
    got = {r.id: r.texture for r in out}
    assert got == {"big1": "dots", "big2": "dots", "mid": "lines", "small": "grid", "tiny": None}
    assert [t.id for t in textures] == ["dots", "lines", "grid"]
    assert textures[0].meaning == "big1 and big2"
    assert textures[0].earcon_hz == EARCONS.texture_hz["dots"]
    assert any("limit" in n for n in by_id(out)["tiny"].notes)


def test_point_symbols_get_no_area_texture() -> None:
    pt = make_point_symbols([region("p", box(0, 0, 2, 2))], RULES.spacing, RULES.layout)[0]
    out, textures = assign_textures([pt], {"p": 0}, limit=3, order=RULES.textures.order,
                                    earcons=EARCONS)  # fmt: skip
    assert out[0].texture is None
    assert textures == []


def test_no_groups_means_no_textures() -> None:
    out, textures = assign_textures([region("a", box(0, 0, 9, 9))], {}, limit=3,
                                    order=RULES.textures.order, earcons=EARCONS)  # fmt: skip
    assert out[0].texture is None and textures == []


# The synthetic figure


@pytest.fixture(scope="module")
def fig() -> SyntheticFigure:
    return load_synthetic()


@pytest.fixture(scope="module")
def laid_out(fig: SyntheticFigure):
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    parts = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(parts, text, fit.mm_per_px, RULES.reconcile)
    regions = regions_from_parts(rec.parts, fit, RULES.vectorize)
    groups = group_by_color(fig.image, rec.parts, RULES.layout.color_group_max_delta)
    return rec, regions, groups


def test_synthetic_color_groups_are_the_categories(fig: SyntheticFigure, laid_out) -> None:
    rec, _, groups = laid_out
    category = {p.label: p.category for p in fig.truth.parts}
    label = {p.id: p.mask.label for p in rec.parts}
    for a, b in itertools.combinations(rec.parts, 2):
        same_category = category[label[a.id]] == category[label[b.id]]
        assert (groups[a.id] == groups[b.id]) is same_category, (label[a.id], label[b.id])


def test_synthetic_layout_fixes_every_planted_problem(fig: SyntheticFigure, laid_out) -> None:
    _, regions, groups = laid_out
    pts = make_point_symbols(regions, RULES.spacing, RULES.layout)
    spaced, unresolved = enforce_gaps(pts, G, RULES.layout)
    limit = RULES.textures.limit_for(fig.truth.grade_band)
    final, textures = assign_textures(spaced, groups, limit, RULES.textures.order, EARCONS)
    labels = {r.label: r for r in final}
    assert unresolved == []
    assert labels["pore"].kind == "point"
    assert [r.label for r in final if r.kind == "point"] == ["pore"]
    assert len(textures) == limit == 3
    assert labels["inner core"].texture is None  # the smallest color group loses out
    for a, b in itertools.combinations(final, 2):
        if a.parent == b.id or b.parent == a.id:
            child, parent = (a, b) if a.parent == b.id else (b, a)
            assert child.polygon.distance(parent.polygon.exterior) >= G
        else:
            assert a.polygon.distance(b.polygon) >= G - 1e-6, (a.label, b.label)
    gap = labels["left lobe"].polygon.distance(labels["right lobe"].polygon)
    assert gap >= G
    assert np.isfinite(gap)
