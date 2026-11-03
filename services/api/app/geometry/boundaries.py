"""Drawn boundaries between parts, from the image alone (S2, Oct 30).

Two parts have a drawn boundary between them when their prompt points lie in different
drawn regions, or their fill colors differ by more than FILL_DELTA.

Drawn regions. The figure (points.object_mask) is cut by barriers: ink (print_marks, under
luminance 64, text and leader lines included) and color edges, pixels where the image,
blurred at sigma 1, changes by more than EDGE_STEP in some channel across 2 px. Barriers
are grown by 1 px to seal anti-aliased gaps, and what is left falls into 4-connected
regions. A point's region is the commonest one within FILL_RADIUS px of it. A part is in
every region one of its points is in; two parts share a drawn region when those overlap.
A crease or a sulcus that does not close is no barrier, since a path goes around it.

The straight segment between two points, crossing ink, was tried first (Oct 30, the five
eval figures) and fails: inside one part it crosses the lines drawn inside a part (6 to 26
ink px on a private test figure, not distributed), the prefecture lines of a Japan region (2
to 18) and a crease drawn across one shape of that private figure (6 px); and an outline there
is taken for a leader line, so one segment crossed 1 ink px. A difference of fill color at the
two points alone fails too: the aortic arch's branches, one shape shaded, differ by up to 48.8
(left common carotid artery and aorta), more than two parts of the private figure drawn in
two colors with no line between (31.0).

EDGE_STEP, from the pairs S2 judged on the five figures (eval/plan/RESULTS.md, Drawn
boundaries, Oct 30), where the answer is known by eye: three parts of the private figure
drawn as one shape with a crease across it share a drawn region from a step of 10, the
heart's aortic arch from 5; two parts of the private figure (red against pink, no line) and
the flower's petal and filament join at 17. So 14, inside 10 to
16.

FILL_DELTA, RGB distance between the median colors within FILL_RADIUS px of the two
closest-colored points, one of each part: the Blausen brain's lobes are shaded into each
other, so six pairs of lobes share a drawn region at step 14; their fills differ by 60.7 and
more. The aortic arch, one shape shaded, differs by up to 48.8. So 55, midway."""

from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt

from app.geometry import print_marks

Mask = npt.NDArray[np.bool_]
Point = tuple[int, int]

EDGE_STEP = 14
FILL_DELTA = 55
FILL_RADIUS = 6  # points.CLEARANCE_PX: a point's clear ring
_BLUR_SIGMA = 1.0
LINE = "a drawn line or color edge lies between them"


def edge_strength(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Per pixel, the largest change in any channel across 2 px, after a light blur."""
    b = cv2.GaussianBlur(image.astype(np.float32), (0, 0), _BLUR_SIGMA)
    out = np.zeros(image.shape[:2], np.float32)
    out[:, 1:-1] = np.abs(b[:, 2:] - b[:, :-2]).max(axis=2)
    out[1:-1] = np.maximum(out[1:-1], np.abs(b[2:] - b[:-2]).max(axis=2))
    return out


def regions(
    edges: npt.NDArray[np.float32], ink: Mask, obj: Mask, step: float = EDGE_STEP
) -> npt.NDArray[np.int32]:
    """Drawn regions: the figure less barriers, labeled from 1; 0 on barriers and page."""
    barrier = cv2.dilate((ink | (edges > step)).astype(np.uint8), np.ones((3, 3), np.uint8))
    _, labels = cv2.connectedComponents((obj & (barrier == 0)).astype(np.uint8), connectivity=4)
    return np.asarray(labels, np.int32)


class Drawn:
    """The drawn regions and fill colors of one figure."""

    def __init__(self, image: npt.NDArray[np.uint8], marks: print_marks.PrintMarks, obj: Mask):
        self.image = image
        self.edges = edge_strength(image)
        self.ink, self.obj = marks.ink, obj
        self.labels = regions(self.edges, self.ink, obj)

    def _window(self, p: Point) -> tuple[slice, slice]:
        x, y = p
        r = FILL_RADIUS
        return slice(max(0, y - r), y + r + 1), slice(max(0, x - r), x + r + 1)

    def region_of(self, p: Point, labels: npt.NDArray[np.int32] | None = None) -> int:
        lab = (self.labels if labels is None else labels)[self._window(p)].ravel()
        lab = lab[lab > 0]
        return int(np.bincount(lab).argmax()) if lab.size else 0

    def fill(self, p: Point) -> npt.NDArray[np.float64]:
        rows, cols = self._window(p)
        return np.asarray(np.median(self.image[rows, cols].reshape(-1, 3), axis=0), np.float64)

    def fill_delta(self, a: Sequence[Point], b: Sequence[Point]) -> float:
        """The RGB distance between the closest-colored pair of points, one of each part."""
        fa, fb = [self.fill(p) for p in a], [self.fill(p) for p in b]
        return min(float(np.linalg.norm(x - y)) for x in fa for y in fb)

    def same_region(
        self, a: Sequence[Point], b: Sequence[Point], labels: npt.NDArray[np.int32] | None = None
    ) -> bool:
        ra = {self.region_of(p, labels) for p in a} - {0}
        rb = {self.region_of(p, labels) for p in b} - {0}
        return bool(ra & rb)

    def between(self, a: Sequence[Point], b: Sequence[Point]) -> str | None:
        """Why there is a drawn boundary between two parts, given their points, or None. A
        part with no point gives no evidence either way: None."""
        if not a or not b:
            return None
        if not self.same_region(a, b):
            return LINE
        delta = self.fill_delta(a, b)
        if delta > FILL_DELTA:
            return f"their fill colors differ by {delta:.0f}"
        return None

    def joins_at(self, a: Sequence[Point], b: Sequence[Point], steps: Sequence[int]) -> int | None:
        """The smallest edge step at which the two parts share a drawn region, or None: the
        data EDGE_STEP is chosen from (app/meta/plan_eval.py)."""
        for step in steps:
            if self.same_region(a, b, regions(self.edges, self.ink, self.obj, step)):
                return step
        return None
