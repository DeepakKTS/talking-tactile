Generated from TRACKER.html by scripts/tracker.py todo. Do not edit by hand.

# TODO.md

Tracker rev 60, updated 2026-10-24T16:59:38.217Z. Change tasks with scripts/tracker.py, then run scripts/tracker.py todo.
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
- [x] d1-4 Repo skeleton and kit (1.5 h)
  - apps/web, services/api, Makefile, CI with lint and tests. Copy the kit and this file into the root.
  - Note: Commit 3c3c1d4 on early-start. apps/web: Vite 8.3.5, React 19.3, TypeScript 6.0.3 strict (noUncheckedIndexedAccess, exactOptionalPropertyTypes), vitest 5, eslint strictTypeChecked, 2 tests. services/api: FastAPI 0.162 on Python 3.11.14 via uv, pytest with warnings as errors, ruff incl. PLR2004 magic-value check on app/, mypy strict, 1 test. make dev/test/lint/typecheck/eval/check. Hook runs make check; probe with a failing staged pytest and a passing unstaged copy: blocked, exit 1, unstaged copy restored.
- [ ] d1-5 Spike Muse Spark (1 h) [blocked]
  - One figure in, structured parts list out. Use the meta-api-spike skill.
  - Note: Script and notes written from the docs: spikes/spark_spike.py (understand case with heart.png and S1 schema, answer case streamed with TTFT and cache check), spikes/muse-spark.md. Dry run passes on Python 3.11 via uv. Blocked on the API key in services/api/.env.
- [ ] d1-6 Spike SAM 3.1 (1.5 h) [blocked]
  - Five phrases on the heart figure. Record mask format, cost and p50 and p95 latency.
  - Fallback: Weak on line art: try the local SAM 3.1 checkpoint with point prompts today.
  - Note: Script and notes written from the docs: spikes/sam_spike.py (5 heart phrases x2 plus text, streamed, parsed with meta-sam-parser, overlays to spikes/out/sam/), spikes/sam.md. Parser wiring and mask placement checked offline with the docs example. Blocked on the API key.
- [ ] d1-7 Spike Muse Voice Transcribe (1 h) [blocked]
  - Stream 10 seconds of audio. Get partial and final text. Try keyword hints.
  - Fallback: Use push-to-talk sync mode if realtime is awkward.
  - Note: Script and notes written from the docs: spikes/voice_spike.py (9.3 s say question with 6 domain terms; 24 kHz with and without keywords, 16 kHz with keywords, 4 runs each; plus the file endpoint), spikes/muse-voice.md. Client checked against a local fake server: pacing 1.005x real time, close 1000. PLAN.md section 17 updated. Blocked on the API key.
- [ ] d1-8 Meta client wrapper (2 h)
  - Timeouts, retry with backoff and jitter, semaphore, cache, cost meter, MOCK_META mode.
- [ ] d1-9 Gate A check (15 min)
  - All three models answer and latencies are written in spikes/.
- [x] d1-10 Regions contract in code (1.5 h)
  - Pydantic models and TypeScript types for regions.json. fixtures/regions/golden.json validated against docs/regions.schema.json from Python and TypeScript, so the two sides cannot drift.
  - Note: Commit f435df1. Python: app/models/regions.py, 52 pytest tests incl. 41 shared cases from fixtures/regions/cases.json and a 600-example hypothesis mutation test (schema vs pydantic agree; it found Literal[1] accepting True). TypeScript: regions.gen.ts generated from the schema, staleness test, ajv 2020 parseRegions, 45 vitest tests on the same golden and cases. Probe: adding an enum value to the schema fails both sides (2 pytest, 2 vitest).
- [x] d1-11 Config loaders (1 h)
  - Load and validate config/tactile_rules.yaml and config/explore.yaml at startup in Python and TypeScript. Tests for missing and invalid values. No magic numbers elsewhere.
  - Note: Commit 2e0ec29. Python app/config.py: pydantic, strict types, extra keys forbidden, no defaults; create_app refuses to start on a bad value; max_area_textures checked against the schema limit. 40 config tests (missing file, YAML syntax, non-mapping, 19 tactile and 14 explore bad values, file named in the error). TypeScript src/shared/config.ts: explore.yaml bundled by a Vite transform, zod strictObject, validated on import in main.tsx; 19 vitest tests. Totals: 92 pytest, 66 vitest.
- [ ] Gate A: Models answer [Pending]
  - Pass when: Muse Spark, SAM 3.1 and Muse Voice all return real results. p50 and p95 latency written in spikes/.
  - Fallback: Weak SAM on line art: local SAM 3.1 checkpoint with point prompts, same day.

## Day 2: Tue Oct 27. Gate B

- [x] d2-1 Camera module, newest frame only (1 h)
  - getUserMedia, drop frames when busy, never queue.
  - Note: Prototype in spikes/tracking (main.js, lib/pump.js): getUserMedia 1280x720, requestVideoFrameCallback, ImageBitmap transferred to a module worker, one frame in flight, drop never queue. Node tests for the pump (4). Headless Chrome with a fake camera and a 100 ms stub worker: camera 20 fps, 78 of 118 frames dropped, max in flight 1, frame to result p95 105.5 ms (no queuing). Port to apps/web on early-start later.
- [x] d2-2 Hand worker with MediaPipe Hand Landmarker (2 h)
  - VIDEO mode, two hands, landmarks only back to the main thread.
  - Note: spikes/tracking/worker.js: MediaPipe tasks-vision 1.1.0 Hand Landmarker in a module worker, VIDEO mode, 2 hands, landmarks only back to the page. Needed forVisionTasks(base, true): module workers have no importScripts (error was 'ModuleFactory not set'). Headless Chrome, 640x480 15 fps clip of a public domain pointing hand: CPU 149 of 155 frames with a hand, infer p50 33.6 ms, keeps up; GPU infer p50 20.7 ms but 8.4 fps processed headless, recheck on real hardware. Load about 0.6 s. Product must vendor the wasm and model for offline (RULES 5.4).
- [x] d2-3 Homography from 4 clicked corners (1 h)
  - 3 x 3 matrix, a few lines of math. Auto registration comes on Day 5.
  - Note: spikes/tracking: lib/homography.js (4 point DLT, convex check for click order), lib/oneeuro.js (per axis, config/explore.yaml values), lib/fingertip.js (pointing hand picker, 4 mm contact offset toward DIP), calib.js (click A to D, overlay of projected sheet and targets, saved per camera size). 18 node tests. Headless: whole frame as sheet, fingertip mapped to 62.7, 69.5 mm, matching the hand math within 0.1 mm, pointing pose recognized. Watch: MediaPipe warns NORM_RECT projection is exact only for square input; check in the touch test.
- [ ] d2-4 Run the 9 point touch test (1 h) [blocked]
  - Print the test sheet, 45 touches, record mean and p95 error in mm.
  - Note: Ready for the user to print and run. spikes/tracking/test-sheet.pdf (Letter, 4 lettered corners, 9 targets, 100 mm bar; measured at 300 dpi: bar 100.41 mm with end caps, target centers within 0.005 mm of sheet.json). Touch test mode: 45 touches (9 x 5, seeded, no back to back repeats), dwell capture 15 mm/s for 600 ms or Space, mean, p95, bias, per target, JSON download. 25 node tests; headless touch flow passes. Waiting on the physical test.
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
- [x] d3-4 S3 reconcile (2 h)
  - Merge near duplicates, nest contained parts, drop slivers, numbered overlay mapping.
  - Note: Commit d9ad1aa. app/geometry/reconcile.py, pure, on Masks. On the synthetic raw masks: 8 parts out, each cleaned part equals its truth mask (speck, text leak, duplicate and sliver handled), core nested under outer chamber, the 45 mm2 lobe overlap goes to the smaller lobe. 82 ms p50 for 10 parts and 8 text masks at 1479 x 2048. The Muse Spark numbered-overlay mapping is not built; it needs the key.
- [x] d3-5 Unit tests for overlap rules (1 h)
  - pytest cases for merge, contain, partial overlap.
  - Note: Written first, in the d3-4 commit d9ad1aa: 17 unit cases (text, specks, sliver, duplicate at and below 0.8 IoU, nested chains, the 0.95 containment threshold, overlap to the smaller part and tie on score, trim speck cleanup, size mismatch) and a 300-example hypothesis property test.
- [x] d3-6 Synthetic test figure (2 h)
  - Generator for fixtures/synthetic/: about 8 labeled shapes with a nested part, two neighbors inside the minimum gap, one part below the point symbol size, fill colors that carry meaning, printed labels, and SAM-like raw masks with a near duplicate, a partial overlap, a sliver, a speck and a text leak. Outputs figure.png, exact truth masks and truth.json. Every geometry test uses it.
  - Note: Commit 0a108bd. Mask type (read-only 2-D bool, label, score, source sam/teacher/synthetic; 16 tests). Generator app/synthetic: exact shapes rasterized at pixel centers, 1479 x 2048 px on the Letter figure area (8.959 px/mm). 8 parts: nested core (clearance above 2x min gap), lobes 2.0 mm apart (only pair under 3.2 mm, checked by distance transform), 4.0 mm pore (only part under 6.4 mm), 4 color categories on a k5 sheet (limit 3). Raw masks: duplicate IoU above 0.8, 45 mm2 lobe overlap, 0.25 mm sliver, 0.8 mm2 speck, text leak equal to the label mask. 12 tests incl. regenerate-and-compare. 168 KB on disk. Totals 130 pytest, 66 vitest.
- [x] d3-7 Vectorize masks and scale to page mm (1.5 h)
  - Contour tracing, simplification to at most 200 points, fit into the Letter or A4 figure area, pixel to mm. Property tests on random shapes.
  - Note: Commit c891307. PageFit (centered fit into the figure area, page mm and back) and mask_to_polygons_mm (contours, mitred half-pixel offset, per-piece polygons, Douglas-Peucker 0.1 mm doubled to the 200 point cap). 13 tests incl. 3 hypothesis properties. Synthetic: worst Hausdorff 0.081 mm, area error under 1 percent, 4 to 65 points per part, 7 ms for 8 parts.

## Day 4: Thu Oct 29

- [x] d4-1 S4 layout (3 h)
  - Polygons in mm, gap enforcement, textures, point symbols.
  - Note: Commit 4a8e2e3. Point symbols (32-gon at least 6.4 mm across at the pole of inaccessibility), gap enforcement by cutting back the larger outline or the child, never a point symbol, by gap + 2 x 0.05 mm, repeated to 8 passes; two point symbols too close are reported, not moved. Textures by median fill color, largest group first, grade limit, pitches from explore.yaml. 14 tests incl. a 150-example property test; a 3000 case stress run: 0 unresolved, 0 pairs under 3.2 mm. Synthetic k5: pore is the only point symbol, right lobe shrunk, 3 textures, inner core untextured. vectorize and color 90 ms, fixes 1 ms. Braille placement is d4-2.
- [ ] d4-2 Braille with liblouis (1.5 h)
  - UEB grade 2, placement, key fallback with abbreviations.
- [ ] d4-3 S5 render (2 h)
  - tactile.svg, print.pdf with 100 mm calibration bar, regions.json, validation report.
- [ ] d4-4 Rules check passes on the heart figure (1 h)
  - tactile-rules-check skill. Fix causes, never loosen rules.
- [ ] d4-5 Print two copies and trace with puffy paint (1 h)
  - Let them dry overnight. Tape the sheet edges for the demo.
  - Fallback: Hot glue or layered card.
- [x] d4-6 Centroids and neighbor directions (1 h)
  - Point inside each region, neighbors within a set distance, 8 directions plus inside and around, all from code. Property tests for symmetry.
  - Note: Commit 1625b6e. app/geometry/neighbors.py: centroid_mm at the pole of inaccessibility (inside even for a C shape), neighbors within 20 mm plus direct inside/around, direction of the shortest outline-to-outline line in 8 sectors. 19 tests incl. 3 hypothesis properties (symmetry, quarter turn of the sheet, centroid inside). Synthetic: vessel down from outer chamber, right lobe right of left lobe, stem has left lobe up.
- [x] d4-7 Tactile rules validator (1.5 h)
  - tactile-rules-check skill: gaps, texture count, point symbol size, polygon validity and page bounds, later braille and SVG ids. Must find every planted violation in the synthetic figure before the fixes and none after.
  - Note: Commit 15d6759. app/geometry/validate.py on a Sheet: ids and parents, polygon validity and 200 point cap, figure area bounds, 3.2 mm gap between outlines and inside a parent, point symbol size, area texture count per grade band; each violation has regions, measured value and limit. Synthetic, before fixes: exactly the planted set (min_gap lobes 2.01 mm, point_symbol pore 4.04 mm, texture_count 5 over 3), from truth masks and from reconciled raw masks. After fixes: none. 16 tests. Braille clearance and SVG id checks are added in d4-2 and d4-3; the CLI from the skill comes with storage in Phase 5.

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
- [ ] d9-5 Credit the CC BY-SA heart figure in the README and demo video (15 min)
  - Use the credit line in ATTRIBUTION.md: Heart diagram-en.svg by ZooFari, CC BY-SA 3.0, via Wikimedia Commons. State that the tactile sheet and its files are adaptations shared under CC BY-SA 3.0.
  - Fallback: A credits slide at the end of the video and a Credits section in the README.
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
