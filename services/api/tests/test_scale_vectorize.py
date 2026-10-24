"""Fitting the image into the figure area, and masks to polygons in page mm."""

import numpy as np
import pytest
import shapely
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from app.config import load_tactile_rules
from app.geometry.scale import PageFit, fit_to_page
from app.geometry.vectorize import mask_to_polygons_mm, mask_to_polygons_px
from app.models.regions import MAX_POLYGON_POINTS
from app.synthetic.load import SyntheticFigure, load_synthetic

RULES = load_tactile_rules()
PAGE = RULES.page


def n_vertices(poly: Polygon) -> int:
    return len(poly.exterior.coords) - 1


# Scaling


@pytest.mark.parametrize("size", ["letter", "a4"])
@settings(max_examples=100, deadline=None)
@given(w=st.integers(16, 4096), h=st.integers(16, 4096))
def test_fit_fills_one_side_and_stays_inside(size: str, w: int, h: int) -> None:
    fit = fit_to_page(w, h, size, PAGE)  # type: ignore[arg-type]
    ax, ay, aw, ah = PAGE.figure_area_mm(size)  # type: ignore[arg-type]
    x0, y0 = fit.to_page_mm(np.array([[0.0, 0.0]]))[0]
    x1, y1 = fit.to_page_mm(np.array([[float(w), float(h)]]))[0]
    eps = 1e-9
    assert ax - eps <= x0 < x1 <= ax + aw + eps
    assert ay - eps <= y0 < y1 <= ay + ah + eps
    assert abs((x1 - x0) - aw) < 1e-6 or abs((y1 - y0) - ah) < 1e-6
    assert (x1 - x0) / (y1 - y0) == pytest.approx(w / h)
    # centered in the area
    assert (x0 - ax) == pytest.approx(ax + aw - x1, abs=1e-6)
    assert (y0 - ay) == pytest.approx(ay + ah - y1, abs=1e-6)


@settings(max_examples=100, deadline=None)
@given(pts=st.lists(st.tuples(st.floats(0, 2048), st.floats(0, 2048)), min_size=1, max_size=20))
def test_page_mm_round_trips_to_pixels(pts: list[tuple[float, float]]) -> None:
    fit = fit_to_page(1479, 2048, "letter", PAGE)
    arr = np.array(pts)
    assert np.allclose(fit.to_image_px(fit.to_page_mm(arr)), arr)


def test_synthetic_fit_matches_the_generator() -> None:
    fig = load_synthetic()
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", PAGE)
    assert 1 / fit.mm_per_px == pytest.approx(fig.truth.px_per_mm, rel=1e-3)


def test_fit_refuses_empty_images() -> None:
    with pytest.raises(ValueError):
        fit_to_page(0, 10, "letter", PAGE)


# Vectorizing


def rect_mask(h: int, w: int, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    data = np.zeros((h, w), bool)
    data[y0:y1, x0:x1] = True
    return data


def test_rectangle_comes_back_exact_in_pixel_coordinates() -> None:
    polys = mask_to_polygons_px(rect_mask(50, 80, 10, 5, 30, 25), tolerance_px=0.5)
    assert len(polys) == 1
    assert (
        polys[0]
        .normalize()
        .equals_exact(Polygon([(10, 5), (30, 5), (30, 25), (10, 25)]).normalize(), 1e-9)
    )


def test_every_component_becomes_a_polygon_largest_first() -> None:
    data = rect_mask(50, 80, 0, 0, 10, 10) | rect_mask(50, 80, 40, 10, 70, 40)
    polys = mask_to_polygons_px(data, tolerance_px=0.5)
    assert [round(p.area) for p in polys] == [900, 100]


def test_empty_mask_has_no_polygons() -> None:
    assert mask_to_polygons_px(np.zeros((10, 10), bool), tolerance_px=0.5) == []


def test_a_mask_with_a_hole_keeps_its_outside() -> None:
    data = rect_mask(60, 60, 10, 10, 50, 50) & ~rect_mask(60, 60, 20, 20, 40, 40)
    polys = mask_to_polygons_px(data, tolerance_px=0.5)
    assert [round(p.area) for p in polys] == [1600]


def test_point_cap_is_met_by_raising_the_tolerance() -> None:
    yy, xx = np.mgrid[0:800, 0:800]
    r = 380 + 12 * np.sin(np.arctan2(yy - 400, xx - 400) * 90)  # a wavy star, many corners
    data = np.hypot(xx - 400, yy - 400) <= r
    polys = mask_to_polygons_px(data, tolerance_px=0.1, max_points=MAX_POLYGON_POINTS)
    assert 3 <= n_vertices(polys[0]) <= MAX_POLYGON_POINTS
    assert polys[0].is_valid


@settings(max_examples=120, deadline=None)
@given(
    cx=st.floats(60, 140), cy=st.floats(60, 140), rx=st.floats(8, 55), ry=st.floats(8, 55),
    angle=st.floats(0, 180),
)  # fmt: skip
def test_random_ellipses_vectorize_within_a_pixel(
    cx: float, cy: float, rx: float, ry: float, angle: float
) -> None:
    true = shapely.affinity.rotate(
        shapely.affinity.scale(shapely.Point(cx, cy).buffer(1, quad_segs=64), rx, ry), angle
    )
    assume(true.bounds[0] > 1 and true.bounds[1] > 1 and true.bounds[2] < 199)
    yy, xx = np.mgrid[0:200, 0:200]
    data = shapely.contains_xy(true, xx + 0.5, yy + 0.5)
    polys = mask_to_polygons_px(data, tolerance_px=0.3, max_points=MAX_POLYGON_POINTS)
    assert len(polys) == 1
    poly = polys[0]
    assert poly.is_valid
    assert n_vertices(poly) <= MAX_POLYGON_POINTS
    assert poly.hausdorff_distance(true) < 1.5
    # Vectorizing must reproduce the mask; rasterizing a small ellipse already moves its area.
    assert poly.area == pytest.approx(data.sum(), rel=0.03)


@pytest.fixture(scope="module")
def fig() -> SyntheticFigure:
    return load_synthetic()


def test_synthetic_parts_vectorize_onto_their_true_outlines(fig: SyntheticFigure) -> None:
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", PAGE)
    for part in fig.truth.parts:
        polys = mask_to_polygons_mm(fig.truth_masks[part.id], fit, RULES.vectorize)
        assert len(polys) == 1, part.id
        poly, true = polys[0], Polygon(part.outline_mm)
        assert poly.is_valid
        assert n_vertices(poly) <= MAX_POLYGON_POINTS
        assert poly.hausdorff_distance(true) < 0.25, part.id
        assert poly.area == pytest.approx(true.area, rel=0.02), part.id


def test_page_fit_is_a_pydantic_model() -> None:
    fit = fit_to_page(100, 200, "a4", PAGE)
    assert isinstance(fit, PageFit)
    assert fit.page == "a4"
