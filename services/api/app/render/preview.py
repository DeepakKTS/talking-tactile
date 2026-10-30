"""The Fix outline preview: the figure at FADE over white, the new mask at full strength with
a 2 px outline outside it in the color farthest from what is around it, the old outline as a
1 px magenta line, positive points as black crosshairs on white, negative points as an X.
The overlay style of the S2 bake-off sheets."""

import io
from collections.abc import Sequence

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

FADE = 0.3
SIDE = 900  # px, the longer side of the preview
OUTLINE_PX = 2
OUTLINE_COLORS = [(0, 200, 255), (255, 0, 200), (0, 190, 0), (255, 140, 0), (40, 40, 255)]
OLD = (230, 0, 230)

Mask = npt.NDArray[np.bool_]


def outline_color(samples: npt.NDArray[np.uint8]) -> tuple[int, int, int]:
    """The candidate farthest, at its 5th percentile, from the given pixel colors."""
    if not len(samples):
        return OUTLINE_COLORS[0]
    px = samples.astype(np.float32)

    def score(c: tuple[int, int, int]) -> float:
        return float(np.percentile(np.linalg.norm(px - np.array(c, np.float32), axis=1), 5))

    return max(OUTLINE_COLORS, key=score)


def preview(
    image: npt.NDArray[np.uint8],
    new: Mask | None,
    old: Mask | None,
    positive: Sequence[tuple[int, int]],
    negative: Sequence[tuple[int, int]],
) -> tuple[bytes, float]:
    """The preview as PNG bytes, and its scale from image pixels."""
    h, w = image.shape[:2]
    scale = min(1.0, SIDE / max(w, h))
    size = (round(w * scale), round(h * scale))
    small = np.asarray(Image.fromarray(image).resize(size, Image.Resampling.LANCZOS))
    out = small.astype(np.float32) * FADE + 255.0 * (1 - FADE)
    k = 2 * OUTLINE_PX + 1
    if new is not None and new.any():
        m = cv2.resize(new.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
        out[m] = small[m]
        band = cv2.dilate(m.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool) & ~m
        out[band] = outline_color(np.concatenate([out[band], small[m]]).astype(np.uint8))
    if old is not None and old.any():
        o = cv2.resize(old.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)
        edge = o.astype(bool) & ~cv2.erode(o, np.ones((3, 3), np.uint8)).astype(bool)
        out[edge] = OLD
    img = Image.fromarray(out.round().astype(np.uint8))
    draw = ImageDraw.Draw(img)
    arm, gap = 12, 3
    for x0, y0 in positive:
        x, y = x0 * scale, y0 * scale
        for width, color in ((5, (255, 255, 255)), (2, (0, 0, 0))):
            draw.line((x - arm, y, x - gap, y), fill=color, width=width)
            draw.line((x + gap, y, x + arm, y), fill=color, width=width)
            draw.line((x, y - arm, x, y - gap), fill=color, width=width)
            draw.line((x, y + gap, x, y + arm), fill=color, width=width)
    for x0, y0 in negative:
        x, y = x0 * scale, y0 * scale
        for width, color in ((5, (255, 255, 255)), (2, (200, 0, 0))):
            draw.line((x - 8, y - 8, x + 8, y + 8), fill=color, width=width)
            draw.line((x - 8, y + 8, x + 8, y - 8), fill=color, width=width)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), scale
