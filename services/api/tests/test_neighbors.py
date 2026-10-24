"""Centroids inside every region, and neighbor directions computed in code."""

import itertools
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon, box

from app.config import load_tactile_rules
from app.geometry.layout import LayoutRegion, regions_from_parts
from app.geometry.neighbors import OPPOSITE, centroids, direction_of, find_neighbors
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.synthetic.load import load_synthetic

RULES = load_tactile_rules()
MAX_GAP = RULES.layout.neighbor_max_gap_mm
TOL = RULES.layout.inside_point_tolerance_mm


def region(rid: str, poly: Polygon, parent: str | None = None) -> LayoutRegion:
    return LayoutRegion(id=rid, label=rid, polygon=poly, parent=parent, score=0.9, source="sam")


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [
        (1, 0, "right"), (-1, 0, "left"), (0, -1, "up"), (0, 1, "down"),
        (1, -1, "up_right"), (-1, -1, "up_left"), (1, 1, "down_right"), (-1, 1, "down_left"),
        (10, -3, "right"), (3, -10, "up"), (10, -5, "up_right"),
    ],
)  # fmt: skip
def test_direction_of_a_page_vector(dx: float, dy: float, expected: str) -> None:
    # Page coordinates: y grows down the sheet, so a negative dy is up.
    assert direction_of(dx, dy) == expected


def test_opposites_pair_up() -> None:
    assert OPPOSITE["inside"] == "around"
    for d, o in OPPOSITE.items():
        assert OPPOSITE[o] == d


def test_centroid_lies_inside_even_for_a_c_shape() -> None:
    c_shape = Polygon([(0, 0), (30, 0), (30, 5), (5, 5), (5, 25), (30, 25), (30, 30), (0, 30)])
    (x, y) = centroids([region("c", c_shape)], TOL)["c"]
    assert c_shape.contains(Point(x, y))
    assert not c_shape.contains(c_shape.centroid)


def test_neighbors_side_by_side_and_below() -> None:
    a = region("a", box(0, 0, 40, 40))
    b = region("b", box(50, 0, 90, 40))
    c = region("c", box(0, 55, 90, 70))  # a bar under both
    far = region("far", box(200, 200, 210, 210))
    got = find_neighbors([a, b, c, far], MAX_GAP)
    assert [(n.id, n.direction) for n in got["a"]] == [("b", "right"), ("c", "down")]
    assert [(n.id, n.direction) for n in got["b"]] == [("a", "left"), ("c", "down")]
    assert [(n.id, n.direction) for n in got["c"]] == [("a", "up"), ("b", "up")]
    assert got["far"] == []


def test_parent_and_child_are_inside_and_around() -> None:
    p = region("p", box(0, 0, 60, 60))
    c = region("c", box(20, 20, 40, 40), parent="p")
    got = find_neighbors([p, c], MAX_GAP)
    assert [(n.id, n.direction) for n in got["p"]] == [("c", "inside")]
    assert [(n.id, n.direction) for n in got["c"]] == [("p", "around")]


@st.composite
def separated_boxes(draw: st.DrawFn) -> list[LayoutRegion]:
    out: list[LayoutRegion] = []
    for i in range(draw(st.integers(2, 7))):
        x, y = draw(st.floats(0, 150)), draw(st.floats(0, 150))
        poly = box(x, y, x + draw(st.floats(5, 30)), y + draw(st.floats(5, 30)))
        if all(poly.distance(o.polygon) > 0.5 for o in out):
            out.append(region(f"r{i}", poly))
    return out


@settings(max_examples=200, deadline=None)
@given(separated_boxes())
def test_neighbors_are_symmetric_and_directions_opposite(regions: list[LayoutRegion]) -> None:
    got = find_neighbors(regions, MAX_GAP)
    for a, b in itertools.combinations(regions, 2):
        ab = {n.id: n.direction for n in got[a.id]}
        ba = {n.id: n.direction for n in got[b.id]}
        assert (b.id in ab) == (a.id in ba) == (a.polygon.distance(b.polygon) <= MAX_GAP)
        if b.id in ab:
            assert ba[a.id] == OPPOSITE[ab[b.id]]


QUARTER_TURN = {
    "right": "down", "down": "left", "left": "up", "up": "right",
    "up_right": "down_right", "down_right": "down_left", "down_left": "up_left",
    "up_left": "up_right", "inside": "inside", "around": "around",
}  # fmt: skip


@settings(max_examples=150, deadline=None)
@given(separated_boxes())
def test_turning_the_sheet_a_quarter_turn_turns_every_direction(
    regions: list[LayoutRegion],
) -> None:
    # (x, y) -> (-y, x) turns the sheet clockwise as seen from above (y grows down).
    turned = [
        r.model_copy(update={"polygon": affine_transform(r.polygon, [0, -1, 1, 0, 0, 0])})
        for r in regions
    ]
    before = find_neighbors(regions, MAX_GAP)
    after = find_neighbors(turned, MAX_GAP)
    for r in regions:
        expect = {n.id: QUARTER_TURN[n.direction] for n in before[r.id]}
        assert {n.id: n.direction for n in after[r.id]} == expect


@settings(max_examples=100, deadline=None)
@given(separated_boxes())
def test_every_centroid_is_inside_its_region(regions: list[LayoutRegion]) -> None:
    for rid, (x, y) in centroids(regions, TOL).items():
        poly = next(r.polygon for r in regions if r.id == rid)
        assert poly.buffer(1e-9).contains(Point(x, y))
        assert math.isfinite(x) and math.isfinite(y)


def test_synthetic_neighbors_read_like_the_figure() -> None:
    fig = load_synthetic()
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    parts = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(parts, text, fit.mm_per_px, RULES.reconcile)
    regions = regions_from_parts(rec.parts, fit, RULES.vectorize)
    label = {r.id: r.label for r in regions}
    got = {
        label[rid]: {label[n.id]: n.direction for n in ns}
        for rid, ns in find_neighbors(regions, MAX_GAP).items()
    }
    assert got["outer chamber"]["inner core"] == "inside"
    assert got["inner core"] == {"outer chamber": "around"}
    assert got["outer chamber"]["right chamber"] == "right"
    assert got["outer chamber"]["cross vessel"] == "down"
    assert got["left lobe"]["right lobe"] == "right"
    assert got["cross vessel"]["left lobe"] == "down"
    assert got["stem"]["left lobe"] == "up"


def test_a_parent_centroid_is_on_the_parent_and_off_its_children() -> None:
    # Explore guides a finger to the centroid, and the smallest region under a point wins,
    # so a parent's target must not sit on a child.
    outer = region("outer", box(0, 0, 60, 60))
    core = region("core", box(15, 15, 45, 45), parent="outer")
    grand = region("grand", box(25, 25, 35, 35), parent="core")
    got = centroids([outer, core, grand], TOL)
    for r, kids in [(outer, [core]), (core, [grand]), (grand, [])]:
        pt = Point(got[r.id])
        assert r.polygon.contains(pt)
        assert not any(k.polygon.buffer(TOL).contains(pt) for k in kids), r.id
    assert Point(got["outer"]).distance(core.polygon) >= 7.5 - TOL  # the middle of the ring


def test_synthetic_centroids_hit_their_own_region_first() -> None:
    fig = load_synthetic()
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    parts = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(parts, text, fit.mm_per_px, RULES.reconcile)
    regions = regions_from_parts(rec.parts, fit, RULES.vectorize)
    got = centroids(regions, TOL)
    for r in regions:
        pt = Point(got[r.id])
        holders = [x for x in regions if x.polygon.contains(pt)]
        assert min(holders, key=lambda x: x.polygon.area).id == r.id, r.label
