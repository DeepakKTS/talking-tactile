# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["httpx==0.28.1", "websockets==15.0.1"]
# ///
"""Muse Voice Transcribe spike. Docs: https://dev.meta.ai/docs/speech-to-text,
https://dev.meta.ai/docs/api-reference/voice/realtime, https://dev.meta.ai/docs/api-reference/voice/transcribe,
https://dev.meta.ai/docs/api-reference/voice/schemas (read 2026-10-24).

Realtime: wss://api.meta.ai/v1/asr/realtime, handshake JSON first (key in authorization.accessToken),
raw PCM paced at real time, {"type": "endStream"}, read until close 1000. PUSH_TO_TALK mode.
Configs, each --runs times: 24 kHz with keywords, 24 kHz without keywords, 16 kHz with keywords.
Also POST /v1/asr/transcribe with a WAV (the push-to-talk sync fallback), 2 runs.

Measures: handshake, first partial after the first audio frame, endStream to final transcript
(the "release Space to text" number), and domain term accuracy with and without keyword hints.

Default audio is the macOS `say` voice reading a heart question, converted with ffmpeg. It is
synthetic speech, so term accuracy here is a smoke test, not the eval. --audio takes a real WAV.

Run: uv run spikes/voice_spike.py [--runs 4] [--audio my.wav] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import websockets

from meta_common import PRICES, load_env, save_fixture, save_results, summarize

MODEL = "muse-voice-transcribe-1.0"
OUT = Path(__file__).resolve().parent / "out" / "voice"
SCRIPT_TEXT = ("What does the left ventricle do? Where is the pulmonary artery? "
               "Is the tricuspid valve next to the chordae tendineae? "
               "Tell me more about the septum, and what is next to the mitral valve.")
TERMS = ["left ventricle", "pulmonary artery", "tricuspid valve", "chordae tendineae", "septum", "mitral valve"]
# Region labels from fixtures/heart.png, as Explore would send them.
KEYWORDS = ["left atrium", "right atrium", "left ventricle", "right ventricle", "septum", "aorta",
            "superior vena cava", "inferior vena cava", "pulmonary artery", "pulmonary veins",
            "tricuspid valve", "mitral valve", "semilunar valves", "chordae tendineae",
            "brachiocephalic artery", "left common carotid artery", "left subclavian artery"]
FRAME_MS = 80


def make_audio(src_wav: Path | None) -> dict[int, Path]:
    """Return raw s16le mono PCM files at 24 and 16 kHz, plus a 16 kHz WAV for the file endpoint."""
    OUT.mkdir(parents=True, exist_ok=True)
    if src_wav is None:
        if not shutil.which("say"):
            raise SystemExit("No --audio given and macOS `say` is not available.")
        # WAVE output; AIFF output from `say` hung and came out truncated on this machine.
        src = OUT / "question_say.wav"
        subprocess.run(["say", "-o", str(src), "--file-format=WAVE", "--data-format=LEI16@24000", SCRIPT_TEXT],
                       check=True, timeout=60)
    else:
        src = src_wav
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                                   check=True, capture_output=True, text=True).stdout.strip() or 0)
    if seconds < 3:
        raise SystemExit(f"{src} is only {seconds:.2f} s; the audio did not render fully.")
    files: dict[int, Path] = {}
    for rate in (24000, 16000):
        raw = OUT / f"question_{rate}.pcm"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(rate),
                        "-f", "s16le", "-acodec", "pcm_s16le", str(raw)], check=True)
        files[rate] = raw
    wav = OUT / "question_16000.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000",
                    "-acodec", "pcm_s16le", str(wav)], check=True)
    files[0] = wav
    return files


def handshake(key: str, rate: int, keywords: bool) -> dict:
    h = {"authorization": {"accessToken": f"Bearer {key}"}, "audioEncoding": "PCM_24KHZ" if rate == 24000 else "PCM_16KHZ",
         "model": MODEL, "mode": "PUSH_TO_TALK", "partialMode": "CUMULATIVE", "languageBias": ["English"]}
    if keywords:
        h["keywords"] = KEYWORDS
    return h


def term_hits(text: str) -> int:
    t = text.lower()
    return sum(1 for term in TERMS if term in t)


async def realtime_once(url: str, key: str, pcm: bytes, rate: int, keywords: bool) -> dict:
    frame = rate * 2 * FRAME_MS // 1000
    events: list[dict] = []
    t0 = time.perf_counter()
    async with websockets.connect(f"{url}?sessionId=spike-{uuid.uuid4()}", open_timeout=30) as ws:
        await ws.send(json.dumps(handshake(key, rate, keywords)))
        ack = json.loads(await ws.recv())
        t_ack = time.perf_counter()
        if "sessionId" not in ack:
            return {"error": f"handshake: {ack}"}
        t_audio0: float | None = None
        t_first_partial: float | None = None
        t_final: float | None = None
        final_text = ""

        async def receive() -> None:
            nonlocal t_first_partial, t_final, final_text
            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                ev = json.loads(msg)
                ev["_t_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                events.append(ev)
                if ev.get("type") == "error":
                    raise RuntimeError(ev.get("message"))
                if ev.get("type") == "transcript":
                    if t_first_partial is None:
                        t_first_partial = time.perf_counter()
                    if ev.get("final"):
                        t_final = time.perf_counter()
                        final_text = ev.get("transcript", "")

        rx = asyncio.create_task(receive())
        start = time.perf_counter()
        for i in range(0, len(pcm), frame):
            if t_audio0 is None:
                t_audio0 = time.perf_counter()
            await ws.send(pcm[i:i + frame])
            # Pace against the wall clock so the stream never runs ahead of real time.
            target = start + (i + frame) / (rate * 2)
            await asyncio.sleep(max(0.0, target - time.perf_counter()))
        t_end_stream = time.perf_counter()
        await ws.send(json.dumps({"type": "endStream"}))
        await rx
        close_code = ws.close_code
    return {
        "session_id": ack.get("sessionId"), "close_code": close_code,
        "handshake_ms": round((t_ack - t0) * 1000, 1),
        "first_partial_ms": round((t_first_partial - t_audio0) * 1000, 1) if t_first_partial and t_audio0 else None,
        "end_to_final_ms": round((t_final - t_end_stream) * 1000, 1) if t_final else None,
        "audio_s": round(len(pcm) / (rate * 2), 2), "final": final_text, "term_hits": term_hits(final_text),
        "event_types": sorted({e.get("type", "") for e in events}), "events": events,
    }


def file_once(client: httpx.Client, wav: Path, keywords: bool) -> dict:
    req = {"model": MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK", "languageBias": ["English"]}
    if keywords:
        req["keywords"] = KEYWORDS
    t0 = time.perf_counter()
    r = client.post("/asr/transcribe", headers={"Accept": "application/json"},
                    files={"request": (None, json.dumps(req), "application/json"),
                           "audio": (wav.name, wav.read_bytes(), "audio/wav")})
    ms = (time.perf_counter() - t0) * 1000
    row = {"status": r.status_code, "ms": round(ms, 1)}
    if r.status_code == 200:
        body = r.json()
        row.update({"final": body.get("transcript", ""), "term_hits": term_hits(body.get("transcript", "")),
                    "audio_duration_ms": body.get("audioDurationMs"), "body": body})
    else:
        row["error"] = r.text[:500]
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--audio", type=Path, help="a WAV of a real voice; default is macOS say")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    audio = make_audio(args.audio)
    print({rate: f"{p.name} {p.stat().st_size} bytes" for rate, p in audio.items()})
    if args.dry_run:
        h = handshake("<key>", 24000, True)
        print(json.dumps({"WS handshake": h, "then": f"binary PCM frames of {FRAME_MS} ms, then {{\"type\": \"endStream\"}}"}, indent=1))
        return

    env = load_env()
    key = env["MODEL_API_KEY"]
    url = env.get("META_ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
    configs = [("24k_hints", 24000, True), ("24k_nohints", 24000, False), ("16k_hints", 16000, True)]
    cases, audio_s, fixture_saved = [], 0.0, False
    for name, rate, kw in configs:
        pcm = audio[rate].read_bytes()
        rows = []
        for i in range(args.runs):
            try:
                row = asyncio.run(realtime_once(url, key, pcm, rate, kw))
            except Exception as e:  # spikes record failures instead of stopping
                row = {"error": f"{type(e).__name__}: {e}"}
            row["run"] = i
            audio_s += row.get("audio_s", 0)
            if not fixture_saved and row.get("final"):
                save_fixture(MODEL, "realtime_heart_question", {"config": name, "events": row["events"]}, key)
                fixture_saved = True
            rows.append(row)
            print(name, json.dumps({k: v for k, v in row.items() if k != "events"}))
        cases.append({"config": name, "rate": rate, "keywords": kw,
                      "handshake": summarize(f"{name} handshake", [r["handshake_ms"] for r in rows if r.get("handshake_ms")]),
                      "first_partial": summarize(f"{name} first partial", [r["first_partial_ms"] for r in rows if r.get("first_partial_ms")]),
                      "end_to_final": summarize(f"{name} endStream to final", [r["end_to_final_ms"] for r in rows if r.get("end_to_final_ms")]),
                      "term_hits": [r.get("term_hits") for r in rows], "terms": len(TERMS),
                      "runs": [{k: v for k, v in r.items() if k != "events"} for r in rows]})
    with httpx.Client(base_url=env["META_API_BASE"], headers={"Authorization": f"Bearer {key}"}, timeout=60) as client:
        file_rows = [file_once(client, audio[0], True) for _ in range(2)]
    for r in file_rows:
        print("file", json.dumps({k: v for k, v in r.items() if k != "body"}))
        if r.get("audio_duration_ms"):
            audio_s += r["audio_duration_ms"] / 1000
    if file_rows and file_rows[0].get("body"):
        save_fixture(MODEL, "transcribe_heart_question", file_rows[0]["body"], key)
    out = {"realtime": cases, "file": {"latency": summarize("file transcribe", [r["ms"] for r in file_rows if r["status"] == 200]),
                                       "runs": [{k: v for k, v in r.items() if k != "body"} for r in file_rows]},
           "audio_seconds": round(audio_s, 1), "cost_usd": round(int(audio_s) * PRICES[MODEL]["audio_second"], 6),
           "audio_source": str(args.audio) if args.audio else "macOS say (synthetic)", "script_text": SCRIPT_TEXT}
    print(f"audio {out['audio_seconds']} s, cost ${out['cost_usd']}")
    save_results(MODEL, out, key)


if __name__ == "__main__":
    main()
