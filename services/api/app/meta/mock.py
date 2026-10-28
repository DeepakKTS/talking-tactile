"""MOCK_META=1: recorded Meta responses, no network, no cost.

The only recorded figure so far is the synthetic test figure, whose S1 answer and SAM masks
come from fixtures/synthetic/truth.json and its raw masks. Recorded live responses join it
after the spikes. An image with no recording is refused rather than guessed."""

import asyncio
import hashlib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal

from app.config import Meta
from app.meta.cost import CostMeter
from app.meta.types import PartPhrase, Understanding
from app.models.image import RGB
from app.models.mask import Mask
from app.pipeline.s0_ingest import figure_id
from app.prompts import Prompt
from app.synthetic.generate import OUT_DIR
from app.synthetic.load import SyntheticFigure, load_synthetic


class MockFixtureMissingError(Exception):
    """No recorded Meta responses exist for this image."""


@dataclass(frozen=True)
class CallRecord:
    call: Literal["understand", "segment"]
    figure_id: str
    phrase: str | None


class MockMetaClient:
    mode: Literal["mock"] = "mock"

    def __init__(self, rules: Meta, root: Path = OUT_DIR) -> None:
        self._rules = rules
        self._root = root
        self.meter = CostMeter(rules)
        self.calls: list[CallRecord] = []

    @cached_property
    def cache_tag(self) -> str:
        """A hash over every fixture file, so editing a recording re-runs what used it."""
        h = hashlib.sha256()
        for path in sorted(p for p in self._root.rglob("*") if p.is_file()):
            h.update(path.relative_to(self._root).as_posix().encode() + b"\0")
            h.update(path.read_bytes() + b"\0")
        return f"mock:{h.hexdigest()}"

    @cached_property
    def _synthetic(self) -> tuple[str, SyntheticFigure]:
        fig = load_synthetic(self._root)
        return figure_id(fig.image), fig

    def _figure(self, fid: str) -> SyntheticFigure:
        known, fig = self._synthetic
        if fid != known:
            raise MockFixtureMissingError(
                "No recorded Meta responses for this image in mock mode. "
                "Mock mode knows only the synthetic test figure so far."
            )
        return fig

    async def understand(self, image: RGB, figure_id: str, prompt: Prompt) -> Understanding:
        fig = self._figure(figure_id)
        self.calls.append(CallRecord(call="understand", figure_id=figure_id, phrase=None))
        printed = {t.text for t in fig.truth.text_labels}
        phrases = [r.phrase for r in fig.truth.raw_masks if r.phrase != self._rules.text_phrase]
        parts = [
            PartPhrase(phrase=p, print_label=p if p in printed else "")
            for p in dict.fromkeys(phrases)
        ]
        await asyncio.sleep(0)
        return Understanding(
            figure_type="labeled_diagram",
            title=fig.truth.title,
            summary=fig.truth.summary,
            parts=parts,
            color_carries_meaning=fig.truth.color_carries_meaning,
            verdict="make_tactile",
            verdict_reason="Mock answer for the synthetic test figure.",
        )

    async def segment(self, image: RGB, figure_id: str, phrase: str, prompt: Prompt) -> list[Mask]:
        fig = self._figure(figure_id)
        self.calls.append(CallRecord(call="segment", figure_id=figure_id, phrase=phrase))
        await asyncio.sleep(0)
        return [m for m in fig.raw_masks.values() if m.label == phrase]
