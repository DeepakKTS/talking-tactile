"""Braille placed on a sheet, and the key. Coordinates are page mm."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from shapely.geometry import Polygon, box


class BrailleLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str  # what the braille says in print
    braille: str  # Unicode braille cells
    x_mm: float  # top-left of the dot block
    y_mm: float
    width_mm: float
    height_mm: float

    @property
    def rect(self) -> Polygon:
        return box(self.x_mm, self.y_mm, self.x_mm + self.width_mm, self.y_mm + self.height_mm)


class Placement(BaseModel):
    model_config = ConfigDict(frozen=True)

    region_id: str
    kind: Literal["label", "abbrev"]
    inside: bool  # on the part itself, or beside it
    line: BrailleLine


class KeyEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    abbrev: str
    abbrev_braille: str
    label: str
    label_braille: str
