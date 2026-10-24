"""regions.json from a laid-out sheet: the file Explore runs from."""

from pydantic import BaseModel, ConfigDict

from app.braille.place import BrailleLayout
from app.config import TactileRules
from app.geometry.neighbors import centroids, find_neighbors
from app.geometry.sheet import Sheet
from app.models.mask import region_source
from app.models.regions import FigureType, Page, Region, RegionsFile


class FigureInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    figure_id: str
    title: str
    figure_type: FigureType
    summary: str


def build_regions_file(sheet: Sheet, braille: BrailleLayout, info: FigureInfo,
                       rules: TactileRules) -> RegionsFile:  # fmt: skip
    d = rules.render.coordinate_decimals
    width, height = rules.page.dimensions_mm[sheet.page]
    abbrev = {p.region_id: p.line.text for p in braille.placements if p.kind == "abbrev"}
    centers = centroids(sheet.regions, rules.layout.inside_point_tolerance_mm)
    neighbors = find_neighbors(sheet.regions, rules.layout.neighbor_max_gap_mm)
    regions: list[Region] = []
    for r in sheet.regions:
        pts: list[tuple[float, float]] = []
        for x, y in list(r.polygon.exterior.coords)[:-1]:
            pt = (round(x, d), round(y, d))
            if not pts or pts[-1] != pt:
                pts.append(pt)
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        cx, cy = centers[r.id]
        optional = {"abbrev": abbrev.get(r.id), "texture": r.texture}
        regions.append(
            Region(
                id=r.id,
                label=r.label,
                polygon_mm=pts,
                centroid_mm=(round(cx, d), round(cy, d)),
                parent=r.parent,
                neighbors=neighbors[r.id],
                source=region_source(r.source),
                confidence=r.score,
                verified_by_teacher=False,
                # The schema allows these to be missing but not null.
                **{k: v for k, v in optional.items() if v is not None},
            )
        )
    return RegionsFile(
        schema_version=1,
        figure_id=info.figure_id,
        title=info.title,
        figure_type=info.figure_type,
        grade_band=sheet.grade_band,
        page=Page(size=sheet.page, width_mm=width, height_mm=height),
        summary=info.summary,
        textures=sheet.textures,
        regions=regions,
    )
