"""Tests for the project website in site/. Run: python3 -m unittest -v scripts/test_site.py

The site is static: plain HTML, one stylesheet and three scripts in site/assets/, the two
published sheets in site/sheets/. These checks keep it honest and self-contained:
- the shared design tokens are the app's, byte for byte (once the app has them);
- every internal link, anchor and asset resolves;
- nothing is requested from another host (scripts, styles, fonts, images);
- every page carries the CSP meta tag, and no page has inline script or style;
- no em or en dash in any text;
- the sheets are the committed regions files, and the page text agrees with them,
  with ATTRIBUTION.md's credit lines, with the README's results and with explore.yaml.
"""

from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
APP_TOKENS = REPO / "apps" / "web" / "src" / "styles" / "tokens.css"
SITE_TOKENS = SITE / "assets" / "tokens.css"
PLACEHOLDERS = {"<VIDEO_URL>"}  # filled in by the owner; grep -rn "<VIDEO_URL>" site
SHEETS = {"heart": "fixtures/qa/heart_v4_regions.json", "brain": "fixtures/qa/brain_lobes_v4_regions.json"}
CREDITS = {"heart": "fixtures/heart.png", "brain": "fixtures/eval/brain_lobes.png"}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str, str]] = []  # (tag, attribute, value)
        self.ids: set[str] = set()
        self.metas: list[dict[str, str]] = []
        self.inline_scripts = 0
        self.style_tags = 0
        self.style_attrs: list[str] = []
        self.stylesheets: list[str] = []
        self.text: list[str] = []
        self._tag: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        self._tag.append(tag)
        if "id" in a:
            self.ids.add(a["id"])
        if "style" in a:
            self.style_attrs.append(tag)
        if tag == "meta":
            self.metas.append(a)
        if tag == "style":
            self.style_tags += 1
        if tag == "script" and "src" not in a:
            self.inline_scripts += 1
        if tag == "link" and "stylesheet" in a.get("rel", ""):
            self.stylesheets.append(a.get("href", ""))
        for attr in ("href", "src", "poster", "data-regions"):
            if attr in a:
                self.refs.append((tag, attr, a[attr]))
        if "srcset" in a:
            for part in a["srcset"].split(","):
                self.refs.append((tag, "srcset", part.strip().split(" ")[0]))

    def handle_endtag(self, tag: str) -> None:
        if self._tag:
            self._tag.pop()

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parse(path: Path) -> Page:
    p = Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def pages() -> list[Path]:
    return sorted(SITE.glob("*.html"))


def external(url: str) -> bool:
    return url.startswith("//") or bool(urlsplit(url).scheme)


def css_urls(text: str) -> list[str]:
    urls = [m.group(2) for m in re.finditer(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", text)]
    urls += re.findall(r"@import\s+['\"]([^'\"]+)['\"]", text)
    return urls


class SiteTest(unittest.TestCase):
    def test_the_site_has_its_pages(self) -> None:
        names = {p.name for p in pages()}
        self.assertTrue({"index.html", "start.html", "project.html", "heart.html", "brain.html", "phone.html"} <= names, names)

    def test_tokens_match_the_app_byte_for_byte(self) -> None:
        if not APP_TOKENS.is_file():
            self.skipTest("apps/web/src/styles/tokens.css is not on this branch yet (it comes with ui-refresh); nothing to compare")
        self.assertTrue(SITE_TOKENS.is_file(), "site/assets/tokens.css is missing: copy apps/web/src/styles/tokens.css")
        self.assertEqual(SITE_TOKENS.read_bytes(), APP_TOKENS.read_bytes(), "site/assets/tokens.css differs from the app's")

    def test_every_internal_link_anchor_and_asset_resolves(self) -> None:
        parsed = {p.name: parse(p) for p in pages()}
        missing = []
        for name, page in parsed.items():
            for tag, attr, ref in page.refs:
                if ref in PLACEHOLDERS or external(ref) or ref.startswith(("mailto:", "tel:")):
                    continue
                parts = urlsplit(ref)
                target = (SITE / unquote(parts.path)).resolve() if parts.path else SITE / name
                if not target.is_file() or SITE.resolve() not in target.parents:
                    missing.append(f"{name}: <{tag} {attr}={ref!r}> has no file")
                    continue
                if parts.fragment:
                    ids = parsed[target.name].ids if target.suffix == ".html" and target.name in parsed else set()
                    if parts.fragment not in ids:
                        missing.append(f"{name}: {ref!r} has no element with that id")
        for css in SITE.rglob("*.css"):
            for ref in css_urls(css.read_text(encoding="utf-8")):
                if ref.startswith("data:") or ref.startswith("#") or external(ref):
                    continue
                if not (css.parent / unquote(urlsplit(ref).path)).is_file():
                    missing.append(f"{css.relative_to(SITE)}: url({ref}) has no file")
        self.assertEqual(missing, [])

    def test_no_request_to_another_host(self) -> None:
        bad = []
        for path in pages():
            page = parse(path)
            for tag, attr, ref in page.refs:
                if tag == "a" or ref in PLACEHOLDERS:
                    continue  # a link the reader follows is not a request the page makes
                if external(ref):
                    bad.append(f"{path.name}: <{tag} {attr}={ref}>")
        for css in SITE.rglob("*.css"):
            bad += [f"{css.name}: {u}" for u in css_urls(css.read_text(encoding="utf-8")) if external(u)]
        for js in SITE.rglob("*.js"):
            text = js.read_text(encoding="utf-8")
            bad += [f"{js.name}: {u}" for u in re.findall(r"""["'`](https?://[^"'`]+)["'`]""", text) if "www.w3.org/2000/svg" not in u]
            if re.search(r"\b(importScripts|new\s+Worker|WebSocket|EventSource|sendBeacon)\b", text):
                bad.append(f"{js.name}: opens a connection of its own")
        self.assertEqual(bad, [])

    def test_every_page_has_the_csp_meta_and_no_inline_script_or_style(self) -> None:
        for path in pages():
            page = parse(path)
            with self.subTest(page=path.name):
                csp = [m.get("content", "") for m in page.metas if m.get("http-equiv", "").lower() == "content-security-policy"]
                self.assertEqual(len(csp), 1, "one CSP meta tag")
                rules = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in csp[0].split(";")) if d}
                self.assertEqual(rules.get("default-src"), ["'none'"])
                for kind in ("script-src", "style-src", "font-src", "img-src", "media-src", "connect-src"):
                    self.assertEqual(rules.get(kind), ["'self'"], kind)
                self.assertEqual(page.inline_scripts, 0, "inline script")
                self.assertEqual(page.style_tags, 0, "style element")
                self.assertEqual(page.style_attrs, [], "style attribute")

    def test_no_em_or_en_dash(self) -> None:
        found = []
        for path in sorted(SITE.rglob("*")):
            if path.suffix in {".html", ".css", ".js", ".svg", ".json"}:
                for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if "—" in line or "–" in line:
                        found.append(f"{path.relative_to(SITE)}:{n}")
        self.assertEqual(found, [])

    def test_the_sheets_are_the_committed_published_files(self) -> None:
        for slug, fixture in SHEETS.items():
            with self.subTest(sheet=slug):
                d = SITE / "sheets" / slug
                self.assertEqual((d / "regions.json").read_bytes(), (REPO / fixture).read_bytes())
                regions = json.loads((d / "regions.json").read_text())
                svg = (d / "tactile.svg").read_text()
                page = regions["page"]
                # One SVG unit is one page millimeter, which the demo's overlay relies on.
                self.assertIn(f'viewBox="0 0 {page["width_mm"]} {page["height_mm"]}"', svg)
                self.assertTrue((d / "print.pdf").read_bytes().startswith(b"%PDF"))

    def test_each_sheet_page_lists_its_parts_and_credits_the_figure(self) -> None:
        attribution = (REPO / "ATTRIBUTION.md").read_text()
        for slug, fixture in SHEETS.items():
            with self.subTest(sheet=slug):
                html = (SITE / f"{slug}.html").read_text()
                regions = json.loads((REPO / fixture).read_text())
                touch = [r["id"] for r in regions["regions"] if r["touchable"]]
                self.assertEqual(re.findall(r'data-say="([^"]+)"', html), touch)
                for r in regions["regions"]:
                    if not r["touchable"]:
                        self.assertIn(f'data-part="{r["id"]}"', html)
                for item in regions.get("needs_teacher", []):
                    self.assertIn(f'data-needs="{item["id"]}"', html)
                for line in regions.get("lines") or []:
                    self.assertIn(f'data-line="{line["id"]}"', html)
                self.assertIn(f'data-regions="sheets/{slug}/regions.json"', html)
                section = attribution.split(f"## {CREDITS[slug]}\n", 1)[1].split("\n## ", 1)[0]
                credit = re.search(r'Credit line: "(.+?)"\n', section).group(1)  # type: ignore[union-attr]
                self.assertIn(f"<q>{credit}</q>", html.replace("&#x27;", "'"))

    def test_the_results_on_the_landing_page_are_the_readmes(self) -> None:
        readme = (REPO / "README.md").read_text()
        table = readme.split("## Results", 1)[1].split("\n## ", 1)[0]
        index = (SITE / "index.html").read_text()
        rows = [r for r in table.splitlines() if r.startswith("| ") and not r.startswith("| What") and "---" not in r]
        self.assertGreater(len(rows), 5)
        for row in rows:
            what, result, files = (c.strip() for c in row.strip("|").split("|"))
            with self.subTest(row=what):
                self.assertIn(what, index)
                if "tt:" in result:
                    marker = re.search(r"<!-- (tt:[a-z-]+) -->", result).group(1)  # type: ignore[union-attr]
                    self.assertIn(f"<!-- {marker} -->", index, "keep make results' marker")
                else:
                    self.assertIn(result, index)
                for file in re.findall(r"`([^`]+)`", files):
                    self.assertIn(file, index)
                    self.assertTrue((REPO / file.rstrip("/")).exists(), file)

    def test_every_make_target_the_site_names_exists(self) -> None:
        makefile = (REPO / "Makefile").read_text()
        targets = set(re.findall(r"^([a-z][a-z-]*):", makefile, re.M))
        named = {t for p in pages() for t in re.findall(r"(?:<code>|\n)(?:[A-Z_]+=\S+ )*make ([a-z][a-z-]*)", p.read_text())}
        self.assertTrue(named, "the site names make targets")
        waiting = {"demo-sheets"} - targets  # comes to main with services/api/app/demo_sheets.py
        self.assertEqual(sorted(named - targets - waiting), [])
        if waiting & named:
            self.skipTest(f"make {', '.join(sorted(waiting & named))} is not in this branch's Makefile yet: merge main before publishing")

    def test_the_demo_uses_explore_yaml_numbers(self) -> None:
        yaml = (REPO / "config" / "explore.yaml").read_text()
        js = (SITE / "assets" / "sheet.js").read_text()
        for key in ("enter_shrink_mm", "exit_grow_mm", "enter_hold_ms", "exit_hold_ms", "speed_below_mm_s", "hold_ms",
                    "speed_window_ms", "default_hz", "tone_ms", "gain", "exit_tick_hz", "exit_tick_ms", "exit_tick_gain"):
            with self.subTest(key=key):
                want = float(re.search(rf"^\s+{key}:\s*([0-9.]+)", yaml, re.M).group(1))  # type: ignore[union-attr]
                got = float(re.search(rf"^\s+{key}:\s*([0-9.]+),", js, re.M).group(1))  # type: ignore[union-attr]
                self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
