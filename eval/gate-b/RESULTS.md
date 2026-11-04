# Gate B and the device latency film

Written by `scripts/results.py` (`make results`) from the files named below; run it again to reproduce.

## Gate B: fingertip error on the 9-point sheet

- File: `eval/gate-b/touch-test-2026-11-04T19-54-20-482Z.json`, sha256 `4a51fe69632556d7f1476bc1f408a36705d7a69e5ae08637f2770600789dfc64`.
- Touches 45: mean 7.93 mm, median 4.0 mm, p95 25.77 mm, max 77.96 mm (target: mean 4 mm or less, p95 8 mm or less). By the numbers: fail.
- Bias x 0.36 ± 1.6 mm, y 0.71 ± 3.95 mm; touches without the pointing pose 2.
- Mean error by target, mm: 1: 7.76, 2: 7.68, 3: 9.19, 4: 4.45, 5: 4.89, 6: 3.98, 7: 2.72, 8: 3.32, 9: 27.41.
- Largest error: touch 1, on target 9, 77.96 mm.
- Video 720 x 1280; x over y scale 1.0963 (suspect).
- Protocol: `eval/gate-b/run.md` is written.

## Touch to tone on the iPhone (latency film)

Not measured: the latency film was cut.

## Release to first word on the iPhone (latency film)

Not measured: the latency film was cut.
