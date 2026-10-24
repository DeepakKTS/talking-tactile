# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["httpx==0.28.1", "meta-sam-parser==0.1.0", "pillow==11.3.0"]
# ///
"""SAM 3.1 spike. Docs: https://dev.meta.ai/docs/sam/overview, https://dev.meta.ai/docs/sam/segmenting,
https://dev.meta.ai/docs/sam/reading-segmentation, https://dev.meta.ai/docs/sam/client-libraries (read 2026-10-24).

Five heart phrases, each --runs-per-phrase times (default 2, so 10 calls), plus one "text" call to test
finding print labels. Streams POST /v1/responses, parses with meta_sam_parser, records time to first
delta and to response.completed, object counts, confidence, and whether each mask raster matches its
box bounds. Saves the raw events of the first good call per phrase as a fixture, and an overlay PNG
per phrase in spikes/out/sam/.

Run: uv run spikes/sam_spike.py [--runs-per-phrase 2] [--model sam-3.1] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
from pathlib import Path

import httpx
import meta_sam_parser as sam
from PIL import Image

from meta_common import FIXTURES, PRICES, load_env, redacted_headers, save_fixture, save_results, summarize

HEART = FIXTURES / "heart.png"
PHRASES = ["left ventricle", "right ventricle", "left atrium", "right atrium", "aorta"]
EXTRA = ["text"]
OUT = Path(__file__).resolve().parent / "out" / "sam"


def payload(model: str, phrase: str) -> dict:
    b64 = base64.b64encode(HEART.read_bytes()).decode()
    return {
        "model": model,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": phrase},
            {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"},
        ]}],
        "stream": True,
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
    }


def call(client: httpx.Client, model: str, phrase: str) -> dict:
    events: list[dict] = []
    t0 = time.perf_counter()
    t_first = t_done = None
    with client.stream("POST", "/responses", json=payload(model, phrase), headers={"Accept": "text/event-stream"}) as r:
        if r.status_code != 200:
            return {"status": r.status_code, "error": r.read().decode(errors="replace")[:500]}
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            ev = json.loads(data)
            events.append(ev)
            if ev.get("type") == "response.output_text.delta" and t_first is None:
                t_first = time.perf_counter()
            if ev.get("type") in ("response.completed", "response.incomplete", "response.failed"):
                t_done = time.perf_counter()
    t_end = time.perf_counter()
    return {"status": 200, "events": events,
            "first_delta_ms": round((t_first - t0) * 1000, 1) if t_first else None,
            "completed_ms": round(((t_done or t_end) - t0) * 1000, 1)}


async def parse(events: list[dict]) -> sam.ImageSegmentationResult:
    async def gen():
        for ev in events:
            yield ev
    return await sam.parse_responses_stream(gen(), sam.image_segmentation_format()).final_result()


def describe(result: sam.ImageSegmentationResult) -> tuple[list[dict], list[tuple]]:
    objs, masks = {}, []
    for rec in result.records:
        if rec.kind == "box":
            objs.setdefault(rec.object_id, {})["box"] = [rec.left, rec.top, rec.right, rec.bottom]
            objs[rec.object_id]["confidence"] = rec.confidence
        elif rec.kind == "mask":
            raster = sam.decode_mask_to_raster(rec.mask)
            b = rec.bounds
            o = objs.setdefault(rec.object_id, {})
            o["mask_hw"] = [rec.mask.height, rec.mask.width]
            o["mask_matches_bounds"] = (rec.mask.height == b.bottom - b.top and rec.mask.width == b.right - b.left)
            o["mask_area_px"] = sum(raster)
            o["encoding"] = str(rec.mask.encoding)
            masks.append((b, rec.mask.width, rec.mask.height, raster))
    return [{"object_id": k, **v} for k, v in objs.items()], masks


def overlay(phrase: str, masks: list[tuple]) -> Path:
    base = Image.open(HEART).convert("RGB")
    layer = Image.new("L", base.size, 0)
    for b, w, h, raster in masks:
        m = Image.frombytes("L", (w, h), bytes(v * 255 for v in raster))
        layer.paste(m, (int(b.left), int(b.top)), m)
    tint = Image.new("RGB", base.size, (255, 0, 255))
    out = Image.composite(Image.blend(base, tint, 0.55), base, layer)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{phrase.replace(' ', '_')}.png"
    out.save(path)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-per-phrase", type=int, default=2)
    ap.add_argument("--model", default="sam-3.1", help="docs say sam-3.1; the product page says sam-3-1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        p = payload(args.model, PHRASES[0])
        p["input"][0]["content"][1]["image_url"] = p["input"][0]["content"][1]["image_url"][:40] + "...<truncated>"
        print(json.dumps({"POST /responses": p}, indent=1))
        return

    env = load_env()
    key = env["MODEL_API_KEY"]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    print("headers:", redacted_headers(headers))
    rows, first_ms, done_ms = [], [], []
    with httpx.Client(base_url=env["META_API_BASE"], headers=headers, timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        for phrase in PHRASES + EXTRA:
            runs = args.runs_per_phrase if phrase in PHRASES else 1
            for i in range(runs):
                res = call(client, args.model, phrase)
                row = {"phrase": phrase, "run": i, "status": res["status"]}
                if res["status"] != 200:
                    row["error"] = res["error"]
                    rows.append(row)
                    print(json.dumps(row))
                    continue
                completed = next((e for e in res["events"] if e.get("type") == "response.completed"), {})
                row.update({"first_delta_ms": res["first_delta_ms"], "completed_ms": res["completed_ms"],
                            "usage": (completed.get("response") or {}).get("usage"),
                            "event_types": sorted({e.get("type", "") for e in res["events"]})})
                try:
                    parsed = asyncio.run(parse(res["events"]))
                except sam.ResponsesStreamError as e:
                    # Kept, not raised: the zero-match stream shape is not shown in the docs.
                    row.update({"parse_error": f"{type(e).__name__}: {e}", "n_objects": None})
                    objects, masks = [], []
                else:
                    objects, masks = describe(parsed)
                    row.update({"outcome": str(parsed.outcome), "diagnostics": [str(d) for d in parsed.diagnostics],
                                "n_objects": len(objects), "objects": objects})
                if phrase in PHRASES:
                    done_ms.append(res["completed_ms"])
                    if res["first_delta_ms"] is not None:
                        first_ms.append(res["first_delta_ms"])
                if i == 0:
                    save_fixture(args.model, f"heart_{phrase.replace(' ', '_')}", {"request_phrase": phrase, "events": res["events"]}, key)
                    if masks:
                        row["overlay"] = str(overlay(phrase, masks))
                rows.append(row)
                print(json.dumps({k: v for k, v in row.items() if k not in ("objects", "usage")}))
                for o in objects:
                    print("   ", json.dumps(o))
    images = sum(1 for r in rows if r["status"] == 200)
    out = {"base": env["META_API_BASE"], "model_id_used": args.model,
           "first_delta": summarize("sam first delta", first_ms), "completed": summarize("sam completed", done_ms),
           "calls": len(rows), "images_billed_est": images,
           "cost_usd": round(images * PRICES["sam-3.1"]["image"], 6), "runs": rows}
    print(f"estimated cost: ${out['cost_usd']} for {images} images")
    save_results("sam-3.1", out, key)


if __name__ == "__main__":
    main()
