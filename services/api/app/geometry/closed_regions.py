"""Closed regions of a figure, found in code: Arm B of the S2 bake-off (spikes/sam.md).

Pixels darker than a luminance threshold are ink. A small square closing seals breaks
in the outlines. Every 4-connected piece of what is left is a region, except pieces that
touch the image edge (the outer background) and pieces under the size floor. Ids run in
reading order of each region's anchor, the point deepest inside it."""

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Region:
    id: int
    area_px: int
    anchor: tuple[int, int]  # (x, y), the pixel farthest from the region's edge


def closed_regions(
    rgb: npt.NDArray[np.uint8], *, ink_below: int, close_px: int, floor_px: float
) -> tuple[npt.NDArray[np.int32], list[Region]]:
    """Returns a label image (0 for ink, background and dropped pieces) and the regions."""
    lum = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = (lum < ink_below).astype(np.uint8)
    if close_px > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_px, close_px))
        ink = np.asarray(cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel), np.uint8)
    n, raw, stats, _ = cv2.connectedComponentsWithStats(1 - ink, connectivity=4)
    edge = set(np.unique(np.concatenate([raw[0], raw[-1], raw[:, 0], raw[:, -1]])).tolist())
    found = []
    for i in range(1, n):
        if i in edge or stats[i, cv2.CC_STAT_AREA] < floor_px:
            continue
        piece = (raw == i).astype(np.uint8)
        depth = cv2.distanceTransform(np.pad(piece, 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
        row, col = np.unravel_index(int(np.argmax(depth)), depth.shape)
        found.append((int(row), int(col), i, int(stats[i, cv2.CC_STAT_AREA])))
    found.sort()
    labels = np.zeros(raw.shape, np.int32)
    regions = []
    for new_id, (y, x, old, area) in enumerate(found, 1):
        labels[raw == old] = new_id
        regions.append(Region(new_id, area, (x, y)))
    return labels, regions
