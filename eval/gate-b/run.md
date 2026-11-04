# Gate B run

- Date and time (local, and the UTC in the file name): Nov 4, 2026, 14:47 to 14:54 ET; the
  file is touch-test-2026-11-04T19-54-20-482Z.json (finished 19:54:20 UTC). The test was
  started at 19:47:54 UTC; all 45 touches were recorded from 19:51:49 UTC, after the last
  calibration at 19:51:45 UTC.
- Phone model, iOS version, browser: iPhone 15 Pro Max, iOS 26.1, Safari.
- Video size (from the page's stats line): 720 x 1280 (portrait).
- Hand tracker backend (GPU or CPU, from the stats line): mediapipe 1.1.0 GPU.
- Camera (from the file): "Back Camera", chosen by deviceId; zoom offered 1 to 10, fixed at
  1; no focusMode offered (focusDistance only), so focus was not fixed. The camera did not
  change during the run (practice: null).
- Printer, paper, scale (100 percent), measured bar: CVS document print, black and white, US
  Letter, regular paper. The online order had no scale setting;
  the 100 mm bar measured 100 mm with a ruler.
- Mount: what holds the phone, height above the sheet: a tripod with a phone mount, camera
  looking straight down, about 30 cm above the sheet.
- Lighting: room lights, window, time of day: daylight from the window plus room lights,
  early afternoon, no direct shadow on the sheet.
- Outline checked after calibration: yes, after the last one; calibrations: 3.
- Touches: 45 (all by rest-to-record, none by Record now).
- Result file: touch-test-2026-11-04T19-54-20-482Z.json, sha256:
  4a51fe69632556d7f1476bc1f408a36705d7a69e5ae08637f2770600789dfc64
- analyze_touch.py: mean 7.93 mm, median 4.0 mm, p95 25.77 mm, verdict: fail (target mean
  4 mm or less).
- Departures from the protocol: none from its five conditions (`eval/gate-b/README.md`). The
  sheet was regular paper, not the cardstock on the materials list (d0-6); the protocol names
  no paper weight.
