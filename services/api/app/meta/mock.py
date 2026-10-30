"""MOCK_META=1: recorded Meta responses, no network, no cost.

The synthetic test figure's S1 answer and SAM masks come from fixtures/synthetic/truth.json
and its raw masks. Figures listed in fixtures/recorded/replays.json are answered from live
recordings, through the live client's own code with a replay transport: the heart, from its
live pipeline run and its Fix outline calls. An image with no recording is refused rather
than guessed, and so is a request that was never recorded."""

import asyncio
import hashlib
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

from app.config import Meta
from app.meta.cost import CostMeter
from app.meta.types import PartPhrase, Understanding
from app.models.image import RGB
from app.models.mask import Mask
from app.paths import RECORDED_DIR
from app.pipeline.s0_ingest import figure_id
from app.prompts import Prompt
from app.synthetic.generate import OUT_DIR
from app.synthetic.load import SyntheticFigure, load_synthetic

REPLAYS = RECORDED_DIR / "replays.json"


class MockFixtureMissingError(Exception):
    """No recorded Meta responses exist for this image."""


@dataclass(frozen=True)
class CallRecord:
    call: Literal["understand", "segment"]
    figure_id: str
    phrase: str | None


class MockMetaClient:
    mode: Literal["mock"] = "mock"

    def __init__(self, rules: Meta, root: Path = OUT_DIR, replays: Path = REPLAYS) -> None:
        self._rules = rules
        self._root = root
        self._replays_index = replays
        self.meter = CostMeter(rules)
        self.calls: list[CallRecord] = []
        self._cap = rules.live_call_cap
        self._replay_clients: dict[str, Any] = {}

    @cached_property
    def _replay_files(self) -> dict[str, list[Path]]:
        """figure id -> its recordings, from the index."""
        if not self._replays_index.is_file():
            return {}
        index = json.loads(self._replays_index.read_text("utf-8"))
        root = self._replays_index.parent
        return {
            fid: sorted(p for pre in entry["prefixes"] for p in root.glob(f"{pre}*.json"))
            for fid, entry in index["figures"].items()
        }

    def _replay(self, fid: str) -> Any:
        """The live client on this figure's recordings, one per job, or None."""
        from app.meta.live import DEFAULT_BASE, Ledger, LiveCaller  # noqa: PLC0415
        from app.meta.live_client import LiveMetaClient  # noqa: PLC0415
        from app.meta.record import ReplayTransport  # noqa: PLC0415

        files = self._replay_files.get(fid)
        if not files:
            return None
        if fid not in self._replay_clients:
            ledger = Ledger(Path(tempfile.mkdtemp()) / "ledger.jsonl")  # mock calls are free

            def caller() -> LiveCaller:
                return LiveCaller(
                    key="unused-in-replay",
                    base_url=DEFAULT_BASE,
                    ledger=ledger,
                    meter=self.meter,
                    cap=self._rules.live_call_cap,
                    transport=ReplayTransport.from_files(files),
                )

            self._replay_clients[fid] = LiveMetaClient(self._rules, caller)
        client = self._replay_clients[fid]
        client.cap_calls(self._cap)
        return client

    @cached_property
    def cache_tag(self) -> str:
        """A hash over every fixture file and replayed recording, so editing a recording
        re-runs what used it."""
        h = hashlib.sha256()
        for path in sorted(p for p in self._root.rglob("*") if p.is_file()):
            h.update(path.relative_to(self._root).as_posix().encode() + b"\0")
            h.update(path.read_bytes() + b"\0")
        for fid, files in sorted(self._replay_files.items()):
            h.update(fid.encode() + b"\0")
            for path in files:
                h.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
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

    def for_job(self) -> "MockMetaClient":
        """The same client; a replayed figure starts fresh call counts, as a live job does.
        Mock jobs of one replayed figure are not run side by side."""
        self._replay_clients = {}
        self._cap = self._rules.live_call_cap
        return self

    @property
    def live_calls(self) -> int | None:
        """A replayed figure's calls under its cap, as live; synthetic answers are not counted."""
        counts = [c.calls for c in self._replay_clients.values()]
        return sum(counts) if counts else None

    def cap_calls(self, cap: int) -> None:
        """Synthetic answers are unlimited; a replayed figure keeps the live cap, since the
        cap decides which retries the recordings hold."""
        self._cap = cap
        for client in self._replay_clients.values():
            client.cap_calls(cap)

    async def understand(
        self, image: RGB, figure_id: str, prompt: Prompt, locate: Prompt
    ) -> Understanding:
        """Synthetic: the listing only, so S2 finds the parts by phrase. Replayed: as live."""
        replay = self._replay(figure_id)
        if replay is not None:
            self.calls.append(CallRecord(call="understand", figure_id=figure_id, phrase=None))
            u: Understanding = await replay.understand(image, figure_id, prompt, locate)
            return u
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
        replay = self._replay(figure_id)
        if replay is not None:
            masks: list[Mask] = await replay.segment(image, figure_id, phrase, prompt)
            return masks
        fig = self._figure(figure_id)
        self.calls.append(CallRecord(call="segment", figure_id=figure_id, phrase=phrase))
        await asyncio.sleep(0)
        return [m for m in fig.raw_masks.values() if m.label == phrase]

    async def segment_points(
        self,
        image: RGB,
        figure_id: str,
        part: str,
        objects: Sequence[tuple[Sequence[tuple[int, int]], Sequence[tuple[int, int]]]],
        prompt: Prompt,
        retry: bool = False,
        kind: str = "s2",
    ) -> list[Any]:
        replay = self._replay(figure_id)
        if replay is None:
            raise MockFixtureMissingError(
                "Mock mode has no recorded point prompts for this figure; the synthetic "
                "figure's parts are found by phrase."
            )
        self.calls.append(CallRecord(call="segment", figure_id=figure_id, phrase=part))
        answer: list[Any] = await replay.segment_points(
            image, figure_id, part, objects, prompt, retry, kind
        )
        return answer
