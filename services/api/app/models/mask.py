"""The internal Mask type. Geometry and every stage after segmentation use only this.

A Mask is a boolean array the size of the normalized image, plus the label it was found
for, a score and where it came from. Only app/meta/sam_adapter.py knows how SAM encodes
masks on the wire; everything else sees Masks.
"""

from typing import Annotated, Any, Literal, Self

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.models.regions import RegionSource

# "synthetic" marks masks drawn by the synthetic test figure, which stands in for SAM in
# mock mode. In regions.json both count as found by segmentation.
# "code" marks print text found in code (app/geometry/print_marks.py) for S3 to cut out.
MaskSource = Literal["sam", "teacher", "synthetic", "code"]

BoolImage = NDArray[np.bool_]
_IMAGE_NDIM = 2  # rows and columns


class Mask(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    data: BoolImage
    label: Annotated[StrictStr, Field(pattern=r"\S")]
    score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    source: MaskSource

    @field_validator("data", mode="before")
    @classmethod
    def _bool_image(cls, value: Any) -> BoolImage:
        if not isinstance(value, np.ndarray):
            raise ValueError("data must be a 2-D numpy bool array")
        if value.dtype != np.bool_ or value.ndim != _IMAGE_NDIM:
            raise ValueError("data must be a 2-D numpy bool array")
        if value.size == 0:
            raise ValueError("data must not be empty")
        data: BoolImage = value.copy()
        data.flags.writeable = False
        return data

    @property
    def shape(self) -> tuple[int, int]:
        h, w = self.data.shape
        return (h, w)

    @property
    def area_px(self) -> int:
        return int(np.count_nonzero(self.data))

    def with_data(self, data: BoolImage) -> Self:
        """A copy with new pixels and the same label, score and source."""
        if data.shape != self.data.shape:
            raise ValueError(f"new data has size {data.shape}, the mask has {self.data.shape}")
        return type(self)(data=data, label=self.label, score=self.score, source=self.source)


def region_source(source: MaskSource) -> RegionSource:
    return "teacher" if source == "teacher" else "sam"
