---
name: meta-api-spike
description: Probe a Meta Model API endpoint (Muse Spark, SAM 3.1, Muse Voice Transcribe) before building on it. Use when calling an endpoint for the first time, when a response shape is unclear, or when latency or errors look wrong.
---

# Meta API spike

1. Read the current docs page for the endpoint. Write the URL at the top of `spikes/<model>.md`.
2. Write the smallest script in `spikes/` that makes one real call. Load the key from `services/api/.env`.
3. Run it 10 times. Record p50 and p95 latency, status codes, and the exact response shape.
4. Save one good response to `fixtures/<model>/<case>.json` so mock mode can replay it.
5. Note the cost of the 10 calls from the cost meter.
6. Write three lines in `spikes/<model>.md`: what works, what surprised you, what the client wrapper must handle.
7. Only then add or change the typed function in `services/api/app/meta/client.py`.

Hard rules
- Never paste the key into a file that is committed.
- If the response shape differs from what PLAN.md assumes, update PLAN.md in the same commit.
