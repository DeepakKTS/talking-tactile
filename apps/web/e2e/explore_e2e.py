# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless Explore run, end to end, in the installed Google Chrome:

  uv run apps/web/e2e/explore_e2e.py

1. Starts the API in mock mode on a temporary data dir, builds the web app and serves it
   with vite preview. In /author: uploads the synthetic figure through the file input,
   renames a part, marks one checked, publishes, and follows the print and Explore links.
2. Explore, script mode (?source=script): hands are injected at 30 fps as worker results would
   arrive. Touches every part on the published sheet, checks earcon then label, then
   turns the network off and checks labels, earcons, guidance and the offline answer.
   Measures Escape to speech stopped. Real speechSynthesis, with speak() wrapped to record
   the voice each utterance was given; every one must be a local voice (localService).
3. Offline from load: a fresh page goes offline as soon as the published regions.json has
   loaded, then a scripted finger touches every part and is guided to one. No request may
   be made after that point.
4. No local voice: getVoices() hides the local voices, as on a device with only network
   voices. The page must show the notice, make the mirror polite and never call speak().
5. Failed loads are told: regions.json refused with and without a saved copy.
6. Explore, camera mode: Chrome's fake camera and the real MediaPipe worker, with every request
   that is not to this machine refused, so the wasm and the model must be local.

Every page's requests are recorded. A request that fails, or answers 400 or more, fails the
run unless the check that caused it also saw the page tell the user. The requests /explore
made are printed by path.

Prints the measured numbers as JSON and exits non-zero if a check fails.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps" / "web"
API = ROOT / "services" / "api"
FIGURE = ROOT / "fixtures" / "synthetic" / "figure.png"
SCALE = 3  # px per mm in the scripted camera view
PAGE_MM = (215.9, 279.4)
W, H = round(PAGE_MM[0] * SCALE), round(PAGE_MM[1] * SCALE)
INSET = 12.7
OFFLINE = "Questions need the network. Labels still work."
NO_VOICE = "This device has no voice that works offline"
SHOTS = ROOT / "data" / "e2e"  # git-ignored screenshots
# Records the voice each utterance was given, then speaks it with the real speechSynthesis.
SPEECH_JS = """
(() => {
  const rec = { spoken: [] };
  window.__speech = rec;
  const speak = speechSynthesis.speak.bind(speechSynthesis);
  speechSynthesis.speak = (u) => {
    rec.spoken.push({ text: u.text, voice: u.voice ? u.voice.name : null, local: !!(u.voice && u.voice.localService) });
    speak(u);
  };
})();
"""
# A device whose voices all need the network.
NETWORK_VOICES_JS = """
(() => {
  const voices = speechSynthesis.getVoices.bind(speechSynthesis);
  speechSynthesis.getVoices = () => voices().filter((v) => !v.localService);
})();
"""


class Requests:
    """Every request a context makes, and the ones that failed or answered 400 or more."""

    def __init__(self, context: Any, name: str) -> None:
        self.name = name
        self.seen: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []
        self.told: list[str] = []  # failed urls a check saw the page explain
        context.on("request", lambda r: self.seen.append({"url": r.url, "type": r.resource_type, "method": r.method}))
        context.on("requestfailed", lambda r: self.failed.append({"url": r.url, "why": r.failure}))
        context.on("response", lambda r: r.status >= 400 and self.failed.append({"url": r.url, "why": r.status}))

    def told_about(self, part: str) -> list[dict[str, Any]]:
        hits = [f for f in self.failed if part in f["url"]]
        self.told += [f["url"] for f in hits]
        return hits

    def silent(self) -> list[dict[str, Any]]:
        return [f for f in self.failed if f["url"] not in self.told]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_http(url: str, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not answer")


def api_json(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# A pointing hand in page mm with its index tip at (x, y), drawn in the scripted view.
HAND_JS = """
(tip, W, H, S, open) => {
  const lm = Array.from({ length: 21 }, () => [0, 0]);
  const put = (i, x, y) => { lm[i] = [(x * S) / W, (y * S) / H]; };
  put(0, tip[0], tip[1] + 90);
  [[5, 0], [9, 8], [13, 16], [17, 24]].forEach(([b, dx], k) => {
    const x = tip[0] + dx, len = k === 0 || open ? 90 : 25;
    put(b, x, tip[1] + 60); put(b + 1, x, tip[1] + 50);
    put(b + 2, x, tip[1] + 90 - (50 + len) / 2); put(b + 3, x, tip[1] + 90 - len);
  });
  return { landmarks: lm, label: "Left", score: 0.9 };
}
"""

PLAY_JS = """
async ([frames, W, H, S, hand]) => {
  const make = eval(hand);
  const offset = %OFFSET%;
  for (const f of frames) {
    // The contact point is the tip moved back by the offset, so aim the tip ahead of it.
    const hands = f ? [make([f[0], f[1] - offset], W, H, S, false)] : [];
    window.__tt.inject(hands, W, H);
    await new Promise((r) => setTimeout(r, 1000 / 30));
  }
}
"""


def play(page: Page, frames: list[tuple[float, float] | None]) -> None:
    page.evaluate(PLAY_JS.replace("%OFFSET%", "4.0"), [frames, W, H, SCALE, HAND_JS])


def hold(p: tuple[float, float] | None, ms: float) -> list[tuple[float, float] | None]:
    return [p] * round(ms / (1000 / 30))


def log_since(page: Page, n: int) -> list[dict[str, Any]]:
    return page.evaluate("(n) => window.__tt.log.slice(n)", n)


def log_len(page: Page) -> int:
    return page.evaluate("() => window.__tt.log.length")


def explore_url(base: str, fid: str) -> str:
    corners = [INSET, INSET, PAGE_MM[0] - INSET, INSET, PAGE_MM[0] - INSET, PAGE_MM[1] - INSET, INSET, PAGE_MM[1] - INSET]
    q = ",".join(f"{c * SCALE:.3f}" for c in corners)
    return f"{base}/explore?figure={fid}&source=script&corners={q}"


def start_by_keys(page: Page) -> None:
    # Keyboard only: Start has the focus once the sheet loads, Enter presses it.
    page.wait_for_function("document.activeElement && document.activeElement.textContent === 'Start exploring'")
    page.keyboard.press("Enter")
    page.wait_for_function("window.__tt.started && window.__tt.calibrated", timeout=10000)
    page.wait_for_timeout(300)


def says(page: Page, n: int) -> list[str]:
    return [e.get("text", "") for e in log_since(page, n) if e["kind"] == "say"]


def typed(page: Page, text: str) -> list[str]:
    n = log_len(page)
    page.get_by_label("Ask, or say where is, more, repeat, stop, what is here").focus()
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    page.evaluate("() => document.activeElement.blur()")
    return says(page, n)


def touch_all(page: Page, regions: list[dict[str, Any]], rounds: int, fail: list[str], when: str) -> int:
    """Touches each part's centroid in turn; each must give its earcon, then its label."""
    ok = 0
    for _ in range(rounds):
        for r in regions:
            n = log_len(page)
            # A scripted finger jumps across the sheet; the 1 euro filter needs a moment to settle.
            play(page, hold((5.0, 5.0), 300) + hold(tuple(r["centroid_mm"]), 1500) + hold((5.0, 5.0), 300))
            got = [e for e in log_since(page, n) if e["kind"] in ("earcon", "say")]
            want_say = r["label"][0].upper() + r["label"][1:]
            if got[:2] and got[0]["kind"] == "earcon" and got[1:2] and got[1].get("text") == want_say:
                ok += 1
            else:
                fail.append(f"{when}, touching {r['label']}: heard {got[:3]}")
    return ok


def guide_to_stem(page: Page, regions: list[dict[str, Any]], fail: list[str], when: str) -> dict[str, Any]:
    """A typed "where is the stem": the sentence, beeps that speed up near it, then the chime."""
    out: dict[str, Any] = {}
    stem = next(r for r in regions if r["label"] == "stem")
    start = (190.0, 260.0)
    n = log_len(page)
    play(page, hold(start, 300))
    typed(page, "where is the stem")
    play(page, hold(start, 3000))
    guide = log_since(page, n)
    said = [e["text"] for e in guide if e["kind"] == "say"]
    beeps = [e for e in guide if e["kind"] == "beep"]
    out["guidance_sentence"] = said[-1] if said else None
    out["guidance_beeps_far"] = len(beeps)
    if not said or not said[-1].startswith("Stem. Left"):
        fail.append(f"{when}, guidance sentence: {said}")
    n = log_len(page)
    near = (stem["centroid_mm"][0] + 25, stem["centroid_mm"][1])
    play(page, hold(near, 3000))
    out["guidance_beeps_near"] = sum(e["kind"] == "beep" for e in log_since(page, n))
    if out["guidance_beeps_near"] <= out["guidance_beeps_far"]:
        fail.append(f"{when}, beeps did not speed up near the part")
    n = log_len(page)
    play(page, hold(tuple(stem["centroid_mm"]), 800))
    arrive = log_since(page, n)
    out["arrival"] = [e["kind"] if e["kind"] != "say" else e["text"] for e in arrive if e["kind"] in ("chime", "say")]
    if "chime" not in out["arrival"] or "Stem" not in out["arrival"]:
        fail.append(f"{when}, no chime and label on arrival: {arrive}")
    return out


def scripted(page: Page, base: str, fid: str, regions: list[dict[str, Any]], fail: list[str]) -> dict[str, Any]:
    page.goto(explore_url(base, fid))
    page.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
    start_by_keys(page)
    out: dict[str, Any] = {}

    def keys(*presses: str) -> list[str]:
        n = log_len(page)
        for k in presses:
            page.keyboard.press(k)
            page.wait_for_timeout(50)
        return says(page, n)

    out["online_touches_ok"] = touch_all(page, regions, 3, fail, "online")
    lobe = next(r for r in regions if r["label"] == "left lobe")
    play(page, hold(tuple(lobe["centroid_mm"]), 900))
    out["keys_w_m_period"] = keys("w", "m", ".")
    if out["keys_w_m_period"][:1] != ["Left lobe"] or len(out["keys_w_m_period"]) != 3:
        fail.append(f"W, M and period keys: {out['keys_w_m_period']}")
    page.context.set_offline(True)
    out["offline"] = page.evaluate("() => !navigator.onLine")
    out["offline_touches_ok"] = touch_all(page, regions, 1, fail, "offline")
    out.update(guide_to_stem(page, regions, fail, "offline"))

    # A question with the network off.
    asked = typed(page, "What does the stem do?")
    out["offline_answer"] = asked
    if asked != [OFFLINE]:
        fail.append(f"offline question: {asked}")

    # Escape stops speech.
    page.evaluate("() => window.addEventListener('keydown', () => { window.__escAt = performance.now(); }, { capture: true })")
    page.keyboard.press("m")
    n = log_len(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    stops = [e for e in log_since(page, n) if e["kind"] == "stop"]
    esc = page.evaluate("() => window.__escAt")
    out["escape_to_stop_ms"] = round(stops[0]["at"] - esc, 3) if stops and esc else None
    if out["escape_to_stop_ms"] is None or out["escape_to_stop_ms"] >= 200:
        fail.append(f"Escape to stop: {out['escape_to_stop_ms']}")
    # A covered camera: dark frames with no hands.
    n = log_len(page)
    t0 = page.evaluate("() => performance.now()")
    page.evaluate("""async ([W, H]) => {
      for (let i = 0; i < 90; i++) { window.__tt.inject([], W, H, 0); await new Promise((r) => setTimeout(r, 1000 / 30)); }
      for (let i = 0; i < 10; i++) { window.__tt.inject([], W, H, 0.5); await new Promise((r) => setTimeout(r, 1000 / 30)); }
    }""", [W, H])
    seen = [e for e in log_since(page, n) if e["kind"] == "say"]
    out["covered_camera"] = [e["text"] for e in seen]
    out["covered_to_said_ms"] = round(seen[0]["at"] - t0) if seen else None
    if out["covered_camera"] != ["The camera cannot see the sheet.", "The camera can see the sheet again."]:
        fail.append(f"covered camera: {out['covered_camera']}")
    elif out["covered_to_said_ms"] >= 2000:
        fail.append(f"covered camera said after {out['covered_to_said_ms']} ms")

    # Who speaks: the app voice with a quiet mirror, or the screen reader and no app voice.
    mirror = "document.querySelector('[role=log]')"
    out["mirror_live_app"] = page.evaluate(f"() => {mirror}.getAttribute('aria-live')")
    spoken = page.evaluate("() => window.__speech.spoken")
    out["app_voice"] = {"utterances": len(spoken), "voices": sorted({s["voice"] or "none" for s in spoken})}
    if not spoken or not all(s["local"] for s in spoken):
        fail.append(f"the app voice did not always use the local voice: {out['app_voice']}")
    if page.get_by_text(NO_VOICE).count():
        fail.append("the no local voice notice showed with a local voice")
    spoken0 = len(spoken)
    page.get_by_label("Who speaks").select_option("screen_reader")
    out["mirror_live_screen_reader"] = page.evaluate(f"() => {mirror}.getAttribute('aria-live')")
    page.evaluate("() => document.activeElement.blur()")
    keys("w", "m")
    out["app_voice_calls_in_screen_reader_mode"] = page.evaluate("() => window.__speech.spoken.length") - spoken0
    lines = page.evaluate(f"() => [...{mirror}.children].map((p) => p.textContent)")
    out["mirror_last_lines"] = lines[-2:]
    if out["mirror_live_app"] != "off" or out["mirror_live_screen_reader"] != "polite":
        fail.append(f"aria-live: app {out['mirror_live_app']}, screen reader {out['mirror_live_screen_reader']}")
    if out["app_voice_calls_in_screen_reader_mode"] != 0:
        fail.append("the app voice spoke in screen reader mode")
    if len(lines[-2:]) != 2 or len(set(lines[-2:])) != 2:
        fail.append(f"mirror lines: {lines[-2:]}")
    page.get_by_label("Who speaks").select_option("app")

    page.screenshot(path=str(SHOTS / "explore.png"), full_page=True)
    out["metrics"] = page.evaluate("() => window.__tt.metrics.summary()")
    page.context.set_offline(False)
    return out


def check_all(page: Page) -> list[str]:
    """The teacher presses Mark all parts checked in the review and confirms. A part is
    touchable only once checked. Returns the warnings the confirm step listed."""
    page.get_by_role("button", name="Mark all parts checked").click()
    confirm = page.get_by_role("region", name="Confirm marking all parts checked")
    warned = confirm.get_by_role("list", name="Parts with a warning")
    listed = warned.locator("li").all_text_contents() if warned.count() else []
    confirm.get_by_role("button", name=re.compile(r"^Yes, mark all \d+ checked$")).click()
    page.get_by_text("Every part is checked.").wait_for(timeout=120000)
    page.wait_for_function("() => [...document.querySelectorAll('button')].some((b) => b.textContent === 'Publish for students' && !b.disabled)")
    return listed


def author(page: Page, base: str, api: str, fail: list[str]) -> tuple[str, dict[str, Any]]:
    """The teacher's flow in the real UI: upload, review, two edits, publish."""
    out: dict[str, Any] = {}
    page.goto(f"{base}/author")
    page.get_by_label("Figure (PNG, JPEG or a PDF page)").set_input_files(str(FIGURE))
    page.get_by_label("Grade band").select_option("k5")
    page.get_by_role("button", name="Make a tactile sheet").click()
    parts = page.get_by_role("list", name="Parts")
    parts.wait_for(timeout=60000)
    fid = page.url.split("figure=")[1]
    publish = page.get_by_role("button", name="Publish for students")
    out["not_checked_at_start"] = parts.get_by_text("Not checked").count()
    out["images_loaded"] = page.evaluate(
        "() => [...document.querySelectorAll('img')].map((i) => [i.alt, i.complete && i.naturalWidth > 0])"
    )
    if not all(ok for _, ok in out["images_loaded"]) or len(out["images_loaded"]) != 2:
        fail.append(f"review images: {out['images_loaded']}")

    page.get_by_role("button", name="Edit pore").click()
    page.get_by_label("New name for pore").fill("pore opening")
    page.get_by_role("button", name="Rename pore").click()
    parts.get_by_text("pore opening", exact=True).wait_for(timeout=30000)
    page.wait_for_function("() => [...document.querySelectorAll('button')].some((b) => b.textContent === 'Publish for students' && !b.disabled)")
    page.get_by_role("button", name="Mark left lobe checked").click()
    page.get_by_role("button", name="Mark left lobe checked").wait_for(state="detached", timeout=30000)
    page.wait_for_function("() => [...document.querySelectorAll('button')].some((b) => b.textContent === 'Publish for students' && !b.disabled)")
    out["not_checked_after_edits"] = parts.get_by_text("Not checked").count()
    if out["not_checked_after_edits"] != out["not_checked_at_start"] - 2:
        fail.append(f"checked flags: {out['not_checked_at_start']} then {out['not_checked_after_edits']}")
    out["rules"] = page.get_by_text("All tactile rules pass.").count() == 1
    out["warnings_at_confirm"] = check_all(page)
    publish = page.get_by_role("button", name="Publish for students")
    publish.click()
    explore = page.get_by_role("link", name="Open version 1 in Explore")
    explore.wait_for(timeout=30000)
    out["explore_link"] = explore.get_attribute("href")
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.get_by_role("button", name="Show on sheet").nth(1).click()
    page.screenshot(path=str(SHOTS / "author.png"), full_page=True)
    pdf = page.get_by_role("link", name="Download print PDF, version 1").get_attribute("href") or ""
    out["print_pdf_is_pdf"] = urllib.request.urlopen(f"{api}{pdf}").read(4) == b"%PDF"
    if out["explore_link"] != f"/explore?figure={fid}&version=1" or not out["print_pdf_is_pdf"]:
        fail.append(f"publish links: {out['explore_link']}, pdf {out['print_pdf_is_pdf']}")
    return fid, out


def offline_from_load(page: Page, reqs: Requests, base: str, fid: str, regions: list[dict[str, Any]],
                      fail: list[str]) -> dict[str, Any]:
    """Offline from the moment the published regions.json has loaded."""
    out: dict[str, Any] = {}
    page.goto(explore_url(base, fid))
    page.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
    sheet = [r["url"] for r in reqs.seen if r["url"].endswith("/regions.json")]
    out["regions_json"] = [u.split("/", 3)[3] for u in sheet]
    if len(sheet) != 1 or "/published/" not in sheet[0]:
        fail.append(f"offline from load: the sheet came from {sheet}")
    page.context.set_offline(True)
    out["offline"] = page.evaluate("() => !navigator.onLine")
    n = len(reqs.seen)
    start_by_keys(page)
    out["touches_ok"] = touch_all(page, regions, 1, fail, "offline from load")
    out.update(guide_to_stem(page, regions, fail, "offline from load"))
    out["answer"] = typed(page, "What does the stem do?")
    if out["answer"] != [OFFLINE]:
        fail.append(f"offline from load, question: {out['answer']}")
    out["requests_after_offline"] = [r["url"] for r in reqs.seen[n:]]
    if out["requests_after_offline"]:
        fail.append(f"offline from load, requests made: {out['requests_after_offline'][:5]}")
    out["utterances_local"] = page.evaluate("() => window.__speech.spoken.every((s) => s.local)")
    page.context.set_offline(False)
    return out


def no_local_voice(page: Page, base: str, fid: str, regions: list[dict[str, Any]], fail: list[str]) -> dict[str, Any]:
    """Only network voices: the app voice must step aside, and say so."""
    page.add_init_script(NETWORK_VOICES_JS)
    page.goto(explore_url(base, fid))
    page.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
    start_by_keys(page)
    out: dict[str, Any] = {"voices_listed": page.evaluate("() => speechSynthesis.getVoices().length")}
    notice = page.get_by_role("alert").filter(has_text=NO_VOICE)
    out["notice_visible"] = notice.count() == 1 and notice.is_visible()
    out["mirror_live"] = page.evaluate("() => document.querySelector('[role=log]').getAttribute('aria-live')")
    lobe = next(r for r in regions if r["label"] == "left lobe")
    touch_all(page, [lobe], 1, fail, "no local voice")
    out["mirror_has_label"] = page.evaluate("() => document.querySelector('[role=log]').textContent.includes('Left lobe')")
    out["speak_calls"] = page.evaluate("() => window.__speech.spoken.length")
    if not out["notice_visible"] or out["mirror_live"] != "polite" or not out["mirror_has_label"] or out["speak_calls"]:
        fail.append(f"no local voice: {out}")
    page.screenshot(path=str(SHOTS / "no_local_voice.png"), full_page=True)
    return out


def failed_loads_are_told(saved: tuple[Any, Requests], fresh: tuple[Any, Requests], base: str, fid: str,
                          fail: list[str]) -> dict[str, Any]:
    """regions.json refused: with a saved copy the page says it opened that, without one it says why."""
    out: dict[str, Any] = {}
    cases = [("with_saved_copy", *saved, "Opened the saved copy; the network is down."),
             ("no_saved_copy", *fresh, "The sheet could not be loaded. Check the network.")]
    for name, ctx, reqs, want in cases:
        page = ctx.new_page()
        page.route("**/regions.json", lambda route: route.abort("internetdisconnected"))
        page.goto(explore_url(base, fid))
        page.get_by_text(want).wait_for(timeout=10000)
        told = reqs.told_about("/regions.json")
        out[name] = {"failed": len(told), "said": want}
        if len(told) != 1 or reqs.silent():
            fail.append(f"failed load {name}: told {told}, silent {reqs.silent()}")
        page.unroute("**/regions.json")
        page.close()
    return out


def camera(page: Page, base: str, fid: str, fail: list[str]) -> dict[str, Any]:
    refused: list[str] = []

    def guard(route: Any) -> None:
        host = route.request.url.split("/")[2]
        if host.startswith("127.0.0.1") or host.startswith("localhost"):
            route.continue_()
        else:
            refused.append(route.request.url)
            route.abort()

    page.route("**/*", guard)
    page.goto(f"{base}/explore?figure={fid}&corners=0,0,1280,0,1280,720,0,720")
    page.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
    page.get_by_role("button", name="Start exploring").click()
    try:
        page.wait_for_function(
            "window.__tt.camera && window.__tt.camera.backend.startsWith('mediapipe')", timeout=60000
        )
    except Exception:
        fail.append(f"MediaPipe did not load from local files; refused {refused[:5]}")
        return {"refused": refused}
    page.wait_for_timeout(5000)
    out = page.evaluate(
        "() => ({ backend: window.__tt.camera.backend, pump: { ...window.__tt.camera.stats },"
        " captureToLandmarksMs: window.__tt.metrics.captureToLandmarksMs.summary() })"
    )
    out["refused_requests"] = refused
    if refused:
        fail.append(f"Explore asked for remote files: {refused[:5]}")
    if out["captureToLandmarksMs"]["count"] < 10:
        fail.append("the worker returned fewer than 10 frames in 5 s")
    return out


def main() -> None:
    fail: list[str] = []
    api_port, web_port = free_port(), free_port()
    api, base = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    data = Path(tempfile.mkdtemp(prefix="tt-e2e-"))
    env = {**os.environ, "MOCK_META": "1", "TT_API": api}
    launch = (
        "import sys, uvicorn; from pathlib import Path; from app.main import create_app; "
        "uvicorn.run(create_app(data_dir=Path(sys.argv[1])), host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')"
    )
    procs = [subprocess.Popen(["uv", "run", "python", "-c", launch, str(data), str(api_port)], cwd=API, env=env)]
    try:
        subprocess.run(["npx", "vite", "build", "--logLevel", "error"], cwd=WEB, env=env, check=True)
        procs.append(subprocess.Popen(["npx", "vite", "preview", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                                      cwd=WEB, env=env, stdout=subprocess.DEVNULL))
        wait_http(f"{api}/api/health")
        wait_http(base)
        regions_url = "{api}/api/figures/{fid}/published/latest/regions.json"
        result: dict[str, Any] = {}
        with sync_playwright() as p:
            args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required"]
            browser = p.chromium.launch(channel="chrome", headless=True, args=args)
            errors: list[str] = []
            audits: list[Requests] = []
            teacher_ctx = browser.new_context()
            audits.append(Requests(teacher_ctx, "author"))
            teacher = teacher_ctx.new_page()
            teacher.on("pageerror", lambda e: errors.append(str(e)))
            fid, result["author"] = author(teacher, base, api, fail)
            regions = json.loads(urllib.request.urlopen(regions_url.format(api=api, fid=fid)).read())["regions"]
            if "pore opening" not in {r["label"] for r in regions}:
                fail.append("the published regions.json lacks the teacher's rename")
            result.update({"figure_id": fid, "regions": len(regions)})
            explore_run(browser, base, fid, regions, fail, errors, result, audits)
            silent = [{"page": a.name, **f} for a in audits for f in a.silent()]
            result["silent_failures"] = silent
            if silent:
                fail.append(f"requests failed with nothing said: {silent[:5]}")
            browser.close()
    finally:
        for proc in procs:
            proc.terminate()
        shutil.rmtree(data, ignore_errors=True)
    print(json.dumps(result, indent=1))
    if fail:
        print("FAIL:\n- " + "\n- ".join(fail))
        sys.exit(1)
    print("PASS")


def explore_run(browser: Any, base: str, fid: str, regions: list[dict[str, Any]], fail: list[str],
                errors: list[str], result: dict[str, Any], audits: list[Requests]) -> None:
    def context(name: str) -> tuple[Any, Page, Requests]:
        ctx = browser.new_context()
        reqs = Requests(ctx, name)
        audits.append(reqs)
        ctx.add_init_script(SPEECH_JS)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        return ctx, page, reqs

    script_ctx, page, script_reqs = context("explore script")
    result["script"] = scripted(page, base, fid, regions, fail)
    _, page, reqs = context("explore offline from load")
    result["offline_from_load"] = offline_from_load(page, reqs, base, fid, regions, fail)
    _, page, _ = context("explore no local voice")
    result["no_local_voice"] = no_local_voice(page, base, fid, regions, fail)
    fresh_ctx, _, fresh_reqs = context("explore no saved copy")
    result["failed_loads"] = failed_loads_are_told((script_ctx, script_reqs), (fresh_ctx, fresh_reqs), base, fid, fail)
    _, cam, cam_reqs = context("explore camera")
    result["camera"] = camera(cam, base, fid, fail)
    # What /explore asked for, by path, in script mode and in camera mode with MediaPipe.
    paths: dict[str, set[str]] = {}
    for r in script_reqs.seen + cam_reqs.seen:
        host, path = r["url"].split("/")[2], "/" + r["url"].split("/", 3)[3].split("?")[0]
        paths.setdefault(f"{r['type']} {path.replace(fid, '<id>')}", set()).add(host.split(":")[0])
    result["explore_requests"] = sorted(f"{k} ({', '.join(sorted(v))})" for k, v in paths.items())
    result["page_errors"] = errors
    if errors:
        fail.append(f"page errors: {errors[:3]}")


if __name__ == "__main__":
    main()
