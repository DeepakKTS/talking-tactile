# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools==4.60.1", "brotli==1.1.0", "uharfbuzz==0.51.1", "pyyaml==6.0.3", "playwright==1.63.0"]
# ///
"""The Talking Tactile logo, made from braille, not drawn by hand:

  uv run apps/web/scripts/brand_logo.py

1. "tt" goes through lou_translate with the table the sheets use (config/tactile_rules.yaml
   braille.display and braille.table). The raised dots of each cell come from its Unicode
   code point, so the mark is exactly what liblouis prints: two cells, dots 2-3-4-5.
2. The dots are laid out in braille's own proportions: the dot pitch in a cell and the cell
   pitch are the low ends of the configured ranges (2.3 mm and 6.1 mm).
3. The wordmark "Talking Tactile" is set in the self-hosted Literata (wght 480, opsz 36),
   shaped with HarfBuzz, and outlined into SVG paths, so the logo needs no font to show.
4. The PNG icons are rendered from favicon.svg in headless Chrome.

Writes apps/web/public/brand/: logo.svg, logo-mark.svg, favicon.svg, favicon-32.png and
apple-touch-icon.png. services/api/tests/test_brand_logo.py checks the mark against liblouis.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import uharfbuzz as hb
import yaml
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "apps" / "web" / "public" / "brand"
FONT = ROOT / "apps" / "web" / "public" / "fonts" / "literata-latin-opsz-normal.woff2"
RULES = ROOT / "config" / "tactile_rules.yaml"

LIGHT, DARK = "#6B5627", "#C9B27C"  # --accent in tokens.css, light and dark
TILE = "#17140C"  # --accent-ink (dark): the favicon's tile
WORDMARK = "Talking Tactile"
AXES = {"wght": 480, "opsz": 36}

U = 10.0  # one dot pitch, in SVG units
R = 3.6  # dot radius: 1.5 mm dots at a 2.3 mm pitch, a little fuller for a logo
PAD = 6.0


def braille(text: str) -> str:
    b = yaml.safe_load(RULES.read_text())["braille"]
    exe = shutil.which("lou_translate")
    if exe is None:
        sys.exit("lou_translate was not found. Install liblouis: brew install liblouis")
    out = subprocess.run([exe, "--forward", f"{b['display']},{b['table']}"], input=text + "\n",
                         capture_output=True, text=True, check=True).stdout
    return out.rstrip("\n")


def dots(cell: str) -> set[int]:
    bits = ord(cell) - 0x2800
    if not 0 <= bits < 0x40:
        sys.exit(f"{cell!r} is not a six-dot braille cell")
    return {d for d in range(1, 7) if bits & (1 << (d - 1))}


def cell_pitch() -> float:
    b = yaml.safe_load(RULES.read_text())["braille"]
    return U * b["cell_to_cell_mm"][0] / b["dot_to_dot_mm"][0]


def mark(cells: str, x0: float, y0: float, scale: float = 1.0, faint: str = "tt-off") -> tuple[list[str], float, float]:
    """Circles for the cells: raised dots class tt-on, the others class tt-off (class names unique enough
    to survive being inlined in a page). Dot n sits in column
    (n - 1) // 3 and row (n - 1) % 3, as braille numbers them."""
    out = []
    pitch = cell_pitch()
    for i, cell in enumerate(cells):
        raised = dots(cell)
        for d in range(1, 7):
            col, row = (d - 1) // 3, (d - 1) % 3
            cx = x0 + (i * pitch + col * U) * scale
            cy = y0 + row * U * scale
            out.append(f'<circle class="{"tt-on" if d in raised else faint}" cx="{cx:.2f}" cy="{cy:.2f}" r="{R * scale:.2f}"/>')
    width = ((len(cells) - 1) * pitch + U) * scale
    return out, width, 2 * U * scale


def style(faint_opacity: float) -> str:
    return (f"<style>.tt-on{{fill:{LIGHT}}}.tt-off{{fill:{LIGHT};opacity:{faint_opacity}}}"
            f"@media (prefers-color-scheme:dark){{.tt-on,.tt-off{{fill:{DARK}}}}}</style>")


def wordmark(size: float, x0: float, baseline: float) -> tuple[str, float]:
    tt = TTFont(FONT)
    buf = io.BytesIO()
    tt.flavor = None
    tt.save(buf)
    face = hb.Face(buf.getvalue())
    font = hb.Font(face)
    font.set_variations(AXES)
    upem = face.upem
    b = hb.Buffer()
    b.add_str(WORDMARK)
    b.guess_segment_properties()
    hb.shape(font, b, {"kern": True, "liga": True})
    k = size / upem
    x = 0.0
    paths = []
    for info, pos in zip(b.glyph_infos, b.glyph_positions, strict=True):
        pen = SVGPathPen(None)
        gx = x0 + (x + pos.x_offset) * k
        font.draw_glyph_with_pen(info.codepoint, TransformPen(pen, (k, 0, 0, -k, gx, baseline - pos.y_offset * k)))
        d = pen.getCommands()
        if d:
            paths.append(d)
        x += pos.x_advance
    return " ".join(paths), x * k


def cap_height() -> float:
    tt = TTFont(FONT)
    return tt["OS/2"].sCapHeight / tt["head"].unitsPerEm


def descender() -> float:
    """The font's descender as a fraction of the em, negative."""
    tt = TTFont(FONT)
    return tt["OS/2"].sTypoDescender / tt["head"].unitsPerEm


def svg(width: float, height: float, body: list[str], title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
            f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{title}">'
            f"<title>{title}</title>" + "".join(body) + "</svg>\n")


def main() -> None:
    cells = braille("tt")
    if len(cells) != 2 or any(dots(c) != {2, 3, 4, 5} for c in cells):
        sys.exit(f"liblouis gave {cells!r} for tt, not two cells of dots 2-3-4-5")
    OUT.mkdir(parents=True, exist_ok=True)

    circles, mw, mh = mark(cells, PAD, PAD)
    w, h = mw + 2 * PAD, mh + 2 * PAD
    (OUT / "logo-mark.svg").write_text(svg(w, h, [style(0.3), *circles], "Talking Tactile: braille tt"))

    # The wordmark: its cap height matches the mark's dot span, centered on the middle row.
    size = (mh + 2 * R) / cap_height()
    gap = 2.2 * U
    baseline = PAD + mh / 2 + cap_height() * size / 2
    d, tw = wordmark(size, w - PAD + gap, baseline)
    word = f'<path class="tt-on" d="{d}"/>'
    low = baseline - descender() * size + PAD / 2  # room for the g's descender
    (OUT / "logo.svg").write_text(svg(w - PAD + gap + tw + PAD, max(h, low), [style(0.3), *circles, word], "Talking Tactile"))

    # The favicon: the raised dots only, on a dark tile, readable on a light or dark tab bar.
    side = 64.0
    scale = 0.9 * side / (mw + 2 * R) * 0.92
    fw, fh = mw * scale, mh * scale
    fc, _, _ = mark(cells, (side - fw) / 2, (side - fh) / 2, scale, faint="tt-off")
    tile = f'<rect width="{side:.0f}" height="{side:.0f}" rx="14" fill="{TILE}"/>'
    fav = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side:.0f} {side:.0f}" width="{side:.0f}" '
           f'height="{side:.0f}" role="img" aria-label="Talking Tactile"><title>Talking Tactile</title>'
           f"<style>.tt-on{{fill:{DARK}}}.tt-off{{fill:{DARK};opacity:.18}}</style>{tile}{''.join(fc)}</svg>\n")
    (OUT / "favicon.svg").write_text(fav)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for name, px in (("favicon-32.png", 32), ("apple-touch-icon.png", 180)):
            page = browser.new_page(viewport={"width": px, "height": px}, device_scale_factor=1)
            body = fav.replace(f'width="{side:.0f}" height="{side:.0f}" role', f'width="{px}" height="{px}" role', 1)
            page.set_content(f"<html><body style='margin:0;background:transparent'>{body}</body></html>")
            page.screenshot(path=str(OUT / name), omit_background=True,
                            clip={"x": 0, "y": 0, "width": px, "height": px})
            page.close()
        browser.close()
    print(f"tt -> {cells} (dots 2-3-4-5 each); wrote {', '.join(sorted(f.name for f in OUT.iterdir()))}")


if __name__ == "__main__":
    main()
