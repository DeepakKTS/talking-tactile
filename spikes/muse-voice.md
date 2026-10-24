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

Not run yet. Waiting for the API key in services/api/.env.
