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

## fixtures/audio/question_aorta_ventricle.wav

| | |
|---|---|
| Content | The question "Where is the aorta? What does the left ventricle do?", 2.72 s, 16 kHz mono |
| Made by | This project, on Oct 27, 2026, with the macOS `say` command (system default voice, rate 160) and ffmpeg |
| Use | Test audio for the Muse Voice Transcribe smoke call and its replay test only |

The voice is Apple's macOS speech synthesis, so Apple's terms for its system voices apply. Replace this clip with a recording of our own voice before anything built from it is shown publicly.

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

## Not stored here

- The other 17 eval figures in `spikes/eval-figures.md` are listed by URL, with their licenses, but not downloaded into the repository. Add each one here if it is ever committed.
- The fake camera clip for the tracking checks is built locally from File:Index finger 2.JPG by Than Ball (public domain, PD-user-en), https://commons.wikimedia.org/wiki/File:Index_finger_2.JPG. It is not committed.
