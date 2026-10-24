# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["httpx==0.28.1"]
# ///
"""Muse Spark 1.3 spike. Docs: https://dev.meta.ai/docs/structured-output,
https://dev.meta.ai/docs/image-understanding, https://dev.meta.ai/docs/reasoning,
https://dev.meta.ai/docs/prompt-caching (all read 2026-10-24).

Two cases, each run --runs times:
  understand  heart.png + S1 JSON schema over Chat Completions, reasoning_effort medium, not streamed
  answer      text-only grounded question, streamed, reasoning_effort low; measures time to first token
              and shows whether the repeated prefix is cached (usage.prompt_tokens_details.cached_tokens)

Run: uv run spikes/spark_spike.py [--case understand|answer|all] [--runs 10] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import json
import time

import httpx

from meta_common import FIXTURES, PRICES, load_env, redacted_headers, save_fixture, save_results, summarize

MODEL = "muse-spark-1.3"
HEART = FIXTURES / "heart.png"

S1_SCHEMA = {
    "type": "object",
    "properties": {
        "figure_type": {"enum": ["labeled_diagram", "bar_chart", "line_graph", "map", "flow_diagram", "other"]},
        "title": {"type": "string"},
        "summary": {"type": "string", "description": "Two sentences at most. No sight words."},
        "parts": {
            "type": "array",
            "maxItems": 25,
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string", "description": "Short noun phrase SAM can segment, such as 'left ventricle'"},
                    "print_label": {"type": "string", "description": "The exact printed label text that points to this part, or empty"},
                },
                "required": ["phrase", "print_label"],
                "additionalProperties": False,
            },
        },
        "color_carries_meaning": {"type": "boolean"},
        "verdict": {"enum": ["make_tactile", "split_two_sheets", "describe_only"]},
        "verdict_reason": {"type": "string"},
    },
    "required": ["figure_type", "title", "summary", "parts", "color_carries_meaning", "verdict", "verdict_reason"],
    "additionalProperties": False,
}

S1_SYSTEM = (
    "You read science figures so they can be made into tactile graphics for blind students. "
    "List the figure's parts as short noun phrases a segmentation model can find. "
    "Use the figure's own printed labels. Do not add parts that are not in the figure."
)

ANSWER_SYSTEM = (
    "You answer a blind student's question about one science figure. Use only the figure data below. "
    "Answer in one or two short sentences. If the figure does not show it, say so in one sentence. "
    "Never use sight words.\n\n"
    "Figure: Heart diagram. Summary: A cutaway of the human heart showing its four chambers, valves and major vessels.\n"
    "Regions: left atrium, right atrium, left ventricle, right ventricle, septum, aorta, superior vena cava, "
    "inferior vena cava, right pulmonary arteries, left pulmonary arteries, right pulmonary veins, "
    "left pulmonary veins, tricuspid valve, mitral valve, semilunar valves, chordae tendineae, "
    "brachiocephalic artery, left common carotid artery, left subclavian artery.\n"
    "Spatial facts (computed in code): the student's finger is on the left ventricle. "
    "The septum is to its left. The aorta is up and to the left."
)
QUESTION = "What does this part do?"


def cost(usage: dict) -> float:
    p = PRICES[MODEL]
    prompt = usage.get("prompt_tokens", 0)
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    out = usage.get("completion_tokens", 0)
    return (prompt - cached) * p["input"] + cached * p["cached_input"] + out * p["output"]


def understand_payload() -> dict:
    b64 = base64.b64encode(HEART.read_bytes()).decode()
    return {
        "model": MODEL,
        "reasoning_effort": "medium",
        "messages": [
            {"role": "system", "content": S1_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": "Read this figure and fill the schema."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "FigureUnderstanding", "schema": S1_SCHEMA}},
    }


def answer_payload() -> dict:
    return {
        "model": MODEL,
        "reasoning_effort": "low",
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": QUESTION}],
    }


def run_understand(client: httpx.Client, runs: int, secret: str) -> dict:
    lat, rows, fixture_saved = [], [], False
    for i in range(runs):
        t0 = time.perf_counter()
        r = client.post("/chat/completions", json=understand_payload())
        ms = (time.perf_counter() - t0) * 1000
        row = {"run": i, "status": r.status_code, "ms": round(ms, 1),
               "ratelimit_remaining_requests": r.headers.get("x-ratelimit-remaining-requests")}
        if r.status_code == 200:
            body = r.json()
            lat.append(ms)
            usage = body.get("usage") or {}
            content = body["choices"][0]["message"].get("content") or ""
            try:
                parsed = json.loads(content)
                row["parts"] = len(parsed.get("parts", []))
                row["verdict"] = parsed.get("verdict")
                row["valid_json"] = True
            except json.JSONDecodeError:
                row["valid_json"] = False
            row["usage"] = usage
            row["cost_usd"] = round(cost(usage), 6)
            if not fixture_saved:
                save_fixture(MODEL, "understand_heart", body, secret)
                fixture_saved = True
        else:
            row["error"] = r.text[:500]
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "usage"}))
    return {"case": "understand", "latency": summarize("understand total", lat), "runs": rows,
            "cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 6)}


def run_answer(client: httpx.Client, runs: int, secret: str) -> dict:
    ttft, first_sentence, total, rows, fixture_saved = [], [], [], [], False
    for i in range(runs):
        t0 = time.perf_counter()
        t_first = t_sentence = None
        text, usage, chunks = "", {}, []
        with client.stream("POST", "/chat/completions", json=answer_payload()) as r:
            row = {"run": i, "status": r.status_code}
            if r.status_code != 200:
                row["error"] = r.read().decode(errors="replace")[:500]
                rows.append(row)
                print(json.dumps(row))
                continue
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                chunks.append(chunk)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for ch in chunk.get("choices") or []:
                    delta = (ch.get("delta") or {}).get("content") or ""
                    if delta:
                        now = time.perf_counter()
                        if t_first is None:
                            t_first = now
                        text += delta
                        if t_sentence is None and any(p in text for p in ".?!"):
                            t_sentence = now
        t_end = time.perf_counter()
        if t_first is not None:
            ttft.append((t_first - t0) * 1000)
        if t_sentence is not None:
            first_sentence.append((t_sentence - t0) * 1000)
        total.append((t_end - t0) * 1000)
        row.update({"ttft_ms": round((t_first - t0) * 1000, 1) if t_first else None,
                    "first_sentence_ms": round((t_sentence - t0) * 1000, 1) if t_sentence else None,
                    "total_ms": round((t_end - t0) * 1000, 1), "answer": text, "usage": usage,
                    "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                    "cost_usd": round(cost(usage), 6) if usage else None})
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "usage"}))
        if not fixture_saved and text:
            save_fixture(MODEL, "answer_left_ventricle", {"request": answer_payload(), "chunks": chunks, "text": text}, secret)
            fixture_saved = True
    return {"case": "answer", "ttft": summarize("answer ttft", ttft),
            "first_sentence": summarize("answer first sentence", first_sentence),
            "total": summarize("answer total", total), "runs": rows,
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 6)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["understand", "answer", "all"], default="all")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="print the requests without sending them")
    args = ap.parse_args()

    if args.dry_run:
        u = understand_payload()
        u["messages"][1]["content"][1]["image_url"]["url"] = u["messages"][1]["content"][1]["image_url"]["url"][:40] + "...<truncated>"
        print(json.dumps({"POST /chat/completions (understand)": u, "POST /chat/completions (answer)": answer_payload()}, indent=1))
        return

    env = load_env()
    key = env["META_API_KEY"]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    print("headers:", redacted_headers(headers))
    out: dict = {"base": env["META_API_BASE"], "cases": []}
    with httpx.Client(base_url=env["META_API_BASE"], headers=headers, timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        if args.case in ("understand", "all"):
            out["cases"].append(run_understand(client, args.runs, key))
        if args.case in ("answer", "all"):
            out["cases"].append(run_answer(client, args.runs, key))
    out["cost_usd"] = round(sum(c["cost_usd"] for c in out["cases"]), 6)
    print(f"total cost: ${out['cost_usd']}")
    save_results(MODEL, out, key)


if __name__ == "__main__":
    main()
