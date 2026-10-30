"""Print marks on a figure, found in code with no model: label text, leader lines and ink.

Text. Thin marks are pixels that differ by more than MARK_CONTRAST from a 15 px morphological
closing (dark marks) or opening (light marks) of the gray image, so black text on a white
page and white text on a blue sea are both found. Each connected piece GLYPH_H px tall and no
wider than GLYPH_WIDE times its height is a glyph. Glyphs whose rows overlap and that sit
closer than WORD_GAP of their height chain into words. A word needs WORD_GLYPHS glyphs, a
box no taller than WORD_TALL times its tallest glyph and at least WORD_WIDE times as wide as
tall, and a ring 3 to 10 px around its box where RING_SAME of the pixels are within RING_COLOR
of the ring's median color: labels sit on a plain page, sea or tint, and anatomy does not. Text is
each word's box, grown 3 px, so a mask that fills a letter's counter is on text.

Leader lines. Straight segments (probabilistic Hough, at least LINE_MIN px) among the dark
marks that are not text, with an end within LINE_REACH px of a word. Line pixels are dark
marks within 4 px of such a segment, and, at the end away from the word, pixels within
DOT_RADIUS px that match the line's color within DOT_COLOR: the flower's red end dots.

Ink. Pixels under luminance INK_BELOW, the Arm B ink threshold: outlines, borders, black text.

Checked Oct 29 by eye on overlays of heart.png, flower.png and japan_regions.png: every
printed label is inside a word box, and no anatomy or coastline is taken for text. The
heart's leader lines are found; on the flower, the two thin ovule lines, the floral axis and
filament lines and the anther bracket are missed, and only some end dots are found. Japan
has no leader lines and none are found."""

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

Mask = npt.NDArray[np.bool_]

MARK_KERNEL = 15
MARK_CONTRAST = 80
GLYPH_H = (14, 70)
GLYPH_WIDE = 2.5
GLYPH_MIN_PX = 15
WORD_GAP = 0.8
WORD_GLYPHS = 3
WORD_TALL = 1.45
WORD_WIDE = 1.4
RING_SAME = 0.7
RING_COLOR = 30
TEXT_GROW = 3
LINE_MIN = 50
LINE_REACH = 30
LINE_HALF_WIDTH = 4
DOT_RADIUS = 14
DOT_COLOR = 60
INK_BELOW = 64

Box = tuple[int, int, int, int]  # x0, y0, x1, y1, half-open


@dataclass(frozen=True)
class PrintMarks:
    text: Mask
    line: Mask
    ink: Mask
    words: list[Box]
    segments: list[Box]  # x0, y0, x1, y1 end points


def thin_marks(gray: npt.NDArray[np.uint8]) -> tuple[Mask, Mask]:
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (MARK_KERNEL, MARK_KERNEL))
    dark = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k) > MARK_CONTRAST
    light = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k) > MARK_CONTRAST
    return np.asarray(dark), np.asarray(light)


def glyphs(marks: Mask) -> list[Box]:
    n, _, st, _ = cv2.connectedComponentsWithStats(marks.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        if GLYPH_H[0] <= h <= GLYPH_H[1] and w <= GLYPH_WIDE * h and area >= GLYPH_MIN_PX:
            out.append((x, y, x + w, y + h))
    return out


def chain(boxes: list[Box]) -> list[list[Box]]:
    """Glyphs whose rows overlap by 40% of the shorter and whose gap is under WORD_GAP of
    the taller, joined transitively."""
    order = sorted(range(len(boxes)), key=lambda i: boxes[i][0])
    parent = list(range(len(boxes)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for ai, a in enumerate(order):
        _, ay0, ax1, ay1 = boxes[a]
        for c in order[ai + 1 :]:
            cx0, cy0, _, cy1 = boxes[c]
            if cx0 > ax1 + WORD_GAP * max(ay1 - ay0, cy1 - cy0):
                break
            shared = min(ay1, cy1) - max(ay0, cy0)
            if shared > 0.4 * min(ay1 - ay0, cy1 - cy0):
                parent[find(a)] = find(c)
    groups: dict[int, list[Box]] = {}
    for i, b in enumerate(boxes):
        groups.setdefault(find(i), []).append(b)
    return list(groups.values())


def ring_same(image: npt.NDArray[np.uint8], box: Box) -> float:
    """The share of a 3 to 10 px ring around a box within 30 of the ring's median color."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = box
    ring = np.zeros((h, w), bool)
    ring[max(0, y0 - 10) : y1 + 10, max(0, x0 - 10) : x1 + 10] = True
    ring[max(0, y0 - 3) : y1 + 3, max(0, x0 - 3) : x1 + 3] = False
    px = image[ring].astype(int)
    if not len(px):
        return 0.0
    return float((np.abs(px - np.median(px, axis=0)).max(axis=1) <= RING_COLOR).mean())


def words(image: npt.NDArray[np.uint8], marks: Mask) -> list[Box]:
    out = []
    for group in chain(glyphs(marks)):
        if len(group) < WORD_GLYPHS:
            continue
        box = (
            min(b[0] for b in group),
            min(b[1] for b in group),
            max(b[2] for b in group),
            max(b[3] for b in group),
        )
        tall = box[3] - box[1]
        if tall > WORD_TALL * max(b[3] - b[1] for b in group):
            continue
        if box[2] - box[0] < WORD_WIDE * tall or ring_same(image, box) < RING_SAME:
            continue
        out.append(box)
    return out


def find(image: npt.NDArray[np.uint8]) -> PrintMarks:
    gray = np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), np.uint8)
    dark, light = thin_marks(gray)
    h, w = gray.shape
    found = words(image, dark) + words(image, light)
    text = np.zeros((h, w), bool)
    g = TEXT_GROW
    for x0, y0, x1, y1 in found:
        text[max(0, y0 - g) : y1 + g, max(0, x0 - g) : x1 + g] = True
    rest = (dark & ~text).astype(np.uint8) * 255
    raw = cv2.HoughLinesP(rest, 1, np.pi / 360, threshold=60, minLineLength=LINE_MIN, maxLineGap=4)
    reach = 2 * LINE_REACH + 1
    near = cv2.dilate(text.astype(np.uint8), np.ones((reach, reach), np.uint8)).astype(bool)
    line = np.zeros((h, w), bool)
    segments: list[Box] = []
    for x0, y0, x1, y1 in raw.reshape(-1, 4) if raw is not None else []:
        if not (near[y0, x0] or near[y1, x1]):
            continue
        segments.append((int(x0), int(y0), int(x1), int(y1)))
        drawn = np.zeros((h, w), np.uint8)
        cv2.line(drawn, (int(x0), int(y0)), (int(x1), int(y1)), 1, 2 * LINE_HALF_WIDTH + 1)
        own = (drawn > 0) & dark
        line |= own
        if near[y0, x0] != near[y1, x1]:
            far = (int(x0), int(y0)) if near[y1, x1] else (int(x1), int(y1))
            line |= end_dot(image, own, far)
    return PrintMarks(text, line, np.asarray(gray < INK_BELOW), found, segments)


def end_dot(image: npt.NDArray[np.uint8], own: Mask, far: tuple[int, int]) -> Mask:
    """Pixels within DOT_RADIUS of a leader line's far end and within DOT_COLOR of the line's
    own color: the dot some figures put where a line meets its part (the flower's red dots)."""
    h, w = own.shape
    out = np.zeros((h, w), bool)
    if not own.any():
        return out
    color = np.median(image[own].astype(int), axis=0)
    x, y, r = far[0], far[1], DOT_RADIUS
    x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r + 1), min(h, y + r + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    disk = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    close = np.abs(image[y0:y1, x0:x1].astype(int) - color).max(axis=2) <= DOT_COLOR
    out[y0:y1, x0:x1] = disk & close
    return out
