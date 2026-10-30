"""S2's output: the touchable part masks, the print text, and what the teacher must see."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.mask import BoolImage, Mask

TeacherReason = Literal["spill", "no_mask", "no_points"]


class TeacherPart(BaseModel):
    """A listed part S2 could not make touchable. A spill keeps SAM's mask as a suggestion
    for the teacher; it is never touchable."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    phrase: str
    reason: TeacherReason
    detail: str
    suggestion: BoolImage | None = None

    @field_validator("suggestion", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        return None if value is None else value.astype(bool)


class Grounded(BaseModel):
    model_config = ConfigDict(frozen=True)

    parts: list[Mask]  # in phrase order, then SAM's instance order
    text: list[Mask]
    flags: dict[str, list[str]] = {}  # per phrase, in words
    teacher: list[TeacherPart] = []
    facts: dict[str, Any] = {}  # per phrase: points, confidences, pixels won and lost
