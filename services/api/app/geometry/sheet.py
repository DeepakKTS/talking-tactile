"""A laid-out tactile sheet: what S4 produces, S5 renders and the validator checks."""

from pydantic import BaseModel, ConfigDict
from shapely.geometry import LineString, Polygon

from app.braille.models import Placement
from app.geometry.layout import LayoutRegion
from app.models.regions import GradeBand, PageSize, Texture


class SheetLine(BaseModel):
    """A line part (app/geometry/plan.py): spoken at a border, never raised as an area."""

    model_config = ConfigDict(frozen=True)

    id: str  # l1, l2, ...
    label: str
    separates: tuple[str, str] | None = None  # part ids, both on the sheet
    between: tuple[str, str] | None = None  # labels, for the teacher and the key
    parent: str | None = None  # a part id on the sheet


class SheetMerge(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    part_ids: tuple[str, ...]
    why: str


class Sheet(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    page: PageSize
    grade_band: GradeBand | None
    regions: list[LayoutRegion]
    textures: list[Texture]
    braille: list[Placement] = []
    lines: list[SheetLine] = []
    merges: list[SheetMerge] = []
    subject: str = ""
    silhouette: Polygon | None = None  # the subject's outline, for Explore
    contour: list[LineString] = []  # the pieces of it raised on the sheet
