# Gate B: the recorded touch test

Gate B: mean fingertip error of 4 mm or less on the 9 point sheet.

## The protocol

Decided before the run (TRACKER decisions "When the Oct 25 touch test counts as Gate B" and
"Demo and Gate B run the page on the demo phone itself"). A run counts only if all of these
hold:

1. `spikes/tracking/test-sheet.pdf` printed on US Letter at 100 percent ("Actual size", not
   "Fit"), and the 100 mm bar measured with a ruler at 100 mm.
2. The demo phone is the camera, running the page in its own browser (not Continuity
   Camera), in a fixed mount that does not move from calibration to the last touch.
3. After calibration, the drawn outline and targets are checked against the printed corner
   marks and targets before the first touch.
4. 45 touches (9 targets times 5, in the page's order).
5. Normal room lighting.

Any other run is practice. Gate B stays pending until a run meets all five.

## What runs

The Gate B page is the touch-test page, `spikes/tracking/index.html`, not Explore. It never
calls the API. MediaPipe's code and hand model load from jsDelivr and Google Cloud Storage,
so the phone needs the network. An iPhone opens the camera only on an HTTPS page, so the page
is served over HTTPS with the phone certificate that `npm run dev:phone` uses.

The API is not needed. To have the app up as well (for an Explore check after the run),
start it in mock mode: it makes no Meta calls and costs nothing.

## Before the run, on the Mac

1. On the commit you will serve:
   ```
   uv run spikes/tracking/e2e_check.py session    # a whole 45 touch test, scripted hands, about 50 s
   (cd spikes/tracking && npm test)               # includes parity with the shipped tracking code
   ```
   Both must print a pass.
2. If the Mac's LAN address changed since the last certificate:
   ```
   cd apps/web && npm run cert:phone
   ```

## Terminals

Each terminal starts at the repo root (the folder you cloned).

Terminal 1, the touch-test page over HTTPS on port 8443:
```
python3 spikes/tracking/serve.py
```
It serves `spikes/tracking` only, with the certificate from `npm run cert:phone` and a
Content-Security-Policy that lets in MediaPipe from jsDelivr and the hand model from Google's
storage and nothing else, so the phone needs the internet for the first load.

Terminal 2, optional, the API in mock mode:
```
cd services/api
MOCK_META=1 uv run uvicorn app.main:app --port 8000
```

Terminal 3, optional, the app for the phone (proxies the API on port 8000):
```
cd apps/web
npm run dev:phone
```

## On the iPhone

Open, in Safari:

- `https://<your-mac>.local:8443/`
- or `https://<LAN address>:8443/`, the address `npm run cert:phone` printed

`<your-mac>` is this Mac's local name: `scutil --get LocalHostName`.

Then:

1. Put the phone in its mount over the taped sheet, with all 4 corner marks in view.
2. Press Start camera and allow the camera. The page asks for the rear camera. If the
   picture shows the front camera, pick the back camera in the Camera menu and press Start
   camera again.
3. Wait for "Hand tracker ready".
4. Press Calibrate, then tap the centers of corners A, B, C and D on the picture, in that
   order. The page asks for each: "Tap corner A, top left." and so on.
5. Check that the magenta outline and targets sit on the printed ones. If not, press
   Calibrate and tap again. Write in `run.md` that the check was done.
6. Press Touch test. For each number shown and spoken, put your index fingertip on that
   target and hold still. A touch records itself after 0.6 s at rest; Record now records one
   at once, and Stop speech stops the voice. 45 touches, about 3 minutes. Do not move the
   phone or the sheet. Every step works by touch: no keyboard is needed on the phone
   (`uv run spikes/tracking/e2e_check.py touch-session` runs the protocol on an emulated
   phone by taps alone).
7. At the end the page shows the mean, the p95 and the bias. Press "Download the raw results
   (JSON)" and choose Download.

## Getting the run into eval/gate-b/

1. Safari saves the file as `touch-test-<finish time, UTC>.json` in the Files app, in the
   Downloads folder that Settings > Apps > Safari > Downloads names (On My iPhone or
   iCloud Drive).
2. In Files, share it by AirDrop to the Mac. It lands in `~/Downloads`.
3. Copy it in unedited, and check that the copy is the same file:
   ```
   # from the repo root
   cp ~/Downloads/touch-test-*.json eval/gate-b/
   shasum -a 256 ~/Downloads/touch-test-*.json eval/gate-b/touch-test-*.json
   ```
4. Recompute the stats from the raw records and get the verdict:
   ```
   python3 spikes/tracking/analyze_touch.py eval/gate-b/touch-test-<finish time>.json
   ```
5. Write `eval/gate-b/run.md` (below).
6. Record it in the tracker (the page prints the two metric commands with the numbers):
   ```
   python3 scripts/tracker.py metric touch-mean <mean> --source live
   python3 scripts/tracker.py metric touch-p95 <p95> --source live
   python3 scripts/tracker.py gate B pass --evidence "eval/gate-b/touch-test-<finish time>.json: mean <mean> mm, p95 <p95> mm, 45 touches, protocol met (run.md)"
   ```
   Use `fail` instead of `pass` when the mean is over 4 mm.

A practice run's JSON stays out of `eval/gate-b/`.

## run.md

One file per counted run, written by hand after the run:

```
# Gate B run

- Date and time (local, and the UTC in the file name):
- Phone model, iOS version, browser:
- Video size (from the page's stats line):
- Hand tracker backend (GPU or CPU, from the stats line):
- Printer, paper, scale (100 percent), measured bar: ___ mm
- Mount: what holds the phone, height above the sheet:
- Lighting: room lights, window, time of day:
- Outline checked after calibration: yes / no, recalibrations:
- Touches: 45
- Result file: touch-test-<finish time>.json, sha256:
- analyze_touch.py: mean ___ mm, p95 ___ mm, verdict:
- Departures from the protocol: none / list (any departure makes this a practice run)
```

## What goes here

- `touch-test-<finish time, UTC>.json`: the session as the touch-test page downloads
  it, not edited. Version 2 has the clicked corners, the video size, and every frame
  of each touch (landmark pixels, the point before and after the filter).
- `run.md`: as above.
- `latency.csv`, from the separate latency film: columns `touch_no, part, frame_enter,
  frame_earcon, fps, video`. `frame_enter` is the first frame where the fingertip visibly
  crosses the traced outline. `frame_earcon` is the first frame where the audio waveform rises
  above background noise. `fps` is read from the video's file info, not assumed.
- `voice-latency.csv`, from hold-to-talk takes in the same film: columns `take, question,
  frame_release, frame_first_word, fps, video`. `frame_release` is the first frame where the
  finger is off the talk button; `frame_first_word` the first frame of the spoken answer (not
  the thinking tone).
- `videos.sha256`: name and sha256 of each latency video. The videos are too large for
  git and stay outside it. These hashes tie the frame counts to the exact files.
- `RESULTS.md`: written by `make results` from the files above.

## The latency film, step by step

1. Film the phone over the sheet from the side, sound on, at the camera's highest frame rate.
   For touch to tone, enter parts one at a time and rest; for questions, hold the talk button,
   ask, let go. Keep each clip short. AirDrop the videos to the Mac; they stay outside git.
2. Hash them and start the tables (needs `brew install ffmpeg`):
   ```
   python3 scripts/latency_film.py touch ~/Downloads/IMG_*.MOV    # writes latency.csv and videos.sha256
   python3 scripts/latency_film.py voice ~/Downloads/IMG_*.MOV    # writes voice-latency.csv
   ```
   The touch table gets one row per sound, `frame_earcon` and `fps` filled in from the audio
   and the file info. Step through each video (QuickTime: arrow keys) and fill in `part` and
   `frame_enter`; delete rows for sounds that are not an earcon. Fill the voice table's frames.
3. `make results`: writes `RESULTS.md`, puts the measured values with their file in place of
   each TBD in README.md, docs/submission/WRITEUP.md and VIDEO_SCRIPT.md, sets the tracker's
   metrics, and prints the Gate B command to run once `run.md` is written. A row left
   unfinished stops it with the row number.
