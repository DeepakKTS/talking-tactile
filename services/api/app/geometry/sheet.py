"""A laid-out tactile sheet: what S4 produces, S5 renders and the validator checks."""

from pydantic import BaseModel, ConfigDict

from app.geometry.layout import LayoutRegion
from app.models.regions import GradeBand, PageSize, Texture


class Sheet(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    page: PageSize
    grade_band: GradeBand | None
    regions: list[LayoutRegion]
    textures: list[Texture]
