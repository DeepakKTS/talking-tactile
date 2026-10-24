# Gate B data

Gate B: mean fingertip error of 4 mm or less on the 9 point sheet. The protocol was
decided before the run (TRACKER decision "When the Oct 25 touch test counts as Gate B"):
the test sheet `spikes/tracking/test-sheet.pdf` printed at 100 percent with the 100 mm
bar checked, the demo phone as the camera, 45 touches (9 targets times 5) and normal room
lighting. A run that departs from any of these is a practice run, and Gate B stays pending.

## What goes here

- `touch-test-<finish time, UTC>.json`: the session as the touch-test page downloads
  it, not edited. Version 2 has the clicked corners, the video size, and every frame
  of each touch (landmark pixels, the point before and after the filter).
- `latency.csv`: columns `touch_no, part, frame_enter, frame_earcon, fps`. `frame_enter`
  is the first frame where the fingertip visibly crosses the traced outline.
  `frame_earcon` is the first frame where the audio waveform rises above background
  noise. `fps` is read from the video's file info, not assumed.
- `videos.sha256`: name and sha256 of each latency video. The videos are too large for
  git and stay outside it. These hashes tie the frame counts to the exact files.
- `run.md`: date and time, phone model and browser, video size, printer and the
  measured bar, lighting, the touch count, and any departure from the protocol.

## Run

```
python3 spikes/tracking/analyze_touch.py eval/gate-b/touch-test-....json
```

It recomputes the stats from the raw records and prints the Gate B verdict.
