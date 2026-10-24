"""Masks to polygons: contour tracing, then Douglas-Peucker simplification to the point cap.

Contours run through the centers of the boundary pixels; a mitred half-pixel outward
offset puts them back on the pixel edges, so a rectangle of pixels comes back exact.
Holes are not kept: regions.json polygons have one ring, and nested parts are their own
regions. Each connected piece becomes its own polygon, largest first.
"""

import cv2
import numpy as np
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import Polygon

from app.config import Vectorize
from app.geometry.scale import PageFit
from app.models.mask import BoolImage, Mask
from app.models.regions import MAX_POLYGON_POINTS, MIN_POLYGON_POINTS

_HALF_PIXEL = 0.5
_TOLERANCE_GROWTH = 2.0


def _largest_polygon(geom: shapely.Geometry) -> Polygon | None:
    polys = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon) and not g.is_empty]
    return max(polys, key=lambda p: p.area) if polys else None


def _vertices(poly: Polygon) -> int:
    return len(poly.exterior.coords) - 1


def _simplify(poly: Polygon, tolerance: float, max_points: int) -> Polygon:
    out = poly
    tol = tolerance
    while True:
        candidate = _largest_polygon(shapely.make_valid(poly.simplify(tol, preserve_topology=True)))
        if candidate is not None and _vertices(candidate) >= MIN_POLYGON_POINTS:
            out = candidate
        if _vertices(out) <= max_points:
            return out
        tol *= _TOLERANCE_GROWTH


def mask_to_polygons_px(
    data: BoolImage, tolerance_px: float, max_points: int = MAX_POLYGON_POINTS
) -> list[Polygon]:
    """Polygons in continuous image pixel coordinates."""
    contours, _ = cv2.findContours(data.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    polys: list[Polygon] = []
    for contour in contours:
        pts = contour.reshape(-1, 2).astype(np.float64) + _HALF_PIXEL
        if len(pts) < MIN_POLYGON_POINTS:
            # A one or two pixel wide piece: its pixel squares are the exact outline.
            ring = shapely.unary_union(
                [shapely.box(x - 0.5, y - 0.5, x + 0.5, y + 0.5) for x, y in pts]
            )
        else:
            ring = shapely.make_valid(Polygon(pts)).buffer(_HALF_PIXEL, join_style="mitre")
        poly = _largest_polygon(ring)
        if poly is None:
            continue
        polys.append(_simplify(Polygon(poly.exterior), tolerance_px, max_points))
    return sorted(polys, key=lambda p: -p.area)


def mask_to_polygons_mm(mask: Mask, fit: PageFit, rules: Vectorize) -> list[Polygon]:
    """Polygons in page millimeters, each within the regions.json point cap."""
    tolerance_px = rules.simplify_tolerance_mm / fit.mm_per_px
    a = fit.mm_per_px
    ox, oy = fit.origin_mm
    return [
        affine_transform(p, [a, 0, 0, a, ox, oy])
        for p in mask_to_polygons_px(mask.data, tolerance_px)
    ]
