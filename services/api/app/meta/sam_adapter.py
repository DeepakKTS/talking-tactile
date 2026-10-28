"""SAM 3.1 responses to Masks. This is the only module that may know how SAM encodes masks
on the wire; everything after it sees app.models.mask.Mask.

What the docs say (read 2026-10-24; spikes/sam.md has the links):
- Model `sam-3.1` on POST /v1/responses, streamed. One short noun phrase per request;
  every matching instance comes back, and zero matches is a valid result.
- Output is special-token text in the output_text lane, one entry per instance:
  `<0f>id<|box;...|><|mask;...;data=H,W,!payload|>`. The payload is base85.
- Masks are box-local: each covers only its instance's box, with half-open bounds in
  source image pixels, and the raster size equals the bounds size.
- `metadata.mask_encoding: "one_bit"` gives the smallest masks;
  `metadata.include_confidence: "true"` (a string) adds a score per instance.
- The Python package meta_sam_parser 0.1.0 decodes the stream:
  `parse_responses_stream(events, image_segmentation_format())`, then
  `await .final_result()`. The events need output_text.delta with output_index,
  content_index and item_id, then output_text.done, then response.completed.

So to_masks will paste each box-local raster into a full-size bool array the size of the
normalized image, label it with the phrase and give it the instance confidence.

The request body and stream parsing below were confirmed by one live call on Oct 27
(fixtures/recorded/smoke_sam_heart_left_ventricle.json): HTTP 200, a completed stream, and
zero instances, which parses to no records. to_masks is not built yet: no real answer with
an instance has been seen (tracker d1-6, the SAM spike), and we do not guess Meta's formats.
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

import meta_sam_parser as sam

from app.models.mask import Mask


def request_body(model: str, png: bytes, phrase: str) -> dict[str, Any]:
    """One phrase on one image, streamed, one_bit masks with a confidence per instance."""
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    content = [{"type": "input_text", "text": phrase}, {"type": "input_image", "image_url": url}]
    return {
        "model": model,
        "input": [{"type": "message", "role": "user", "content": content}],
        "stream": True,
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
    }


async def parse_events(events: list[Any]) -> sam.ImageSegmentationResult:
    async def gen() -> AsyncIterator[Any]:
        for ev in events:
            yield ev

    parsed = sam.parse_responses_stream(gen(), sam.image_segmentation_format())
    return await parsed.final_result()


def instances(result: sam.ImageSegmentationResult) -> list[dict[str, Any]]:
    """Per instance: box, confidence and mask size, to show the shape of a real answer."""
    out: dict[Any, dict[str, Any]] = {}
    for rec in result.records:
        if isinstance(rec, sam.SegmentationBoxRecord):
            o = out.setdefault(rec.object_id, {})
            o["box"] = [rec.left, rec.top, rec.right, rec.bottom]
            o["confidence"] = rec.confidence
        elif isinstance(rec, sam.SegmentationMaskRecord):
            b = rec.bounds
            o = out.setdefault(rec.object_id, {})
            o["mask_hw"] = [rec.mask.height, rec.mask.width]
            o["bounds"] = [b.left, b.top, b.right, b.bottom]
            o["mask_px"] = sum(sam.decode_mask_to_raster(rec.mask))
    return [{"object_id": str(k), **v} for k, v in out.items()]


def to_masks(parsed: object, image_shape: tuple[int, int], phrase: str) -> list[Mask]:
    """One Mask per instance in a parsed SAM response."""
    raise NotImplementedError(
        "The SAM adapter is written after the SAM spike runs with the API key (tracker d1-6)."
    )
