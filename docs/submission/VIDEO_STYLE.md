# Video style

For the video tool and anyone cutting the demo. The colors, fonts and logo are the project's own
(`site/assets/tokens.css`, `site/assets/fonts/`, `site/assets/brand/`); the shot list and narration are in
`docs/submission/VIDEO_SCRIPT.md`, captions in `docs/submission/captions.srt`.

## The one rule

The product is shown in real footage only: the printed and raised sheet, the iPhone in its
stand, a real fingertip, the real screen of Author and Explore, and the real spoken audio.
Generated visuals are allowed only for abstract title cards and transitions: never a picture
of the product, a hand, a phone, a sheet, a figure or a screen, and never a redrawn science
figure. A student learns from the textbook's own picture; the video must not suggest otherwise.

## Palette

Dark is the video's default (black background); light is for a paper look on title cards.

| Token | Dark | Light | Use |
|---|---|---|---|
| Background | `#000000` | `#E7E1D1` | Frames, title cards |
| Text | `#ECE4CF` | `#1B1912` | Titles, captions |
| Secondary text | `#ECE4CF` at 76 percent | `#1B1912` at 74 percent | Small print, credits |
| Accent (brass) | `#C9B27C` | `#6B5627` | The logo, one highlight per frame, the dot motif |
| Ink on accent | `#17140C` | `#FBF7EC` | Text on a brass fill |
| Focus | `#E8D7A6` | `#2F5D8A` | An outline that points at something on screen |

Status colors appear only as the app shows them; do not add new ones. Keep captions at WCAG AA
contrast or better (4.5 to 1): Text on Background is 16.6 to 1 in dark and 13.5 to 1 in light.

## Fonts

- Headings and title cards: **Literata** (SIL OFL 1.1), regular to semibold.
- Captions, labels, credits: **Atkinson Hyperlegible Next** (SIL OFL 1.1), regular and bold.
- Files: `site/assets/fonts/` (woff2, with their OFL texts). Captions at least 42 px tall
  on a 1080p frame, two lines of at most 42 characters (as `captions.srt` is cut).

## Logo

- `site/assets/brand/logo.svg`: the braille cells for "tt" (dots 2-3-4-5, twice) and the
  wordmark "Talking Tactile" in Literata. Use it on the first and last card.
- `site/assets/brand/logo-mark.svg`: the two cells alone, for corners and small spaces.
- In brass on black, or deep brass on paper. Do not recolor, stretch, outline or animate the
  dots out of their cell positions; the pattern is real braille and must stay readable.

## Motion

- Slow and smooth: cuts or cross-dissolves of 400 to 800 ms, eases that settle (the site uses
  `cubic-bezier(0.2, 0.7, 0.2, 1)`), titles that rise 10 to 15 px while fading in.
- The dot motif: the six-dot braille cell as the one recurring shape. Dots may fade in one at
  a time to form "tt", or a single dot may mark where a finger is, but never faster than about
  four dots a second.
- No flashy effects: no glitch, zoom punches, whip pans, particle bursts, lens flares, shakes
  or strobing. Nothing flashes more than three times a second.
- Let the real audio lead: the tone and the spoken part name must be heard clearly; music, if
  any, stays low under narration and drops out when the phone speaks.

## Credits on screen

Show both figure credits from `ATTRIBUTION.md` on the shots that show them and on the end card
(`VIDEO_SCRIPT.md` shots 1, 9 and 10): the heart (CC BY-SA 3.0, the sheet is an adaptation) and
the Commons brain (CC BY 3.0). If the landing page's dot mosaic appears, credit it as the site
does: "Background art: Vignette Bloom by Serafim, 21st.dev, MIT."

