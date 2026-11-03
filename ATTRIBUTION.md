# Attribution

Third-party content stored in this repository, with its author, source and license.

## fixtures/heart.png

| | |
|---|---|
| Title | Heart diagram-en.svg |
| Author | ZooFari |
| Source | https://commons.wikimedia.org/wiki/File:Heart_diagram-en.svg |
| License | Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0), https://creativecommons.org/licenses/by-sa/3.0/ |
| License checked | 2026-10-24, on the file page and through the Wikimedia Commons API |
| Changes | Rendered from the SVG by Commons at 3840 px, resized to 2048 x 1612 px, and flattened onto a white background |

Credit line: "Heart diagram-en.svg by ZooFari, CC BY-SA 3.0, via Wikimedia Commons. Resized and placed on a white background."

**Share-alike applies to everything made from this figure.** A tactile SVG, print PDF or regions.json built from fixtures/heart.png is an adaptation. It carries the same license, CC BY-SA 3.0 (or a later version with the same terms, which the license allows), and must show the credit line above. That covers the printed and traced sheet in the demo, and the figure as it appears in the demo video and the README.

## fixtures/control/banana.png

| | |
|---|---|
| Title | Banana-Single.jpg |
| Author | Evan-Amos |
| Source | https://commons.wikimedia.org/wiki/File:Banana-Single.jpg |
| License | Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0), https://creativecommons.org/licenses/by-sa/3.0/ |
| License checked | 2026-10-29, through the Wikimedia Commons API (LicenseShortName, Artist, Credit "Own work") |
| Changes | The 1280 px rendering from Commons, resized to 1024 x 902 px and saved as PNG with no metadata |
| Use | The control image for the SAM diagnostic (`services/api/app/meta/sam_diagnostic.py`) only |

Credit line: "Banana-Single.jpg by Evan-Amos, CC BY-SA 3.0, via Wikimedia Commons. Resized."

## fixtures/eval/flower.png

| | |
|---|---|
| Title | Mature flower diagram.svg |
| Author | Mariana Ruiz (LadyofHats) |
| Source | https://commons.wikimedia.org/wiki/File:Mature_flower_diagram.svg |
| License | Public domain. Page statement: "This work has been released into the public domain by its author, LadyofHats" |
| License checked | 2026-10-24 on the file page (spikes/eval-figures.md), again 2026-10-29 through the Wikimedia Commons API (LicenseShortName "Public domain") |
| Changes | Rendered from the SVG by Commons at 3840 px, resized to 2048 x 1183 px, and flattened onto a white background |
| Use | The S2 bake-off (Gate A step 4.1b): labels with leader lines |

Credit line, not required: "Mature flower diagram.svg by Mariana Ruiz (LadyofHats), public domain, via Wikimedia Commons."

## fixtures/eval/japan_regions.png

| | |
|---|---|
| Title | Eight regions of Japan (en).svg |
| Author | Bigmorr, derived from File:Japan large full.svg by Orange Wave |
| Source | https://commons.wikimedia.org/wiki/File:Eight_regions_of_Japan_(en).svg |
| License | Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/ |
| License checked | 2026-10-24 on the file page (spikes/eval-figures.md), again 2026-10-29 through the Wikimedia Commons API (LicenseShortName "CC BY-SA 4.0") |
| Changes | Rendered from the SVG by Commons at 3840 px, resized to 1796 x 2048 px |
| Use | The S2 bake-off (Gate A step 4.1b): mostly closed outlines |

Credit line: "Eight regions of Japan (en).svg by Bigmorr, derived from a map by Orange Wave, CC BY-SA 4.0, via Wikimedia Commons. Resized." Share-alike applies to anything made from it, as for heart.png.

## fixtures/eval/brain_lobes.png

| | |
|---|---|
| Title | Blausen 0111 BrainLobes.png |
| Author | BruceBlaus (Blausen.com staff), "Medical gallery of Blausen Medical 2014", WikiJournal of Medicine 1 (2), DOI:10.15347/wjm/2014.010 |
| Source | https://commons.wikimedia.org/wiki/File:Blausen_0111_BrainLobes.png |
| License | Creative Commons Attribution 3.0 Unported (CC BY 3.0), https://creativecommons.org/licenses/by/3.0/ |
| License checked | 2026-10-30, through the Wikimedia Commons API (LicenseShortName "CC BY 3.0", Artist BruceBlaus, Credit "Own work") |
| Changes | None. The original 2250 x 1350 px PNG, sha1 d65957456cce55d799f2ca3326ee64934fa266c9 as the API lists it |
| Use | Eval figure for the tactile-aware part plan (eval/plan/): a lateral view with labeled lobes, drawn as one unbroken shape |

Credit line: "Blausen 0111 BrainLobes.png by BruceBlaus (Blausen.com staff, Medical gallery of Blausen Medical 2014), CC BY 3.0, via Wikimedia Commons."

## fixtures/audio/question_aorta_ventricle.wav

| | |
|---|---|
| Content | The question "Where is the aorta? What does the left ventricle do?", 2.72 s, 16 kHz mono |
| Made by | This project, on Oct 27, 2026, with the macOS `say` command (system default voice, rate 160) and ffmpeg |
| Use | Test audio for the Muse Voice Transcribe smoke call and its replay test only |

The voice is Apple's macOS speech synthesis, so Apple's terms for its system voices apply. Replace this clip with a recording of our own voice before anything built from it is shown publicly.

## fixtures/audio/question_left_ventricle.wav, question_superior_vena_cava.wav, question_left_pulmonary_veins.wav

| | |
|---|---|
| Content | "What does the left ventricle do?" (1.53 s), "Where is the superior vena cava?" (1.72 s), "What is next to the left pulmonary veins?" (2.19 s), 16 kHz mono 16-bit PCM |
| Made by | This project, on Oct 30, 2026, with the macOS `say` command (system default voice, rate 160) and `afconvert -f WAVE -d LEI16@16000 -c 1` |
| Use | Synthetic test audio: the transcribe path with and without keyword hints, and the headless hold-to-talk check (Chrome's fake microphone) |

The same terms apply as for the clip above.

## apps/web/public/models/hand_landmarker.task

| | |
|---|---|
| Title | MediaPipe Hand Landmarker, float16, version 1 |
| Author | Google, The MediaPipe Authors |
| Source | https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task |
| License | Apache License 2.0. Full text next to the model: `apps/web/public/models/LICENSE` |
| License checked | 2026-10-29, in the model card "Hand Tracking (Lite/Full) with Fairness, Oct 2021" ("Licensed under: Apache License, Version 2.0"), linked from the MediaPipe Hand Landmarker docs page |
| Changes | None. sha256 fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1 |
| Use | Served by the web app so hand tracking works with no network |

## @mediapipe/tasks-vision 1.1.0 (npm), its wasm in the web build

| | |
|---|---|
| Title | MediaPipe Tasks Vision |
| Author | Google, The MediaPipe Authors ("Copyright 2022 The MediaPipe Authors" in the package's source headers) |
| Source | https://www.npmjs.com/package/@mediapipe/tasks-vision, installed from `apps/web/package.json` |
| License | Apache License 2.0 (`"license": "Apache-2.0"` in its package.json). The package ships no license file, so the full text is in `apps/web/public/licenses/mediapipe-tasks-vision-LICENSE` and goes into every build |
| License checked | 2026-10-29, in node_modules/@mediapipe/tasks-vision/package.json |
| Changes | None. The hand worker imports `vision_wasm_module_internal.js` and `.wasm` by URL, so the build copies them into `dist/assets/` |

The license text in both places is the Apache License 2.0 from https://www.apache.org/licenses/LICENSE-2.0.txt (sha256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30).

## meta-sam-parser 0.1.0 (PyPI)

| | |
|---|---|
| Author | Meta Platforms, Inc. |
| Source | https://github.com/meta-models/meta-sam, installed from `services/api/pyproject.toml` (hash-pinned in `services/api/uv.lock`) |
| License | SAM License, last updated November 19, 2025 (in the package's `dist-info/licenses/LICENSE`). Not an open-source license: it binds each installer, including trade controls and no reverse engineering, and a redistribution must carry the license |
| Use | Decodes SAM 3.1's mask output in `services/api/app/meta/sam_adapter.py`. No code from it is copied here |

## liblouis

Installed on the system (`brew install liblouis` or `apt install liblouis-bin liblouis-data`), version 3.39.0 when checked; GPL-3.0-or-later for the tools and LGPL-2.1-or-later for the library. The backend runs `lou_translate` as a separate process (`services/api/app/braille/louis.py`). Not distributed here.

## Derived from the figures above

These are adaptations of a figure listed above, so each carries that figure's license and,
where it asks for one, its credit line. Share-alike applies to the heart and Japan ones.

### The S2 reference masks, eval/s2-bakeoff/*/reference/ (16 PNG masks and an index.json each)

| Folder | Masks | Derived from | License |
|---|---|---|---|
| `eval/s2-bakeoff/heart/reference/` | 4: left common carotid artery, left pulmonary arteries, right atrium, right pulmonary arteries | fixtures/heart.png | CC BY-SA 3.0, with the heart's credit line |
| `eval/s2-bakeoff/flower/reference/` | 5: anther, connective, filament stalk, ovary, pollen sac | fixtures/eval/flower.png | Public domain |
| `eval/s2-bakeoff/japan_regions/reference/` | 7: Chubu, Chugoku, Hokkaido, Kansai, Kanto, Kyushu, Shikoku regions | fixtures/eval/japan_regions.png | CC BY-SA 4.0, with the Japan map's credit line |

Each is the passing mask of one part, as graded in the S2 bake-off (Oct 29), saved at the
figure's normalized size.

### Regions files

| File | Derived from | License |
|---|---|---|
| `fixtures/pipeline/heart_regions.json`, `fixtures/pipeline/heart_fixed_draft.json` | fixtures/heart.png, through the pipeline | CC BY-SA 3.0, with the heart's credit line |
| `fixtures/qa/heart_v4_regions.json` | fixtures/heart.png, published version 4 | CC BY-SA 3.0, with the heart's credit line |
| `fixtures/qa/brain_lobes_v4_regions.json` | fixtures/eval/brain_lobes.png, published version 4 | CC BY 3.0, with the brain's credit line |

### Screenshots, docs/submission/screenshots/

The four screenshots of Author and Explore (Nov 3, a headless mock-mode run) show
fixtures/heart.png in the review and the Fix outline panel: CC BY-SA 3.0, with the heart's
credit line, which README.md prints under them.

### Recorded model answers, fixtures/recorded/

Each recording is one Meta model call about one figure above: an S1 listing or plan, SAM
masks, a question's answer, or a transcript. The request names the figure by its image
digest, and a question's prompt also holds the figure's title and parts in words; masks and
outlines are adaptations of the figure. A recording carries that figure's license: the heart
(names with `heart`, the questions on it) CC BY-SA 3.0, the flower public domain, Japan
(`japan_regions`) CC BY-SA 4.0, the Commons brain (`brain_lobes`, the questions on it) CC
BY 3.0. The question recordings (`qa*_ask_*`) are on the heart or the Commons brain, as
`fixtures/recorded/replays.json` and `eval/qa/questions.jsonl` say. The transcribe recordings
hold the synthetic speech of `fixtures/audio/`, above.

## Own work, under the project's license

- `fixtures/synthetic/` (figure.png, its 26 masks, regions.json, truth.json): the synthetic
  test figure, generated by `services/api/app/synthetic/`.
- `spikes/tracking/test-sheet.pdf`: the touch-test sheet, generated by
  `spikes/tracking/make_sheet.py` from `spikes/tracking/sheet.json`.
- `fixtures/regions/golden.json` and `cases.json`: a hand-written contract figure and its test
  cases.
- `docs/submission/architecture.svg` (the system diagram) and `docs/submission/captions.srt`
  (the video's narration as captions, made by `scripts/captions.py`).

## Not stored here

- The other 17 eval figures in `spikes/eval-figures.md` are listed by URL, with their licenses, but not downloaded into the repository. Add each one here if it is ever committed.
- A private test figure, not distributed: it is not openly licensed. It and its live recordings stay local, git-ignored as `fixtures/private/` and `fixtures/recorded/private_*`; eval/plan/ keeps its counts only.
- The fake camera clip for the tracking checks is built locally from File:Index finger 2.JPG by Than Ball (public domain, PD-user-en), https://commons.wikimedia.org/wiki/File:Index_finger_2.JPG. It is not committed.
