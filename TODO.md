Generated from TRACKER.html by scripts/tracker.py todo. Do not edit by hand.

# TODO.md

Tracker rev 18, updated 2026-10-24T06:37:11.217Z. Change tasks with scripts/tracker.py, then run scripts/tracker.py todo.
If a task runs 50 percent over its time box, take its fallback. If it has none, propose one first.

## Day 0: Oct 23 to 25

- [ ] d0-1 Submit the hackathon application (1 h)
  - Use the crisp answers in Handbook, Application answers. One application only.
- [ ] d0-2 Make the Weavory repo public and its README current (30 min)
  - Reviewers will click github.com/DeepakKTS/weavory.ai. Check the 232 tests and npm link are visible.
- [ ] d0-3 Email Northeastern disability services (20 min)
  - Ask for a student who reads tactile graphics, or staff who make them, for a 15 to 30 minute session between Nov 1 and Nov 3.
- [ ] d0-4 Email Perkins School for the Blind (20 min)
  - Ask an educator or transcriber for a remote review of one tactile sheet and the talking layer.
- [ ] d0-5 Email one braille transcription service (20 min)
  - Ask for a short remote design review of a print PDF. Offer to credit them.
- [ ] d0-6 Buy materials (1 h)
  - Puffy fabric paint in 2 colors, heavy cardstock, a phone stand or gooseneck clamp, masking tape, a ruler.
  - Fallback: Hot glue and layered card also work.
- [ ] d0-7 Read BANA tactile graphics guidelines, units 1 to 3 (2 h)
  - Use the 2022 edition. Note anything that changes config/tactile_rules.yaml.
- [x] d0-8 List 20 openly licensed figures for the eval set (1.5 h)
  - 5 labeled diagrams, 5 bar charts, 5 line graphs, 5 maps. Write the license next to each.
  - Note: spikes/eval-figures.md: 20 figures, 5 per type, all on Wikimedia Commons. Licenses: 7 PD, 1 CC0, 7 CC BY 4.0, 5 CC BY-SA 3.0/4.0, each checked on the file page and the Commons API, then rechecked independently (20 of 20 match). fixtures/heart.png is Heart_diagram-en.svg by ZooFari, CC BY-SA 3.0, 2048x1612 on white. Learned: Commons thumbnails come back at 3840 px with transparent backgrounds, so S0 must flatten onto white and resize locally; CC BY-SA figures need the license carried onto the tactile sheet.
- [ ] d0-9 Note phone model and laptop GPU (10 min)
  - Baseline for the Day 2 device decision.

## Day 1: Mon Oct 26. Gate A

- [ ] d1-1 Watch kickoff, read and accept the Official Rules (1.5 h)
  - Write anything that changes the plan into PLAN.md section 17 and a decision here.
- [x] d1-2 Check what Muse Wonder is (20 min)
  - It is listed on the event page. Read its docs and decide if it has a real job here. Default answer: no.
  - Note: Read dev.meta.ai/docs/models and pricing-rate-limits. Wonder is muse-wonder-1.0, preview, 1M context, same request shape as Spark, 4.00/20.00 per 1M tokens. Decision: no job in the product; optional S1 comparison only if Spark recall misses 80 percent. Also noted: rate limit table says sam-3.1, models table says sam-3-1; SAM spike will confirm.
- [ ] d1-3 Get the API key and credits, set BUDGET_USD (20 min)
  - Key goes only in services/api/.env.
- [ ] d1-4 Repo skeleton and kit (1.5 h)
  - apps/web, services/api, Makefile, CI with lint and tests. Copy the kit and this file into the root.
  - Note: Pin Python 3.11 for services/api with uv (uv python pin 3.11, then uv venv); system python3 is 3.13. Check that the liblouis Python bindings (louis) install on macOS. Fallback: call lou_translate through subprocess.
- [ ] d1-5 Spike Muse Spark (1 h) [blocked]
  - One figure in, structured parts list out. Use the meta-api-spike skill.
  - Note: Script and notes written from the docs: spikes/spark_spike.py (understand case with heart.png and S1 schema, answer case streamed with TTFT and cache check), spikes/muse-spark.md. Dry run passes on Python 3.11 via uv. Blocked on the API key in services/api/.env.
- [ ] d1-6 Spike SAM 3.1 (1.5 h) [blocked]
  - Five phrases on the heart figure. Record mask format, cost and p50 and p95 latency.
  - Fallback: Weak on line art: try the local SAM 3.1 checkpoint with point prompts today.
  - Note: Script and notes written from the docs: spikes/sam_spike.py (5 heart phrases x2 plus text, streamed, parsed with meta-sam-parser, overlays to spikes/out/sam/), spikes/sam.md. Parser wiring and mask placement checked offline with the docs example. Blocked on the API key.
- [ ] d1-7 Spike Muse Voice Transcribe (1 h)
  - Stream 10 seconds of audio. Get partial and final text. Try keyword hints.
  - Fallback: Use push-to-talk sync mode if realtime is awkward.
- [ ] d1-8 Meta client wrapper (2 h)
  - Timeouts, retry with backoff and jitter, semaphore, cache, cost meter, MOCK_META mode.
- [ ] d1-9 Gate A check (15 min)
  - All three models answer and latencies are written in spikes/.
- [ ] Gate A: Models answer [Pending]
  - Pass when: Muse Spark, SAM 3.1 and Muse Voice all return real results. p50 and p95 latency written in spikes/.
  - Fallback: Weak SAM on line art: local SAM 3.1 checkpoint with point prompts, same day.

## Day 2: Tue Oct 27. Gate B

- [ ] d2-1 Camera module, newest frame only (1 h)
  - getUserMedia, drop frames when busy, never queue.
- [ ] d2-2 Hand worker with MediaPipe Hand Landmarker (2 h)
  - VIDEO mode, two hands, landmarks only back to the main thread.
- [ ] d2-3 Homography from 4 clicked corners (1 h)
  - 3 x 3 matrix, a few lines of math. Auto registration comes on Day 5.
- [ ] d2-4 Run the 9 point touch test (1 h)
  - Print the test sheet, 45 touches, record mean and p95 error in mm.
- [ ] d2-5 Measure fps on phone browser and laptop (30 min)
  - Pick the device for Explore.
  - Fallback: Laptop plus phone as webcam.
- [ ] d2-6 Record hand touch videos for replay tests (30 min)
  - Lets tracking accuracy be measured the same way every run, with no person needed.
- [ ] d2-7 Gate B check (15 min)
  - Mean fingertip error 4 mm or less.
  - Fallback: Require the pointing pose, dwell 800 ms, parts above 12 mm.
- [ ] Gate B: Tracking is accurate [Pending]
  - Pass when: Mean fingertip error of 4 mm or less on the 9 point sheet.
  - Fallback: Require the pointing pose, dwell 800 ms, keep parts above 12 mm.

## Day 3: Wed Oct 28

- [ ] d3-1 S0 ingest (2 h)
  - Type and size check, PDF page render, deskew, blur check, 2048 px, hash.
- [ ] d3-2 S1 understand (2 h)
  - Muse Spark structured output: type, title, summary, parts, color meaning, verdict.
- [ ] d3-3 S2 ground (2 h)
  - One SAM 3.1 call per phrase, four at a time, plus print text.
- [ ] d3-4 S3 reconcile (2 h)
  - Merge near duplicates, nest contained parts, drop slivers, numbered overlay mapping.
- [ ] d3-5 Unit tests for overlap rules (1 h)
  - pytest cases for merge, contain, partial overlap.

## Day 4: Thu Oct 29

- [ ] d4-1 S4 layout (3 h)
  - Polygons in mm, gap enforcement, textures, point symbols.
- [ ] d4-2 Braille with liblouis (1.5 h)
  - UEB grade 2, placement, key fallback with abbreviations.
- [ ] d4-3 S5 render (2 h)
  - tactile.svg, print.pdf with 100 mm calibration bar, regions.json, validation report.
- [ ] d4-4 Rules check passes on the heart figure (1 h)
  - tactile-rules-check skill. Fix causes, never loosen rules.
- [ ] d4-5 Print two copies and trace with puffy paint (1 h)
  - Let them dry overnight. Tape the sheet edges for the demo.
  - Fallback: Hot glue or layered card.

## Day 5: Fri Oct 30. Gate C

- [ ] d5-1 Auto registration (2.5 h)
  - /api/register: OpenCV outline first, SAM fallback, four rotation check, confidence.
- [ ] d5-2 Region engine and state machine (2.5 h)
  - Box check, point-in-polygon, hysteresis, dwell, vitest coverage.
- [ ] d5-3 Earcons, dwell labels, exit tick, more (1.5 h)
  - Earcons decoded once. Cap at 6 per second.
- [ ] d5-4 Offline mode (1 h)
  - Labels, earcons and guidance work with the network off.
- [ ] d5-5 Gate C check (30 min)
  - The heart figure works end to end on the real traced sheet.
  - Fallback: Cut Plus features, spend Day 6 on the loop.
- [ ] Gate C: One figure end to end [Pending]
  - Pass when: The heart figure: upload, print, trace, explore, labels spoken, on the real sheet.
  - Fallback: Cut Plus features. Spend Day 6 on the loop only.

## Day 6: Sat Oct 31

- [ ] d6-1 Voice capture and proxy (2.5 h)
  - AudioWorklet, 16 kHz mono, /api/voice relay, keyword hints from labels.
- [ ] d6-2 Local intent parser (1 h)
  - where is, more, repeat, stop, what is here.
- [ ] d6-3 Grounded answers (2 h)
  - /api/ask with the cached figure context, streamed, first sentence spoken early.
- [ ] d6-4 Barge-in (30 min)
  - Space cancels speech and starts listening.
- [ ] d6-5 Guidance mode (2 h)
  - Direction in words once, beeps speed up, chime and label on arrival.

## Day 7: Sun Nov 1

- [ ] d7-1 Teacher review screen (3 h)
  - Edit, merge, delete, add by name, publish.
- [ ] d7-2 Accessibility pass (1.5 h)
  - Keyboard only, VoiceOver or NVDA, onboarding audio. accessibility-pass skill.
- [ ] d7-3 Tester session or remote expert review (1.5 h)
  - Record tasks, times and their own words, with consent.
  - Fallback: Expert review of the print PDF, or an honest README note.
- [ ] d7-4 Evidence-based design table (1 h)
  - Map each design choice to its source: BANA, APH, CamIO user feedback.

## Day 8: Mon Nov 2

- [ ] d8-1 Fix the top three issues (3 h)
  - From testing and the Issues tab.
- [ ] d8-2 Three more figure types (2.5 h)
  - add-figure-type skill.
- [ ] d8-3 Run every eval suite (1.5 h)
  - run-eval skill. Fill the Metrics tab from eval/RESULTS.md.

## Day 9: Tue Nov 3. Gate D

- [ ] d9-1 Feature freeze at noon (0)
  - Only bug fixes, video and README after this.
- [ ] d9-2 Demo readiness checklist (1 h)
  - demo-readiness skill. Passes twice in a row.
- [ ] d9-3 Record the demo video (2 h)
  - Two takes minimum. Only steps that work every time.
  - Fallback: Cut the failing step from the script.
- [ ] d9-4 README with measured numbers (1.5 h)
  - Setup, models and why, numbers from RESULTS.md, honest tester status.
- [ ] Gate D: Demo ready [Pending]
  - Pass when: Demo readiness checklist passes twice in a row, live, with no restart.
  - Fallback: Cut the failing step from the script. Never record a flaky step.

## Day 10: Wed Nov 4

- [ ] d10-1 Fresh clone test (45 min)
  - Clone, make dev, run the demo script once.
- [ ] d10-2 Submit by 3 PM ET (30 min)
  - The official deadline is 9 PM ET. Do not use it.

## Open issues

None. Add one with scripts/tracker.py issue.
