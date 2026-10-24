"""The Meta client interface. The pipeline talks to Meta only through a MetaClient.

Mock mode (MOCK_META=1) serves recorded responses and costs nothing. The live client, with
timeouts, retries, the SAM semaphore and the response cache, is tracker d1-8 and is
written from the spike results, not before."""

from typing import Literal, Protocol

from app.config import Meta
from app.meta.cost import CostMeter
from app.meta.mock import MockMetaClient
from app.meta.types import Understanding
from app.models.image import RGB
from app.models.mask import Mask

ClientMode = Literal["mock", "live"]


class LiveClientUnavailableError(Exception):
    """The live client does not exist yet."""


class MetaClient(Protocol):
    @property
    def mode(self) -> ClientMode: ...

    @property
    def meter(self) -> CostMeter: ...

    async def understand(self, image: RGB, figure_id: str) -> Understanding:
        """S1: Muse Spark reads the figure."""
        ...

    async def segment(self, image: RGB, figure_id: str, phrase: str) -> list[Mask]:
        """S2: SAM finds every instance of one phrase. Zero matches gives an empty list."""
        ...


def make_client(mock: bool, rules: Meta) -> MetaClient:
    if mock:
        return MockMetaClient(rules)
    raise LiveClientUnavailableError(
        "The live Meta client is not built yet (tracker d1-8, after the spikes). "
        "Run with MOCK_META=1."
    )
