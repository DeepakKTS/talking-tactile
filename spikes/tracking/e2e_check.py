# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless browser check for the tracking spike, using the installed Google Chrome and a fake camera.

  uv run spikes/tracking/e2e_check.py loop          stub worker with a 100 ms delay: frames must drop, never queue
  uv run spikes/tracking/e2e_check.py hands VIDEO [CPU|GPU]   MediaPipe on a y4m clip: hands must be found
  uv run spikes/tracking/e2e_check.py touch VIDEO [CPU|GPU]   same, then T and 3 Space presses record 3 touches

Prints the page's stats as JSON. Exits non-zero if a check fails.
"""

from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(QuietHandler, directory=str(HERE))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def run(mode: str, video: str | None, seconds: float, delegate: str | None = None) -> dict:
    srv, port = serve()
    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
    if video:
        args.append(f"--use-file-for-fake-video-capture={Path(video).resolve()}")
    query = "?stub=100" if mode == "loop" else (f"?delegate={delegate}" if delegate else "")
    if mode in ("hands", "touch"):
        # Whole 640x480 frame as the sheet, so the fingertip lands at a known place in mm.
        query += ("&" if query else "?") + "corners=0,0,640,0,640,480,0,480"
    logs: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True, args=args)
            page = browser.new_page()
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
            page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
            page.goto(f"http://127.0.0.1:{port}/index.html{query}")
            page.click("#start")
            if mode in ("hands", "touch"):
                try:
                    page.wait_for_function("window.__tt.backend && !window.__tt.backend.startsWith('stub')", timeout=60000)
                except Exception:
                    print("model did not load. status:", page.inner_text("#status"))
                    print("\n".join(logs[-20:]))
                    raise
            page.wait_for_timeout(seconds * 1000)
            if mode == "touch":
                page.keyboard.press("t")
                for _ in range(3):
                    page.wait_for_timeout(400)
                    page.keyboard.press(" ")
                page.wait_for_timeout(300)
            stats = page.evaluate(
                """() => { const s = window.__tt; return { backend: s.backend, videoSize: s.videoSize,
                    camFps: s.camFps, procFps: s.procFps, pump: s.pump, maxInFlight: s.maxInFlight,
                    results: s.results, handsNow: s.hands.length, framesWithHands: s.framesWithHands ?? null,
                    loadMs: s.loadMs, backendErrors: s.backendErrors, tip: s.tip, calibrated: !!(s.calib && s.calib.toMm),
                    touch: s.touchTest ? { active: s.touchTest.active, i: s.touchTest.i, n: s.touchTest.seq.length,
                        records: JSON.parse(JSON.stringify(s.touchTest.records)) } : null, firstHand: s.hands[0] ? JSON.parse(JSON.stringify(s.hands[0])) : null,
                    inferP50: [...s.inferMs].sort((a,b)=>a-b)[Math.floor(s.inferMs.length/2)],
                    loopP95: [...s.loopMs].sort((a,b)=>a-b)[Math.ceil(0.95*s.loopMs.length)-1] }; }"""
            )
            stats["status"] = page.inner_text("#status")
            shot = HERE.parent / "out" / f"tracking_e2e_{mode}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)
            stats["screenshot"] = str(shot)
            browser.close()
    finally:
        srv.shutdown()
    stats["console"] = logs[-10:]
    return stats


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    video = sys.argv[2] if len(sys.argv) > 2 else None
    delegate = sys.argv[3] if len(sys.argv) > 3 else None
    stats = run(mode, video, seconds=6 if mode == "loop" else 8, delegate=delegate)
    print(json.dumps(stats, indent=1))
    failures = []
    if mode == "loop":
        if stats["maxInFlight"] != 1:
            failures.append("more than one frame in flight")
        if stats["pump"]["dropped"] == 0:
            failures.append("no frames dropped with a 100 ms worker; frames may be queuing")
        if not stats["procFps"] or stats["procFps"] > 11:
            failures.append("processed fps should be at most about 10 with a 100 ms worker")
        if stats["loopP95"] > 160:
            failures.append("frame to result p95 above 160 ms; frames may be queuing")
    if mode == "hands":
        if not stats.get("framesWithHands"):
            failures.append("no hands found in the clip")
        if not stats.get("calibrated"):
            failures.append("calibration from ?corners= did not apply")
        tip = stats.get("tip") or {}
        if not tip.get("mm") or not all(0 <= v <= 300 for v in tip["mm"]):
            failures.append(f"fingertip not mapped onto the sheet: {tip}")
    if mode == "touch":
        t = stats.get("touch") or {}
        recs = t.get("records") or []
        spaces = sum(1 for r in recs if r.get("how") == "space")
        # The clip's pan slows to a stop at each end, so dwell captures may add to the 3 Space presses.
        if spaces != 3 or t.get("n") != 45 or t.get("i") != len(recs):
            failures.append(f"expected 3 Space touches of 45, got {spaces} Space, {len(recs)} total, i={t.get('i')}")
        if any(not (r["errorMm"] >= 0) for r in recs):
            failures.append("touch errors are not finite")
    if failures:
        print("FAIL:", "; ".join(failures))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
