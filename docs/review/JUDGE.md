# Judge review (Indie track)

> Saved from the reviewer's report unchanged except for redactions: local paths, the author's email, the Mac's name, LAN addresses and the private figure's file name. Triage of every finding: `docs/review/TRIAGE.md`.

- Project: Talking Tactile
- Commit reviewed: `c3503ab` (main, "License field: Apache-2.0 ...")
- Date of review: 2026-11-03
- Clone: a fresh local clone, no API key, mock mode only. No live Meta call was made.

## Verdict in one paragraph

This is a serious, deep and careful build. The idea is strong and the engineering is far above
a typical solo hackathon entry. The weak spot is proof that the core product works: there is
no video, no photo and no measurement of a finger on a raised sheet under a phone, and every
device number is TBD. A judge who follows the README literally gets a working Author flow, but
the question answering in Explore does not work. The GitHub repo also showed as PRIVATE when I
checked, so a judge may not be able to clone it at all.

## Scores

| Criterion | Score | Short reason |
|---|---|---|
| Creativity | 8 / 10 | A real, specific problem. A smart split: the models read and outline, code owns geometry, the teacher confirms |
| Technical ambition | 9 / 10 | A full pipeline S0 to S5, braille, sourced tactile rules, homography, hand tracking in a worker, offline Explore, strict grounded QA, 1,110 tests, CI |
| Whether it works | 6 / 10 | Author works in mock mode and every test suite passes. The touch path is not shown or measured on a phone, and mock questions fail on the quickstart path |
| Use of Meta models | 8 / 10 | Three models, each with a distinct and justified job, 1,013 logged live calls for $5.31, evals for each. Voice is tested on synthetic speech only |

### Official weights quoted in the repo

`CLAUDE.md:18`: "Judging weights (from a guide quoting the event waiver, confirm in the
Official Rules): Impact 30, Use of Meta tooling 25, Demo 25, Technical depth 20."

No copy or link to the Official Rules is committed. `docs/submission/VIDEO_SCRIPT.md:6` uses a
different set ("creativity, technical ambition, or whether it works"). The team should confirm
which set is real and write to it.

Mapped onto the quoted weights, my rough read: Impact 7 (strong case, no user evidence),
Meta tooling 8, Demo 4 (nothing to watch yet, the README has no video and no physical photo),
Technical depth 9. Demo and Impact are where points are being lost.

### Creativity: 8

- The problem is real and well chosen: tactile graphics are slow to make by hand, and a
  raised shape does not say what it is (`PLAN.md:9-15`, `docs/submission/WRITEUP.md:21-25`).
- A good, honest design principle: no generative image model redraws a figure
  (`README.md`, `WRITEUP.md:56-57`), and "Directions, neighbors, distances ... come from code;
  the model never guesses geometry" (`README.md:91-92`).
- Thoughtful tactile ideas: lines (valves, sulci) are spoken when crossed, never raised as
  areas (`README.md:101-102`); point symbols for parts too small to enter (`README.md:103-105`);
  texture earcons; "where is" guidance with beeps.
- Teacher in the loop by design: nothing is touchable until checked; spills go to "Needs you"
  (`README.md:96-100`, verified in the review screen).
- Minus: a sighted helper must tap four corners (`README.md:160-161`), which weakens the
  "no markers" pitch in `PLAN.md:7` and `APPLICATION.md:23,37`. No input from a blind student
  or a teacher of the visually impaired is committed.

### Technical ambition: 9

- Backend: about 12,900 lines of Python in `services/api/app`, one file per stage in
  `services/api/app/pipeline/` (S0 to S5), per-stage cache, SQLite jobs, deskew
  (`s0_ingest.py:123`), a 50 million pixel guard (`s0_ingest.py:44`), braille through liblouis,
  a rules report that blocks publishing.
- Sourced design constants: `config/tactile_rules.yaml:6-11` cites tactilegraphics.org and
  APH for the 3.2 mm gap, 6.4 mm point symbol and the 5 texture limit.
- Explore: about 5,300 lines of TypeScript. MediaPipe in a Web Worker, newest frame only
  (`explore_e2e.py` run: 20 fps, 12.8 ms p50 capture to landmarks, 3 of 98 frames dropped),
  homography, 1 euro filter, hysteresis region engine (`config/explore.yaml:2-23`), the hand
  model served locally so touch works offline (verified: every Explore request went to
  127.0.0.1).
- Questions: a strict JSON schema built per figure, cited ids checked in code, fixed
  deflection sentences, a 50 question cap and 8 s / 20 s / 25 s timeouts
  (`services/api/app/ask.py:34,51`, `apps/web/src/explore/session.ts:99,103`).
- Quality: 752 pytest and 358 vitest tests, ruff, eslint, mypy strict and tsc all pass
  (`make check`, 3 min 9 s here). CI on GitHub was green on the last three pushes to main.
  Four headless browser end-to-end scripts. A network guard in tests. A CSP on every page.
- Edge cases are listed with file and line and test (`docs/EDGE_CASES.md`).

### Whether it works: 6

What I ran and saw work:
- Author in mock mode: upload `fixtures/heart.png`, "Ready for review." in 24.9 s (README says
  about 25 s), the septum in "Needs you", the aortic arch merge proposal, mark all checked,
  publish, a 93 KB print PDF.
- `apps/web/e2e/explore_e2e.py`: PASS in 2 min 15 s. Scripted hands touch every part, offline
  touch works, guidance works, camera denied is handled, the device check runs.
- `apps/web/e2e/ask_e2e.py`: PASS in 42 s. With the heart published exactly as version 4
  (merge plus two teacher descriptions), the left ventricle question is answered and the
  right ventricle question is deflected.
- `python -m app.meta.plan_eval` on replay: reproduces `eval/plan/RESULTS.md` exactly, except
  the private figure, which is not in the repo.

What did not work or is not shown:
- Typed questions on the README quickstart path all said "Questions are not working right
  now. Labels still work." (HTTP 502), including the eval question "What does the left
  ventricle do?". The README (`README.md:43-46`) says eval questions are answered in mock mode.
  They are only answered if the sheet matches version 4 exactly, which the README never says
  how to make.
- The Commons brain in mock mode failed with "HTTP 599: no recording for POST
  /v1/chat/completions" unless the grade band is set to "6 to 8". The README does not say so.
- `python -m app.meta.qa_eval` (the "no calls" replay in `CLAUDE.md`) fails on a fresh clone
  in 0.7 s: "This figure has no published version 4." The question numbers in the README cannot
  be reproduced from the clone.
- The core product claim, a phone over a raised sheet that speaks the part under the finger,
  has no committed evidence from a real device: Gate B, touch to tone and iPhone question
  latency are all TBD (`README.md:156-158`, `WRITEUP.md:69-73`). No photo of a raised sheet,
  no video link.
- Question latency is p50 5.0 s on a Mac, against the repo's own budget of "under 2.0 s"
  (`RULES.md` section 4 table). The README does not mention the budget.

### Use of Meta's models: 8

- `muse-spark-1.3`: two S1 calls (understand, then a touch plan with kinds, groups, parents
  and points, `services/api/app/prompts/s1_locate.v2.json`) and the grounded answers
  (`ask_answer.v2.json`) under a strict per-figure schema, at "minimal" effort chosen from a
  measured comparison (`eval/qa/VOICE.md:80-107`). This is careful, measured use.
- `sam-3.1`: point prompts per part, a spill retry, a phrase call for the silhouette, and a
  teacher "Fix outline" with clicks (`live_client.py:265-301`). Scored against graded reference
  masks (`eval/plan/RESULTS.md`).
- `muse-voice-transcribe-1.0`: file transcribe with the figure's part names as keywords
  (`live_client.py:314-342`).
- Cost metering: `eval/live/ledger.jsonl` has 1,013 lines, $5.308 total (532 Spark, 328 SAM,
  153 Voice).
- Standard models only; the backend refuses a Contributor model id (`app/config.py:160-171`).
- Minus: voice is tested on three synthetic `say` clips, which hit the ceiling, so the value
  of keyword hints is not shown (`eval/qa/VOICE.md:16`). Two planned model jobs are not built:
  Spark in S3 and SAM for sheet registration (`README.md:87`, `README.md:160`), yet
  `CLAUDE.md:24-25` still lists them.

## Quickstart, followed literally

Machine: macOS, uv 0.11.29, Node 24.21.0, liblouis already installed. Ports 8000 and 5173 were
held by the live demo, so I substituted 18000 and 15173.

| # | Command | Worked | Time | Notes |
|---|---|---|---|---|
| 1 | `git clone https://github.com/DeepakKTS/talking-tactile.git` | Not run (local clone given) | | `gh repo view` reported the repo as **PRIVATE**. A judge without access gets a 404 here |
| 2 | `make install` | Yes | 18.8 s | Warm caches on this Mac; a cold machine will be slower. It ended with 11 moderate npm advisories and the `fsevents` note, exactly as `README.md:27-29` warns |
| 3 | `MOCK_META=1 make dev` | Yes, with ports changed | API ready about 40 s after start; Vite ready in 1.2 s | The literal command binds 8000 and 5173 and would have collided. Vite uses `strictPort`, so it would refuse to start. The Vite proxy defaults to 127.0.0.1:8000 (`apps/web/vite.config.ts`), so running Vite on another port without `TT_API` would silently send API calls to whatever owns 8000. `TT_API` is not in the README. I ran `MOCK_META=1 uv run uvicorn app.main:app --port 18000` and `TT_API=http://127.0.0.1:18000 npx vite --port 15173 --strictPort` |
| 4 | Author step 1: open /author, upload heart.png | Yes | | The button is "Make a tactile sheet", not "upload". The page has Grade band and Paper options; any change from the defaults breaks mock replay for the heart (only one recording exists) |
| 5 | Author step 2: wait for "Ready for review." | Yes | 24.9 s | Septum in Needs you and the aortic arch merge appear as described |
| 6 | Author step 3: Mark all parts checked, confirm, Publish | Yes | about 3 s | |
| 7 | Author step 4: print PDF, Open version 1 in Explore | Yes | | PDF 93,205 bytes, HTTP 200 |
| 8 | Explore: Enter starts, H says help | Yes | | Says the title, summary, "One part is not touchable yet: septum", then "A helper sets the corners. Click corner A, top left." Without a camera and sheet, a judge can do nothing more with touch |
| 9 | Explore: typed questions | **No** | | All three, including the eval question "What does the left ventricle do?", returned "Questions are not working right now. Labels still work." |
| 10 | Brain in mock mode (README says both figures replay) | Only with grade band 6 to 8 | about 20 s | Default grade band fails: "HTTP 599: no recording for POST /v1/chat/completions" |
| 11 | `make check` | Yes | 3 min 9 s | 752 pytest, 358 vitest, ruff, eslint, mypy, tsc |
| 12 | `uv run apps/web/e2e/explore_e2e.py` | PASS | 2 min 15 s | Uses its own free ports |
| 13 | `uv run apps/web/e2e/ask_e2e.py` | PASS | 42 s | The only path where mock questions work |
| 14 | `cd services/api && uv run python -m app.meta.plan_eval` | Yes | 1 min 14 s | Output matches the committed file except the private figure section |
| 15 | `cd services/api && uv run python -m app.meta.qa_eval` | **No** | 0.7 s | "This figure has no published version 4." |
| 16 | `python3 scripts/tracker.py spend` | Yes | instant | "$5.308222 from the ledger" |

Where a judge gets confused or loses interest:

1. The clone URL may 404 (private repo).
2. The first screen of the README has no picture of the physical product and no video link.
   The first image (`README.md:61`) is an architecture diagram.
3. The API takes about 40 s before it answers on the first start. `make dev` starts Vite at
   once, so an early upload may fail with a proxy error.
4. Explore cannot do anything useful without a printed, raised sheet and a camera mount. The
   README says so, but offers no simulated touch mode for judges (the e2e scripts have
   `?source=script` and `?corners=`, which are not mentioned).
5. Typed questions fail on the path the README describes.
6. The Commons brain fails unless the judge guesses the grade band.
7. The unstyled UI (default browser fonts and buttons) looks unfinished in screenshots, even if
   it is plain for accessibility reasons.
8. About 60 lines of the README (`README.md:198-263`) are a legal reading of Meta's terms. It
   is careful work, but it pushes Results and Limitations out of a 3 minute read.
9. Root folder noise: `APPLICATION.md` (another project, personal details), `TODO.md`
   (109 KB), `TRACKER.html` (440 KB), `CLAUDE.md`, `SKILLS.md`, `.claude/skills/`.

## Claims with no evidence, or with evidence that says something else

### Claims with no committed evidence

| # | Claim | Where | What is missing |
|---|---|---|---|
| 1 | "A phone camera over the sheet finds the student's fingertip and speaks the part under it" | `README.md:5-6`, `WRITEUP.md:13-14` | No device run, photo or video. Gate B, touch to tone and iPhone latency are TBD (`README.md:156-158`, `WRITEUP.md:69-73`). Only scripted hands in headless Chrome |
| 2 | "In mock mode a typed question is answered from the question eval's live recordings ... an eval question asked with no part under the finger is answered wherever the finger is" | `README.md:43-46` | Fails on the quickstart path. Works only when the published sheet equals `fixtures/qa/heart_v4_regions.json` (merge plus two exact teacher descriptions), which the README does not describe |
| 3 | "Mock mode replays live Meta answers ... for two figures: the heart ... and the Commons brain" | `README.md:13-15` | The brain replays only with grade band 6 to 8. Not stated |
| 4 | "Every number here is from a committed result file; rerun the command to reproduce it." | `README.md:141` | No command is given in the table. The question eval replay fails on a fresh clone (no published version 4) |
| 5 | Release to first spoken word p50 5.0 s, "10 of 12 within 6.0 s, two at 13.8 and 14.7 s" | `README.md:147`, `eval/qa/VOICE.md:109-120` | Only a hand-written table. No raw per-run file (CSV or JSON) is committed. `VOICE.md:85` says the variant runs were "Not recorded" |
| 6 | Quotes from Meta's docs and Terms, and the billing page text "While using free credits your content may be used for product improvement" (screenshot taken by Deepak) | `README.md:205-234` | External pages and a screenshot that is not committed. A judge cannot check them from the repo |
| 7 | "Judging weights ... Impact 30, Use of Meta tooling 25, Demo 25, Technical depth 20" | `CLAUDE.md:18` | No source committed; the file itself says "confirm in the Official Rules" |
| 8 | Problem statistics: 1 to 5 hours per image, 200 to 1,000 hours per book, the 2007 Tactile Graphics Assistant figures, Smith-Kettlewell, Ray-Ban Meta adoption | `PLAN.md:9-15`, `APPLICATION.md:29` | Named, but no links or references |
| 9 | "feedback from a blind student or teacher I am arranging now"; the User eval "blind tester: find 3 named parts, answer 3 questions" | `APPLICATION.md:39`, `PLAN.md:217,254,263` | No tester session or quotes committed |
| 10 | "No QR codes, no stickers, no special tablet. The camera and the models do the work." | `PLAN.md:7`; also "with no markers", `APPLICATION.md:23,37` | The sheet has printed corner marks and a sighted helper taps four corners (`README.md:160-161`) |
| 11 | `muse-spark-1.3` in "Author S1, S3"; `sam-3.1` in "Explore registration ... Finds the sheet for registration"; Voice is "Streaming speech to text" | `CLAUDE.md:24-26` | S3 uses no model (`README.md:87`); there is no registration (`README.md:160`); voice uses the file endpoint `/asr/transcribe` (`services/api/app/meta/live_client.py:332`) |
| 12 | Routes "figures, ask, register, voice"; geometry "homography, orientation"; `make eval` "writes eval/RESULTS.md" | `CLAUDE.md:40,43,59`, `SKILLS.md:10` | No register or voice route file, no homography or orientation module in `app/geometry/`. `eval/RESULTS.md` does not exist, and `eval/run.py` writes "not run" for every suite |
| 13 | "Code was written before Oct 26, all of it on Oct 24." and "S1 and S2 have only run on mocks." | `CLAUDE.md:17` | Git history: 84 commits on Oct 24, then 184 commits from Oct 27 to Nov 3. The ledger shows live S1 and S2 calls. Stale, and it reads like an eligibility statement |
| 14 | The accessibility pass | `eval/a11y.md` | Last run dated 2026-10-24. Explore changed a lot after that. A real screen reader was "not run" |

### Claims whose cited file does not say what is claimed

| # | Claim | Where | What the cited file says |
|---|---|---|---|
| 1 | "All 9 questions the figures do not answer, and all 7 prompt injections, were sent back to the teacher." | `WRITEUP.md:65-66` | In `eval/qa/scores.json`, injection h30 was answered from the left ventricle's teacher description ("The left ventricle pumps blood out to the whole body through the aortic arch."), source `teacher_description`. It passes by the rule in `eval/qa/README.md:23-28`, but 6 of 7 were sent back, not 7 |
| 2 | "Transcribe on synthetic speech: Every word right on 3 clips, with and without keywords" | `README.md:148` | `eval/qa/VOICE.md:10` shows "What does the the left ventricle do?" with keywords, scored 6/6. `VOICE.md:16` admits the repeated "the". The transcript has an extra word |
| 3 | "S2 against the graded reference masks: ... flower 3 of 3"; "all 3 reference parts regressed" | `README.md:150`, `README.md:169-170` | `eval/plan/RESULTS.md:40` says "regressions 3 of 3 references", but its own table (`RESULTS.md:42-48`) lists 5 flower reference parts, all "still regressed". The file contradicts itself |
| 4 | "Spend: $5.31 of the $150 credits over 1,012 live calls" | `WRITEUP.md:74` | `eval/live/ledger.jsonl` has 1,013 lines (1,012 cache misses, 1 cache hit). 5 lines are not status 200 (4 null, 1 a 401). The total is $5.308. Close, but the count needs a definition |
| 5 | "Spark over the 73 questions of eval/qa/scores.json (Nov 3, v2): p95 16.1 s on the heart, slowest 18.7 s" | `docs/EDGE_CASES.md:59-60` | The current `eval/qa/scores.json` (the minimal effort rerun) has heart Spark p50 3,543.6 ms, p95 5,634.5 ms, slowest 7,690 ms. The cite is stale |
| 6 | "eval/qa/scores.json, 73 questions has Spark at p50 7657 ms on the heart and 6692 ms on the brain, slowest 18693 ms" | `eval/qa/VOICE.md:74-76` | Same file, same problem: it was overwritten by the qa7 run. Now p50 3,543.6 and 3,239.1 ms |
| 7 | "Questions, live, answer prompt v2 at minimal reasoning effort (Nov 3)" | `README.md:145` | `eval/qa/RESULTS.md` has no date, prompt version or effort in it. `scores.json` names the prompt (`ask_answer.v2.json`) but not the effort. The date and effort are only in git history and `VOICE.md:105` |
| 8 | The 2.0 s target for "End of question to first spoken word" | `RULES.md` section 4 | Measured p50 5.0 s (`eval/qa/VOICE.md:115`). `RULES.md` 4.4 says "A budget miss is a bug". The README does not mention the miss |

Claims I checked and found true: about 25 s to "Ready for review." (24.9 s); the 11 npm
advisories; 3.2 mm gap, 6.4 mm point symbol, 5 textures (`config/tactile_rules.yaml`); 10 MB and
50 million pixels; four SAM calls at a time; enter 1 mm and 120 ms, leave 2 mm, 6 earcons a
second, 600 ms dwell, 4 mm contact offset, 1 euro filter (`config/explore.yaml`); 250 ms
post-roll, 15 s cap, 16 kHz (`voice.ts:19-24`); 50 questions and 25 s deadline (`ask.py`); 8 s
and 20 s (`session.ts`); the Contributor model guard; offline hand model; heart 36 of 38 and
35 citations, brain 35 of 35 and 34; picture questions 5 of 6 and 6 of 6; without the image 3
of 6 each; heart 14 of 15, Japan 9 of 9, flower 7 of 13, brain 5 of 6 touchable areas; heart 0
regressions of 4; CI green.

## Placeholder, dummy, boilerplate or filler text

| File:line | Text | Why it matters |
|---|---|---|
| `docs/submission/WRITEUP.md:3-4` | "TBD marks what is not measured yet; fill it in from the named file once it is, or leave it out." | An instruction to the author inside the submission text |
| `docs/submission/WRITEUP.md:69,71,73` | `<!-- tt:voice-device -->TBD<!-- /tt:voice-device -->`, the same for `tt:gate-b` and `tt:earcon-device` | Three TBDs in the write-up a judge reads |
| `docs/submission/VIDEO_SCRIPT.md:38-40` | "TBD: the device latency film", "TBD: Gate B" | Same |
| `README.md:155,159` and `:158` | `<!-- tt:limits-touch -->` markers; "`make results` fills this in from the measurements." | Internal tooling note in the README |
| `eval/run.py:9-17` | `lines += [f"\| {name} \| not run \|" for name in SUITES]` | A stub that marks every suite "not run", including the ones with results. `CLAUDE.md:59` presents `make eval` as a real command |
| `APPLICATION.md:1-65` | "Form: cerebralvalley.ai/e/meta-ai-developer-hackathon/apply ... Submit on Saturday."; "Weavory, an MCP memory server ..."; "Do not claim accessibility experience." | The hackathon application draft: another project's claims, a LinkedIn URL, school and employer, and advice to the author. Should not be in the submission repo |
| `SKILLS.md:10`, `.claude/skills/run-eval/SKILL.md:3,15`, `.claude/skills/demo-readiness/SKILL.md:14` | "Updated `eval/RESULTS.md`" | Points at a file that does not exist |
| `CLAUDE.md:1-3` | "Read this first, every session. It is the map." | Instructions for an AI coding agent. Fine to keep, but a judge reads it as agent boilerplate |
| `CLAUDE.md:32` | "## Repo map (created on Day 1)" | A plan, not the repo as it is (see claims table, row 12) |
| `eval/plan/RESULTS.md:9,31,54,79,87` | "Touchable parts in regions.json: 0." | Repeated zero on every figure looks like a broken metric. It means "before the teacher checks", which the file does not say |
| `README.md:145` | "a lead for a reader, not a verdict" | Jargon; unclear to a judge |
| `apps/web/package.json:4` | `"version": "0.1.0"` | Default boilerplate (minor) |
| `TODO.md` (109 KB), `TRACKER.html` (440 KB) | Generated project memory | Root noise |

I found no marketing filler ("seamless", "robust" and so on) and no em dashes in the docs.
`RULES.md:60` bans them, and the house style is held. The style is terse and consistent
throughout, which reads as agent-written, but it is concrete, not empty.

## Top 10 changes, most effective first

| # | Change | Why it moves the score | Time |
|---|---|---|---|
| 1 | Make sure judges can open the repo: make it public, or confirm the judges' access, before the deadline | `gh repo view` said PRIVATE. If a judge cannot clone, every other score is zero | 5 min |
| 2 | Film and link a short demo video, and put one photo or GIF of the raised sheet, the phone in its mount and a finger at the top of the README | Demo is 25 percent by the quoted weights, and today there is nothing to watch. It is also the only proof that the core touch loop works on a device | 3 to 5 h (the shot list in `docs/DEMO.md` is ready) |
| 3 | Run Gate B and the latency film on the iPhone, then `make results` to fill every TBD | Turns "Whether it works" from belief into a number. Removes six TBDs from the write-up and video script | 1 to 2 h |
| 4 | Fix the judge path for mock questions and the brain: add a one-command `make demo-sheet` (or a button) that publishes the heart and brain exactly as version 4, or list the merge and the two exact teacher descriptions in the README; say to pick grade band "6 to 8" for the brain; mention `TT_API` and `?source=script` for judges without a camera | Today the README quickstart ends in "Questions are not working right now." That is the moment a judge decides it does not work | 1 h |
| 5 | Add an Impact section near the top of the README: the problem with linked sources (from `PLAN.md:9-15`), who uses it, and any feedback from a teacher of the visually impaired or a blind tester, with quotes | Impact is 30 percent. The README never states the problem's size, and there is no user voice anywhere | 1 h to write; a tester session if one can be had |
| 6 | Remove `APPLICATION.md`; fix the stale lines in `CLAUDE.md` (17, 24-26, 40, 43, 59) and `SKILLS.md:10`; make `eval/run.py` call the real evals or delete it | Removes another project's claims and personal details, and stops a judge from finding statements that contradict the code or suggest a rules problem | 30 min |
| 7 | Correct the mis-stated numbers: 6 of 7 injections sent back (all 7 passed); flower reference count 3 vs 5; "every word right" with the doubled "the"; 1,013 logged calls; the stale `scores.json` cites in `EDGE_CASES.md:59-60` and `VOICE.md:74-76`; add date, prompt and effort to the top of `eval/qa/RESULTS.md` | The repo's strongest asset is honesty ("every number names its file"). One wrong number found by a judge costs trust in all of them | 30 min |
| 8 | Restructure the README for a 3 minute read: pitch, hero image, video, the three models and their jobs, results, quickstart. Move the privacy legal section (`README.md:198-263`) to `docs/PRIVACY.md` with a 3 line summary | Judges skim. The best facts (36 of 38, $5.31, 1,110 tests, offline touch) are below the fold, and the legal text is long | 45 min |
| 9 | Make the question eval reproducible from a fresh clone (seed the version 4 sheets from `fixtures/qa/`) and put the reproduce command in each row of the README results table | Backs the README promise "rerun the command to reproduce it", which fails today | 1 h |
| 10 | Strengthen the Meta tooling evidence: record 10 to 20 questions in a real human voice, scored with and without keyword hints; add one image of SAM's outlines over the heart next to the tactile sheet | Meta tooling is 25 percent. The keyword hint feature is claimed but unproven on synthetic speech, and SAM's work is never shown as a picture | 1 to 2 h |

Also worth a short pass if time remains: light CSS on the Author page so screenshots look
finished; state the RULES.md 2.0 s question budget and the measured 5.0 s honestly in Known
limitations.

## Housekeeping

- I ran my own mock API on 127.0.0.1:18000 and Vite on 127.0.0.1:15173, and stopped both at
  the end. The e2e scripts picked their own free ports. Nothing touched ports 8000, 5173 or 8443,
  the original working tree, or GitHub (only read-only `gh run list` and `gh repo view`).
- The replay evals rewrote `eval/plan/RESULTS.md` and `scores.json` in the clone; I restored
  them with `git checkout`. The clone's git status is clean apart from ignored files.
- Logs and screenshots: `<scratchpad>/judge-shots/`,
  `<scratchpad>/quickstart.out`,
  `<scratchpad>/check.log`.
