"""The Meta client interface. The pipeline talks to Meta only through a MetaClient.

Mock mode (MOCK_META=1) serves recorded responses and costs nothing. Live mode needs LIVE=1:
each pipeline job gets its own LiveCaller (for_job), so the live call cap counts per job,
while the ledger and the cost meter are shared by every job of the process.
META_RECORD=NAME also saves each live call to fixtures/recorded/NAME_*.json."""

import os
from collections.abc import Sequence
from typing import Literal, NamedTuple, Protocol

from app.config import Meta
from app.meta.cost import CostMeter
from app.meta.live import Ledger, LiveCaller, live_enabled
from app.meta.mock import MockMetaClient
from app.meta.record import Recorder
from app.meta.types import Understanding
from app.models.image import RGB
from app.models.mask import BoolImage, Mask
from app.prompts import Prompt

ClientMode = Literal["mock", "live"]
Point = tuple[int, int]
SamObject = tuple[Sequence[Point], Sequence[Point]]  # positive points, negative points
RECORD_ENV = "META_RECORD"


class LiveClientUnavailableError(Exception):
    """Live mode was asked for without LIVE=1."""


class ObjectMask(NamedTuple):
    """SAM's answer for one prompted object: ids run from 1 in the order sent."""

    object_id: int
    confidence: float | None
    mask: BoolImage  # full size, empty when the answer did not decode


class MetaClient(Protocol):
    @property
    def mode(self) -> ClientMode: ...

    @property
    def meter(self) -> CostMeter: ...

    @property
    def cache_tag(self) -> str:
        """What the answers depend on besides the request, for the stage cache keys: the
        mode, and in mock mode a hash of the fixture files."""
        ...

    def for_job(self) -> "MetaClient":
        """The client one pipeline job uses: in live mode a fresh call count under the cap."""
        ...

    async def understand(
        self, image: RGB, figure_id: str, prompt: Prompt, locate: Prompt
    ) -> Understanding:
        """S1: Muse Spark reads the figure. Live, a second call locates each part."""
        ...

    async def segment(self, image: RGB, figure_id: str, phrase: str, prompt: Prompt) -> list[Mask]:
        """SAM finds every instance of one phrase. Zero matches gives an empty list."""
        ...

    async def segment_points(
        self,
        image: RGB,
        figure_id: str,
        part: str,
        objects: Sequence[SamObject],
        prompt: Prompt,
        retry: bool = False,
    ) -> list[ObjectMask]:
        """S2: SAM segments each object from its points, in one call."""
        ...


def make_client(mock: bool, rules: Meta) -> MetaClient:
    if mock:
        return MockMetaClient(rules)
    if not live_enabled():
        raise LiveClientUnavailableError(
            "Live Meta calls need LIVE=1 in the environment. "
            "Run with MOCK_META=1 for recorded responses."
        )
    from app.meta.live_client import LiveMetaClient  # noqa: PLC0415 - it imports this module

    ledger, meter = Ledger(), CostMeter(rules)
    record = os.environ.get(RECORD_ENV) or None

    def caller() -> LiveCaller:
        made = LiveCaller.from_env(rules, recorder=Recorder() if record else None)
        made.ledger, made.meter = ledger, meter
        return made

    return LiveMetaClient(rules, caller, record_prefix=record)
