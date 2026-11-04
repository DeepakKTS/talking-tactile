# Next fix: snap each tapped corner to its printed L mark

Status: design only. No code on this branch yet, and nothing here changes behavior. It lands
after the hackathon, with its tests, through the same gates as everything else.

## Why

Explore and the Gate B page map the camera to the sheet from four corner taps. A tap is only
as exact as a finger on a phone screen, and one corner off by a few pixels tilts the whole
mapping. In the Gate B run of Nov 4
(`eval/gate-b/touch-test-2026-11-04T19-54-20-482Z.json`), most of the error came from one
target (target 9, five touches, mean 27.41 mm), including the run's first touch at 77.96 mm,
while the median touch was 4.0 mm. That pattern points at the mapping, not the fingertip.

## What

1. When a corner is tapped, search the current video frame within about 40 px of the tap for
   the corner of the printed L mark (two dark arms, `config/tactile_rules.yaml`
   `mark_arm_mm` 8.0, inset `mark_inset_mm` 12.7 in `config/explore.yaml`).
2. If one clear corner is found, use it, and show the snapped point next to the tap.
3. If not, keep the tap and say "Corner set by tap".
4. The same code runs in Explore (`apps/web/src/explore/corners.ts`) and on the Gate B page
   (`spikes/tracking/calib.js`), held equal by the parity tests, so a Gate B number stays a
   measurement of what Explore does.

## Tests

- Synthetic frames of a printed corner with noise, blur, rotation (up to about 30 degrees)
  and perspective: the snapped point is within 1 px of the true corner; a tap more than 40 px
  away, or a frame with no mark, keeps the tap.
- `uv run spikes/tracking/e2e_check.py session` and the four e2e runs unchanged.
- A new Gate B run on the phone, against the same 4 mm target.
