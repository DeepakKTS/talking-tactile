# Muse Voice Transcribe spike

Docs read 2026-10-24:
- https://dev.meta.ai/docs/speech-to-text
- https://dev.meta.ai/docs/api-reference/voice/realtime
- https://dev.meta.ai/docs/api-reference/voice/transcribe
- https://dev.meta.ai/docs/api-reference/voice/schemas
- https://dev.meta.ai/docs/pricing-rate-limits

Script: `uv run spikes/voice_spike.py` (Python 3.11, websockets, httpx; needs ffmpeg and macOS `say`). `--dry-run` renders the audio and prints the handshake with no key. `--audio my.wav` uses a real recording.

## Request shape, from the docs

- Realtime: `wss://api.meta.ai/v1/asr/realtime?sessionId=...`. Send the handshake as the first JSON text frame within 10 s. The key goes in `authorization.accessToken` as `Bearer <key>`. The endpoint ignores the HTTP Authorization header.
- Handshake fields used: `model`, `audioEncoding` (`PCM_24KHZ` native, or `PCM_16KHZ` resampled by the server), `mode` (`PUSH_TO_TALK`), `partialMode` (`CUMULATIVE`), `keywords` (array of strings, our region labels), `languageBias` (`["English"]`). Keywords and language bias can only be set in the handshake.
- The ack is `{"sessionId": ...}` with no `type`. Then `transcript` events: in `PUSH_TO_TALK`, `final: true` marks completion. Errors arrive as `type: error`.
- Audio: raw s16le mono in binary frames, paced at real time. The server rejects streams that run ahead or stay slower than real time (close 1008).
- End input with `{"type": "endStream"}` and read until close 1000. 1011 means retry, and 1013 means rate limited.
- File endpoint: `POST /v1/asr/transcribe`, multipart with `request` JSON and an `audio` WAV (16 or 24 kHz), 10 min and 32 MB max. This is the sync fallback for push-to-talk.
- Price: $0.18 per hour of audio, billed in whole seconds. Limits: 256 concurrent streams and 16,000 per hour.

## Cases

A 9.3 s question read by the macOS `say` voice, containing 6 domain terms (left ventricle, pulmonary artery, tricuspid valve, chordae tendineae, septum, mitral valve). Configs, 4 runs each: 24 kHz with keywords, 24 kHz without, 16 kHz with keywords. Plus 2 file-endpoint runs. About 2 minutes of audio, under $0.01.

Synthetic speech is a smoke test. The voice eval later uses 20 recorded questions from a real voice.

The realtime client was checked against a local fake server: handshake, partial, final, close 1000, and pacing at 1.005 times real time.

## Results

The realtime WebSocket configs have not run yet. The realtime endpoint is untested.

Keyword hints, docs reread 2026-10-29 (speech-to-text and api-reference/voice/schemas): the transcribe endpoint takes them. The parameter is `keywords`, an array of strings, in the `request` JSON part (schema "Transcribe Request"), the same field as in the realtime handshake. Docs: "Terms to bias recognition toward ... Biasing does not guarantee an exact spelling." It is set once, at the start of a request or session. The docs give no limit on the number of keywords. Not yet sent live.

File endpoint latency, Oct 29, 10 live calls through `app/meta/latency_spike.py voice` (per run in `spikes/results/latency_voice.json`, responses in `fixtures/recorded/latency_voice_*.json`). The request is the smoke call's: `fixtures/audio/question_aorta_ventricle.wav`, 2.72 s, 16 kHz mono, `PUSH_TO_TALK`, `languageBias: ["English"]`, no keywords. Timed from request to full answer. Nearest-rank percentiles, so p95 of 10 is the slowest run.

| n | p50 | p95 | min | max | cost |
|---|---|---|---|---|---|
| 10 | 957 ms | 1221 ms | 839 ms | 1221 ms | $0.00150 |

10 of 10 HTTP 200, `audioDurationMs` 2800 every run, billed as 3 s each. Word error is not measured here: it waits for real recordings of the 10 questions in `eval/voice/record-list.md`.

Smoke call, Oct 27, one call to the file endpoint through `app/meta/smoke.py` (response in `fixtures/recorded/smoke_voice_transcribe.json`):

- Works: `POST /v1/asr/transcribe`, multipart with the `request` JSON and a 16 kHz mono WAV, and a Bearer header. HTTP 200 in 1205 ms for 2.72 s of audio. Body: `sessionId`, `transcript`, `audioDurationMs`, `turns` (empty).
- Surprised: with no keywords, "Where is the aorta?" came back as "Where is the order?". `audioDurationMs` was 2800 for a 2.72 s clip. There is no usage object.
- The wrapper must: price voice from the audio duration, because the response has no usage. Send the region labels as `keywords`. The 6 term test in this spike measures how much that helps.
