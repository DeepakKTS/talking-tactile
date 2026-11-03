# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless browser check for the tracking spike, using the installed Google Chrome and a fake camera.

  uv run spikes/tracking/e2e_check.py loop          stub worker with a 100 ms delay: frames must drop, never queue
  uv run spikes/tracking/e2e_check.py fallback      stub GPU worker that never answers: the page must be on CPU 8 s after its first frame
  uv run spikes/tracking/e2e_check.py hands VIDEO [CPU|GPU]   MediaPipe on a y4m clip: hands must be found
  uv run spikes/tracking/e2e_check.py touch VIDEO [CPU|GPU]   same, then T and 3 Space presses record 3 touches
  uv run spikes/tracking/e2e_check.py session       a whole 45 touch test through the page, scripted hands,
                                                    then the downloaded JSON through analyze_touch.py

Prints the page's stats as JSON. Exits non-zero if a check fails.
"""

from __future__ import annotations

import functools
import http.server
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out"  # git-ignored


# The order of the Wake Lock request and the camera request; headless Chrome has no screen to
# keep on, so a stand-in grants the lock and records the call.
ORDER_JS = """
(() => {
  window.__order = [];
  Object.defineProperty(navigator, "wakeLock", { configurable: true, value: {
    request: () => { window.__order.push("wakeLock"); return Promise.resolve({ release: () => Promise.resolve() }); },
  } });
  const md = navigator.mediaDevices;
  const gum = md.getUserMedia.bind(md);
  md.getUserMedia = (c) => { window.__order.push(c && c.video ? "camera" : "microphone"); return gum(c); };
})();
"""


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
    query = {"loop": "?stub=100", "fallback": "?stub=600000"}.get(mode) or (f"?delegate={delegate}" if delegate else "")
    if mode in ("hands", "touch"):
        # Whole 640x480 frame as the sheet, so the fingertip lands at a known place in mm.
        query += ("&" if query else "?") + "corners=0,0,640,0,640,480,0,480"
    logs: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True, args=args)
            page = browser.new_page()
            page.add_init_script(ORDER_JS)
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
            restart_fps = None
            if mode == "loop":  # Start again, as when picking the rear camera: still one frame loop
                restart_fps = page.evaluate("() => window.__tt.camFps")
                page.click("#start")
                page.wait_for_timeout(3000)
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
            stats["order"] = page.evaluate("() => window.__order")
            stats["delegate"] = page.evaluate("() => window.__tt.warmup.delegate")
            stats["fellBack"] = page.evaluate("() => window.__tt.warmup.fellBack")
            stats["camFpsBeforeRestart"] = restart_fps
            shot = HERE.parent / "out" / f"tracking_e2e_{mode}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)
            stats["screenshot"] = str(shot)
            browser.close()
    finally:
        srv.shutdown()
    stats["console"] = logs[-10:]
    return stats


# The page's worker, kept so session() can hand it results as MediaPipe would.
KEEP_WORKER = """
const W = window.Worker;
window.Worker = function (...a) { const w = new W(...a); window.__worker = w; return w; };
window.Worker.prototype = W.prototype;
"""

# A pointing hand built in sheet mm and mapped to pixels through the calibration, so its
# contact point (4 mm back from the tip, toward the DIP joint) lands on each target. It
# comes in from the right, then rests; one frame in 20 has no hand.
PLAY_SESSION = """
async () => {
  const { homographyFromPoints, applyHomography } = await import('./lib/homography.js');
  const s = window.__tt;
  const toPx = homographyFromPoints(s.sheet.corners_mm, s.calib.corners);
  const [vw, vh] = s.videoSize;
  const offset = Number(document.getElementById('offset').value);
  const hand = (x, y) => {
    const mm = Array.from({ length: 21 }, () => [x, y + 60]);
    const finger = (b, dx, tipFromWrist) => {
      mm[b] = [x + dx, y + 36]; mm[b + 1] = [x + dx, y + 26];
      mm[b + 2] = [x + dx, y + 60 - (34 + tipFromWrist) / 2]; mm[b + 3] = [x + dx, y + 60 - tipFromWrist];
    };
    finger(5, 0, 60 + offset);       // index: the tip is offset mm above (x, y)
    mm[7] = [x, y + 10];             // its DIP joint, straight below the tip
    [[9, 8], [13, 16], [17, 24]].forEach(([b, dx]) => finger(b, dx, 18)); // curled: tips nearer the wrist than the PIP
    return { landmarks: mm.map((p) => { const [px, py] = applyHomography(toPx, p); return { x: px / vw, y: py / vh }; }) };
  };
  let n = 0;
  while (s.touchTest.active) {
    const i = s.touchTest.i;
    const [tx, ty] = s.sheet.targets_mm[s.touchTest.seq[i]];
    for (let k = 0; k < 90 && s.touchTest.active && s.touchTest.i === i; k++) {
      const hands = n++ % 20 === 7 ? [] : [hand(tx + Math.max(0, 10 - k) * 2, ty)];
      window.__worker.onmessage({ data: { type: 'result', id: -1, inferMs: 0, hands } });
      await new Promise((r) => setTimeout(r, 1000 / 30));
    }
  }
  return JSON.parse(localStorage.getItem('tt-last-touch-test'));
}
"""


def session() -> list[str]:
    """A whole touch test through the page: stub worker, ?corners=, T, then scripted hands
    for all 45 touches. The JSON the page offers must analyze to a near zero error."""
    t0 = time.monotonic()
    srv, port = serve()
    fail: list[str] = []
    corners = [[110, 20], [540, 35], [560, 465], [90, 450]]
    query = f"?stub=600000&seed=3&corners={','.join(str(v) for c in corners for v in c)}"
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
            browser = p.chromium.launch(channel="chrome", headless=True, args=args)
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(KEEP_WORKER)
            page.goto(f"http://127.0.0.1:{port}/index.html{query}")
            page.click("#start")
            page.wait_for_function("window.__tt.calib && window.__tt.calib.toMm && window.__worker", timeout=30000)
            page.keyboard.press("t")
            page.wait_for_function("window.__tt.touchTest.active")
            result = page.evaluate(PLAY_SESSION)
            link = page.evaluate("() => { const a = document.querySelector('#results a'); return a && a.download; }")
            browser.close()
    finally:
        srv.shutdown()
    OUT.mkdir(exist_ok=True)
    path = OUT / (link or "touch-test-missing.json")
    path.write_text(json.dumps(result, indent=1))
    py = subprocess.run([sys.executable, str(HERE / "analyze_touch.py"), str(path)], capture_output=True, text=True)
    analysis = json.loads(py.stdout) if py.returncode == 0 else {}
    recs = result.get("records", [])
    frames = [f for r in recs for f in r.get("frames", [])]
    seen = [f for f in frames if not f.get("lost")]
    print(json.dumps({
        "seconds": round(time.monotonic() - t0, 1), "file": str(path), "touches": len(recs),
        "frames": len(frames), "lost_frames": len(frames) - len(seen),
        "analysis": {k: analysis.get(k) for k in ("n", "mean_mm", "p95_mm", "max_mm", "gate_b")},
        "page_errors": errors,
    }, indent=1))
    if errors:
        fail.append(f"page errors: {errors[:3]}")
    if not link or not link.startswith("touch-test-"):
        fail.append(f"no download link: {link}")
    if py.returncode != 0:
        fail.append(f"analyze_touch.py failed: {py.stderr[-300:]}")
    elif analysis["n"] != 45 or analysis["mean_mm"] > 0.5 or analysis["gate_b"] != "pass":
        fail.append(f"analysis: {analysis}")
    if result.get("version") != 2 or result.get("calibration", {}).get("cornersPx") != corners:
        fail.append(f"version or calibration: {result.get('version')}, {result.get('calibration')}")
    if result.get("corners") != corners or not result.get("videoSize"):
        fail.append("corners or videoSize missing")
    if any(not r.get("frames") for r in recs) or not all({"t", "tipPx", "dipPx", "rawMm", "mm"} <= f.keys() for f in seen):
        fail.append("a touch has no frames, or a frame lacks a field")
    if not frames or len(frames) == len(seen):
        fail.append("no frames, or no lost frames recorded")
    return fail


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if mode == "session":
        failures = session()
        print("FAIL: " + "; ".join(failures) if failures else "PASS")
        sys.exit(1 if failures else 0)
    video = sys.argv[2] if len(sys.argv) > 2 else None
    delegate = sys.argv[3] if len(sys.argv) > 3 else None
    stats = run(mode, video, seconds={"loop": 6, "fallback": 10}.get(mode, 8), delegate=delegate)
    print(json.dumps(stats, indent=1))
    failures = []
    order = stats.get("order") or []
    if not order or order[0] != "wakeLock" or "camera" not in order:
        failures.append(f"the Wake Lock was not requested before the camera: {order}")
    if mode == "fallback":
        # A stub GPU that never answers: 8 s after its first frame the page is on CPU.
        if stats["delegate"] != "CPU" or not (stats["fellBack"] or "").startswith("no result from the GPU 8 s"):
            failures.append(f"no CPU fallback: delegate {stats['delegate']}, {stats['fellBack']}")
    if mode == "loop":
        if stats["maxInFlight"] != 1:
            failures.append("more than one frame in flight")
        if stats["camFps"] > 1.3 * stats["camFpsBeforeRestart"]:
            failures.append("a second Start sped up the camera count: two frame loops")
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
