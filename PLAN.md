# Talking Tactile: the complete plan

## 1. The idea

A teacher uploads a science figure. Talking Tactile finds its parts, applies tactile design rules, and prints a sheet that can be traced into a raised graphic. A blind student puts the sheet under a phone camera and explores it with their fingers. When a finger rests on a part, the app says its name. When the student asks a question out loud, the app answers from that figure.

No QR codes, no stickers, no special tablet. The camera and the models do the work.

## 2. Why this matters, with sources

- Postsecondary science textbooks can have images on half their pages, sometimes up to 500 per book, and these are rarely available in tactile form. Done by hand, several hundred images can take 1 to 5 hours each, which is 200 to 1,000 hours per textbook. (University of Washington, Tactile Graphics Assistant study)
- The 2007 Tactile Graphics Assistant cut human time to 6.3 to 10.2 minutes per figure, but had to be retrained for each class of textbook. SAM 3.1 is zero-shot, so that limit goes away.
- Earlier audio-tactile systems needed special hardware or materials on every object (touch tablets, smart pens, fiducial markers, QR codes). Researchers at Smith-Kettlewell note this is costly and limits adoption. Finger tracking based on color alone is error prone.
- Meta's own direction: personal superintelligence on glasses, and Muse that can act on what you are looking at. Ray-Ban Meta glasses saw strong adoption in the blind and low vision community. A phone camera is our stand-in for the glasses camera.

## 3. Two modes, two users

| | Author mode | Explore mode |
|---|---|---|
| User | Teacher of students with visual impairments, or a transcriber | Student who is blind or has low vision |
| Device | Laptop browser | Phone or laptop with a camera looking down at the sheet. The demo and Gate B use the phone's own browser (section 17) |
| Input | A figure image or PDF page | Fingertip position and voice |
| Output | Tactile SVG, print PDF at 1:1, regions.json | Earcons, spoken labels, spoken answers, guidance |
| Needs a screen | Yes | No |

## 4. How it works

Loop one runs once per figure. Muse Spark reads the figure and lists its parts as short phrases. SAM 3.1 finds each part. Code turns the masks into clean shapes that obey the tactile rules, adds braille or a key, and writes the region map.

Loop two runs live. A hand tracker in a Web Worker finds the fingertip. A homography maps it from camera pixels to millimeters on the sheet. A region engine with hysteresis decides which part is under the finger and when to speak. Questions go through Muse Voice Transcribe and Muse Spark.

## 5. Architecture

### 5.1 Frontend (apps/web)

React, TypeScript strict, Vite. Two routes.

`/author`
- Upload panel (PNG, JPG, PDF page picker), grade band, page size.
- Job progress by stage, with live stage names.
- Review screen: original figure on the left, tactile preview on the right, region list in the middle. Edit a label, merge two regions, delete one, add a missing part by name. Amber flag on anything not yet checked.
- Print screen: download print PDF, calibration bar instructions, tracing tips.

`/explore`
- No visual dependence. Large single button to start, everything else by keys and voice.
- Camera module: getUserMedia, newest frame only, ImageBitmap transferred to the worker.
- Worker: MediaPipe Hand Landmarker in VIDEO mode, up to 2 hands. Returns landmarks only.
- Pointing hand picker, fingertip offset, 1 euro filter on x and y.
- Homography (3x3, computed once per registration, applied in a few multiplications).
- Region engine: bounding box prefilter, point-in-polygon, hysteresis state machine, dwell timer, guidance mode.
- Audio engine: preloaded earcons with Web Audio, speechSynthesis for the app voice, aria-live mirror for screen reader users.
- Voice capture: AudioWorklet, downsample to 16 kHz mono PCM16, WebSocket to the backend.
- Local intent parser for "where is", "more", "repeat", "stop", "what is here", so the commonest requests need no network.

State: React context plus reducers. No state library. The camera loop does not go through React state at all, it writes to refs.

### 5.2 Backend (services/api)

Python 3.11, FastAPI, uvicorn. One process.

Routes
- `POST /api/figures` upload, returns figure_id (sha256) and starts the pipeline
- `GET /api/figures/{id}` status and stage timings
- `GET /api/figures/{id}/regions.json`, `/tactile.svg`, `/print.pdf`
- `PATCH /api/figures/{id}/regions/{rid}` teacher edits
- `POST /api/figures/{id}/publish` locks a reviewed version. Refused with 409 `rules_violated` and each violation (regions, rule, measured, limit) when that version's rules report is not empty; no override
- `POST /api/register` one frame in, sheet corners, orientation and confidence out
- `POST /api/ask` question plus context in, answer streamed out as server-sent events
- `WS /api/voice` audio in, transcripts out, proxied to Muse Voice Transcribe

Libraries: httpx, pydantic, numpy, opencv-python-headless, shapely, louis (liblouis bindings), cairosvg for print PDF.

Storage: SQLite for jobs and edits. Files under `data/figures/<sha256>/`. Same figure uploaded twice costs nothing.

### 5.3 Middleware

- Request id on every request, JSON logs with stage, latency and cost.
- One error envelope: `{error: {code, message, retryable}}`.
- Upload guard: 10 MB, PNG, JPG or PDF, one page per job.
- CORS for the local web origin only.
- Meta client wrapper: timeouts, retry with backoff and jitter on 429 and 5xx, semaphore for SAM concurrency (4), response cache keyed by model, input hash and params, cost meter that warns at 70 and 90 percent of budget.
- Mock mode: `MOCK_META=1` serves recorded fixtures. Used for tests, offline dev and a backup demo.

### 5.4 Meta layer

| Call | Model | Settings |
|---|---|---|
| Understand figure | muse-spark-1.3 | image in, structured output, reasoning medium |
| Map labels to masks | muse-spark-1.3 | image with numbered mask outlines, structured output |
| Segment parts | sam-3.1 | Responses API, streamed. One short noun phrase per call, image at 2048 px max. Masks are box-local, base85 special-token text; parse with meta-sam-parser |
| Find the sheet (fallback) | sam-3.1 | phrase "sheet of paper" |
| Answer a question | muse-spark-1.3 | text only, streaming, reasoning low, static figure context first so it can be cached |
| Transcribe | muse-voice-transcribe-1.0 | realtime WebSocket, keyword hints from region labels, language hint English |

Prices from Meta's pricing page as quoted by a hackathon guide (confirm on Day 1): Muse Spark Standard $1.25 per million input tokens and $4.25 per million output. SAM 3.1 $2.50 per 1,000 images. Muse Voice Transcribe $0.18 per hour. Rate limits: Spark 3,000 requests and 4 million tokens per minute, SAM 3,000 requests per minute.

## 6. Authoring pipeline, stage by stage

S0 Ingest. Validate type and size. Render the PDF page. Deskew a photographed page using its largest four-sided outline. Reject blurry images with a clear message. Normalize to 2048 px longest side. Hash.

S1 Understand (Muse Spark). Returns figure type, title, a one paragraph summary, up to 25 parts as short noun phrases, which print labels point to which part, whether color carries meaning, and a verdict: make tactile, split into two sheets, or describe in words only. BANA Unit 1 is about whether a tactile graphic should be made at all, so this verdict is a real step, not a formality.

S1, live since d1-8 (Oct 30): a second Muse Spark call locates each listed part: kind (area, thin or group), a group's members, the part it sits inside, and every instance with 1 to 3 points (app/prompts/s1_locate.v1.json).

S1 plans for touch since Oct 30 (d5-6, app/prompts/s1_locate.v2.json). The locate call is told the grade band, the printed size, the smallest part a fingertip explores (point_symbol_min_mm) and the gap, and plans as a transcriber would: each part is an area, a line (a sulcus, a border: never touched, no points) or a group; an area may have a parent; a line separates two listed areas, or has a parent; shares_region names areas drawn as one unbroken shape, with a combined name; subject names the whole object. Every listed part comes back once; one left out keeps no kind and goes to the teacher. S1's key now holds the job options, so a new grade band or page plans again.

S2 Ground (SAM 3.1). Live since d1-8, Arm A v2f, locked Oct 30 (section 17): point prompts, one call per located part, four at a time; the points guarded in code, a spill retry, the oversize rule, and contested pixels to the smaller mask (app/pipeline/s2_points.py). Print text is found in code. Mock mode keeps the original path: one call per phrase, four at a time, and a call for "text label" so print text can be removed from the raised layer. Keep masks with their scores.

S2 on the plan (d5-6): a line gets no SAM call and never needs the teacher. A part's points are no spill for a mask they lie inside when that part is Spark's child, is nested in the mask (95% or more of its first mask inside, smaller; NEST_INSIDE from the eval figures' masks, eval/plan/RESULTS.md), or shares its region. Each shared group is a merge proposal. Nesting is tested again on the masks S2 keeps; a child stays inside its parent's outline.

Drawn boundaries (Oct 30, app/geometry/boundaries.py): two parts have one when their points lie in different regions of the figure cut by ink and sharp color edges (EDGE_STEP 14), or their fills differ by more than FILL_DELTA 55; both are chosen from the five eval figures (eval/plan/RESULTS.md, Drawn boundaries). A merge is proposed only where the image shows none: masks with IoU 0.8 or more and no drawn boundary share a region, and of Spark's shares_region the largest set of members with none between them does; a member left out is recorded with the reason. Near-identical masks across a drawn boundary are never split: the smaller part goes to the teacher, 'same outline as' the larger, its mask a suggestion with Fix outline. Near-identical masks with no drawn boundary are no longer split by the nearer point either; the merge proposal stands for them, and the smaller mask takes the contested pixels as any other. One SAM phrase call for the subject gives the silhouette, its largest piece; a failure leaves the sheet without one.

S3 Reconcile (code first, then Muse Spark). Code merges near duplicates (overlap above 0.8), turns full containment into parent and child, assigns partial overlaps to the smaller part, and drops slivers. Then Muse Spark sees the figure with each mask outlined and numbered, and returns which number is which label plus a short description from the caption. This numbered overlay is how we stop the model guessing coordinates.

S4 Layout (code only). Masks to polygons with contour tracing, simplified to 200 points or fewer. Scale to page millimeters. Enforce the 3.2 mm gap by shrinking neighbors, never by moving them. Pick up to 5 textures (3 for lower grades). Turn parts below the point symbol size into point symbols or merge them. Translate labels with liblouis, place braille where it fits, otherwise build a key with abbreviations. Compute centroids and neighbor directions.

S4 on the plan (d5-6): line parts are listed in the key ("central sulcus, a line between precentral gyrus and postcentral gyrus", print note "Not raised: ..."), never drawn as areas. The silhouette's outer contour is raised, untextured, only where every part outline is at least min_gap_mm from its line and braille its clearance; pieces shorter than point_symbol_min_mm are left out. The rules check measures it.

S5 Render. tactile.svg with layers (outlines, textures, braille, key), print.pdf at exact scale with a 100 mm calibration bar, regions.json, and a validation report from the rules check.

S6 Review (teacher). Approve, edit, merge, delete or add. Publishing writes a locked version that Explore loads.

regions.json schema version 2 (Oct 30, d1-8). Migration from version 1:
- Each region has `touchable` (required). False marks a teacher suggestion: a spill mask kept for the teacher, not raised on the sheet and never used by Explore. Version 1 regions were all touchable.
- Each region may have `flags`: `spill` (only on untouchable regions), `thin` and `under_point_symbol` (both stay touchable).
- `needs_teacher` lists the parts with no shape at all: `no_points`, `no_mask` or `dropped` by S3.
- Explore accepts version 2 only and drops untouchable regions at load. A version 1 file is refused as damaged: publish the figure again to make a version 2 file. Neighbors only name touchable regions.

regions.json schema version 3 (Oct 30, d5-6). Migration from version 2:
- Optional `subject` ({label, polygon_mm}): the whole object and its silhouette. Explore says the label once each time a finger rests inside it on no part.
- Optional `lines` ({id, label, separates?, between?, parent?}): line parts. `separates` names two touchable regions by their parts' main region ids; Explore says "line, part" when a finger crosses from one into the other. Line ids share the id space with regions and needs_teacher.
- Optional `merge_proposals` ({name, region_ids, why}): touchable regions drawn as one shape. Author shows each as one merge button.
- Explore accepts version 3 only; a version 2 file is refused as damaged: publish the figure again. Nothing in a version 2 file changes meaning.

Target: under 90 seconds from upload to review screen.

## 7. Explore loop

E0 Setup. Spoken onboarding. Camera and mic permission. Registration: one frame to `/api/register`. The server tries a fast OpenCV outline first and falls back to SAM 3.1. It tests all four rotations against the rendered SVG and returns the best with a confidence score. Low confidence leads to spoken guidance such as "slide the sheet toward you".

E1 Track. Worker returns hand landmarks. The pointing hand is the one with the index finger extended and the others curled. The contact point is the fingertip moved slightly back along the finger, tuned on the test sheet. A 1 euro filter smooths jitter without adding lag on fast moves.

E2 Locate. Map to sheet millimeters. Point in polygon against regions, smallest region first so children win over parents.

E3 Decide. A small state machine per finger:

```
OUTSIDE -> ENTERING   point inside the region shrunk by 1 mm
ENTERING -> INSIDE    stays 120 ms        play the texture earcon
INSIDE -> DWELLED     slower than 15 mm/s for 600 ms   speak the label
INSIDE or DWELLED -> LEAVING   point outside the region grown by 2 mm
LEAVING -> OUTSIDE    stays out 120 ms    play a soft exit tick
```
All numbers are starting values in `config/explore.yaml`, tuned with the touch eval. Earcons are capped at 6 per second during fast scanning. The exit tick follows Smith-Kettlewell user feedback asking for a signal when the finger leaves a hotspot.

E4 Health. If the hand disappears for 2 seconds during a question, say so. If mapped points keep landing off the page, ask to recalibrate. R recalibrates any time.

Guidance mode. "Where is the aorta?" is parsed locally. The app says the direction once in words, then beeps faster as the finger gets closer, and plays a chime and the label on arrival. Direction and distance come from code.

## 8. Voice question flow

1. Student holds Space. Mic opens. App voice pauses.
2. Browser streams 16 kHz PCM to `/api/voice`. Backend streams to Muse Voice Transcribe with the region labels as keyword hints.
3. On release, the final transcript goes through the local intent parser. Navigation and repeat requests are handled locally.
4. Anything else goes to `/api/ask` with the current region, the last two regions, computed spatial facts and the question.
5. Muse Spark streams the answer. The browser speaks the first sentence as soon as it is complete.
6. Space during an answer cancels it and starts listening again.

Target: under 2 seconds from releasing Space to the first spoken word.

## 9. Speed and memory

Browser
- One frame in flight. Drop frames, never queue.
- Worker returns at most 2 x 21 landmarks per frame. No pixels come back.
- A ring buffer of the last 30 fingertip points is the only history.
- Region tests are a bounding box check then a polygon test, around 60 regions at most. No spatial index needed.
- Earcons decoded once at start.

Backend
- Async throughout. SAM calls run four at a time.
- Images capped at 2048 px. Masks stored as 1-bit PNG. Polygons capped at 200 points.
- Content hash cache for every stage. Prompt prefix for answers kept identical so it can be cached.

Cost estimate per figure, to confirm on Day 1: about 10 to 25 SAM calls, so roughly $0.03 to $0.06, plus two Spark calls with an image. Each question is a short text call. Thirty figures and several hundred questions should stay well under a quarter of the credits.

## 10. Not building, on purpose

- Accounts, login, multi-tenancy
- Redis, Celery, Postgres, Kubernetes, microservices
- Any model training or fine tuning
- OpenCV in the browser
- Muse Image, because a model must not redraw a science figure
- A native mobile app or a glasses SDK integration
- Braille math codes. Math labels stay as audio only.

## 11. Edge cases

See the edge case table in the PDF. The rule of thumb: when in doubt, say less. A wrong label spoken with confidence is worse than silence.

## 12. Evaluation

| Suite | What | Goal |
|---|---|---|
| Authoring | 20 openly licensed figures, 4 types. Part recall against a teacher list, label accuracy, rule violations, seconds per figure | recall 80 percent or more, zero violations, under 90 s |
| Touch | 9 point test sheet, 5 touches each. Mean and p95 error. Region hit rate on 30 touches. False switches per minute at rest | mean error 4 mm or less, hit rate 95 percent or more |
| Latency | touch to earcon, release to first word | under 100 ms, under 2 s |
| Voice | 20 recorded questions, term accuracy with and without keyword hints | report both |
| Answers | 20 questions with known answers, including 5 the figure cannot answer | correct refusals on all 5 |
| User | blind tester: find 3 named parts, answer 3 questions, free comments | report honestly, with quotes |

Goals are goals. The README reports measured numbers only.

## 13. Features

MVP (must ship)
- Upload, author pipeline, review and edit, print PDF at 1:1
- Explore with registration, fingertip tracking, earcons, dwell labels, "more"
- Voice questions with grounded answers, push-to-talk, barge-in
- Guidance mode for "where is"
- Offline labels and guidance when the network drops
- Mock mode and the eval suites

Plus (only after Gate C)
- Quiz mode: "find the aorta", with timing
- Two sheet split for dense figures
- Spanish prompts and answers using the language hint
- Teacher view of which parts a student touched most, stored only on the device

Stretch (after the hackathon unless everything is green)
- Wrap authoring as a Muse connector over MCP so a teacher can ask their agent to make chapter figures tactile
- Glasses camera path when developer access allows it
- Embosser and swell paper output tuned with a transcriber
- Batch a whole chapter PDF

## 14. Timeline and gates

| Day | Date | Focus | Gate |
|---|---|---|---|
| 0 | Oct 23 to 25 | Apply. Tester outreach. Materials. Read BANA units 1 to 3. No project code | |
| 1 | Oct 26 | Kickoff, rules, keys, repo. Spikes on Spark, SAM, Voice | A: all three models answer, latencies known |
| 2 | Oct 27 | Hand tracking spike, homography, 9 point test | B: mean error 4 mm or less |
| 3 | Oct 28 | Author S0 to S3 | |
| 4 | Oct 29 | Author S4 to S5, print, trace first sheet, dry overnight | |
| 5 | Oct 30 | Explore E0 to E3 on the real sheet | C: one figure works end to end |
| 6 | Oct 31 | Voice, answers, guidance mode | |
| 7 | Nov 1 | Review UI, accessibility pass, tester session | |
| 8 | Nov 2 | Fixes from testing, full eval | |
| 9 | Nov 3 | Freeze at noon, demo video, README | D: demo readiness passes |
| 10 | Nov 4 | Buffer. Submit by 3 PM ET | |

## 15. Risks

| Risk | Likelihood | Impact | Plan |
|---|---|---|---|
| No blind tester in time | Medium | High | Outreach now. Fallback: feedback from a teacher of students with visual impairments, stated honestly |
| SAM weak on thin line art | Medium | High | Day 1 test on 5 figures. Fallback: teacher names the missing part, or local SAM 3.1 checkpoint with point prompts |
| Fingertip error too high | Medium | High | Gate B. Fallback: larger regions, pointing pose required, slower dwell |
| API latency | Medium | Medium | Local intents cover the common requests. Speak the first sentence early |
| Hand made sheet quality | Medium | Medium | Make two copies on Day 4. Fallback: hot glue or layered card |
| Credits | Low | Medium | Cost meter, mock mode |
| Scope creep | High | High | Gates and the noon freeze on Nov 3 |
| Official rules conflict | Low | High | Read them on Oct 26 and adjust this plan the same day |

## 16. Demo video, about 2.5 minutes

0:00 One line on the problem and the hours per textbook.
0:15 Teacher uploads a heart diagram. Stage names tick by. Review screen appears.
0:45 The printed sheet, traced and dry. Calibration bar measured with a ruler.
1:00 Student places it under the phone. Onboarding voice. Finger moves, earcons, "Left ventricle".
1:25 "What does this do?" Short answer.
1:40 "Where is the aorta?" Guidance beeps, chime, label.
2:00 Measured numbers from eval/RESULTS.md.
2:15 Which Meta model does which job, and why there is no Muse Image.
2:30 End.

## 17. Settle on Day 1

- SAM 3.1 hosted request shape: one phrase or many per call, mask format returned. From the docs (Oct 24): model `sam-3.1` on `POST /v1/responses`, one concept per request, every instance returned as a box plus a box-local mask in special-token text, `one_bit` or `lossless` encoding, optional confidence. Confirm with the live spike. Live, Oct 29 (spikes/sam.md, SAM diagnostic): that shape holds, except that a mask raster can be smaller than its bounds (a 1423 px tall box came with a 1024 px tall raster), so masks are scaled to their bounds. Concept prompts found the whole heart on heart.png and none of its parts.
- S2 method, from the bake-off of Oct 29 (spikes/sam.md; grades in eval/s2-bakeoff/FIGURE/grades.json). heart.png is a colored illustration without dark outlines, not line art. Arm B's ink threshold (luminance under 64) found the label text and leader lines, not the anatomy. Arm B is set aside, for three reasons. It fails on figures without dark outlines (the heart). Spark misassigned numbered regions on the map (Tohoku took Kanto, Kanto took a Chubu prefecture). Its naming calls took 42 s on the flower and 92 s on the map (14.5 s on the heart). Revisit Arm B only if Arm A v2 fails the flower's small parts.
- Voice realtime event names and the keyword hint parameter. From the docs (Oct 24): handshake JSON first with the key in `authorization.accessToken`, `keywords` and `languageBias` set only there, `transcript` events with `final: true` in `PUSH_TO_TALK`. `PCM_24KHZ` is native and `PCM_16KHZ` is resampled, so 5.1 and 8 may move to 24 kHz after the spike. A file endpoint, `POST /v1/asr/transcribe`, exists for the push-to-talk fallback
- Whether Muse Spark 1.3 caches a repeated prompt prefix
- Real latencies for each call
- What the Official Rules require: public repo, video length, open source license
- Where Explore runs. Decided Oct 24: the demo and Gate B run the page in the demo phone's own browser, in a fixed mount, not on a laptop with the phone as its webcam (Continuity Camera). The measured accuracy and latency are then the shipped setup's. Whether it is fast enough is measured on that phone (d2-5, Gate B). A shortfall calls for a new decision, not a quiet switch to the laptop
