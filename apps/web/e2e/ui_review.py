# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Screenshots and axe-core checks of every app screen, for the UI review:

  uv run apps/web/e2e/ui_review.py [--no-shots]

Starts the API in mock mode on a temporary data dir (port 18400) and Vite on 15400, then in
Chromium (the installed Chrome) and WebKit, light and dark, at 390x844 and 1440x900:

  upload        /author, the upload card
  upload-error  /author after uploading a text file: S0's real refusal
  progress      a real job's running status, the one with the most stages done, held there
                (the page's status requests get that recorded answer, so the shot holds still)
  review        the synthetic figure's review, no part checked
  fix           Fix outline of stem, before any point
  publish       after Mark all parts checked and Publish for students
  explore       /explore, started in script mode (no camera), the Ask box and settings
  device-check  /explore?check=1 before Check is pressed

Saves docs/review/ui/app-<screen>-<theme>-<width>x<height>-<browser>.png and runs axe-core
4.10.3 (WCAG 2.0 to 2.2 A and AA rules, plus best practices) on each screen. axe is fetched
once from jsDelivr into the git-ignored data/ui-review/, checked against its sha256, and
injected by the test (the contexts bypass the page's CSP for that); the app never loads it. Prints every finding as
JSON; exits non-zero if any is serious or critical.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps" / "web"
API = ROOT / "services" / "api"
FIGURE = ROOT / "fixtures" / "synthetic" / "figure.png"
OUT = Path(os.environ.get("TT_UI_OUT", ROOT / "docs" / "review" / "ui"))  # TT_UI_OUT: a trial run elsewhere
API_PORT, WEB_PORT = 18400, 15400
BASE = f"http://127.0.0.1:{WEB_PORT}"
SIZES = [(390, 844), (1440, 900)]
THEMES = ["light", "dark"]
BROWSERS = ["chromium", "webkit"]
AXE_URL = "https://cdn.jsdelivr.net/npm/axe-core@4.10.3/axe.min.js"
AXE_SHA256 = "880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb"
UA = "talking-tactile (https://github.com/DeepakKTS/talking-tactile)"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]


def wait_http(url: str, timeout: float = 90) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"{url} did not answer")


def wait_js(page: Page, expression: str, timeout: float = 60000) -> None:
    end = time.monotonic() + timeout / 1000
    while not page.evaluate(f"() => !!({expression})"):
        if time.monotonic() > end:
            raise TimeoutError(expression)
        page.wait_for_timeout(50)


def axe_source() -> str:
    path = ROOT / "data" / "ui-review" / "axe.min.js"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(AXE_URL, headers={"User-Agent": UA})
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != AXE_SHA256:
        sys.exit(f"{path} is not axe-core 4.10.3")
    return data.decode()


def upload(page: Page, path: Path) -> None:
    page.goto(f"{BASE}/author")
    page.get_by_label("Figure (PNG, JPEG or a PDF page)").set_input_files(str(path))
    page.get_by_role("button", name="Make a tactile sheet").click()


def setup(browser: Any) -> tuple[str, dict[str, Any]]:
    """Uploads the synthetic figure once and records a real status answer from mid-run."""
    ctx = browser.new_context()
    page = ctx.new_page()
    seen: list[dict[str, Any]] = []

    def keep(route: Route) -> None:
        r = route.fetch()
        body = r.json()
        if isinstance(body, dict) and body.get("job", {}).get("status") == "running":
            seen.append(body)
        route.fulfill(response=r)

    page.route("**/api/figures/*", lambda route: keep(route) if route.request.method == "GET" else route.continue_())
    upload(page, FIGURE)
    page.get_by_role("list", name="Parts").wait_for(timeout=180000)
    fid = page.url.split("figure=")[1]
    ctx.close()
    # The answer with the most stages done that is still running: a real mid-run state.
    mid = max(seen, key=lambda b: len(b["job"]["stages"])) if seen else None
    if mid is None:
        sys.exit("no running status was seen; the mock pipeline finished between two polls")
    return fid, mid


def shoot(page: Page, name: str, theme: str, size: tuple[int, int], engine: str, shots: bool,
          findings: list[dict[str, Any]], axe: str, runs: list[dict[str, Any]]) -> None:
    page.wait_for_timeout(400)  # fonts and images settle
    if shots:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT / f"app-{name}-{theme}-{size[0]}x{size[1]}-{engine}.png"), full_page=True)
    page.evaluate(axe)
    result = page.evaluate("(tags) => axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations', 'incomplete'] })", TAGS)
    # "incomplete" is what axe could not decide alone, such as text over a gradient: listed
    # for a person to check (docs/DESIGN.md computes those pairs).
    runs.append({"screen": name, "theme": theme, "size": f"{size[0]}x{size[1]}", "browser": engine,
                 "passes": len(result["passes"]), "violations": len(result["violations"]),
                 "incomplete": sorted({i["id"] for i in result["incomplete"]})})
    for v in result["violations"]:
        findings.append({
            "screen": name, "theme": theme, "size": f"{size[0]}x{size[1]}", "browser": engine,
            "id": v["id"], "impact": v["impact"], "help": v["help"],
            "nodes": [n["target"] for n in v["nodes"]][:6],
        })


def main() -> None:
    shots = "--no-shots" not in sys.argv
    data = Path(tempfile.mkdtemp(prefix="tt-ui-"))
    bad = data / "notes.txt"
    bad.write_text("Not a figure.\n")
    env = {**os.environ, "MOCK_META": "1", "TT_API": f"http://127.0.0.1:{API_PORT}"}
    env.pop("LIVE", None)
    launch = (
        "import sys, uvicorn; from pathlib import Path; from app.main import create_app; "
        "uvicorn.run(create_app(data_dir=Path(sys.argv[1])), host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')"
    )
    procs = [subprocess.Popen(["uv", "run", "python", "-c", launch, str(data), str(API_PORT)], cwd=API, env=env)]
    findings: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    try:
        procs.append(subprocess.Popen(["npx", "vite", "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"],
                                      cwd=WEB, env=env, stdout=subprocess.DEVNULL))
        wait_http(f"http://127.0.0.1:{API_PORT}/api/health")
        wait_http(BASE)
        axe = axe_source()
        with sync_playwright() as p:
            engines = {"chromium": p.chromium.launch(channel="chrome"), "webkit": p.webkit.launch()}
            fid, mid = setup(engines["chromium"])
            mid = {**mid, "figure_id": fid}
            published = False
            # Screen by screen, so the review is shot before any part is checked.
            for screen in ["upload", "upload-error", "progress", "review", "fix", "publish", "explore", "device-check"]:
                for engine in BROWSERS:
                    for theme in THEMES:
                        for size in SIZES:
                            ctx = engines[engine].new_context(viewport={"width": size[0], "height": size[1]},
                                                              color_scheme=theme, bypass_csp=True)
                            page = ctx.new_page()
                            if screen == "upload":
                                page.goto(f"{BASE}/author")
                                page.get_by_role("button", name="Make a tactile sheet").wait_for()
                            elif screen == "upload-error":
                                upload(page, bad)
                                page.get_by_role("alert").wait_for()
                            elif screen == "progress":
                                page.route(f"**/api/figures/{fid}", lambda route: route.fulfill(json=mid))
                                page.goto(f"{BASE}/author?figure={fid}")
                                page.locator(".step[data-state=active]").wait_for()
                            elif screen == "review":
                                page.goto(f"{BASE}/author?figure={fid}")
                                page.get_by_role("list", name="Parts").wait_for(timeout=60000)
                            elif screen == "fix":
                                page.goto(f"{BASE}/author?figure={fid}")
                                page.get_by_role("list", name="Parts").get_by_role("button", name="Fix outline of stem").click()
                                page.get_by_role("region", name="Fix outline of stem").get_by_text(
                                    "Click inside stem to add a point.").wait_for(timeout=60000)
                            elif screen == "publish":
                                page.goto(f"{BASE}/author?figure={fid}")
                                page.get_by_role("list", name="Parts").wait_for(timeout=60000)
                                if not published:
                                    page.get_by_role("button", name="Mark all parts checked").click()
                                    page.get_by_role("button", name=re.compile(r"^Yes, mark all \d+ checked$")).click()
                                    page.get_by_text("Every part is checked.").wait_for(timeout=120000)
                                    published = True
                                publish = page.get_by_role("button", name="Publish for students")
                                wait_js(page, "[...document.querySelectorAll('button')].some((b) => b.textContent === 'Publish for students' && !b.disabled)")
                                publish.click()
                                page.get_by_role("link", name="Open version 1 in Explore").wait_for(timeout=60000)
                            elif screen == "explore":
                                page.goto(f"{BASE}/explore?figure={fid}&version=1&source=script")
                                wait_js(page, "window.__tt && window.__tt.ready", timeout=30000)
                                page.get_by_role("button", name="Start exploring").click()
                                wait_js(page, "window.__tt.started", timeout=10000)
                                page.wait_for_timeout(600)
                            else:
                                page.goto(f"{BASE}/explore?check=1")
                                page.get_by_role("button", name="Check this device").wait_for()
                            shoot(page, screen, theme, size, engine, shots, findings, axe, runs)
                            ctx.close()
            for b in engines.values():
                b.close()
    finally:
        for proc in procs:
            proc.terminate()
    serious = [f for f in findings if f["impact"] in ("serious", "critical")]
    incomplete = sorted({i for r in runs for i in r["incomplete"]})
    print(json.dumps({"runs": len(runs), "rules_passed_min": min(r["passes"] for r in runs), "incomplete": incomplete,
                      "findings": findings, "serious_or_critical": len(serious)}, indent=1))
    sys.exit(1 if serious else 0)


if __name__ == "__main__":
    main()
