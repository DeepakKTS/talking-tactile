# Edge cases

What the code does in each case, what it should do, and where that stands. Current behavior
is from the code and tests at commit 4debae0 (Nov 2), file and line as of that commit; a fix
commit moves the lines. Paths are short: `api/` is `services/api/app/`, `web/` is
`apps/web/src/`, `tests/` is `services/api/tests/`. Status: **ok** (right as it is),
**fixed** (with the commit), **limitation** (known, not changed in the feature freeze, in
the README), **needs device** (only an iPhone run can confirm it).

Every sentence a student hears follows the voice rules (RULES.md 2): short, no em dashes, no
filler, and it says what still works or what to do next.

## Author upload

| # | Case | Current behavior | Expected | Status |
|---|---|---|---|---|
| U1 | Very large file | Over 10 MB refused: 413 "The file is over 10 MB." (`config/tactile_rules.yaml:41`, `api/middleware.py:72-78`, `api/pipeline/s0_ingest.py:160-161`). Test `test_api_figures.py::test_an_oversized_upload_is_refused` | Same | ok |
| U2 | Very large pixel count | No pixel limit; Pillow's `DecompressionBombError` (over about 179M px, possible from a flat PNG under 10 MB) is not caught at `s0_ingest.py:78`, so the teacher gets 500 "Something went wrong." marked retryable (`api/errors.py:71-74`) | Refused before decoding with a reason and the limit | fix |
| U3 | Very small image | Accepted and enlarged to 2048 px on its longest side (`s0_ingest.py:131-138,177`); sharpness judged at its own size (`:141-151`). Test `test_ingest.py::test_a_small_sharp_image_is_judged_at_its_own_size` | Same | ok |
| U4 | Blank image (one color) | Sharpness 0, refused as "The image is too blurry to find the parts." (`s0_ingest.py:149-150,173-176`) | Refused as blank | fix |
| U5 | Multi-page PDF | Only the chosen page is rendered (`s0_ingest.py:87-91`); the form asks for a 1-based page (`web/author/AuthorPage.tsx:100,120`). Test `test_ingest.py::test_pdf_page_is_picked_by_index` | Same | ok |
| U6 | PDF page out of range | 422 "The PDF has {n} pages. Pick one of them." (`s0_ingest.py:89`). Test `test_api_figures.py::test_a_pdf_page_out_of_range_is_refused` | Same | ok |
| U7 | Page number other than 1 for an image | "An image has one page. Use page 0." (`s0_ingest.py:166-167`), but the form counts from 1 | Says to use page 1 | fix |
| U8 | Photo with no labels | Spark's `describe_only` verdict ends the job as `describe_only` (`api/pipeline/runner.py:273-277`); the web app shows "Ready for review." and no review, since review needs `done` (`AuthorPage.tsx:10,56,155-161`); the reason is never shown | Says the figure is better described than made tactile, with Spark's reason | fix |
| U9 | Transparent PNG | Flattened onto white (`s0_ingest.py:72-76`). Test `test_ingest.py::test_transparency_becomes_white` | Same | ok |
| U10 | Unsupported or corrupt file | Detected by content: 415 "Upload a PNG, JPEG or PDF file."; corrupt: 422 "The image file could not be read." (`s0_ingest.py:26-30,60-64,78-86`). Tests `test_ingest.py::test_unsupported_types_are_refused_by_content`, `::test_a_truncated_png_is_unreadable`, `::test_a_broken_pdf_is_unreadable`. iPhone HEIC photos are refused the same way | Same | ok |
| U11 | Duplicate upload | Same pixels, same figure id; the newest job that has not failed is reused, 200 with `created: false` (`api/figures.py:402-418`). The web app ignores `created` (`AuthorPage.tsx:97-102`): the teacher lands on the earlier review without being told. Test `test_api_figures.py::test_a_duplicate_upload_returns_the_existing_job` | Says this figure was uploaded before | fix |

## Author edits

| # | Case | Current behavior | Expected | Status |
|---|---|---|---|---|
| E1 | Fix-outline click on the background | A positive point off the figure: 422 "Point ({x}, {y}) is on the page, not the figure." (`api/pipeline/outlines.py:40-41`); dropped in the panel with the message (`web/author/Review.tsx:514-515`). Test `test_outlines.py::test_a_positive_click_off_the_figure_is_refused_and_one_on_text_warned` | Same | ok |
| E2 | Fix-call cap reached | 429 "This figure used its fix calls for this version." (`api/figures.py:224-225`); does not say what still works | Says a previewed outline can still be accepted | fix |
| E3 | Accept fails (cap, network) | `send()` swallows the error and the panel closes, losing the teacher's points (`Review.tsx:60-73,128-131`) | Panel stays open with its points and the error | fix |
| E4 | Undo after accept | No undo: edits are append-only (`api/pipeline/edits.py:276-289`); rename again or accept a new outline; merge, delete and check are final. Delete asks to confirm, merge from a part's form does not (`Review.tsx:457-475`) | Undo | limitation |
| E5 | Publish twice | Same job: same version, 200 `created: false` (`api/figures.py:476-478`). Tests `test_api_figures.py::test_upload_edit_publish_and_fetch`, `::test_a_new_edit_after_publishing_makes_version_two` | Same | ok |
| E6 | Publish with every part unchecked | Allowed (`api/figures.py:466-480`); Explore gets no touchable region (`web/shared/regions.ts:41-43`). Test `AuthorPage.test.tsx` "publish still goes ahead" | Refused: a sheet with nothing to touch is not published | fix |

## Explore sheet

| # | Case | Current behavior | Expected | Status |
|---|---|---|---|---|
| X1 | Unknown figure id | Shown on screen only ("That is not a figure id.", "This figure is not published yet.", `web/explore/loader.ts:31,43`); the status line is a plain `<p>` (`web/explore/ExplorePage.tsx:458`), so a screen reader does not announce it, and Start stays disabled | Announced by the screen reader | fix |
| X2 | Old schema version | Refused by the schema (`docs/regions.schema.json:9`); shown as "The sheet is damaged: regions.json is invalid: /schema_version must be equal to constant" (`loader.ts:68`), screen only | Announced, in plain words: ask the teacher to publish again | fix |
| X3 | Camera denied | Says "The camera did not start. Allow the camera and press Start again." (`ExplorePage.tsx:308`), but Start is already hidden (`:281,459`), so it cannot be pressed | Start comes back | fix |
| X4 | No rear camera | `facingMode: { ideal: "environment" }` falls back to any camera, silently (`web/explore/camera.ts:60`); `/explore?check=1` warns (`web/explore/check.ts:28-29`) | Same; the device check is where it shows | ok, needs device |
| X5 | Corners not found | No automatic registration (`web/explore/corners.ts:1-2`): a sighted helper taps the four corners, prompted aloud (`ExplorePage.tsx:240`, `corners.ts:6,14,48`) | Automatic registration (PLAN d5-1) | limitation |
| X6 | Phone or sheet moved | No drift check. After 15 points off the page: "Your finger is off the sheet. Press R to set the corners again." (`web/explore/session.ts:84,353-362`, test `session.test.ts:201`); a shift that stays on the page gives wrong labels | Drift detection | limitation |
| X7 | No hand visible | Silent; touch state resets after 300 ms (`web/explore/touch.ts:95`). `health.no_hand_warn_ms` in `config/explore.yaml:42` is read nowhere. Tests `touch.test.ts:110`, `fingertip.test.ts:62` | Silent: a lifted hand is normal. The unused key is noted | ok |
| X8 | Two hands | One hand used, ranked pointing, then the dominant-hand setting, then the same side as before, then index extension (`web/explore/hands.ts:79-85`). Tests `hands.test.ts:73-114` | Same | ok, needs device |
| X9 | Finger held still | Earcon on entry, the label once after the dwell, then silence (`touch.ts:191-195`); "." repeats. Tests `touch.test.ts:56,87` | Same | ok |
| X10 | Low light | Mean brightness under 0.06 for 1.8 s: "The camera cannot see the sheet."; then "The camera can see the sheet again." (`session.ts:85-86,208-216`). Tests `session.test.ts:217,227`, `apps/web/e2e/explore_e2e.py:288-300` | Same | ok, needs device |

## Questions

Measured (eval/qa/VOICE.md, live, headless Chrome on this Mac): release to first spoken word
p95 5.9 s (12 holds); Spark p95 5.3 s on the heart, slowest of 61 answers 6.9 s
(eval/qa/scores.json); transcribe p95 1.4 s. The slowest observed server time is then about
8.3 s.

| # | Case | Current behavior | Expected | Status |
|---|---|---|---|---|
| Q1 | Offline | "Questions need the network. Labels still work." before recording (`web/explore/voice.ts:273-276`, `session.ts:83`); typed the same (`camera.ts:130`, `session.ts:344`). Tests `voice.test.ts:167`, `session.test.ts:190,336` | Same | ok |
| Q2 | Request timeout | No client timeout (`camera.ts:122,131`); the server waits up to 120 s a read, two calls a question (`api/meta/live.py:33`). A server that never answers leaves the hold busy for good: later holds are ignored (`voice.ts:245`) | Server deadline 12 s, client timeout 15 s (below) | fix |
| Q3 | 50-question cap | 429 "That is 50 questions for this session. Ask your teacher." (`api/ask.py:43,303-304`), spoken as sent. Test `test_ask.py:161` | Same | ok |
| Q4 | Silence or empty transcript | "I did not catch a question. Hold the screen and ask again." (`api/ask.py:42,313-316`); under 400 ms: "Hold the screen while you ask, then let go." (`voice.ts:28,296-299`). Tests `test_ask.py:155`, `voice.test.ts:177` | Same | ok |
| Q5 | Very long hold | Capped at 15 s (`voice.ts:22,53-55`): sent, with the release earcon | Same | ok |
| Q6 | Microphone denied | "The microphone is not allowed, so I cannot hear questions. Type a question instead. Labels still work." said on every hold (`voice.ts:26-27,278-289`). Test `voice.test.ts:154` | Same | ok, needs device |
| Q7 | Microphone busy (another app) | Any failure to open counts as denied for good (`voice.ts:283-289`): the wrong sentence, and no retry once the other app lets go | Says the microphone is busy; tries again on the next hold | fix |
| Q8 | Let go while the microphone is opening (first hold) | The hold is already listening (`voice.ts:49`); letting go after 400 ms sends a WAV recorded before the microphone was open, with no start earcon (`voice.ts:291`) | Nothing sent; says to hold while asking | fix |
| Q9 | Question while an answer is spoken | The hold stops the answer and listens (`voice.ts:292`), as intended; a screen reader's speech cannot be stopped (`web/explore/audio.ts:208-212`). Test `voice.test.ts:139-148` | Same | ok, needs device |
| Q10 | Typed question while waiting | No thinking tone for a typed question (`session.ts:338-347`) | Thinking tone, as for a spoken one | fix |

Timeout choice: the server stops a question at 12 s and answers "Questions are not working
right now. Labels still work."; that is 1.4 times the slowest observed server time (8.3 s)
and 2 times the p95 release to first word. The client gives up at 15 s, leaving 3 s for the
network and the server's own answer, so the server's sentence normally arrives first, and a
hold is never stuck.

## Server

| # | Case | Current behavior | Expected | Status |
|---|---|---|---|---|
| S1 | Meta unreachable or timing out | Ask: 502 "Questions are not working right now. Labels still work." (`api/routes/ask.py:24,58-59`), after up to 10 s connect or 120 s a read, twice. Job: S1 fails as `stage_failed`, retryable, with the raw httpx text (`api/pipeline/runner.py:279-286`); in S2 every part goes to the teacher as `no_mask` and the job ends `done` (`api/pipeline/s2_points.py:192-208`) | Ask: Q2. Job: fails with "The Meta API could not be reached." | fix |
| S2 | 401 or 403 key error | Ask: 502, as S1. Job: `stage_failed`, retryable, "HTTP 401: <redacted body>". Key redacted (`live.py:269-272`, test `test_live_ledger.py:168-183`) | Job: "The Meta API refused the key. Check services/api/.env.", not retryable | fix |
| S3 | 429 rate limit | Ask: 502, as S1. Job: `stage_failed`. No retry, Retry-After not read (`live.py:294-295`) | Job: says Meta is busy, retryable. No automatic retry in the freeze | fix |
| S4 | Malformed model response | Ask: a non-JSON body (`live.py:296`), empty choices or non-JSON content (`api/meta/live_client.py:359`), or a reply failing `SparkAnswer` (`api/ask.py:323`) end in 500 "Something went wrong." (`api/errors.py:71-74`), which Explore speaks. A non-JSON 200 also leaves no ledger line (`live.py:296`) | Ask: 502 with the questions sentence. Ledger line kept | fix |
| S5 | Server message not written for a student | Explore speaks any error message but a 404's (`web/explore/camera.ts:110-114`): a 500 says "Something went wrong.", a 503 without LIVE=1 says "Live Meta calls need LIVE=1 in the environment. ..." | Only the ask route's own messages are spoken; anything else says "Questions are not working right now. Labels still work." | fix |
