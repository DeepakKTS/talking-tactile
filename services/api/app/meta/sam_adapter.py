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

Not built yet: the format is confirmed only by a live call (tracker d1-6, the SAM spike),
and we do not guess Meta's formats.
"""

from app.models.mask import Mask


def to_masks(parsed: object, image_shape: tuple[int, int], phrase: str) -> list[Mask]:
    """One Mask per instance in a parsed SAM response."""
    raise NotImplementedError(
        "The SAM adapter is written after the SAM spike runs with the API key (tracker d1-6)."
    )
