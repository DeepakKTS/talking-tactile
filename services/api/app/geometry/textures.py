"""Area textures. When color carries meaning in the print figure, parts are grouped by
their fill color in code, and each group gets one texture, largest group first, up to the
limit for the grade band. Point symbols take no area texture."""

from collections.abc import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from app.config import Earcons
from app.geometry.layout import LayoutRegion
from app.geometry.reconcile import ReconciledPart
from app.models.regions import Texture, TextureId


def _fill_color(image: NDArray[np.uint8], own: NDArray[np.bool_]) -> NDArray[np.float64]:
    # The median ignores the thin dark outline at the edge of each part.
    color: NDArray[np.float64] = np.median(image[own].astype(np.float64), axis=0)
    return color


def group_by_color(
    image: NDArray[np.uint8], parts: Sequence[ReconciledPart], max_delta: float
) -> dict[str, int]:
    """Part id to color group number. Children are left out of their parent's color."""
    groups: dict[str, int] = {}
    centers: list[NDArray[np.float64]] = []
    for part in parts:
        own = part.mask.data.copy()
        for other in parts:
            if other.parent == part.id:
                own &= ~other.mask.data
        if not own.any():
            continue
        color = _fill_color(image, own)
        for g, center in enumerate(centers):
            if float(np.linalg.norm(color - center)) < max_delta:
                groups[part.id] = g
                break
        else:
            groups[part.id] = len(centers)
            centers.append(color)
    return groups


def _join(labels: Sequence[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def assign_textures(
    regions: Sequence[LayoutRegion],
    groups: Mapping[str, int],
    limit: int,
    order: Sequence[TextureId],
    earcons: Earcons,
) -> tuple[list[LayoutRegion], list[Texture]]:
    members: dict[int, list[LayoutRegion]] = {}
    for r in regions:
        if r.kind == "area" and r.group_key in groups:
            members.setdefault(groups[r.group_key], []).append(r)
    first_seen = {g: i for i, g in enumerate(members)}
    ranked = sorted(
        members, key=lambda g: (-sum(r.polygon.area for r in members[g]), first_seen[g])
    )
    texture_of: dict[int, TextureId] = {g: order[i] for i, g in enumerate(ranked[:limit])}

    textures: list[Texture] = []
    for group in ranked[:limit]:
        labels = list(dict.fromkeys(r.label for r in members[group]))
        tid = texture_of[group]
        textures.append(Texture(id=tid, meaning=_join(labels), earcon_hz=earcons.texture_hz[tid]))

    out: list[LayoutRegion] = []
    for r in regions:
        g = groups.get(r.group_key) if r.kind == "area" else None
        if g is None:
            out.append(r.model_copy(update={"texture": None}))
        elif g in texture_of:
            out.append(r.model_copy(update={"texture": texture_of[g]}))
        else:
            out.append(
                r.noted(
                    f"no area texture: color groups are over the limit of {limit}", texture=None
                )
            )
    return out, textures
