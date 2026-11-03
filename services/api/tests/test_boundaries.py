"""Drawn boundaries between parts (app/geometry/boundaries.py), and how S2's relations use
them (app/geometry/part_masks.py): same outlines and the members of Spark's shared groups."""

import numpy as np
import numpy.typing as npt

from app.geometry import boundaries
from app.geometry import part_masks as pm
from app.geometry import points as gp

W, H = 200, 120
Image = npt.NDArray[np.uint8]


def page() -> Image:
    return np.full((H, W, 3), 255, np.uint8)


def outlined(img: Image, x0: int, x1: int) -> None:
    img[10:12, x0:x1] = img[98:100, x0:x1] = 0
    img[10:100, x0 : x0 + 2] = img[10:100, x1 - 2 : x1] = 0


def drawn(img: Image) -> boundaries.Drawn:
    scene = gp.scene_of(img, 40.0)
    return boundaries.Drawn(img, scene.marks, scene.obj)


def test_an_outline_between_two_shapes_is_a_drawn_boundary() -> None:
    img = page()
    img[12:98, 12:88] = img[12:98, 112:188] = (240, 200, 120)  # one fill, two shapes
    outlined(img, 10, 90)
    outlined(img, 110, 190)
    assert drawn(img).between([(40, 60)], [(150, 60)]) == boundaries.LINE


def test_an_open_crease_inside_one_shape_is_no_boundary() -> None:
    """One shape with a crease drawn across it, open at one end (as on a private test figure).
    The straight segment between its two sides crosses it; a path around it does not."""
    img = page()
    img[12:98, 12:188] = (240, 200, 120)
    outlined(img, 10, 190)
    img[12:70, 99:101] = 0
    assert drawn(img).between([(60, 40)], [(140, 40)]) is None


def test_a_sharp_color_edge_with_no_line_is_a_drawn_boundary() -> None:
    """Two parts in red against pink, no line between, 31 apart (as on a private test figure)."""
    img = page()
    img[12:98, 12:100] = (235, 124, 120)
    img[12:98, 100:188] = (242, 150, 140)
    outlined(img, 10, 190)
    d = drawn(img)
    assert d.fill_delta([(50, 60)], [(150, 60)]) < boundaries.FILL_DELTA
    assert d.between([(50, 60)], [(150, 60)]) == boundaries.LINE


def shaded(left: tuple[int, int, int], right: tuple[int, int, int]) -> Image:
    """One outlined shape whose fill shades smoothly from left to right."""
    img = page()
    t = np.linspace(0, 1, 176)[None, :, None]
    img[12:98, 12:188] = np.rint((1 - t) * np.array(left) + t * np.array(right)).astype(np.uint8)
    outlined(img, 10, 190)
    return img


def test_one_shape_shaded_is_no_boundary() -> None:
    """The aortic arch: one shape, shaded, the fills at two points up to 48.8 apart."""
    d = drawn(shaded((252, 26, 46), (253, 62, 79)))
    assert d.same_region([(20, 60)], [(180, 60)])
    assert d.between([(20, 60)], [(180, 60)]) is None


def test_fills_far_apart_are_a_boundary_even_when_shaded_into_each_other() -> None:
    """The Blausen lobes: shaded into each other, so one drawn region, but 60.7 and more
    apart in fill."""
    d = drawn(shaded((182, 69, 64), (111, 144, 175)))
    why = d.between([(20, 60)], [(180, 60)])
    assert d.same_region([(20, 60)], [(180, 60)])
    assert why is not None and why.startswith("their fill colors differ by ")


def test_a_part_with_no_point_gives_no_evidence() -> None:
    assert drawn(shaded((0, 0, 200), (200, 0, 0))).between([], [(100, 60)]) is None


def test_joins_at_is_the_smallest_edge_step_that_joins_the_two() -> None:
    img = page()
    img[12:98, 12:100] = (200, 120, 120)
    img[12:98, 100:188] = (220, 120, 120)  # a 20 step in one channel, blurred to less
    outlined(img, 10, 190)
    step = drawn(img).joins_at([(50, 60)], [(150, 60)], range(4, 41))
    assert step is not None and 4 < step <= 20


def box(x0: int, x1: int) -> npt.NDArray[np.bool_]:
    m = np.zeros((H, W), bool)
    m[12:98, x0:x1] = True
    return m


def test_relate_sends_the_smaller_of_two_same_outlines_across_a_boundary_to_the_teacher() -> None:
    masks = {"cerebellum": box(12, 188), "pons": box(14, 188), "far": box(0, 5)}
    r = pm.relate(masks, apart=lambda a, b: "a line")
    assert r.same_outline == {"pons": ("cerebellum", "a line")} and r.shared == []
    r = pm.relate(masks, apart=lambda a, b: None)
    assert r.same_outline == {} and r.shared == [{"cerebellum", "pons"}]


def test_core_keeps_the_largest_set_with_no_boundary_and_says_why_for_the_rest() -> None:
    """pons, medulla and spinal cord drawn as one shape; Spark adds the cerebellum."""
    stem = {"pons", "medulla", "spinal cord"}

    def apart(a: str, b: str) -> str | None:
        return None if {a, b} <= stem else "a line"

    kept, out = pm.core(["pons", "medulla", "cerebellum", "spinal cord"], apart)
    assert kept == ["pons", "medulla", "spinal cord"]
    assert out == {"cerebellum": ("pons", "a line")}
    r = pm.relate({}, [("pons", "medulla", "cerebellum", "spinal cord")], apart)
    assert r.shared == [stem] and r.left_out == {"cerebellum": ("pons", "a line")}


def test_core_with_no_two_members_together_shares_nothing() -> None:
    kept, out = pm.core(["a", "b"], lambda a, b: "a line")
    assert kept == ["a"] and out == {"b": ("a", "a line")}
    assert pm.relate({}, [("a", "b")], lambda a, b: "a line").shared == []
