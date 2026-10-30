Generated from TRACKER.html by scripts/tracker.py todo. Do not edit by hand.

# TODO.md

Tracker rev 181, updated 2026-10-30T17:48:24.916Z. Change tasks with scripts/tracker.py, then run scripts/tracker.py todo.
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

- [x] d1-1 Watch kickoff, read and accept the Official Rules (1.5 h)
  - Write anything that changes the plan into PLAN.md section 17 and a decision here.
  - Note: Deepak read and accepted the Official Rules on Oct 27. Pre-event work is allowed; see the decision Official Rules read by Deepak.
- [x] d1-2 Check what Muse Wonder is (20 min)
  - It is listed on the event page. Read its docs and decide if it has a real job here. Default answer: no.
  - Note: Read dev.meta.ai/docs/models and pricing-rate-limits. Wonder is muse-wonder-1.0, preview, 1M context, same request shape as Spark, 4.00/20.00 per 1M tokens. Decision: no job in the product; optional S1 comparison only if Spark recall misses 80 percent. Also noted: rate limit table says sam-3.1, models table says sam-3-1; SAM spike will confirm.
- [x] d1-3 Get the API key and credits, set BUDGET_USD (20 min)
  - Key goes only in services/api/.env.
  - Note: Key verified Oct 27: one live call per model through app/meta/smoke.py, all HTTP 200. Spark text 1858 ms, $0.00166 (353 of 384 completion tokens were reasoning). SAM sam-3.1 on heart.png 1269 ms, $0.0025, but zero instances of left ventricle (valid empty result; SAM quality on line art still open). Voice file endpoint 1205 ms, $0.00015, heard aorta as order without keywords. Total $0.00431, 3 lines in eval/live/ledger.jsonl. BUDGET_USD stays 150 (config meta.budget_usd). Credits balance not checked: no balance endpoint was called.
- [x] d1-4 Repo skeleton and kit (1.5 h)
  - apps/web, services/api, Makefile, CI with lint and tests. Copy the kit and this file into the root.
  - Note: Commit 3c3c1d4 on early-start. apps/web: Vite 8.3.5, React 19.3, TypeScript 6.0.3 strict (noUncheckedIndexedAccess, exactOptionalPropertyTypes), vitest 5, eslint strictTypeChecked, 2 tests. services/api: FastAPI 0.162 on Python 3.11.14 via uv, pytest with warnings as errors, ruff incl. PLR2004 magic-value check on app/, mypy strict, 1 test. make dev/test/lint/typecheck/eval/check. Hook runs make check; probe with a failing staged pytest and a passing unstaged copy: blocked, exit 1, unstaged copy restored.
- [ ] d1-5 Spike Muse Spark (1 h) [blocked]
  - One figure in, structured parts list out. Use the meta-api-spike skill.
  - Note: Script and notes written from the docs: spikes/spark_spike.py (understand case with heart.png and S1 schema, answer case streamed with TTFT and cache check), spikes/muse-spark.md. Dry run passes on Python 3.11 via uv. Blocked on the API key in services/api/.env.
- [ ] d1-6 Spike SAM 3.1 (1.5 h) [doing]
  - Five phrases on the heart figure. Record mask format, cost and p50 and p95 latency.
  - Fallback: Weak on line art: try the local SAM 3.1 checkpoint with point prompts today.
  - Note: Oct 29 SAM diagnostic (app/meta/sam_diagnostic.py, 8 live calls, $0.020, spikes/sam.md): banana control 1 instance at 0.977, heart.png whole 1 at 0.570, left ventricle, aorta and right atrium 0 in both phrasings. Request and mask decoding verified on both answers. A raster can be smaller than its bounds (668 x 1024 for 928 x 1423). Waiting for Deepak's review before 4.2. SAM p50 and p95 not measured: only 2 answers had instances.
- [ ] d1-7 Spike Muse Voice Transcribe (1 h) [blocked]
  - Stream 10 seconds of audio. Get partial and final text. Try keyword hints.
  - Fallback: Use push-to-talk sync mode if realtime is awkward.
  - Note: Script and notes written from the docs: spikes/voice_spike.py (9.3 s say question with 6 domain terms; 24 kHz with and without keywords, 16 kHz with keywords, 4 runs each; plus the file endpoint), spikes/muse-voice.md. Client checked against a local fake server: pacing 1.005x real time, close 1000. PLAN.md section 17 updated. Blocked on the API key.
- [x] d1-8 Meta client wrapper (2 h)
  - Timeouts, retry with backoff and jitter, semaphore, cache, cost meter, MOCK_META mode.
  - Note: Live S1 and S2 in the pipeline (dc76d92 to 64a123b). S1 live = listing + locate (kind, members, parent, instances, points). S2 = Arm A v2f in app/pipeline/s2_points.py, SAM 4 at a time, spill retry, oversize rule at 50%, background points dropped, flags into regions.json v2 (touchable, flags, needs_teacher). One call cap per job. Live heart through the API, Oct 30: 25 calls (2 Spark, 19 SAM, 4 retries; 3 more retries refused by the cap), $0.096317; S1 30.6 s, S2 28.9 s, end to end 61.3 s; S5 first failed on a texture bug (72ee37b) and finished from the cache with no new call. 15 of 19 parts touchable, 4 spill, 3 thin, 0 rule violations. Replay e2e test reproduces the published regions.json exactly. Arm B and the v2 harness deleted; API suite 88.2 s to 79.0 s.
- [ ] d1-9 Gate A check (15 min)
  - All three models answer and latencies are written in spikes/.
- [x] d1-10 Regions contract in code (1.5 h)
  - Pydantic models and TypeScript types for regions.json. fixtures/regions/golden.json validated against docs/regions.schema.json from Python and TypeScript, so the two sides cannot drift.
  - Note: Commit f435df1. Python: app/models/regions.py, 52 pytest tests incl. 41 shared cases from fixtures/regions/cases.json and a 600-example hypothesis mutation test (schema vs pydantic agree; it found Literal[1] accepting True). TypeScript: regions.gen.ts generated from the schema, staleness test, ajv 2020 parseRegions, 45 vitest tests on the same golden and cases. Probe: adding an enum value to the schema fails both sides (2 pytest, 2 vitest).
- [x] d1-11 Config loaders (1 h)
  - Load and validate config/tactile_rules.yaml and config/explore.yaml at startup in Python and TypeScript. Tests for missing and invalid values. No magic numbers elsewhere.
  - Note: Commit 2e0ec29. Python app/config.py: pydantic, strict types, extra keys forbidden, no defaults; create_app refuses to start on a bad value; max_area_textures checked against the schema limit. 40 config tests (missing file, YAML syntax, non-mapping, 19 tactile and 14 explore bad values, file named in the error). TypeScript src/shared/config.ts: explore.yaml bundled by a Vite transform, zod strictObject, validated on import in main.tsx; 19 vitest tests. Totals: 92 pytest, 66 vitest.
- [x] d1-12 Meta client interface, mock and SAM adapter stub (1.5 h)
  - MetaClient protocol (understand, segment), MockMetaClient serving the synthetic figure's truth, cost meter with budget warnings, app/meta/sam_adapter.py as a documented stub. The real client is d1-8 and waits for the spikes.
  - Note: Commit 9eab058. MetaClient protocol, MockMetaClient (synthetic S1 answer with 9 phrases incl. a duplicate proposal, every SAM instance per phrase incl. the sliver, zero matches as [], unknown image refused), CostMeter (Spark with cached input, SAM per image, voice per hour; warns at 0.7 and 0.9; refuses calls past the budget), sam_adapter stub with the documented format, boundary test that no other app module mentions the SAM encoding. Live mode refuses with a pointer to MOCK_META=1. 13 tests.
- [x] Gate A: Models answer [Passed]
  - Pass when: Muse Spark, SAM 3.1 and Muse Voice all return real results. p50 and p95 latency written in spikes/.
  - Fallback: Weak SAM on line art: local SAM 3.1 checkpoint with point prompts, same day.
  - Evidence: Criteria as written met: Spark, SAM and Voice returned real results; p50/p95 in spikes/. SAM numbers are from point prompts; text-prompt part segmentation returned zero instances on line art. Realtime Voice untested. S2 quality is decided by the bake-off grading, not by this gate.

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
  - Note: Ready for the user to print and run. spikes/tracking/test-sheet.pdf (Letter, 4 lettered corners, 9 targets, 100 mm bar; measured at 300 dpi: bar 100.41 mm with end caps, target centers within 0.005 mm of sheet.json). Touch test mode: 45 touches (9 x 5, seeded, no back to back repeats), dwell capture 15 mm/s for 600 ms or Space, mean, p95, bias, per target, JSON download. 41 node tests (counted Oct 27 with npm test in spikes/tracking; was 25 on Oct 24); headless touch flow passes. Waiting on the physical test, protocol in eval/gate-b/README.md.
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

- [x] d3-1 S0 ingest (2 h)
  - Type and size check, PDF page render, deskew, blur check, 2048 px, hash.
  - Note: Commit 20a637d. app/pipeline/s0_ingest.py, pure. Content sniffing, 10 MB guard before decoding, pypdfium2 page render at 200 dpi with page index, transparency to white, deskew only for a bright quad over 20 to 98 percent of the photo with 40 levels contrast (a chart frame is not cropped), blur floor 0.15 measured on synthetic and heart (sharp 0.49 to 0.56, 4 px blur 0.09 to 0.13), sha256 of normalized pixels. 22 tests. Synthetic PNG 34 ms, photo deskew 63 ms (90 percent of ink within 10 px), PDF 83 ms.
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
- [x] d3-8 Pipeline runner with stage cache and SQLite jobs (2 h)
  - S0 to S5 in order, content-hash cache per stage under data/figures/<sha256>/, job records in SQLite with stage timings, mock S1 and S2.
  - Note: Commit 73687bf on early-start. app/pipeline/runner.py: submit runs S0 (bad upload makes no job), run takes S1 to S5 with mock S1 and S2. One file per stage s1_understand to s5_render, each with save and load for the cache. Cache under data/figures/<figure_id>/<stage>/<key>/, key chain over the previous key: S1 and S2 on client mode, version, max_parts and text phrase (a code change never pays for a call again); S3 to S5 on the source hash, config and job options. Resumes after the latest cached stage, rebuilds an unreadable entry, writes through a temp dir and rename. S2 keeps to sam_concurrency (tested at 4). describe_only stops after S1. SQLite jobs and stage_runs (ran, cached, skipped; ms; cost). Mock synthetic figure: cold run S0 65, S1 47, S2 23, S3 106, S4 403, S5 65 ms (1.16 s process); same upload again 55 ms with zero Meta calls, same regions.json. 12 tests, 319 api tests pass. Live mode waits on d1-8. Numbered overlay Spark pass in S3 not built (needs the spike).
- [x] d3-9 Figure API routes and middleware (2 h)
  - POST /api/figures, GET status, regions.json, tactile.svg, print.pdf, PATCH a region, POST publish. Request id, JSON logs, error envelope, upload guard, CORS. API test runs the synthetic figure end to end.
  - Note: Commit 5525b68 on early-start. POST /api/figures (idempotent per image, options and edit version), GET status, draft regions.json, tactile.svg, print.pdf, PATCH /regions/{rid} (label, describe, merge, delete), POST /regions (add by name through SAM, cached), POST publish (numbered read-only copies in data/published), GET published index and published/{n or latest}/{file} for Explore. Figure id checked as 64 lowercase hex before any path, also inside FigureCache. Edits are a versioned SQLite layer, replayed on S3 parts before S4; their hash joins the S4 and S5 keys, so an edit re-runs S4 and S5 only. Middleware: request id (echoed when well formed), JSON logs with stage, ms, cost and the request id carried into pipeline tasks, error envelope, upload guard (Content-Length over 10 MB plus form slack is 413 before reading; S0 refuses the rest; PNG, JPEG or one PDF page), CORS for localhost:5173 only. ETag is the sha256, 304 on If-None-Match. 29 API tests (end to end upload, edit, publish, fetch; duplicate; concurrent double submit; concurrent publish and edits, which fail without the lock; 10 bad id and traversal paths; oversized; wrong type; bad edits; CORS; live mode 503), 15 edit tests. Smoke tested over HTTP with uvicorn. Found and fixed: regions.json wrote grade_band null when no grade band was given, so S5 failed.
- [x] d3-10 Cache keys cover prompts, upstream outputs and mock fixtures (1.5 h)
  - S1 and S2 keys hash the prompt file and response schema (prompts in app/prompts/). Every key includes the digests of the upstream outputs it consumed. Mock mode keys hash the fixture files. A test for each that would have caught the silent stale hit.
  - Note: Commit 5525b68 on early-start. Prompts moved to app/prompts/s1_understand.v1.json and s2_ground.v1.json; the Prompt object hashed into the key is the one passed to the client. S1 and S2 keys add the response schema digest and MetaClient.cache_tag (mock: sha256 over the fixture files). Every key adds the digests of the upstream outputs it consumed; each entry writes .digest last and a hit must match it, so a damaged entry is rebuilt. Tests, each checked to fail with its key input removed: one character in the S1 prompt re-runs S1 to S5; a new S1 answer under the same key re-runs S2 to S5 with S0 cached and the new title in regions.json; an edited truth.json re-runs S1 to S5 with no manual deletion. Mock synthetic cold S1 60, S2 26, S3 115, S4 405, S5 66 ms; warm hits 0 to 3 ms each including digest checks.

## Day 4: Thu Oct 29

- [x] d4-1 S4 layout (3 h)
  - Polygons in mm, gap enforcement, textures, point symbols.
  - Note: Commit 4a8e2e3. Point symbols (32-gon at least 6.4 mm across at the pole of inaccessibility), gap enforcement by cutting back the larger outline or the child, never a point symbol, by gap + 2 x 0.05 mm, repeated to 8 passes; two point symbols too close are reported, not moved. Textures by median fill color, largest group first, grade limit, pitches from explore.yaml. 14 tests incl. a 150-example property test; a 3000 case stress run: 0 unresolved, 0 pairs under 3.2 mm. Synthetic k5: pore is the only point symbol, right lobe shrunk, 3 textures, inner core untextured. vectorize and color 90 ms, fixes 1 ms. Braille placement is d4-2.
- [x] d4-2 Braille with liblouis (1.5 h)
  - UEB grade 2, placement, key fallback with abbreviations.
  - Note: Commit 8518864. lou_translate subprocess (decision recorded), UEB grade 2: 'left ventricle' contracts en, capital and number signs, grade 1 indicator for lone letters. Placement: label inside, abbreviation inside, abbreviation beside within 15 mm, key only; 3.7 mm clearance to every outline, 3.2 mm between blocks; validator extended with braille_clearance, braille_gap, braille_overlap. Synthetic: cross vessel, left lobe, right lobe labels inside; oc, ic, rc inside; po, st beside; key of 5; none key only; validator clean. 27 tests incl. 2 hypothesis properties. translate 12 ms, place 200 ms. Needs brew install liblouis on a fresh machine.
- [x] d4-3 S5 render (2 h)
  - tactile.svg, print.pdf with 100 mm calibration bar, regions.json, validation report.
  - Note: Commits a2ca503 and 88fe8fe. tactile.svg layers guides, textures, outlines, braille; L marks 12.7 mm in (explore.yaml, shared with Explore); 1 mm outlines inside each edge (gaps, nested clearance and braille clearance now count it); textures 3.2 mm inside, off children, 3.7 mm off braille, pieces under 4 mm dropped; key pages with abbreviations and texture samples; print.pdf via cairosvg 2.9.1 (works with Homebrew cairo 1.18.4) and pypdf; regions.json valid against the schema; SVG ids match. Print scale at 300 dpi with pdftoppm: 2550 x 3300 px, bar 1182 px = 100.08 mm, lobe edge and mark corner within 0.2 mm. make synthetic-sheet writes data/synthetic/print.pdf, 2 pages, 0 violations. Render 23 ms, PDF 162 ms. 12 render tests.
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
- [x] d5-2 Region engine and state machine (2.5 h)
  - Box check, point-in-polygon, hysteresis, dwell, vitest coverage.
  - Note: Commits 2099e86, 9967ea0 on early-start. apps/web/src/explore: regionIndex.ts (box check, even-odd point in polygon, signed edge distance for shrunk and grown outlines, smallest area first, earcon pitch from texture) and touch.ts (enter on outline shrunk 1 mm, 120 ms hold then earcon; dwell under 15 mm/s for 600 ms then label once; exit on outline grown 2 mm, 120 ms then tick; earcons and ticks capped 6 per second; speed over a 200 ms window, dwell clock backdated to the window start). Every value from explore.yaml. fast-check, 300 runs each: border rest with jitter under 1 mm never flickers; scanning at 25 mm/s or more never speaks a label and stays capped; each property fails with its mechanism removed. Region lookup 0.39 us per point on the synthetic sheet (8 regions), 2.96 us at 60 regions of 200 points.
- [x] d5-3 Earcons, dwell labels, exit tick, more (1.5 h)
  - Earcons decoded once. Cap at 6 per second.
  - Note: Commits 85fa08d, b0ce014, d7a609a on early-start. audio.ts renders every earcon pitch, the exit tick, the guidance beep and the 3 note chime once at start (9 AudioBuffers for the synthetic sheet, none rendered after). Dwell labels, exit tick and more (description, or two neighbors in words from regions.json) in session.ts. Headless Chrome: 24 of 24 touches online gave earcon then label; frame to earcon 0.2 ms p50, 0.3 ms p95; dwell met to label handed to speech 0.4 ms p50, 0.5 ms p95.
- [x] d5-4 Offline mode (1 h)
  - Labels, earcons and guidance work with the network off.
  - Note: Commit d7a609a on early-start. Headless run with the network off after load: all 8 parts earcon then label, guidance sentence, beeps and arrival chime work, a question says 'Questions need the network. Labels still work.' MediaPipe wasm and model are served by the app; the camera run refused every non-local request and still loaded mediapipe GPU (0 refused). The last published regions.json is kept in localStorage for an offline reopen. A page reload with no network still needs the app files (no service worker, by choice).
- [ ] d5-5 Gate C check (30 min)
  - The heart figure works end to end on the real traced sheet.
  - Fallback: Cut Plus features, spend Day 6 on the loop.
- [x] d5-6 Tactile-aware part planning: S1 plans areas, lines, groups, parents, shared regions and subject; S2, sheet, Explore and Author use the plan (this phase)
  - Live brain run fa460241: 5 of 12 touchable; sulci got points, gyri nested in lobes read as spill, pons, medulla and spinal cord one shape. Re-run heart, flower, Japan against graded references; brain uploaded and an openly licensed brain from Commons.
  - Note: S1 locate v2 plans for touch (grade band, printed size, minimum part and gap): area, line, group, parent, separates, shares_region, subject; S1 key holds the job options. S2: lines get no call and never need the teacher; spill excuses Spark's children, parts nested in the checked mask (NEST_INSIDE 0.95 from the eval masks, not 0.9) and shared regions (IoU 0.8 or Spark); nesting re-tested on kept masks; near-identical masks split by the nearer point; merge proposals; silhouette by one SAM phrase call. S4: lines in the key, silhouette contour raised clear of every outline and braille, checked by the validator. regions.json v3 (subject, lines, merge_proposals; PLAN.md migration). Explore: crossing a line says 'line, part' with the earcon (enter hold and earcon cap kept), code path 0.8 ms headless (plan_e2e, frameToBoundaryMs); resting on the silhouette on no part says the subject once per entry. Author: Needs you, For your information, one merge button per proposal. Live, replayed in app/meta/plan_eval.py (eval/plan/RESULTS.md): heart 14 of 15 areas touchable, needs you 1 (septum spill), references 3 held, 1 improved (left common carotid 0.0 to 0.927), 0 regressed; Japan 9 of 9, 6 held, 1 improved (Kansai 0.612 to 0.804); flower 12 of 13, needs you 1, its 5 references all below 0.8 as in v2f (ovary 0.245 to 0.0, pollen sac 0.476 to 0.367: Spark's points moved); uploaded brain 10 of 10 areas (was 5 of 12 parts), needs you 0, 2 lines, 2 merge proposals, silhouette in regions.json with 0 raised pieces; Commons brain (Blausen 0111, CC BY 3.0) 5 of 6, olfactory bulb no points. 107 live calls, $0.476566. Rules: heart 1 point-symbol violation (clears with the aortic arch merge), flower 31 from its groups' nesting in S3/S4, none from the silhouette.
- [x] d5-7 Drawn boundary evidence: merges only where the image shows no boundary; same outlines to the teacher (this phase)
  - Note: app/geometry/boundaries.py: drawn regions (ink and color edges over EDGE_STEP 14, grown 1 px, 4-connected) and fill colors (FILL_DELTA 55); both chosen from the pairs S2 judged on the five figures (eval/plan/RESULTS.md, Drawn boundaries). S2: Spark's shares_region keeps the largest set with no boundary, the rest left out with the reason (MergeProposal.left_out, flags); IoU 0.8 pairs with a boundary send the smaller to the teacher as same_outline (S5: a spill-style suggestion), with none they are a merge proposal and no longer split. Replay of the live recordings, no calls: heart, Japan, Commons brain unchanged (heart draft equals its fixture; aortic arch keeps 4 members). Uploaded brain: 8 of 10 areas touchable (was 10); needs you parietal lobe (same outline as postcentral gyrus) and pons (same outline as cerebellum); brainstem proposal pons, medulla, spinal cord, cerebellum dropped; but medulla loses every pixel to spinal cord (IoU 0.97, no split) and is dropped as empty, so regions.json has no proposal left; medulla and spinal cord now nest in the cerebellum's mask, which covers the brainstem. Flower: 6 of 13 (was 12): connective, filament, ovules same outline; stigma, style, ovary no longer share a region, so their spill retries are asked for and have no recording; references keep their verdicts (all still below 0.8; anther 0.198 to 0.421, connective 0.068 to 0.0). Tests: test_boundaries.py, S2 merge and same-outline tests, S5 mapping.
- [x] d5-8 Groups are not drawn: members drawn as themselves, spoken with their group (this phase)
  - Note: S2 no longer unites group masks; runner._grounded drops groups for S3 and S5 (s3_reconcile.without_groups), S3's key holds S1. plan.sheet_groups maps each member's part id to the group that lists it; regions.json region.group (optional, within v3, PLAN.md note; golden fixture has one). Explore: dwell, 'what is here', guidance arrival and a line crossing say 'anther, part of the stamen'. Author: For your information lists 'stamen A group of anther and filament'. Flower rule violations, replay of the live recordings: 2 before, 0 after (all from the perianth group); with last phase's S2 (no boundary evidence) 31 before, 7 after, none from a group (style pieces, connective and microsporangium, anther pieces, two point symbols). Flower: pistil no longer needs the teacher. Heart, Japan, both brains unchanged. Tests: S2, plan, render, contract (Python and Ajv), Explore session, Author; plan_e2e, fix_e2e, explore_e2e pass.
- [x] d5-9 Republish the demo figures on regions.json v3: heart after the aortic arch merge, the Commons brain (this phase)
  - Note: Published into the dev data dir (data/, what make dev serves) through Author in headless Chrome on a mock-mode API answering from the live recordings: no network, no spend. A repeated upload returns the figure's existing job unless it failed, so the heart's two done jobs from before the plan's merge proposals were marked failed (error_code superseded) in the git-ignored dev database first (backed up). Heart: one press of 'Merge brachiocephalic artery, left common carotid artery, left subclavian artery and aorta as aortic arch' (3 merges and a rename), rules pass, published version 1, schema 3: 11 touchable parts, septum a suggestion, 4 lines, subject heart, no proposal left. Commons brain (fixtures/recorded/replays.json now indexes it; grade band 6_8 as recorded): no rule failure, published version 1, schema 3: 5 touchable, olfactory bulb in needs_teacher (no points), subject brain. Explore loads both versions (ready, intro names the one untouchable part), no page errors.
- [x] d5-10 Job identity includes the pipeline version: a re-upload after a pipeline change is a new job from the cached stages (this phase)
  - Note: Runner.pipeline_version(options); jobs.pipeline (db schema 3, migrated from 2 in place: tables, rows and publications kept; checked on a copy of the dev database: 2 publications kept, old jobs pipeline None). FigureService.submit and JobStore.find_live match on it; edit runs record it. Tests: an upload after a code change is a new job with S0 to S2 cached, S3 to S5 run, no Meta call, and a third upload returns that job; a version 2 database migrates and its jobs are not reused. No hand edit to the dev database.
- [x] d5-11 Flower: the 3 unrecorded SAM retries live (this phase)
  - Note: Phase A captured the exact requests S2 sends for the flower with no recording (mock run, nothing sent): stigma, style and ovary retries. Phase B sent only those live under caffeinate -i, META_RECORD=plan3_flower: 3 SAM calls, $0.0075. plan_eval replays them with the rest. Flower: 7 of 13 areas touchable (was 6; stigma cleared by its retry), rule violations 0; still needs you: style and ovary spill after their retries, ovules, connective, filament same outline, floral axis no mask. Reference verdicts unchanged (all 5 still below 0.8). Heart, Japan, both brains unchanged.
- [ ] Gate C: One figure end to end [Pending]
  - Pass when: The heart figure: upload, print, trace, explore, labels spoken, on the real sheet.
  - Fallback: Cut Plus features. Spend Day 6 on the loop only.

## Day 6: Sat Oct 31

- [ ] d6-1 Voice capture and proxy (2.5 h)
  - AudioWorklet, 16 kHz mono, /api/voice relay, keyword hints from labels.
- [x] d6-2 Local intent parser (1 h)
  - where is, more, repeat, stop, what is here.
  - Note: Commit fc6117e on early-start. intents.ts: stop, repeat, more, what is here, where is, after fillers; labels and braille abbreviations matched on spelling or a rough sound key (rite and write match right), min_label_similarity 0.75 from explore.yaml; no match says 'There is no X on this sheet.' Everything else goes to /api/ask with the current and last two regions. 31 tests.
- [ ] d6-3 Grounded answers (2 h)
  - /api/ask with the cached figure context, streamed, first sentence spoken early.
- [ ] d6-4 Barge-in (30 min)
  - Space cancels speech and starts listening.
- [x] d6-5 Guidance mode (2 h)
  - Direction in words once, beeps speed up, chime and label on arrival.
  - Note: Commit fc6117e on early-start. guidance.ts: direction to the part's centroid in 8 sectors (same as the Python neighbors code, reversal property tested), distance to the outline in whole cm, said once when a finger is seen; beeps from 1.5 per s at 150 mm to 10 per s at the edge, updated every 300 ms, none over its own speech; chime and label after 200 ms inside. Headless offline: 'Stem. Left, 12 centimeters.', 3 beeps in 3 s far, 27 near, chime and Stem on arrival.

## Day 7: Sun Nov 1

- [x] d7-1 Teacher review screen (3 h)
  - Edit, merge, delete, add by name, publish.
  - Note: Commits 56c1698, 903e500 on early-start. API: draft-only GET source.png (S0 image) and report.json (the rules report publish would refuse with), 404 under /published/. /author: upload (PNG, JPEG, PDF page number, grade band, paper), stage progress by name with times, review with the figure as uploaded, parts flagged Checked or Not checked in words beside an amber or green bar, the tactile preview with the selected part outlined from regions.json; mark checked, rename, describe, merge, delete with confirm, add by name; rules report in words; refused publish lists each violation (parts, rule, measured, limit); publish gives that version's print PDF, print and trace steps and the Explore link; ?figure= reopens. 10 vitest tests on a fake API. Headless Chrome against the mock API: upload through the file input, rename pore, mark left lobe checked (8 then 6 not checked), all rules pass, publish v1, PDF link serves %PDF, Explore link opens v1 and Explore runs on it. Live mode waits on d1-8.
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

- (medium) ASR heard "aorta" as "order" on a synthetic clip with no hints
- (high) SAM returned zero instances for "left ventricle" on heart.png in 2 of 2 live calls; diagnostic in progress
