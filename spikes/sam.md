# SAM 3.1 spike

Docs read 2026-10-24:
- https://dev.meta.ai/docs/sam/overview
- https://dev.meta.ai/docs/sam/segmenting
- https://dev.meta.ai/docs/sam/reading-segmentation
- https://dev.meta.ai/docs/sam/client-libraries
- https://dev.meta.ai/docs/media-segmentation
- https://dev.meta.ai/docs/pricing-rate-limits

Script: `uv run spikes/sam_spike.py` (Python 3.11, httpx, meta-sam-parser 0.1.0, Pillow). `--dry-run` prints the request with no key.

## Request shape, from the docs

- Model id `sam-3.1` on `POST https://api.meta.ai/v1/responses`. The product page writes `sam-3-1`, and the kit used that too. The script defaults to `sam-3.1`, and `--model` lets the live run settle it.
- One user message: an `input_text` part with one short noun phrase, plus an `input_image` part (a public URL or a `data:image/png;base64,...` string).
- One concept per request. A list such as "bus, bicycle" returns zero matches. So S2 makes one call per part, as PLAN.md assumed.
- Every matching instance comes back, each as a box plus a mask. Zero matches is a valid result, not an error.
- `stream: true` is recommended. Output is special-token text in the `output_text` lane: `<0f>id<|box;...|><|mask;...;data=H,W,!payload|>,...`
- `metadata.mask_encoding: "one_bit"` gives the smallest masks. `metadata.include_confidence: "true"` is a string, not a boolean.
- Masks are box-local. `meta_sam_parser` returns each mask with half-open bounds in source pixels, and the raster size equals the bounds size. This was checked offline with the docs example.
- Python parser: `parse_responses_stream(events, image_segmentation_format())`, then `await .final_result()`. The events need the full Responses lane: `output_text.delta` with `output_index`, `content_index` and `item_id`, then `output_text.done`, then `response.completed`.
- Price: $2.50 per 1,000 images. 3,000 RPM per team.

## Cases

Five phrases on heart.png (left ventricle, right ventricle, left atrium, right atrium, aorta), 2 runs each, plus one "text" call to test finding print labels for S2. That is 11 calls, about $0.03.

## Open questions for the live run

- Which model id works: `sam-3.1` or `sam-3-1`.
- The exact event sequence for zero matches. The script records parse errors instead of crashing.
- Whether `usage` appears on `response.completed` for images.
- How well SAM separates chambers on line art with text labels.

## Results

Not run yet. Waiting for the API key in services/api/.env.
