# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["playwright==1.63.0"]
# ///
"""Headless questions in Explore, end to end, in the installed Google Chrome, on the mock API:

  uv run apps/web/e2e/ask_e2e.py

Mock mode answers the heart from its live recordings (fixtures/recorded/replays.json), the
questions included (qa_ask_*, the question eval of Oct 30), so no request reaches the network.

1. /author: upload heart.png; press the aortic arch merge; Mark all parts checked; describe
   the left ventricle and the right atrium as the eval did. Publish. The published
   regions.json must equal fixtures/qa/heart_v3_regions.json, the version the answers were
   recorded on.
2. /explore: type "What does the left ventricle do?". The answer comes from the teacher's
   description, as recorded. Type "What does the right ventricle do?": the off-figure
   deflection that sends the student to the teacher.

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
    check_all,
    explore_url,
    free_port,
    start_by_keys,
    typed,
    wait_http,
)
from fix_e2e import enabled  # noqa: E402
from plan_e2e import MERGE  # noqa: E402

HEART = ROOT / "fixtures" / "heart.png"
V3 = json.loads((ROOT / "fixtures" / "qa" / "heart_v3_regions.json").read_text("utf-8"))
DESCRIPTIONS = {  # as the eval's version 3 has them
    "left ventricle": "The left ventricle pumps blood out to the whole body through the aortic arch.",
    "right atrium": "The right atrium collects blood coming back from the body.",
}
FROM_FIGURE = ("What does the left ventricle do?", "The left ventricle pumps blood out to the whole body through the aortic arch.")
OFF_FIGURE = ("What does the right ventricle do?", "This figure does not show that. Ask your teacher.")


def author(page: Page) -> None:
    page.get_by_role("button", name=MERGE).click()
    page.get_by_role("button", name="Edit aortic arch", exact=True).wait_for(timeout=180000)
    enabled(page, "Publish for students")
    check_all(page)
    for part, text in DESCRIPTIONS.items():
        page.get_by_role("button", name=f"Edit {part}", exact=True).click()
        page.get_by_label(f'Description of {part}, spoken on "more"').fill(text)
        page.get_by_role("button", name=f"Save description of {part}").click()
        page.get_by_role("button", name=f"Edit {part}", exact=True).wait_for(timeout=120000)
        enabled(page, "Publish for students")


def main() -> None:
    fail: list[str] = []
    api_port, web_port = free_port(), free_port()
    api, base = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    data = Path(tempfile.mkdtemp(prefix="tt-ask-e2e-"))
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
            author(page)
            page.get_by_role("button", name="Publish for students").click()
            page.get_by_role("link", name="Open version 1 in Explore").wait_for(timeout=60000)
            published = json.loads(urllib.request.urlopen(f"{api}/api/figures/{fid}/published/1/regions.json").read())
            result["published_equals_v3"] = published == V3
            if published != V3:
                fail.append("the published regions.json is not the version the answers were recorded on")

            ex = browser.new_context()
            ex.add_init_script(SPEECH_JS)
            explore = ex.new_page()
            explore.on("pageerror", lambda e: errors.append(str(e)))
            explore.goto(explore_url(base, fid))
            explore.wait_for_function("window.__tt && window.__tt.ready", timeout=30000)
            start_by_keys(explore)
            for name, (question, want) in (("from_figure", FROM_FIGURE), ("off_figure", OFF_FIGURE)):
                n = len(explore.evaluate("() => window.__tt.log"))
                typed(explore, question)
                explore.wait_for_function(
                    f"() => window.__tt.log.slice({n}).some((e) => e.kind === 'say')", timeout=30000
                )
                said = explore.evaluate(
                    f"() => window.__tt.log.slice({n}).filter((e) => e.kind === 'say').map((e) => e.text)"
                )
                result[name] = {"question": question, "said": said}
                if said[-1:] != [want]:
                    fail.append(f"{name}: said {said}, want {want!r}")
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
