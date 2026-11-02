# Tracking spike

A standalone page that covers Day 2 (d2-1 to d2-4) as a prototype. The camera keeps only the newest frame. MediaPipe Hand Landmarker runs in a Web Worker (VIDEO mode, 2 hands). A homography is built from 4 corners you click. The fingertip is mapped to sheet millimeters through a 1 euro filter. A 9 point touch test reports mean and p95 error.

## Run the touch test

1. Print `test-sheet.pdf` on US Letter at 100 percent ("Actual size", not "Fit"). Measure the bar with a ruler. It must be 100 mm.
2. Tape the sheet flat. Fix the camera above it so all 4 corner marks are in view. For Gate B the page runs in the demo phone's own browser, with the phone in a fixed mount (see `eval/gate-b/README.md`). For practice, a laptop with an iPhone as a Continuity Camera works, and so does a webcam on a stand.
3. Serve this folder: `python3 -m http.server 8000 -d spikes/tracking`. Open http://localhost:8000 in Chrome. A phone needs the page over HTTPS: `eval/gate-b/README.md` has the command and the iPhone URL.
4. Pick the camera and press Start camera. Wait for "Hand tracker ready".
5. Press R and click the centers of corners A, B, C, D on the video, in that order. The magenta outline and targets should land on the printed ones. If they do not, press R again.
6. Press T. For each number shown and spoken, put your index fingertip on that target and hold still. The touch records itself after 0.6 s at rest. Space records one at once. There are 45 touches, about 3 minutes.
7. The page shows mean, p95, bias and per target means, plus the two tracker commands, and offers the raw JSON. Download it and save it, unedited, in `eval/gate-b/` (see `eval/gate-b/README.md`).
8. `python3 spikes/tracking/analyze_touch.py eval/gate-b/touch-test-....json` recomputes the stats from the raw records and decides Gate B (mean 4 mm or less). It also tests whether x and y differ, both as signed bias and as scale per axis in camera pixels. A frame aspect ratio bug shows only in the scale: errors on both sides of center cancel in the mean bias.

Keys: R recalibrate, T start the test, Space record now, Escape stop speech. The contact offset field moves the contact point back from the fingertip, 4 mm by default from config/explore.yaml.

## Checks

- `cd spikes/tracking && npm test`: node tests for the frame pump, homography, 1 euro filter, pointing hand picker and touch test logic. Node only, nothing to install.
- `test/parity.test.mjs` (part of `npm test`) holds the spike to the shipped tracking code in `apps/web/src/explore` on early-start: same inputs, same contact point every frame. main has no `apps/web`, so the shipped outputs are stored in `test/parity/port_outputs.json`. They record the early-start commit and a sha256 of each shipped file they came from (`SHIPPED_SOURCES` in `test/parity/inputs.mjs`), and the test fails, naming the file, once any of those files on early-start changes. It also fails if a listed file imports one that is not listed. To remake them, from the early-start worktree: `cd .worktrees/early-start/apps/web && npx vitest run --config ../../../../spikes/tracking/test/parity/vitest.config.mjs`.
- `uv run spikes/tracking/e2e_check.py loop`: headless Chrome with a fake camera and a 100 ms stub worker. Frames must drop and never queue.
- `uv run spikes/tracking/e2e_check.py hands CLIP.y4m CPU`: MediaPipe on a fake camera clip. A hand must be found and mapped onto the sheet.
- `uv run spikes/tracking/e2e_check.py touch CLIP.y4m CPU`: the same, then T and 3 Space presses.
- `uv run spikes/tracking/e2e_check.py session`: a whole 45 touch test through the page with scripted hands (stub worker, `?corners=`, T, dwell captures), then the downloaded JSON through `analyze_touch.py`. The contact point must land on every target, mean under 0.5 mm, with no page errors. Takes about 50 s, so it is not in the pre-commit hook; run it before a Gate B run.
- `uv run spikes/tracking/make_sheet.py`: rebuild `test-sheet.pdf` from `sheet.json`.

The test clip used so far is built from File:Index finger 2.JPG on Wikimedia Commons (public domain, PD-user-en, by Than Ball), panned over a white frame.

## Not product code

This is a prototype. MediaPipe's wasm and model load from jsDelivr and Google Cloud Storage, so it needs the network. The product must vendor both so Explore works offline (RULES 5.4). The `lib/` modules are meant to move to `apps/web/src/explore/` as TypeScript, with their tests.
