# Muse Spark 1.3 spike

Docs read 2026-10-24:
- https://dev.meta.ai/docs/api-reference/chat-completions/create-chat-completion
- https://dev.meta.ai/docs/structured-output
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/reasoning
- https://dev.meta.ai/docs/prompt-caching
- https://dev.meta.ai/docs/error-handling
- https://dev.meta.ai/docs/pricing-rate-limits

Script: `uv run spikes/spark_spike.py` (Python 3.11, httpx). `--dry-run` prints the requests with no key.

## Request shape, from the docs

- `POST https://api.meta.ai/v1/chat/completions`, `Authorization: Bearer <key>`. Keys start with `LLM_`.
- Image: a content part `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`. Up to 50 images per request.
- Structured output: `response_format: {type: "json_schema", json_schema: {name, schema}}`. Decoding is constrained, so output always matches. Recursive schemas return 400. `strict` defaults to false and only adds schema validation.
- Reasoning: top-level `reasoning_effort`, `minimal` to `max`. Spark has no `none`.
- Streaming: `stream: true` with `stream_options.include_usage` puts `usage` on the final chunk.
- Caching: automatic prefix caching, no flag. Reported at `usage.prompt_tokens_details.cached_tokens`. Optional `prompt_cache_key`.
- Errors: retry 429, 500 and 503 with backoff and jitter, and honor `Retry-After`. Do not blindly retry 504, because the same request usually times out again.
- Price: $1.25 input, $0.15 cached input, $4.25 output per 1M tokens. Limits: 3,000 RPM and 4M TPM per team.

## Cases

- `understand`: heart.png at 2048 px with the S1 schema (figure type, title, summary, up to 25 parts with print labels, color meaning, verdict). `reasoning_effort: medium`. Not streamed.
- `answer`: a text-only grounded question with static figure context first, then the question. Streamed, `reasoning_effort: low`. Measures time to first token and first sentence, and reports `cached_tokens` across repeats.

## Results

The full spike (10 runs, image understand case, streamed answers) has not run yet.

Smoke call, Oct 27, one call through `app/meta/smoke.py` (ledger line in `eval/live/ledger.jsonl`, response in `fixtures/recorded/smoke_spark_text.json`):

- Works: `POST /v1/chat/completions` with `muse-spark-1.3`, a one-line text prompt and `reasoning_effort: low`. HTTP 200 in 1858 ms. The body is OpenAI shaped: `choices[0].message.content`, `refusal`, `finish_reason: stop`. The answer named all four chambers. Cost $0.00166.
- Surprised: 353 of the 384 completion tokens were reasoning, on a one-line prompt at `low`. Usage reports them at `usage.completion_tokens_details.reasoning_tokens`, inside `completion_tokens`. `cached_tokens` was 0 on a 22-token prompt.
- The wrapper must: price reasoning tokens as output, since they are inside `completion_tokens`. Measure `minimal` effort against the 2 s answer budget before choosing `low` for answers.
