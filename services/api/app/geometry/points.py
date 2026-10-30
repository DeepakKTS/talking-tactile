"""Prompt points for SAM, checked in code before they are sent (S2, Arm A v2f).

Spark proposes points; code decides where they go. A point is fine when it is on the figure
and at least CLEARANCE_PX from any print mark: label text, a leader line or ink
(app/geometry/print_marks.py). A point on the background (object_mask) is dropped, never
moved, since moving it would guess which part was meant. Any other point that is not fine
moves to the nearest pixel within GUARD_PX that is fine and within the fill tolerance of
the part's fill color; with none, it is dropped.

The fill color is the median color under the instance's fine points, or, with none, the
commonest color among fine pixels within GUARD_PX of the point.

CLEARANCE_PX: the widest strokes measured on the bake-off figures (90th percentile of twice
the distance transform on each stroke's ridge) were 6.0 px, the heart's leader lines and the
heart's and flower's ink outlines. So a point keeps one full line width, plus the
anti-aliased edge, between itself and a mark. 6 px is 0.48 mm on the printed flower.

OBJECT_DIFF: a pixel is figure, not page or sea, when it differs from the median border
color by more than this in some channel. Stable from 40 to 60 on the bake-off figures; at 20
the flower's tinted inset backgrounds count as figure."""

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from app.geometry import print_marks

Mask = npt.NDArray[np.bool_]
Point = tuple[int, int]

GUARD_PX = 15
CLEARANCE_PX = 6
OBJECT_DIFF = 40
NEAR = "near a mark"
BACKGROUND = "background"


def object_mask(image: npt.NDArray[np.uint8]) -> Mask:
    border = np.concatenate([image[0], image[-1], image[:, 0], image[:, -1]]).astype(int)
    background = np.median(border, axis=0)
    return np.asarray(np.abs(image.astype(int) - background).max(axis=2) > OBJECT_DIFF)


@dataclass
class Scene:
    """What the guard needs from a figure."""

    image: npt.NDArray[np.uint8]
    marks: print_marks.PrintMarks
    obj: Mask
    fill_delta: float  # layout.color_group_max_delta: RGB distance within one fill
    clearance: int = CLEARANCE_PX
    near: Mask = field(init=False)  # on a mark, or closer to one than clearance
    clean: Mask = field(init=False)  # figure, and not near a mark

    def __post_init__(self) -> None:
        m = self.marks
        marks = m.text | m.line | m.ink
        dist = cv2.distanceTransform((~marks).astype(np.uint8), cv2.DIST_L2, 5)
        self.near = np.asarray(dist < max(self.clearance, 1))
        self.clean = self.obj & ~self.near

    def on(self, p: Point) -> list[str]:
        x, y = p
        m = self.marks
        return [k for k, a in (("text", m.text), ("line", m.line), ("ink", m.ink)) if a[y, x]]


def scene_of(image: npt.NDArray[np.uint8], fill_delta: float) -> Scene:
    return Scene(image, print_marks.find(image), object_mask(image), fill_delta)


def window(scene: Scene, p: Point) -> tuple[slice, slice, npt.NDArray[np.float64]]:
    """The GUARD_PX square around p as row and column slices, and each pixel's distance."""
    h, w = scene.clean.shape
    x, y = p
    rows = slice(max(0, y - GUARD_PX), min(h, y + GUARD_PX + 1))
    cols = slice(max(0, x - GUARD_PX), min(w, x + GUARD_PX + 1))
    yy, xx = np.mgrid[rows, cols]
    return rows, cols, np.hypot(xx - x, yy - y)


def common_color(scene: Scene, p: Point) -> npt.NDArray[np.float64] | None:
    """The median color of the commonest color bin (32 levels a channel) among clean pixels
    within GUARD_PX of p."""
    rows, cols, dist = window(scene, p)
    ok = scene.clean[rows, cols] & (dist <= GUARD_PX)
    px = scene.image[rows, cols][ok].astype(int)
    if not len(px):
        return None
    bins = (px // 32) @ np.array([64, 8, 1])
    top = np.bincount(bins).argmax()
    return np.asarray(np.median(px[bins == top], axis=0), np.float64)


def guard(scene: Scene, p: Point, fill: npt.NDArray[np.float64] | None) -> dict[str, Any]:
    """A point as it would be sent: px is Spark's, sent is where it goes or None, on says
    what was under or near it, moved_px how far it moved."""
    x, y = p
    if not scene.obj[y, x]:
        return {"px": list(p), "on": [BACKGROUND], "sent": None, "moved_px": None, "dropped": True}
    on = scene.on(p) or ([NEAR] if scene.near[y, x] else [])
    if not on:
        return {"px": list(p), "on": [], "sent": list(p), "moved_px": 0.0, "dropped": False}
    ref = fill if fill is not None else common_color(scene, p)
    out: dict[str, Any] = {"px": list(p), "on": on, "sent": None, "moved_px": None}
    if ref is None:
        return out | {"dropped": True}
    rows, cols, dist = window(scene, p)
    color = np.linalg.norm(scene.image[rows, cols].astype(float) - ref, axis=2)
    ok = scene.clean[rows, cols] & (dist <= GUARD_PX) & (color <= scene.fill_delta)
    if not ok.any():
        return out | {"dropped": True}
    r, c = np.unravel_index(np.argmin(np.where(ok, dist, np.inf)), dist.shape)
    sent = [int(cols.start + c), int(rows.start + r)]
    return out | {"sent": sent, "moved_px": round(float(dist[r, c]), 1), "dropped": False}


def guard_instance(scene: Scene, points: list[Point]) -> list[dict[str, Any]]:
    clean = [p for p in points if scene.clean[p[1], p[0]]]
    fill = (
        np.asarray(np.median([scene.image[y, x].astype(int) for x, y in clean], axis=0), float)
        if clean
        else None
    )
    return [guard(scene, p, fill) for p in points]


def where_on(on: list[str]) -> str:
    """How a flag says what a dropped point was on."""
    if on == [BACKGROUND]:
        return "on the background"
    marks = [m for m in on if m != NEAR]
    return "on " + " and ".join(marks) if marks else NEAR
