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
- Masks are box-local. `meta_sam_parser` returns each mask with half-open bounds in source pixels, and the raster size equals the bounds size. This was checked offline with the docs example. Live on Oct 29 it held for a box under 1024 px, not for a larger one (see Results).
- The docs list no confidence, score or threshold parameter, and no instance limit for images (segmenting and reading-segmentation pages, read Oct 29). The only metadata keys are `mask_encoding` (default `lossless`) and `include_confidence`. We send `one_bit` and `"true"`.
- Python parser: `parse_responses_stream(events, image_segmentation_format())`, then `await .final_result()`. The events need the full Responses lane: `output_text.delta` with `output_index`, `content_index` and `item_id`, then `output_text.done`, then `response.completed`.
- Price: $2.50 per 1,000 images. 3,000 RPM per team.

## Cases

Five phrases on heart.png (left ventricle, right ventricle, left atrium, right atrium, aorta), 2 runs each, plus one "text" call to test finding print labels for S2. That is 11 calls, about $0.03.

## Open questions for the live run

- Which model id works: `sam-3.1` or `sam-3-1`.
- The exact event sequence for zero matches. The script records parse errors instead of crashing.
- Whether `usage` appears on `response.completed` for images.
- How well SAM separates the chambers of heart.png, a colored illustration with filled, shaded chambers and vessels and no dark outlines, labeled in black text with black leader lines.

## Results

The full spike (5 phrases twice, plus "text") has not run yet.

Smoke call, Oct 27, one call through `app/meta/smoke.py` (response in `fixtures/recorded/smoke_sam_heart_left_ventricle.json`):

- Works: model id `sam-3.1` on `POST /v1/responses`, streamed, with the request shape above. HTTP 200 in 1269 ms, 8 events ending in `response.completed` with `status: completed`. That settles the model id question: `sam-3.1`. Usage is on `response.completed`: `{"images_processed": 1, "input_tokens": 0, ...}`. Cost $0.0025.
- Surprised: "left ventricle" on heart.png found zero instances. There was no `output_text.delta` at all, and `output_text.done` had empty text. `meta_sam_parser` parses that to no records, with no error.
- The wrapper must: treat zero deltas as a valid empty result. Decoding a real non-empty mask is still unchecked, so the adapter needs one real answer with instances before it is written. Whether SAM finds the chambers on heart.png, a colored illustration without dark outlines, is the Day 1 risk in PLAN.md section 15, and it is still open.

SAM diagnostic, Oct 29, 8 calls through `app/meta/sam_diagnostic.py` (Gate A step 4.1; responses in `fixtures/recorded/sam_diag_*.json`). Same request as S2: one phrase, `one_bit`, confidence on, the image file as it is.

| Image | Prompt | Instances | Confidence | Latency ms | Cost |
|---|---|---|---|---|---|
| control/banana.png 1024x902 (photo) | banana | 1 | 0.977 | 1904 | $0.0025 |
| heart.png 2048x1612 | heart | 1 | 0.570 | 1261 | $0.0025 |
| heart.png | left ventricle | 0 | | 2441 | $0.0025 |
| heart.png | left ventricle of the heart | 0 | | 2189 | $0.0025 |
| heart.png | aorta | 0 | | 2159 | $0.0025 |
| heart.png | aorta of the heart | 0 | | 2647 | $0.0025 |
| heart.png | right atrium | 0 | | 1689 | $0.0025 |
| heart.png | right atrium of the heart | 0 | | 1113 | $0.0025 |

- Works: the request and the decoding. The banana mask decodes to the banana, row-major, on its box (bounds 47,44 to 978,855, raster 811x931, the bounds size). The heart mask decodes to the whole heart silhouette, vessels included, with gaps where label leader lines cross it. So the zero answers are SAM's answer, not our request.
- Surprised: SAM finds the heart as one object and none of its parts, in either phrasing. The heart raster was 1024x668 for bounds 1423x928, the same shape scaled so its longer side is 1024. The docs say the raster equals the bounds size. One sample, so "at most 1024 px on a side" is inferred, not documented.
- The wrapper must: scale each raster to its bounds before pasting it. Not decided here: how S2 gets parts when concept prompts find only the whole figure. Latency counts only on the two answers with instances (1261 and 1904 ms), too few for p50 and p95.

The three bake-off figures:
- heart.png (2048 x 1612): a colored anatomical illustration. Chambers and vessels are filled red, blue and cream with soft shading and no dark outlines. Black labels sit on the white page, joined to the parts by thin black leader lines.
- flower.png (2048 x 1183): a colored diagram with thin dark outlines. Red leader lines end in red dots on the parts. Two enlarged insets, the pistil and the stamen, sit on pale tinted ellipses, and black arrows and circles tie them to the main drawing.
- japan_regions.png (1796 x 2048): a map of 9 regions in flat colors on a blue sea, with black coastlines and prefecture borders, white labels, and an Okinawa inset in a thin-lined box.

S2 bake-off, Oct 29 (Gate A step 4.1b, `app/meta/s2_bakeoff.py`; sheets in `eval/s2-bakeoff/FIGURE/index.html`, numbers in `results.json`, responses in `fixtures/recorded/bakeoff_*.json`). Counts only; Deepak grades the sheets.

- Coordinates. Spark answers points on a 0-1000 grid of the image it was sent (image-understanding docs). SAM object prompts take integer pixels of the image as sent, origin top left, with the image's own `w` and `h` on each token (segmenting docs). Code maps one to the other with floor(v * size / 1000), clamped to the image. The 1024 px raster cap is on the answer, not the prompt.
- Point prompts: 44 calls on 3 figures, 44 answers with exactly 1 instance. The point sits inside its own mask in 38 of 44 (heart 19 of 19, flower 10 of 16, Japan 9 of 9). No point-prompted box was over 1024 px on a side, so the cap was not exercised: every raster was its bounds size.
- Arm B regions (ink under luminance 64, 5 px square closing, 2 mm2 floor): heart 11, flower 30, Japan 47. Spark assigned 9, 24 and 47 of them. Luminance finds dark-line boundaries; heart.png's chamber walls are fills, not dark lines.
- Spark: the list, points and naming calls took 5 to 15 s, 4.5 to 7.5 s and 14.5 to 92 s, at reasoning effort medium. The naming call on Japan cost $0.0998.
- Decoding speed: `meta_sam_parser.decode_mask_to_raster` is pure Python and re-encodes each mask to check it, about 0.3 to 0.9 s for a mask of a few hundred px a side. S2 must decode each mask once.

SAM latency for Gate A, Oct 29, no new calls (`app/meta/latency_spike.py sam`, per answer in `spikes/results/latency_sam.json`): the 44 point-prompt answers from the bake-off, all with 1 instance, so all count. Each is timed from request to the end of the stream, one point on the full figure (heart 2048x1612, flower 2048x1183, Japan 1796x2048). Nearest-rank percentiles.

| Answers | n | p50 | p95 | min | max |
|---|---|---|---|---|---|
| All | 44 | 1207 ms | 3632 ms | 740 ms | 7738 ms |
| heart | 19 | 1426 ms | 3690 ms | 871 ms | 3690 ms |
| flower | 16 | 1207 ms | 7738 ms | 835 ms | 7738 ms |
| japan_regions | 9 | 1009 ms | 1441 ms | 740 ms | 1441 ms |

These are point prompts, not the phrase prompts S2 was first planned around. Phrase-prompt answers with instances are still only the 2 from the diagnostic. The slowest answer, 7738 ms for the flower's ovules, is one call; the next slowest are 3690 and 3632 ms on the heart. The p95 of 44 is the 42nd fastest.
