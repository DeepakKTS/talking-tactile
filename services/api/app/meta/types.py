"""What the pipeline gets back from the Meta models, as our own types. The Spark spike's S1
schema (spikes/spark_spike.py) is the source for Understanding."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.regions import FigureType

Verdict = Literal["make_tactile", "split_two_sheets", "describe_only"]


class PartPhrase(BaseModel):
    model_config = ConfigDict(frozen=True)

    phrase: str  # a short noun phrase SAM can segment
    print_label: str  # the printed label that points to this part, or empty


class Understanding(BaseModel):
    """S1: what Muse Spark reads in the figure."""

    model_config = ConfigDict(frozen=True)

    figure_type: FigureType
    title: str
    summary: str
    parts: list[PartPhrase]
    color_carries_meaning: bool
    verdict: Verdict
    verdict_reason: str
