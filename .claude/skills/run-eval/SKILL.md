---
name: run-eval
description: Run the evaluation suites (authoring part recall, touch accuracy, latency, voice term accuracy, grounded answers) and update eval/RESULTS.md. Use before each gate and before recording the demo.
---

# Run eval

1. `make eval` runs every suite. Use `make eval SUITE=<name>` for one.
2. Suites
   - `authoring`: part recall and label accuracy against `truth.json`, rule violations, seconds per figure
   - `touch`: mean and p95 fingertip error in mm on the 9 point test sheet, region hit rate, false switches per minute
   - `latency`: p50 and p95 for touch to earcon and question to first word
   - `voice`: domain term accuracy with and without keyword hints on the 20 recorded questions
   - `answers`: correctness and correct refusals on the 20 question set
3. Results go to `eval/RESULTS.md` with the date, commit hash and whether mock or live.
4. Compare with the previous run. A drop of more than 5 points on any metric is a blocker for the next gate.
5. Numbers in the demo video and README come only from this file.
