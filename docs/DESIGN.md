# Design

The look of Author and Explore, and how it stays accessible. The source of truth for the look
is the landing page (`talking-tactile.html`, not in this repository); the source of truth for
the values is `apps/web/src/styles/tokens.css`.

## Files

| File | What it is |
|---|---|
| `apps/web/src/styles/tokens.css` | The one token file: colors, glass, radii, fonts, both themes, @font-face. Self-contained, so the project website copies it byte for byte. Needs the fonts at `/fonts/` |
| `apps/web/src/styles/app.css` | The app's styles, written only against the tokens |
| `apps/web/public/fonts/` | Literata and Atkinson Hyperlegible Next, Latin, variable, woff2, with their OFL texts. See ATTRIBUTION.md |
| `apps/web/public/brand/` | logo.svg (mark and wordmark), logo-mark.svg (the two cells), favicon.svg, favicon-32.png, apple-touch-icon.png |
| `apps/web/scripts/brand_logo.py` | Makes the brand files: `uv run apps/web/scripts/brand_logo.py` |
| `apps/web/scripts/contrast.ts` | Prints the contrast table below from tokens.css: `cd apps/web && node scripts/contrast.ts` |
| `apps/web/e2e/ui_review.py` | Screenshots of every screen and the axe-core check: `uv run apps/web/e2e/ui_review.py` |

## Themes

Light (paper) by default, dark when the system asks for it (`prefers-color-scheme: dark`).
There is no switch in the app; `data-theme="light"` or `"dark"` on `<html>` pins one, which
the website uses. Both themes keep the landing page's values: dark `--bg #000000`,
`--text #ECE4CF`, `--accent #C9B27C`, `--accent-ink #17140C`, focus `#E8D7A6`; light
`--bg #E7E1D1`, `--text #1B1912`, `--accent #6B5627`, focus `#2F5D8A`. The app adds
`--surface` (the glass composited over the background, the solid fill), `--field-edge`, and
four status colors (`--ok`, `--warn`, `--danger`, `--info`).

Fonts: Literata for headings, Atkinson Hyperlegible Next for text. Both are served by the app
(font-src 'self' in the CSP was already there; no change to the policy). Nothing is fetched
from Google Fonts or any other host, so Explore's offline claim holds.

Radii: item 14 px, panel 24 px, slab 30 px, pill 999 px.

Glass: the landing page's fill gradient (`--glass-fill-2` to `--glass-fill`), edge, rim and
sheen, and its shadow. The app does not use `backdrop-filter`: its background is flat, so the
blur would show nothing; on a phone it costs frames the camera loop needs; and it would make a
glass panel the containing block of anything fixed inside it.

## Logo

Braille "tt" as the sheets print it: `lou_translate` with `unicode.dis,en-ueb-g2.ctb` (the
table in `config/tactile_rules.yaml`) gives `⠞⠞`, two cells of dots 2-3-4-5. The generator
reads the dots from the code points, so the mark is liblouis's answer, not a drawing of it.
Dot pitch and cell pitch are the low ends of the configured ranges (2.3 mm and 6.1 mm); the
dots are a little fuller than 1.5 mm, for a logo. Raised dots are solid brass, the two flat
dots of each cell faint, as on the landing page. `services/api/tests/test_brand_logo.py`
checks that each SVG raises exactly the dots liblouis prints.

The wordmark "Talking Tactile" is Literata (weight 480, optical size 36), shaped with
HarfBuzz and outlined into paths: the logo shows the same with no font loaded, in an `<img>`,
in a README, or on another site. The SVGs follow `prefers-color-scheme` (brass #6B5627 on
paper, #C9B27C at night). The favicon is the raised dots only, on a dark tile, so it reads
on a light or a dark tab bar; the PNGs (32 px and 180 px for iOS) are rendered from it.

## Accessibility

- Contrast: every text and background pair below meets WCAG AA in both themes, glass
  included. Computed, not eyeballed; the method is under the table, and
  `apps/web/scripts/contrast.test.ts` fails the build if a pair drops below its minimum.
- Focus: a 3 px ring in `--focus` on every control (`:focus-visible`), 3 px off the element.
  The hidden file input draws its ring on the Browse label.
- Targets: every button, field and select is at least 44 px tall; Explore's are 56 px, and
  Start is 72 px.
- No information by color alone: a checked part says "Checked" and an unchecked one "Not
  checked" beside its colored edge; a step in the progress has words ("Done in 40 ms",
  "Working", "Waiting") and a different shape (filled check, spinner, empty ring, cross); a
  pressed toggle shows a check mark; device check rows have a check, a triangle or a cross
  beside OK, Look at this, Not working.
- Reduced motion: `prefers-reduced-motion` stops the spinner and every transition.
- Reduced transparency: `prefers-reduced-transparency` paints the glass with `--surface`,
  a solid fill, and drops the sheen.
- Unchanged: every spoken sentence, ids, roles and labels the tests use, the camera view and
  its overlay, and every timing.

## Contrast

Measured on Nov 3 from tokens.css by `node scripts/contrast.ts` (in apps/web), which prints
this table; `scripts/contrast.test.ts` runs the same numbers in `make test`.

Lowest text pair in each theme:
- Worst text pair, light: --ok on page (--bg), 5.32
- Worst text pair, dark: --danger on error notice (--danger 10% over the glass under its sheen), 5.25

Method:
- Colors are sRGB. A translucent color is composited over what is under it ("source over",
  as a browser paints it). Text with alpha (`--text-2`) is composited over its background
  before it is measured.
- The glass is measured at both ends of its gradient: `--glass-fill-2` over `--bg` (its top)
  and `--glass-fill` over `--bg`. The sheen is a radial gradient on top of the glass; its
  brightest point (`--glass-sheen` at full strength over the glass top) is measured too, as the
  worst case for light text. The app has no backdrop blur and a flat page, so what is under
  the glass is `--bg`.
- `color-mix(in srgb, X p%, transparent)` is X at alpha p, composited; `color-mix(in srgb,
  X p%, Y)` is the opaque mix.
- Relative luminance and the ratio are WCAG 2.2's: linearized channels,
  L = 0.2126 R + 0.7152 G + 0.0722 B, ratio (L1 + 0.05) / (L2 + 0.05).
- Minimums: 4.5 for text (1.4.3); 3 for the focus ring, field and button edges, and step and
  state icons (1.4.11). Disabled controls are drawn at half opacity and are exempt (1.4.3).
- Not measured here: the figure and the tactile sheet previews (images on white, from the
  pipeline) and the camera view and its overlay (unchanged, magenta on video).

| Theme | Text or mark | On | Used for | Ratio | Needs | Result |
|---|---|---|---|---|---|---|
| light | `--text` | page (--bg) | body text | 13.47 | 4.5 | pass |
| light | `--text-2` | page (--bg) | secondary text | 6.47 | 4.5 | pass |
| light | `--accent` | page (--bg) | links, badges, step text | 5.39 | 4.5 | pass |
| light | `--danger` | page (--bg) | error text | 5.91 | 4.5 | pass |
| light | `--warn` | page (--bg) | warning text, flags | 5.73 | 4.5 | pass |
| light | `--ok` | page (--bg) | Checked flag | 5.32 | 4.5 | pass |
| light | `--focus` | page (--bg) | focus ring | 5.27 | 3 | pass |
| light | `--field-edge` | page (--bg) | field and button edge, pending step | 3.63 | 3 | pass |
| light | `--text` | glass, top (--glass-fill-2 over --bg) | body text | 14.28 | 4.5 | pass |
| light | `--text-2` | glass, top (--glass-fill-2 over --bg) | secondary text | 6.69 | 4.5 | pass |
| light | `--accent` | glass, top (--glass-fill-2 over --bg) | links, badges, step text | 5.71 | 4.5 | pass |
| light | `--danger` | glass, top (--glass-fill-2 over --bg) | error text | 6.27 | 4.5 | pass |
| light | `--warn` | glass, top (--glass-fill-2 over --bg) | warning text, flags | 6.08 | 4.5 | pass |
| light | `--ok` | glass, top (--glass-fill-2 over --bg) | Checked flag | 5.64 | 4.5 | pass |
| light | `--focus` | glass, top (--glass-fill-2 over --bg) | focus ring | 5.59 | 3 | pass |
| light | `--field-edge` | glass, top (--glass-fill-2 over --bg) | field and button edge, pending step | 3.69 | 3 | pass |
| light | `--text` | glass (--glass-fill over --bg) | body text | 15.01 | 4.5 | pass |
| light | `--text-2` | glass (--glass-fill over --bg) | secondary text | 6.87 | 4.5 | pass |
| light | `--accent` | glass (--glass-fill over --bg) | links, badges, step text | 6.00 | 4.5 | pass |
| light | `--danger` | glass (--glass-fill over --bg) | error text | 6.59 | 4.5 | pass |
| light | `--warn` | glass (--glass-fill over --bg) | warning text, flags | 6.39 | 4.5 | pass |
| light | `--ok` | glass (--glass-fill over --bg) | Checked flag | 5.93 | 4.5 | pass |
| light | `--focus` | glass (--glass-fill over --bg) | focus ring | 5.87 | 3 | pass |
| light | `--field-edge` | glass (--glass-fill over --bg) | field and button edge, pending step | 3.75 | 3 | pass |
| light | `--text` | glass under its sheen (--glass-sheen over the glass top) | body text | 16.04 | 4.5 | pass |
| light | `--text-2` | glass under its sheen (--glass-sheen over the glass top) | secondary text | 7.13 | 4.5 | pass |
| light | `--accent` | glass under its sheen (--glass-sheen over the glass top) | links, badges, step text | 6.42 | 4.5 | pass |
| light | `--danger` | glass under its sheen (--glass-sheen over the glass top) | error text | 7.04 | 4.5 | pass |
| light | `--warn` | glass under its sheen (--glass-sheen over the glass top) | warning text, flags | 6.83 | 4.5 | pass |
| light | `--ok` | glass under its sheen (--glass-sheen over the glass top) | Checked flag | 6.33 | 4.5 | pass |
| light | `--focus` | glass under its sheen (--glass-sheen over the glass top) | focus ring | 6.27 | 3 | pass |
| light | `--field-edge` | glass under its sheen (--glass-sheen over the glass top) | field and button edge, pending step | 3.82 | 3 | pass |
| light | `--text` | surface (--surface: items, fields, buttons) | body text | 15.04 | 4.5 | pass |
| light | `--text-2` | surface (--surface: items, fields, buttons) | secondary text | 6.88 | 4.5 | pass |
| light | `--accent` | surface (--surface: items, fields, buttons) | links, badges, step text | 6.02 | 4.5 | pass |
| light | `--danger` | surface (--surface: items, fields, buttons) | error text | 6.60 | 4.5 | pass |
| light | `--warn` | surface (--surface: items, fields, buttons) | warning text, flags | 6.40 | 4.5 | pass |
| light | `--ok` | surface (--surface: items, fields, buttons) | Checked flag | 5.94 | 4.5 | pass |
| light | `--focus` | surface (--surface: items, fields, buttons) | focus ring | 5.88 | 3 | pass |
| light | `--field-edge` | surface (--surface: items, fields, buttons) | field and button edge, pending step | 3.75 | 3 | pass |
| light | `--info` | surface (--surface: items, fields, buttons) | For your information edge | 5.88 | 3 | pass |
| light | `--accent-ink` | accent (--accent: primary buttons, pressed toggles, tile) | button text | 6.57 | 4.5 | pass |
| light | `--accent` | surface (--surface: items, fields, buttons) | done step icon, tone edge | 6.02 | 3 | pass |
| light | `--text` | drop area (--surface 60% over the glass) | drop area heading | 15.03 | 4.5 | pass |
| light | `--text-2` | drop area (--surface 60% over the glass) | accepted types and limit | 6.88 | 4.5 | pass |
| light | `--text` | drop area, file over it (--accent 10% in --surface) | drop area heading | 13.09 | 4.5 | pass |
| light | `--text-2` | drop area, file over it (--accent 10% in --surface) | accepted types and limit | 6.37 | 4.5 | pass |
| light | `--text` | error notice (--danger 10% over the glass) | error message | 12.80 | 4.5 | pass |
| light | `--danger` | error notice (--danger 10% over the glass) | Not uploaded. | 5.62 | 4.5 | pass |
| light | `--text` | error notice (--danger 10% over the glass under its sheen) | error message | 13.64 | 4.5 | pass |
| light | `--danger` | error notice (--danger 10% over the glass under its sheen) | Not uploaded. | 5.99 | 4.5 | pass |
| light | `--text` | confirm box (--warn 8% in --surface) | question | 13.39 | 4.5 | pass |
| light | `--accent-ink` | pressed toggle (--accent) | check mark and words | 6.57 | 4.5 | pass |
| dark | `--text` | page (--bg) | body text | 16.56 | 4.5 | pass |
| dark | `--text-2` | page (--bg) | secondary text | 9.41 | 4.5 | pass |
| dark | `--accent` | page (--bg) | links, badges, step text | 10.14 | 4.5 | pass |
| dark | `--danger` | page (--bg) | error text | 10.14 | 4.5 | pass |
| dark | `--warn` | page (--bg) | warning text, flags | 12.11 | 4.5 | pass |
| dark | `--ok` | page (--bg) | Checked flag | 11.41 | 4.5 | pass |
| dark | `--focus` | page (--bg) | focus ring | 14.70 | 3 | pass |
| dark | `--field-edge` | page (--bg) | field and button edge, pending step | 4.38 | 3 | pass |
| dark | `--text` | glass, top (--glass-fill-2 over --bg) | body text | 15.61 | 4.5 | pass |
| dark | `--text-2` | glass, top (--glass-fill-2 over --bg) | secondary text | 9.12 | 4.5 | pass |
| dark | `--accent` | glass, top (--glass-fill-2 over --bg) | links, badges, step text | 9.56 | 4.5 | pass |
| dark | `--danger` | glass, top (--glass-fill-2 over --bg) | error text | 9.55 | 4.5 | pass |
| dark | `--warn` | glass, top (--glass-fill-2 over --bg) | warning text, flags | 11.41 | 4.5 | pass |
| dark | `--ok` | glass, top (--glass-fill-2 over --bg) | Checked flag | 10.75 | 4.5 | pass |
| dark | `--focus` | glass, top (--glass-fill-2 over --bg) | focus ring | 13.85 | 3 | pass |
| dark | `--field-edge` | glass, top (--glass-fill-2 over --bg) | field and button edge, pending step | 4.43 | 3 | pass |
| dark | `--text` | glass (--glass-fill over --bg) | body text | 15.61 | 4.5 | pass |
| dark | `--text-2` | glass (--glass-fill over --bg) | secondary text | 9.12 | 4.5 | pass |
| dark | `--accent` | glass (--glass-fill over --bg) | links, badges, step text | 9.56 | 4.5 | pass |
| dark | `--danger` | glass (--glass-fill over --bg) | error text | 9.55 | 4.5 | pass |
| dark | `--warn` | glass (--glass-fill over --bg) | warning text, flags | 11.41 | 4.5 | pass |
| dark | `--ok` | glass (--glass-fill over --bg) | Checked flag | 10.75 | 4.5 | pass |
| dark | `--focus` | glass (--glass-fill over --bg) | focus ring | 13.85 | 3 | pass |
| dark | `--field-edge` | glass (--glass-fill over --bg) | field and button edge, pending step | 4.43 | 3 | pass |
| dark | `--text` | glass under its sheen (--glass-sheen over the glass top) | body text | 10.43 | 4.5 | pass |
| dark | `--text-2` | glass under its sheen (--glass-sheen over the glass top) | secondary text | 6.74 | 4.5 | pass |
| dark | `--accent` | glass under its sheen (--glass-sheen over the glass top) | links, badges, step text | 6.38 | 4.5 | pass |
| dark | `--danger` | glass under its sheen (--glass-sheen over the glass top) | error text | 6.38 | 4.5 | pass |
| dark | `--warn` | glass under its sheen (--glass-sheen over the glass top) | warning text, flags | 7.62 | 4.5 | pass |
| dark | `--ok` | glass under its sheen (--glass-sheen over the glass top) | Checked flag | 7.18 | 4.5 | pass |
| dark | `--focus` | glass under its sheen (--glass-sheen over the glass top) | focus ring | 9.25 | 3 | pass |
| dark | `--field-edge` | glass under its sheen (--glass-sheen over the glass top) | field and button edge, pending step | 3.83 | 3 | pass |
| dark | `--text` | surface (--surface: items, fields, buttons) | body text | 15.61 | 4.5 | pass |
| dark | `--text-2` | surface (--surface: items, fields, buttons) | secondary text | 9.12 | 4.5 | pass |
| dark | `--accent` | surface (--surface: items, fields, buttons) | links, badges, step text | 9.56 | 4.5 | pass |
| dark | `--danger` | surface (--surface: items, fields, buttons) | error text | 9.55 | 4.5 | pass |
| dark | `--warn` | surface (--surface: items, fields, buttons) | warning text, flags | 11.41 | 4.5 | pass |
| dark | `--ok` | surface (--surface: items, fields, buttons) | Checked flag | 10.75 | 4.5 | pass |
| dark | `--focus` | surface (--surface: items, fields, buttons) | focus ring | 13.85 | 3 | pass |
| dark | `--field-edge` | surface (--surface: items, fields, buttons) | field and button edge, pending step | 4.43 | 3 | pass |
| dark | `--info` | surface (--surface: items, fields, buttons) | For your information edge | 10.09 | 3 | pass |
| dark | `--accent-ink` | accent (--accent: primary buttons, pressed toggles, tile) | button text | 8.88 | 4.5 | pass |
| dark | `--accent` | surface (--surface: items, fields, buttons) | done step icon, tone edge | 9.56 | 3 | pass |
| dark | `--text` | drop area (--surface 60% over the glass) | drop area heading | 15.61 | 4.5 | pass |
| dark | `--text-2` | drop area (--surface 60% over the glass) | accepted types and limit | 9.12 | 4.5 | pass |
| dark | `--text` | drop area, file over it (--accent 10% in --surface) | drop area heading | 13.58 | 4.5 | pass |
| dark | `--text-2` | drop area, file over it (--accent 10% in --surface) | accepted types and limit | 8.30 | 4.5 | pass |
| dark | `--text` | error notice (--danger 10% over the glass) | error message | 13.60 | 4.5 | pass |
| dark | `--danger` | error notice (--danger 10% over the glass) | Not uploaded. | 8.32 | 4.5 | pass |
| dark | `--text` | error notice (--danger 10% over the glass under its sheen) | error message | 8.59 | 4.5 | pass |
| dark | `--danger` | error notice (--danger 10% over the glass under its sheen) | Not uploaded. | 5.25 | 4.5 | pass |
| dark | `--text` | confirm box (--warn 8% in --surface) | question | 13.88 | 4.5 | pass |
| dark | `--accent-ink` | pressed toggle (--accent) | check mark and words | 8.88 | 4.5 | pass |

## Screens and axe

`uv run apps/web/e2e/ui_review.py` (Nov 3, on this branch, mock API): 8 screens (upload,
upload error, progress, review, fix outline, publish, Explore started, device check) in light
and dark, at 390x844 and 1440x900, in Chrome and WebKit, 64 runs. Screenshots are in
`docs/review/ui/`, named `app-<screen>-<theme>-<size>-<browser>.png`.

axe-core 4.10.3 with the WCAG 2.0, 2.1 and 2.2 A and AA rules and best practices: no violation
of any impact on any run (at least 30 rules passed on each). Two rules came back "needs
review", which axe leaves to a person:
- `color-contrast`: text on the glass, whose fill is a gradient axe does not compute. The
  table above computes those pairs, top and bottom of the gradient and under the sheen.
- `video-caption`: the camera `<video>` on Explore and the device check. It is muted and
  shows the live camera, with no speech to caption.

The progress screen is a real status answer from the mock pipeline, the running one with the
most stages done (S5 active in this run), served again to the page so the shot holds still; the active step's seconds are the
page's own count from that moment.
