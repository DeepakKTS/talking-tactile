"""S2's output: the touchable part masks, the print text, what the teacher must see, and
what S2 found about the parts: nesting, merge proposals and the subject's silhouette."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.mask import BoolImage, Mask

TeacherReason = Literal["spill", "same_outline", "no_mask", "no_points"]


class TeacherPart(BaseModel):
    """A listed part S2 could not make touchable. A spill, or a mask with another part's
    outline across a drawn boundary (same_outline), keeps SAM's mask as a suggestion for
    the teacher; it is never touchable."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    phrase: str
    reason: TeacherReason
    detail: str
    suggestion: BoolImage | None = None

    @field_validator("suggestion", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        return None if value is None else value.astype(bool)


class MergeProposal(BaseModel):
    """Areas drawn as one shape: Spark said so (shares_region), or their masks overlap, and
    the image shows no drawn boundary between them."""

    model_config = ConfigDict(frozen=True)

    parts: tuple[str, ...]  # phrases, in S1 order
    name: str  # the suggested combined name
    why: str  # in words, for the teacher
    # (phrase, why): parts Spark marked as one shape with these that the image separates
    left_out: tuple[tuple[str, str], ...] = ()


class Grounded(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    parts: list[Mask]  # in phrase order, then SAM's instance order
    text: list[Mask]
    flags: dict[str, list[str]] = {}  # per phrase, in words
    teacher: list[TeacherPart] = []
    facts: dict[str, Any] = {}  # per phrase: points, confidences, pixels won and lost
    nested: dict[str, str] = {}  # child phrase -> parent phrase, from the masks alone
    merges: list[MergeProposal] = []
    silhouette: BoolImage | None = None  # the subject's outline, largest piece only

    @field_validator("silhouette", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        return None if value is None else value.astype(bool)
