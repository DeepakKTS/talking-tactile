"""Arm B of the S2 bake-off: closed regions found in code. Dark pixels are ink, a small
closing seals breaks in the outlines, and each connected piece of the rest is a region,
except the background that touches the image edge and pieces under the size floor."""

import numpy as np
import numpy.typing as npt

from app.geometry.closed_regions import closed_regions

WHITE = 255


def canvas(h: int = 120, w: int = 200) -> npt.NDArray[np.uint8]:
    return np.full((h, w, 3), WHITE, np.uint8)


def outline(img: npt.NDArray[np.uint8], x0: int, y0: int, x1: int, y1: int, v: int = 0) -> None:
    img[y0 : y0 + 2, x0:x1] = v
    img[y1 - 2 : y1, x0:x1] = v
    img[y0:y1, x0 : x0 + 2] = v
    img[y0:y1, x1 - 2 : x1] = v


def test_each_closed_outline_is_one_region_and_the_outer_background_is_dropped() -> None:
    img = canvas()
    outline(img, 10, 10, 90, 100)
    outline(img, 110, 10, 190, 100)
    labels, regions = closed_regions(img, ink_below=64, close_px=5, floor_px=50)
    assert [r.id for r in regions] == [1, 2]
    left, right = regions
    assert left.anchor[0] < right.anchor[0]
    assert labels[50, 50] == left.id and labels[50, 150] == right.id
    assert labels[5, 5] == 0 and labels[10, 10] == 0  # outer background and ink
    assert left.area_px == int((labels == left.id).sum())


def test_a_small_break_in_an_outline_is_closed() -> None:
    img = canvas()
    outline(img, 10, 10, 90, 100)
    img[50:53, 10:12] = WHITE  # a 3 px break in the left wall
    assert len(closed_regions(img, ink_below=64, close_px=5, floor_px=50)[1]) == 1
    assert closed_regions(img, ink_below=64, close_px=1, floor_px=50)[1] == []


def test_pieces_under_the_floor_are_dropped() -> None:
    img = canvas()
    outline(img, 10, 10, 90, 100)
    outline(img, 120, 20, 128, 28)  # a 4 x 4 px inside
    _, regions = closed_regions(img, ink_below=64, close_px=3, floor_px=50)
    assert len(regions) == 1 and regions[0].area_px > 50


def test_a_fill_lighter_than_the_ink_threshold_is_not_a_boundary() -> None:
    img = canvas()
    img[20:80, 20:80] = (230, 20, 30)  # a red fill with no outline, luminance about 84
    assert closed_regions(img, ink_below=64, close_px=5, floor_px=50)[1] == []


def test_the_anchor_is_inside_its_region_even_for_a_ring() -> None:
    img = canvas()
    outline(img, 10, 10, 110, 110)
    img[40:80, 40:80] = 0  # a solid ink block in the middle: the region is a ring
    labels, [ring] = closed_regions(img, ink_below=64, close_px=3, floor_px=50)
    x, y = ring.anchor
    assert labels[y, x] == ring.id
