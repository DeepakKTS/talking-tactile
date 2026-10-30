"""The live Meta client. Every call goes through LiveCaller, so it is gated on LIVE=1, capped
per job, metered and written to the ledger.

S1 is two Muse Spark calls at reasoning effort medium (the S1 spike's effort). The listing
call sends the S1 prompt and LISTING_SCHEMA. The locate call sends the listed parts and the
sheet (grade band, printed size, minimum part and gap) with app/prompts/s1_locate.v2.json
and LOCATE_SCHEMA, and its answer is merged into the parts: kind, members, parent, the
areas a line separates, and instances with their points on the 0-1000 grid; and into the
figure: subject and shares_region. Names that are not listed parts are dropped in code.

S2 sends point prompts, several objects per call (sam_adapter.objects_request_body).
segment sends a phrase: S2's subject, for the silhouette, and a part a teacher adds by
name."""

import asyncio
import base64
import io
import json
import re
from collections.abc import Callable, Sequence
from typing import Any, Literal

from PIL import Image

from app.config import Meta
from app.meta import sam_adapter
from app.meta.client import MetaClient, ObjectMask, SamObject, job_cap
from app.meta.cost import CostMeter
from app.meta.live import LiveCaller, spark_units
from app.meta.types import (
    LISTING_SCHEMA,
    LOCATE_SCHEMA,
    Instance,
    PartPhrase,
    SharedRegion,
    SheetContext,
    Understanding,
)
from app.models.image import RGB
from app.models.mask import Mask
from app.prompts import Prompt

SPARK_EFFORT = "medium"  # spikes/muse-spark.md
_PAIR = 2  # a line separates two areas; a shared region has two or more
_SLUG = re.compile(r"[^a-z0-9]+")


def png_bytes(image: RGB) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return buf.getvalue()


def slug(text: str) -> str:
    return _SLUG.sub("_", text.lower()).strip("_")


def spark_body(
    model: str,
    system: str | None,
    text: str,
    png: bytes,
    schema: tuple[str, dict[str, Any]],
) -> dict[str, Any]:
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    content = [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    if system is not None:
        messages.insert(0, {"role": "system", "content": system})
    name, js = schema
    return {
        "model": model,
        "reasoning_effort": SPARK_EFFORT,
        "messages": messages,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": js}},
    }


def object_masks(parsed: Any, size: tuple[int, int]) -> list[ObjectMask]:
    """Each numbered object's mask, full size."""
    return [
        ObjectMask(int(d.object_id), d.confidence, sam_adapter.full_mask(d, size))
        for d in sam_adapter.decoded(parsed)
        if d.object_id.isdigit()
    ]


def locate_text(locate: Prompt, parts: Sequence[PartPhrase], sheet: SheetContext) -> str:
    listed = "; ".join(
        f'"{p.phrase}" (printed label "{p.print_label}")' if p.print_label else f'"{p.phrase}"'
        for p in parts
    )
    return str(locate.template["user"]).format(
        listed=listed,
        reader=sheet.reader,
        width_mm=round(sheet.width_mm),
        height_mm=round(sheet.height_mm),
        min_part_mm=sheet.min_part_mm,
        gap_mm=sheet.gap_mm,
    )


def _plan(item: dict[str, Any], kinds: dict[str, str], listed: set[str]) -> dict[str, Any]:
    """One part's plan, with names checked against the listing: a line separates two areas
    the answer planned or nothing, and has no instances; a parent is a listed part other
    than itself."""
    name, kind = item["part"], item["kind"]
    parent = item.get("parent", "")
    parent = parent if parent in listed and parent != name else ""
    separates = tuple(dict.fromkeys(q for q in item.get("separates", []) if q != name))
    two_areas = len(separates) == _PAIR and all(kinds.get(q) == "area" for q in separates)
    line = kind == "line"
    return {
        "kind": kind,
        "members": tuple(m for m in item["members"] if m in listed and m != name),
        "parent": parent,
        "separates": separates if line and two_areas else (),
        "instances": ()
        if line or kind == "group"
        else tuple(Instance.model_validate(i) for i in item["instances"]),
    }


def merge_located(u: Understanding, answer: dict[str, Any]) -> Understanding:
    """The listed parts with what the locate call said about each, by exact name. A part
    the answer leaves out keeps kind None, so S2 sends it to the teacher. Shared regions
    keep their listed areas, and only those with two or more."""
    found: dict[str, dict[str, Any]] = {}
    listed = {p.phrase for p in u.parts}
    for item in answer["parts"]:
        if item["part"] in listed:
            found.setdefault(item["part"], item)
    kinds = {name: str(item["kind"]) for name, item in found.items()}
    parts = [
        p if p.phrase not in found else p.model_copy(update=_plan(found[p.phrase], kinds, listed))
        for p in u.parts
    ]
    shared = []
    for s in answer.get("shares_region", []):
        names = tuple(dict.fromkeys(q for q in s["parts"] if kinds.get(q) == "area"))
        if len(names) >= _PAIR:
            name = str(s["name"]).strip() or " and ".join(names)
            shared.append(SharedRegion(parts=names, name=name))
    return u.model_copy(
        update={
            "parts": parts,
            "located": True,
            "subject": str(answer.get("subject", "")).strip(),
            "shares_region": shared,
        }
    )


class LiveMetaClient:
    mode: Literal["live"] = "live"

    def __init__(
        self,
        rules: Meta,
        caller: Callable[[], LiveCaller],
        record_prefix: str | None = None,
    ) -> None:
        self._rules = rules
        self._models = rules.models
        self._make_caller = caller
        self._caller = caller()
        self._record_prefix = record_prefix

    @property
    def meter(self) -> CostMeter:
        return self._caller.meter

    @property
    def calls(self) -> int:
        return self._caller.calls

    @property
    def live_calls(self) -> int | None:
        return self._caller.calls

    @property
    def cache_tag(self) -> str:
        """Live answers depend on the model ids, so a model change re-runs S1 and S2."""
        return f"live:{self._models.spark}:{self._models.sam}"

    def cap_calls(self, cap: int) -> None:
        self._caller.cap = cap

    def for_job(self) -> MetaClient:
        return LiveMetaClient(self._rules, self._make_caller, self._record_prefix)

    def _sam_name(self, kind: str, part: str, retry: bool) -> str:
        """S2's names are one per part; a fix part gets a call count, since recordings are
        never overwritten and a teacher clicks several times."""
        if kind == "s2":
            return f"s2_{slug(part)}{'_retry' if retry else ''}"
        return f"{kind}_{slug(part)}_{self._caller.calls + 1:02d}"

    def _name(self, what: str) -> str | None:
        return None if self._record_prefix is None else f"{self._record_prefix}_{what}"

    async def _spark(self, what: str, figure_id: str, body: dict[str, Any]) -> dict[str, Any]:
        res = await self._caller.post_json(
            "/chat/completions",
            body,
            caller="s1",
            model=self._models.spark,
            describe=f"figure {figure_id[:12]}, {what}",
            units=spark_units,
            record_as=self._name(f"s1_{what}"),
        )
        return dict(json.loads(res.body["choices"][0]["message"]["content"]))

    async def understand(
        self, image: RGB, figure_id: str, prompt: Prompt, locate: Prompt, sheet: SheetContext
    ) -> Understanding:
        png = png_bytes(image)
        t = prompt.template
        listing = await self._spark(
            "list",
            figure_id,
            spark_body(
                self._models.spark,
                t["system"],
                t["user"],
                png,
                ("FigureUnderstanding", LISTING_SCHEMA),
            ),
        )
        u = Understanding.model_validate(listing)
        u = u.model_copy(update={"parts": u.parts[: self._rules.max_parts]})
        self.cap_calls(job_cap(len(u.parts), self._rules))
        if not u.parts or u.verdict == "describe_only":
            return u
        body = spark_body(
            self._models.spark,
            None,
            locate_text(locate, u.parts, sheet),
            png,
            ("PartPoints", LOCATE_SCHEMA),
        )
        return merge_located(u, await self._spark("locate", figure_id, body))

    async def segment(
        self, image: RGB, figure_id: str, phrase: str, prompt: Prompt, what: str = ""
    ) -> list[Mask]:
        h, w = image.shape[:2]
        res = await self._caller.post_sse(
            "/responses",
            sam_adapter.request_body(self._models.sam, png_bytes(image), prompt.template, phrase),
            caller="s2",
            model=self._models.sam,
            describe=f"figure {figure_id[:12]} {w}x{h}, {what or 'phrase'}: {phrase}",
            units=lambda _usage: {"images": 1},
            record_as=self._name(f"{what}_{slug(phrase)}" if what else slug(phrase)),
        )
        parsed = await sam_adapter.parse_events(res.body)
        return await asyncio.to_thread(sam_adapter.to_masks, parsed, (h, w), phrase)

    async def segment_points(
        self,
        image: RGB,
        figure_id: str,
        part: str,
        objects: Sequence[SamObject],
        prompt: Prompt,
        retry: bool = False,
        kind: str = "s2",
    ) -> list[ObjectMask]:
        h, w = image.shape[:2]
        body = sam_adapter.objects_request_body(
            self._models.sam,
            png_bytes(image),
            (w, h),
            [(list(pos), list(neg)) for pos, neg in objects],
            prompt.template["metadata"],
        )
        what = " retry" if retry else ""
        res = await self._caller.post_sse(
            "/responses",
            body,
            caller=kind,
            model=self._models.sam,
            describe=f"figure {figure_id[:12]} {w}x{h}, {len(objects)} objects for {part}{what}",
            units=lambda _usage: {"images": 1},
            record_as=self._name(self._sam_name(kind, part, retry)),
        )
        parsed = await sam_adapter.parse_events(res.body)
        # Decoding is pure Python, about 1 s a mask: off the event loop, so the API answers
        # other requests meanwhile.
        return await asyncio.to_thread(object_masks, parsed, (w, h))
