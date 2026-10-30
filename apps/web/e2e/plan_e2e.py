# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless run of S1's plan for touch, end to end, in the installed Google Chrome, on the
mock API:

  uv run apps/web/e2e/plan_e2e.py

Mock mode answers the heart from its live recordings of Oct 30 with the plan (fixtures/
recorded/replays.json), so no request reaches the network.

1. /author: upload heart.png. Needs you lists the septum only; For your information lists
   the four valve lines with what each separates.
2. The one merge proposal is one button: "Merge brachiocephalic artery, left common carotid
   artery, left subclavian artery and aorta as 'aortic arch'". Pressing it sends three
   merges and a rename. The rules report then passes, and the sheet publishes.
3. The published regions.json: version 3, the aortic arch one touchable part, the lines
   and the subject kept.
4. /explore, script mode: the intro names the septum as not touchable and no line. A finger
   rests in the right atrium, then slides across the tricuspid valve into the right
   ventricle: it hears the earcon, then "Tricuspid valve, right ventricle", and no label on
   the rest after. A finger resting inside the heart's silhouette on no part hears "Heart"
   once. The code path from the crossing frame to speech is measured (frameToBoundaryMs).

Prints what it saw as JSON and exits non-zero if a check fails."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from explore_e2e import (  # noqa: E402
    API,
    ROOT,
    SPEECH_JS,
    WEB,
    Requests,
    check_all,
    explore_url,
    free_port,
    hold,
    log_len,
    log_since,
    play,
    start_by_keys,
    wait_http,
)
from fix_e2e import enabled  # noqa: E402

HEART = ROOT / "fixtures" / "heart.png"
MERGE = (
    "Merge brachiocephalic artery, left common carotid artery, left subclavian artery and aorta "
    "as 'aortic arch'"
)
Pt = tuple[float, float]


def inside(poly: list[list[float]], p: Pt) -> bool:
    hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def edge(poly: list[list[float]], p: Pt) -> float:
    best = math.inf
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i - 1], poly[i]
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy)))
    return best


def deep(poly: list[list[float]], start: Pt, toward: Pt, depth: float) -> Pt:
    """The first point from start toward `toward` that is inside poly and depth from its edge."""
    for k in range(1, 200):
        f = k / 200
        p = (start[0] + f * (toward[0] - start[0]), start[1] + f * (toward[1] - start[1]))
        if inside(poly, p) and edge(poly, p) >= depth:
            return p
    raise RuntimeError("no point deep enough")


def crossing(a: dict[str, Any], b: dict[str, Any]) -> tuple[Pt, Pt]:
    """A point well inside a and one well inside b, either side of where they come closest."""
    pa, pb = a["polygon_mm"], b["polygon_mm"]
    va, vb = min(((p, q) for p in pa for q in pb), key=lambda pq: math.dist(pq[0], pq[1]))
    return deep(pa, tuple(va), tuple(a["centroid_mm"]), 4.0), deep(pb, tuple(vb), tuple(b["centroid_mm"]), 4.0)


def slide(a: Pt, b: Pt, mm_s: float) -> list[Pt | None]:
    n = max(2, round(math.dist(a, b) / mm_s * 30))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def bare_spot(published: dict[str, Any]) -> Pt:
    """A point inside the silhouette, 4 mm from its edge and from every region."""
    sil = published["subject"]["polygon_mm"]
    xs, ys = [p[0] for p in sil], [p[1] for p in sil]
    regions = [r["polygon_mm"] for r in published["regions"] if r["touchable"]]
    y = min(ys)
    while y < max(ys):
        x = min(xs)
        while x < max(xs):
            p = (x, y)
            if inside(sil, p) and edge(sil, p) > 4 and all(not inside(r, p) and edge(r, p) > 4 for r in regions):
                return p
            x += 1.0
        y += 1.0
    raise RuntimeError("no bare spot inside the silhouette")


def author(page: Page, fail: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["needs_you"] = page.get_by_role("list", name="Needs you").locator("strong").all_text_contents()
    if out["needs_you"] != ["septum"]:
        fail.append(f"needs you: {out['needs_you']}")
    out["for_your_information"] = page.get_by_role("list", name="For your information").locator("li").all_text_contents()
    lines = [t for t in out["for_your_information"] if "A line" in t]
    if len(lines) != 4 or not any(t.startswith("tricuspid valve A line between right atrium and right ventricle") for t in lines):
        fail.append(f"for your information: {out['for_your_information']}")
    page.get_by_role("button", name=MERGE).click()
    page.get_by_role("button", name="Edit aortic arch", exact=True).wait_for(timeout=180000)
    enabled(page, "Publish for students")
    out["rules_pass_after_merge"] = page.get_by_text("All tactile rules pass.").count() == 1
    out["rule_problems"] = page.get_by_role("list", name="Rule problems").locator("li").all_text_contents()
    out["merges_left"] = page.get_by_role("list", name="Suggested merges").count()
    return out


def explore(page: Page, published: dict[str, Any], fail: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    start_by_keys(page)
    intro = [e.get("text", "") for e in log_since(page, 0) if e["kind"] == "say"]
    out["intro"] = intro[:1]
    # The summary may mention valves; the sentence on untouchable parts must name the septum only.
    if not intro or " One part is not touchable yet: septum. Press H for help." not in intro[0]:
        fail.append(f"intro: {intro[:1]}")
    regions = {r["label"]: r for r in published["regions"] if r["touchable"]}
    a, b = crossing(regions["right atrium"], regions["right ventricle"])
    n = log_len(page)
    play(page, hold(a, 1500))
    rested = [e.get("text") for e in log_since(page, n) if e["kind"] == "say"]
    n = log_len(page)
    play(page, slide(a, b, 40.0) + hold(b, 2000))
    heard = [e["kind"] if e["kind"] != "say" else e["text"] for e in log_since(page, n) if e["kind"] in ("earcon", "say", "exit")]
    out["crossing"] = {"from": a, "to": b, "rest_in_atrium": rested, "heard": heard}
    if rested[-1:] != ["Right atrium"] or heard[-2:] != ["earcon", "Tricuspid valve, right ventricle"]:
        fail.append(f"crossing the tricuspid valve: {out['crossing']}")
    spot = bare_spot(published)
    n = log_len(page)
    play(page, hold((5.0, 5.0), 300) + hold(spot, 3000))
    said = [e.get("text") for e in log_since(page, n) if e["kind"] == "say"]
    out["subject"] = {"at": spot, "said": said}
    if said != ["Heart"]:
        fail.append(f"resting on the silhouette: {said}")
    out["metrics"] = page.evaluate("() => window.__tt.metrics.summary()")
    if out["metrics"]["frameToBoundaryMs"]["count"] < 1:
        fail.append("no boundary latency measured")
    return out


def main() -> None:
    fail: list[str] = []
    api_port, web_port = free_port(), free_port()
    api, base = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    data = Path(tempfile.mkdtemp(prefix="tt-plan-e2e-"))
    env = {**os.environ, "MOCK_META": "1", "TT_API": api}
    env.pop("LIVE", None)
    launch = (
        "import sys, uvicorn; from pathlib import Path; from app.main import create_app; "
        "uvicorn.run(create_app(data_dir=Path(sys.argv[1])), host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')"
    )
    procs = [subprocess.Popen(["uv", "run", "python", "-c", launch, str(data), str(api_port)], cwd=API, env=env)]
    result: dict[str, Any] = {}
    try:
        subprocess.run(["npx", "vite", "build", "--logLevel", "error"], cwd=WEB, env=env, check=True)
        procs.append(subprocess.Popen(["npx", "vite", "preview", "--port", str(web_port), "--strictPort"],
                                      cwd=WEB, env=env, stdout=subprocess.DEVNULL))
        wait_http(f"{api}/api/health")
        wait_http(base)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            errors: list[str] = []
            ctx = browser.new_context(viewport={"width": 1600, "height": 1400})
            reqs = Requests(ctx, "author")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/author")
            page.get_by_label("Figure (PNG, JPEG or a PDF page)").set_input_files(str(HEART))
            page.get_by_role("button", name="Make a tactile sheet").click()
            page.get_by_role("list", name="Parts").wait_for(timeout=180000)
            fid = page.url.split("figure=")[1]
            result["author"] = author(page, fail)
            result["warnings_at_confirm"] = check_all(page)
            page.get_by_role("button", name="Publish for students").click()
            page.get_by_role("link", name="Open version 1 in Explore").wait_for(timeout=60000)
            published = json.loads(urllib.request.urlopen(f"{api}/api/figures/{fid}/published/1/regions.json").read())
            arch = [r for r in published["regions"] if r["label"] == "aortic arch"]
            result["published"] = {
                "schema_version": published["schema_version"],
                "aortic_arch": [(r["id"], r["touchable"]) for r in arch],
                "lines": [(x["label"], x.get("separates")) for x in published.get("lines", [])],
                "subject": published.get("subject", {}).get("label"),
                "merge_proposals": published.get("merge_proposals", []),
            }
            if published["schema_version"] != 3 or not arch or published.get("merge_proposals"):
                fail.append(f"published: {result['published']}")

            ex = browser.new_context()
            ex.add_init_script(SPEECH_JS)
            page = ex.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(explore_url(base, fid))
            page.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
            result["explore"] = explore(page, published, fail)
            result["silent_failures"] = reqs.silent()
            result["page_errors"] = errors
            if errors:
                fail.append(f"page errors: {errors[:3]}")
            browser.close()
    except Exception:
        print(json.dumps(result, indent=1))
        raise
    finally:
        for proc in procs:
            proc.terminate()
        shutil.rmtree(data, ignore_errors=True)
    print(json.dumps(result, indent=1))
    if fail:
        print("FAIL:\n- " + "\n- ".join(fail))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
