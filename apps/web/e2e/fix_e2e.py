# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless Fix outline run, end to end, in the installed Google Chrome, on the mock API:

  uv run apps/web/e2e/fix_e2e.py

Mock mode answers the heart from the live recordings of Oct 30 (fixtures/recorded/
replays.json), Fix outline clicks included, so no request reaches the network.

1. /author: upload heart.png. With S1's plan the aorta is touchable (its branches share its
   region), and the septum is the one part that needs the teacher (a spill suggestion).
2. Fix outline of aorta, from its row: click the two points of the live check, (1020, 340)
   and (980, 520) in figure pixels, on the preview. Each click is answered from its
   recording; the branches are no spill, as they share the aorta's region. Accept.
3. The branches are merged into the aorta by the Edit form, as a teacher would. Publish.
4. The published regions.json: version 3, the aorta touchable and set by the teacher.
5. /explore, script mode: the intro names the septum only, and touching the aorta gives its
   earcon, then "Aorta".

Prints what it saw as JSON and exits non-zero if a check fails."""

from __future__ import annotations

import json
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
    explore_url,
    free_port,
    log_since,
    start_by_keys,
    touch_all,
    wait_http,
)

HEART = ROOT / "fixtures" / "heart.png"
CLICKS = [(1020, 340), (980, 520)]  # the live check's aorta points, figure pixels
BRANCHES = ["brachiocephalic artery", "left common carotid artery", "left subclavian artery"]


def enabled(page: Page, name: str) -> None:
    page.wait_for_function(
        "(n) => [...document.querySelectorAll('button')].some((b) => b.textContent === n && !b.disabled)",
        arg=name,
        timeout=120000,
    )


def fix_aorta(page: Page, fail: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flagged = page.get_by_role("list", name="Needs you")
    out["not_touchable"] = flagged.locator("strong").all_text_contents()
    if out["not_touchable"] != ["septum"]:
        fail.append(f"not touchable at the start: {out['not_touchable']}")
    page.get_by_role("list", name="Parts").get_by_role("button", name="Fix outline of aorta").first.click()
    panel = page.get_by_role("region", name="Fix outline of aorta")
    status = panel.get_by_role("status")
    status.get_by_text("Click inside aorta to add a point.").wait_for(timeout=60000)
    img = panel.get_by_role("img")
    width, height = 2048, 1612  # the normalized heart
    out["answers"] = []
    for x, y in CLICKS:
        # A click lands on a whole CSS pixel. The recorded answers are for these exact points,
        # so the preview is shown at one CSS pixel per figure pixel, at the page's top left,
        # and a real mouse click at (x, y) maps back to exactly (x, y).
        img.evaluate(
            "(el, w) => Object.assign(el.style, { position: 'fixed', left: '0px', top: '0px', "
            "width: w + 'px', maxWidth: 'none', zIndex: '9999' })",
            width,
        )
        before = status.text_content()
        page.mouse.click(x, y)
        page.wait_for_function(
            "([el, before]) => el.textContent !== before && !el.textContent.startsWith('Asking')",
            arg=[status.element_handle(), before],
            timeout=120000,
        )
        out["answers"].append(status.text_content())
    out["points_shown"] = panel.get_by_text("Positive points:").text_content()
    out["spill_warnings"] = panel.get_by_role("alert").count()
    want = "(1020, 340), (980, 520)"
    if want not in (out["points_shown"] or "") or out["spill_warnings"]:
        fail.append(f"fix panel: {out['points_shown']} / {out['spill_warnings']} spill warning(s)")
    if not all((a or "").startswith("SAM answered in") and " of 30." in (a or "") for a in out["answers"]):
        fail.append(f"fix answers: {out['answers']}")
    img.evaluate("(el) => el.removeAttribute('style')")  # back in the panel, off the buttons
    panel.get_by_role("button", name="Accept the outline of aorta").click()
    panel.wait_for(state="detached", timeout=120000)
    enabled(page, "Publish for students")
    out["rule_problems"] = page.get_by_role("list", name="Rule problems").locator("li").all_text_contents()
    return out


def merge_branches(page: Page) -> None:
    for branch in BRANCHES:
        page.get_by_role("button", name=f"Edit {branch}", exact=True).click()
        page.get_by_label(f"Merge {branch} into").select_option(label="aorta")
        page.get_by_role("button", name=f"Merge {branch}", exact=True).click()
        page.get_by_role("button", name=f"Edit {branch}", exact=True).wait_for(state="detached", timeout=120000)
        enabled(page, "Publish for students")


def main() -> None:
    fail: list[str] = []
    api_port, web_port = free_port(), free_port()
    api, base = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    data = Path(tempfile.mkdtemp(prefix="tt-fix-e2e-"))
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
            ctx = browser.new_context(viewport={"width": 2100, "height": 1700})
            reqs = Requests(ctx, "author")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            sent: list[Any] = []
            page.on("request", lambda r: r.url.endswith("/fix") and sent.append(r.post_data))
            result["fix_requests"] = sent
            page.goto(f"{base}/author")
            page.get_by_label("Figure (PNG, JPEG or a PDF page)").set_input_files(str(HEART))
            page.get_by_role("button", name="Make a tactile sheet").click()
            page.get_by_role("list", name="Parts").wait_for(timeout=180000)
            fid = page.url.split("figure=")[1]
            result["author"] = fix_aorta(page, fail)
            merge_branches(page)
            result["rules_after_merges"] = page.get_by_text("All tactile rules pass.").count() == 1
            page.get_by_role("button", name="Publish for students").click()
            page.get_by_role("link", name="Open version 1 in Explore").wait_for(timeout=60000)
            published = json.loads(urllib.request.urlopen(f"{api}/api/figures/{fid}/published/1/regions.json").read())
            aorta = [r for r in published["regions"] if r["label"] == "aorta"]
            result["published"] = {
                "schema_version": published["schema_version"],
                "aorta": [(r["id"], r["touchable"], r["source"]) for r in aorta],
                "untouchable": [r["label"] for r in published["regions"] if not r["touchable"]],
                "needs_teacher": published.get("needs_teacher", []),
            }
            if published["schema_version"] != 3 or not aorta or not all(r["touchable"] and r["source"] == "teacher" for r in aorta):
                fail.append(f"published aorta: {result['published']}")

            ex = browser.new_context()
            ex.add_init_script(SPEECH_JS)
            explore = ex.new_page()
            explore.on("pageerror", lambda e: errors.append(str(e)))
            explore.goto(explore_url(base, fid))
            explore.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
            start_by_keys(explore)
            intro = [e.get("text", "") for e in log_since(explore, 0) if e["kind"] == "say"]
            result["explore_intro"] = intro[:1]
            if not intro or " One part is not touchable yet: septum. " not in intro[0]:
                fail.append(f"the intro does not name the septum alone: {intro[:1]}")
            result["aorta_touched"] = touch_all(explore, aorta[:1], 1, fail, "explore") == 1
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
