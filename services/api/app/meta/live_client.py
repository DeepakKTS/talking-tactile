"""The live Meta client, as far as it is built. segment calls SAM 3.1 through LiveCaller, so
each call is gated on LIVE=1, capped, metered and written to the ledger. understand (S1) and
the retries, semaphore and response cache are tracker d1-8; understand raises until then.
make_client does not hand this out yet."""

import io
import re
from typing import Literal

from PIL import Image

from app.config import Meta
from app.meta import sam_adapter
from app.meta.client import LiveClientUnavailableError
from app.meta.cost import CostMeter
from app.meta.live import LiveCaller
from app.meta.types import Understanding
from app.models.image import RGB
from app.models.mask import Mask
from app.prompts import Prompt

_SLUG = re.compile(r"[^a-z0-9]+")


def png_bytes(image: RGB) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return buf.getvalue()


class LiveMetaClient:
    mode: Literal["live"] = "live"

    def __init__(self, rules: Meta, caller: LiveCaller, record_prefix: str | None = None) -> None:
        self._models = rules.models
        self._caller = caller
        self._record_prefix = record_prefix

    @property
    def meter(self) -> CostMeter:
        return self._caller.meter

    @property
    def cache_tag(self) -> str:
        """Live answers depend on the model ids, so a model change re-runs S1 and S2."""
        return f"live:{self._models.spark}:{self._models.sam}"

    async def understand(self, image: RGB, figure_id: str, prompt: Prompt) -> Understanding:
        raise LiveClientUnavailableError(
            "S1 on the live client is tracker d1-8. Run with MOCK_META=1 for recorded answers."
        )

    async def segment(self, image: RGB, figure_id: str, phrase: str, prompt: Prompt) -> list[Mask]:
        h, w = image.shape[:2]
        name = None
        if self._record_prefix is not None:
            name = f"{self._record_prefix}_{_SLUG.sub('_', phrase.lower()).strip('_')}"
        res = await self._caller.post_sse(
            "/responses",
            sam_adapter.request_body(self._models.sam, png_bytes(image), prompt.template, phrase),
            caller="s2",
            model=self._models.sam,
            describe=f"figure {figure_id[:12]} {w}x{h}, phrase: {phrase}",
            units=lambda _usage: {"images": 1},
            record_as=name,
        )
        parsed = await sam_adapter.parse_events(res.body)
        return sam_adapter.to_masks(parsed, (h, w), phrase)
