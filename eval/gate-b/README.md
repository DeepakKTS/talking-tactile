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

Terminal 1, the touch-test page over HTTPS on port 8443:
```
cd /Users/deepakzedler/Downloads/talking-tactile
python3 - <<'EOF'
import functools, http.server, ssl
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory="spikes/tracking")
server = http.server.ThreadingHTTPServer(("0.0.0.0", 8443), handler)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain("apps/web/.certs/phone.pem", "apps/web/.certs/phone-key.pem")
server.socket = tls.wrap_socket(server.socket, server_side=True)
print("Touch test on https://<this Mac>:8443/", flush=True)
server.serve_forever()
EOF
```

Terminal 2, optional, the API in mock mode:
```
cd /Users/deepakzedler/Downloads/talking-tactile/services/api
MOCK_META=1 uv run uvicorn app.main:app --port 8000
```

Terminal 3, optional, the app for the phone (proxies the API on port 8000):
```
cd /Users/deepakzedler/Downloads/talking-tactile/apps/web
npm run dev:phone
```

## On the iPhone

Open, in Safari:

- `https://Zedlers-MacBook-Pro.local:8443/`
- or `https://<LAN address>:8443/`, the address `npm run cert:phone` printed

Then:

1. Put the phone in its mount over the taped sheet, with all 4 corner marks in view.
2. Press Start camera and allow the camera. The page asks for the rear camera. If the
   picture shows the front camera, pick the back camera in the Camera menu and press Start
   camera again.
3. Wait for "Hand tracker ready".
4. Press Calibrate, then tap the centers of corners A, B, C and D on the picture, in that
   order.
5. Check that the magenta outline and targets sit on the printed ones. If not, press
   Calibrate and tap again. Write in `run.md` that the check was done.
6. Press Touch test. For each number shown and spoken, put your index fingertip on that
   target and hold still. A touch records itself after 0.6 s at rest. 45 touches, about 3
   minutes. Do not move the phone or the sheet.
7. At the end the page shows the mean, the p95 and the bias. Press "Download the raw results
   (JSON)" and choose Download.

## Getting the run into eval/gate-b/

1. Safari saves the file as `touch-test-<finish time, UTC>.json` in the Files app, in the
   Downloads folder that Settings > Apps > Safari > Downloads names (On My iPhone or
   iCloud Drive).
2. In Files, share it by AirDrop to the Mac. It lands in `~/Downloads`.
3. Copy it in unedited, and check that the copy is the same file:
   ```
   cd /Users/deepakzedler/Downloads/talking-tactile
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
  frame_earcon, fps`. `frame_enter` is the first frame where the fingertip visibly crosses
  the traced outline. `frame_earcon` is the first frame where the audio waveform rises above
  background noise. `fps` is read from the video's file info, not assumed.
- `videos.sha256`: name and sha256 of each latency video. The videos are too large for
  git and stay outside it. These hashes tie the frame counts to the exact files.
