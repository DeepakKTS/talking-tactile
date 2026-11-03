# QA and security review

> Saved from the reviewer's report unchanged except for redactions: local paths, the author's email, the Mac's name, LAN addresses and the private figure's file name; two mentions of the key variable are reworded so the repo's secret check passes. Triage of every finding: `docs/review/TRIAGE.md`.

- Repository: Talking Tactile, fresh clone at `scratchpad/qa-clone`
- Commit reviewed: `c3503ab40c4980d77493fee0c24f82925429d9c6` (main, "License field: Apache-2.0 in both package.json files, the lockfile root and pyproject.toml")
- Date: 2026-11-03
- Reviewer: QA and red team pass, read-only on the clone. Probes ran in a throwaway copy (`scratchpad/qa-run`) against a mock-mode API on 127.0.0.1:18731 and a Vite dev server on 127.0.0.1:15731. No live Meta call was made, and nothing touched ports 8000, 5173 or 8443.

File and line numbers refer to the reviewed commit. Paths are from the repo root unless noted.

## What was run

| Check | Result |
|---|---|
| `uv run pytest` (services/api, MOCK_META=1) | 752 passed, 0 failed |
| `npx vitest run` (apps/web) | 27 files, 358 tests passed |
| `vite build` (apps/web) | builds; 512 KB main chunk warning |
| `npm audit` | 11 moderate, all dev-only (eslint chain); 0 in runtime deps |
| `pip-audit` on the locked Python deps | no known vulnerability |
| Every claim in docs/EDGE_CASES.md marked "fixed" | each named test exists and passes; the code matches the claim |
| Probes on the mock API and the Vite proxy | results below |

## Summary

39 findings: 1 high, 10 medium, 28 low.

The one high finding is a copy of what looks like the Meta API key. It is a loose, unreachable git object in the original repo's object store, and every local clone made from that folder has a copy too. A push to GitHub sends only objects that a ref can reach, so this object does not go to GitHub. A zip or a copy of the folder does take it. The medium findings are about abuse of paid calls. Any web page can send simple cross-origin POSTs that start uploads, questions and publishes. Uploads have no rate limit. The fix-call cap starts over with every edit. The rate limit reads the wrong X-Forwarded-For entry. There are also two Explore behaviors that differ from the docs, a privacy point on commit emails, and the macOS-voice audio clips.

## 1. Edge cases

### docs/EDGE_CASES.md "fixed" claims

Every "fixed" row was checked against the code and its named test. All hold:

- U2 pixel limit: `services/api/app/pipeline/s0_ingest.py:44,82-83,92-93,108-109`.
- U4 blank: `s0_ingest.py:193-194`.
- U7 page 1: `s0_ingest.py:186-188`.
- U8 describe only: `apps/web/src/author/AuthorPage.tsx:12,167-168`.
- U11 duplicate: `AuthorPage.tsx:62-68,87`.
- E2 fix cap sentence: `services/api/app/figures.py:233-247`.
- E6 nothing touchable: `figures.py:170-181,502`.
- X1 alert: `apps/web/src/explore/ExplorePage.tsx:515`.
- X2 other version: `apps/web/src/explore/loader.ts:20,71`.
- X3 Start comes back: `ExplorePage.tsx:313-322`.
- Q2 timeouts: `apps/web/src/explore/camera.ts:118-129`, `apps/web/src/explore/session.ts:95-99,404-418`, `services/api/app/ask.py:51`, `services/api/app/routes/ask.py:63,81`.
- Q7 and Q8 microphone: `apps/web/src/explore/voice.ts:29-34,286-305,314`.
- Q10 thinking tone: `session.ts:364-376`.
- S1 to S4 job errors: `services/api/app/pipeline/runner.py:119-127`.
- S5 spoken codes: `camera.ts:104-116`.

Line numbers in EDGE_CASES.md are as of commit 4debae0 and have drifted (finding F25).

### Probes (mock API on :18731)

| Input | Result | Verdict |
|---|---|---|
| Empty file, text file, PNG magic plus garbage | 415, 415, 422 with plain messages | ok |
| No `file` field, JSON body to upload | 422 "file: Field required" | ok |
| Chunked upload, no Content-Length | 411 "Send the request with its length." | ok, see F18 |
| `page_index=1.5` | 422 "page_index: Input should be a valid integer, unable to parse string as an integer" | ok, wording technical |
| `page=a3` | 422 "page: Input should be 'letter' or 'a4'" | ok |
| Uppercase or short figure id; `..%2f` paths | 400 bad_figure_id; 404 | ok, no traversal |
| `source.png`, `repairs.json`, unknown file name | 200, 200, 404 | ok |
| Image 20000 x 3 px | 500 "Something went wrong." | F12 |
| Zero-page PDF, encrypted PDF | 422 "The PDF file could not be read." | F19 |
| PDF page 10^9 | 422 "The PDF has 1 pages. Pick one of them." | F19 |
| 16-bit gray PNG, CMYK JPEG, EXIF-rotated JPEG, animated PNG | accepted and normalized | ok |
| `/api/ask` empty, bad JSON, a list, a 600-character question | 422 "The question request is not valid." | ok, see F16 |
| `/api/ask` body with invalid UTF-8 | 500 "Something went wrong." | F13 |
| `/api/ask` version 0 or 10^23 | 404 "This figure has no published version N." | ok |
| `/api/transcribe` with JSON, or with a non-WAV audio part | 422, 404 before the WAV check when unpublished | ok |
| Malformed multipart, no boundary | 400 "Invalid multipart data." / "Missing boundary in multipart." | ok |
| Fix points outside the figure, 3-tuples, 1e400 | 422 with plain messages | ok |
| Label of 5000 characters | 422 "label.label: String should have at most 80 characters" | ok, wording |
| Label with an em dash, NUL and U+202E | 202 accepted; the next job failed at S4 | F14 |
| Cross-origin `text/plain` POST to `/api/ask`, multipart upload, empty POST to `/publish` with `Origin: http://evil.example` | processed: question sent to the model client, job created, version 1 published | F02 |
| 32 questions through the Vite proxy, each with a new `X-Forwarded-For` | none refused | F03 |
| Foreign `Host:` header | Vite 403; API 200 | F24 |

### Edge-case findings

- **F02 (medium) Cross-site request forgery on paid and state-changing routes.** Some routes take a body type that a browser can send cross-origin with no preflight. `routes/ask.py:36-46` reads JSON whatever the Content-Type, so `text/plain` works. The upload is `multipart/form-data` (`routes/figures.py:71-87`). Publish has no body (`routes/figures.py:150-154`). CORS (`services/api/app/main.py:90-96`) only hides the response. The server still runs the route. Any page the teacher or student opens can start uploads (paid S1 and S2 calls), questions (paid Spark calls) and publishes on the API, or on the LAN dev server. Chrome's local network prompts help in Chrome only. Fix: for every POST and PATCH, require `Content-Type: application/json` for JSON bodies. Also require a custom header (for example `X-Requested-With`) or a same-origin `Origin` or `Sec-Fetch-Site`. Return 403 otherwise. Code.
- **F03 (medium) The rate limit trusts the first X-Forwarded-For entry.** `services/api/app/middleware.py:142-150` takes `forwarded.split(",")[0]`. Vite's proxy appends the real address after whatever the client sent (`node_modules/vite/dist/node/chunks/node.js:19240`), so the first entry is the client's choice. A phone on the LAN is still counted right today. That is because uvicorn's default `--proxy-headers` (trusted 127.0.0.1) replaces the client address with the right-most untrusted entry before RateLimit runs. Verified: 32 of 32 rotated requests passed from the Mac, and a phone-shaped chain got 429 at 31. So the protection depends on an undocumented uvicorn default. Any client on the Mac (a browser tab, F02) gets a fresh bucket each request. `services/api/tests/test_rate_limit.py:48-55` asserts the wrong rule. `docs/SECURITY.md:89-95` describes it as the protection. Fix: take the right-most entry that is not loopback, or rely on uvicorn's value and drop the header parsing. Then fix the test and the doc. Code and docs.
- **F04 (medium) Uploads have no rate limit and no per-client cap.** `middleware.py:134-140` limits only questions and `/fix`. Each new image (one changed pixel is a new figure id) starts S1 and S2 with up to 25 live calls (`config/tactile_rules.yaml:56`). Runs of different figures run at the same time with no limit (`figures.py:410-413,438-439`). There is no authentication on any Author route (`services/api/app/routes/figures.py`). Fix: rate-limit `POST /api/figures`, cap jobs per client per hour, and cap concurrent pipeline runs. Code.
- **F05 (medium) The fix-call cap starts over with every edit.** `figures.py:298-304` keys the capped client by `(figure_id, edit_version)`. Any cheap edit, such as a rename, gives 30 more paid SAM calls. Fix: cap per figure per day, or across versions. Code.
- **F06 (medium) Explore questions ignore the version Explore loaded.** `session.ts:325-333` never sends `version`, so `ask.py:130` falls back to the latest published version. Say a student opens `?version=1` or a saved copy, and the teacher then publishes version 2 with merged or renamed parts. The student's region ids and touch context are read against version 2. The answer can be about a sheet the student is not touching. Fix: send `version: file.version` (or the loaded number) in `request()`. Code.
- **F07 (medium) The saved sheet is used only when fetch throws.** `loader.ts:39-48` uses the saved copy only on a network exception. Through the dev server, a stopped API returns 502 from Vite's proxy (`vite/dist/node/chunks/node.js:19907`). Explore then says "The sheet could not be loaded (502)." and does not use the saved copy. There is also no service worker, so a page reload with the Mac's server down loads nothing. `README.md:117-118` ("Explore works offline, with the last good copy of each sheet kept on the device") overstates this. Fix: fall back to the saved copy on any status of 500 or more. Say in the README that offline means no internet with the Mac's server still up. Code and docs.
- **F12 (low) An extreme aspect ratio crashes S0.** A 20000 x 3 image gives 500 "Something went wrong.", marked retryable. `_resize` rounds the short side to 0 (`s0_ingest.py:151-158`, called at `:200`), and cv2 raises an error that `errors.py:71-74` turns into a 500. Fix: refuse images whose short side would be under a few pixels after resizing, with a plain message. Code.
- **F13 (low) A JSON body that is not UTF-8 gives a 500.** `routes/ask.py:45-48` catches `JSONDecodeError` but not `UnicodeDecodeError`. Fix: catch `ValueError`. Code.
- **F14 (low) Edits accept control characters and dashes.** `services/api/app/pipeline/edits.py:39-40` (`Text`, `LongText`) accepts NUL, bidi controls and em dashes. The edit returns 202. Then every job fails at S4 with "label has a control character: '...'" (`services/api/app/braille/louis.py:43`), marked retryable even though a retry cannot help (`figures.py:67`). An em dash in a label is spoken as is, against the voice rule (RULES.md 2, CLAUDE.md "Never"). Fix: refuse control and format characters in the edit model (422), and replace dashes as `ask.py:119` does for answers. Code.
- **F15 (low) Author progress stops after one failed poll.** `AuthorPage.tsx:36-38` sets the error and never schedules another poll. One network blip during a 25 s job leaves the page stuck until reload. Fix: keep polling with backoff. Code.
- **F16 (low) A long typed question gets a vague message.** The Ask box has no `maxLength` (`ExplorePage.tsx:527`). The server limit is 500 (`ask.py:131`). The student hears "The question request is not valid." (`routes/ask.py:47-48`). Fix: add `maxLength={500}`, and say "That question is too long. Ask a shorter one." Code.
- **F17 (low) The server does not cap recording length.** `check_wav` returns the duration (`ask.py:176-190`), but `ask.py:327,342` ignore it. The 2 MB body limit (`middleware.py:70`) allows about 65 s at 16 kHz, and transcription is billed per second. The client caps at 15 s (`voice.ts` MAX_MS). Fix: refuse clips over 16 s on the server. Code.
- **F18 (low) A POST with no body and no Content-Length gets 411.** `middleware.py:94-99`. Browsers send `Content-Length: 0`, but `curl -X POST .../publish` and some HTTP clients do not. Fix: treat a missing length with no Transfer-Encoding as 0, or document it. Code.
- **F19 (low) PDF messages.** `s0_ingest.py:105` says "The PDF has 1 pages." and "0 pages". An encrypted PDF gets "The PDF file could not be read." (`:101-102`), not "it is password protected". Code.
- **F20 (low) In-memory maps grow without bound.** `RateLimit.seen` (`middleware.py:131,156`), `SessionCap.asked` and `credits` (`ask.py:284-285`), `_fix_clients` and `_scenes` (`figures.py:388-389`). Made-up session ids or many figures grow memory until restart. Fix: evict old keys. Code.
- **F21 (low) Test hooks ship in Explore.** `?source=script` takes hands from `window.__tt.inject` (`ExplorePage.tsx:4,138,300`). `window.__tt` is set on every load (`:409`) and holds the last question WAV (`lastWav`, `:71,287`). That is harmless on a student's phone, but it is test code in production. It also keeps a recording in memory after the hold, which the README privacy section does not mention. Fix: gate the hooks behind a build flag. Code.
- **F22 (low) API file responses have no CSP.** API responses carry only nosniff (`middleware.py:41-45`). Through the proxy, `tactile.svg` is served from the app's own origin. ElementTree escapes labels (`services/api/app/render/svg.py:18`), so there is no injection today, but there is no second line of defense. Fix: add `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` to file responses. Code.
- **F23 (low) The Gate B server lists directories.** `spikes/tracking/serve.py:42-46,62` is a `SimpleHTTPRequestHandler` on 0.0.0.0. It lists and serves every file in `spikes/tracking`, including any local output dropped there. Fix: turn off `list_directory`, or allow only the page's files. Code.
- **F24 (low) The API accepts any Host header.** No trusted-host check (`main.py:73-97`). Vite checks the host (403 verified), but the API at 127.0.0.1:8000 can be reached by DNS rebinding from a browser on the Mac. Fix: `TrustedHostMiddleware(allowed_hosts=["127.0.0.1","localhost"])`. Code.

### Cases EDGE_CASES.md misses

F02 to F07 and F12 to F24 above are not listed. The most useful to add are F06 (version mismatch), F07 (5xx does not fall back), F14 (control characters in edits) and F12 (aspect ratio).

- **F25 (low) EDGE_CASES.md line references have drifted.** `docs/EDGE_CASES.md:4-5` says lines are as of 4debae0. Several have moved. For example, U1 cites `s0_ingest.py:160-161`, now `:180-181`. U7 cites `:166-167`, now `:186-188`. Fix: refresh, or cite function names. Docs.
- **F26 (low) `health.no_hand_warn_ms` is still unused.** It is noted in X7, but the key remains in `config/explore.yaml:42`, `services/api/app/config.py:334` and `apps/web/src/shared/config.ts:69`. Fix: remove it, or mark it reserved. Code.

## 2. Links in Markdown

A script checked every tracked `.md` file for relative links, image links and `#anchors`. **No broken link or anchor was found.** Most file references are in backticks, not links. A second pass checked those paths:

- **F27 (low) Stale path references.**
  - `.claude/skills/add-figure-type/SKILL.md:10` names `app/geometry/rules.py`. It does not exist (the validator is `app/geometry/validate.py`). Line 11 names `eval/figures/<type>/`, which does not exist either.
  - `CLAUDE.md:40` lists `app/routes/` "register, voice", `:42` lists "retries, cache" in `app/meta/`, and `:43` lists "rules, homography, orientation" in `app/geometry/`. None of these exist. `CLAUDE.md:17` says "S1 and S2 have only run on mocks", which is stale.
  - `eval/s2-bakeoff/flower/diagnosis_v2.md:4` names `app/meta/s2_armav2.py`, which was deleted.
  - `spikes/tracking/README.md:21` says "main has no `apps/web`". It does now.
  - `eval/RESULTS.md` (`SKILLS.md:10`, `CLAUDE.md:59`, `.claude/skills/run-eval/SKILL.md:15`, `.claude/skills/demo-readiness/SKILL.md:14`), `eval/gate-b/run.md` and `eval/gate-b/voice-latency.csv` are made by commands and not committed. That is fine, but say "generated".

  Docs.
- **F28 (low) Committed HTML reports have broken images.** `eval/s2-bakeoff/{heart,flower,japan_regions}/index.html` use `img/...`, which is git-ignored (`.gitignore:19`). Fix: note it in the page, or drop the images. Docs.
- **F29 (low) README overstates ATTRIBUTION.md.** `README.md:195` says ATTRIBUTION.md lists "every third-party ... library". It lists MediaPipe only. meta-sam-parser and liblouis are in NOTICE only. Docs.

External links (57), not fetched:

- Local: `http://localhost:5173`, `/author`, `http://127.0.0.1:5173`, `http://localhost:8000`.
- GitHub: `https://github.com/DeepakKTS/talking-tactile.git`.
- Meta API: `https://api.meta.ai/v1`, `/chat/completions` and `/responses`.
- Meta docs pages on dev.meta.ai (20): `docs/api-reference/chat-completions/create-chat-completion`, `voice/realtime`, `voice/schemas`, `voice/transcribe`, `error-handling`, `image-understanding`, `media-segmentation`, `pricing-rate-limits`, `prompt-caching`, `reasoning`, `sam/client-libraries`, `sam/overview`, `sam/reading-segmentation`, `sam/segmenting`, `speech-to-text`, `structured-output`.
- Wikimedia Commons file pages (24): Heart_diagram-en.svg, Banana-Single.jpg, Mature_flower_diagram.svg, Eight_regions_of_Japan_(en).svg, Blausen_0111_BrainLobes.png, Index_finger_2.JPG, and 18 eval candidates in `spikes/eval-figures.md`.
- Creative Commons licenses: by-sa 3.0, by-sa 4.0, by 3.0, by 4.0, CC0 1.0.
- Tools and files: `https://docs.astral.sh/uv/`, `https://www.apache.org/licenses/LICENSE-2.0.txt`, `https://www.npmjs.com/package/@mediapipe/tasks-vision`, and the MediaPipe model URL on storage.googleapis.com.

## 3. Stale code

- **TODO, FIXME, XXX, HACK:** none in code or docs. The only hits are the word "todo" as a tracker status and a local variable `todo` in `services/api/app/geometry/overlap.py:50` and `services/api/app/geometry/part_masks.py:257`.
- **Debug output in the shipped web app:** three `console.info` lines in `apps/web/src/explore/tracker.ts:118,128,139` (tracker start, GPU fallback, ready). They are intentional and documented (`docs/SECURITY.md:124-125`). `apps/web/scripts/gen-regions-types.ts:26` is a dev script. Nothing else is printed.
- **`print` in the backend:** only in command-line entry points: `services/api/app/meta/cache_check.py:85,87`, `latency_spike.py:182-184`, `plan_eval.py:423`, `qa_eval.py:155,254`, `s2_score.py:345-346`, `sam_diagnostic.py:166-172`, `smoke.py:113-140`, `services/api/app/pipeline/runner.py:603`, `services/api/app/synthetic/generate.py:205`, `services/api/app/synthetic/sheet.py:59`. None runs in a request.
- **F30 (low) Dev tools and test-only code inside the shipped package.**
  - Eval and spike tools live in `services/api/app/meta/`: `smoke.py`, `latency_spike.py`, `cache_check.py`, `sam_diagnostic.py`, `s2_bakeoff.py`, `s2_score.py`, `s2_grades.py`, `plan_eval.py`, `qa_eval.py`. The server never imports them.
  - Functions used only by tests: `s2_grades.py:59` `tally`, `sam_adapter.py:169` `cache_decodes`, `render/svg.py:179` `texture_geometry`.
  - The type `PointMm` (`apps/web/src/shared/regions.ts:12`) is exported and used nowhere.
  - `apps/web/src/explore/testkit.ts` is a test helper inside `src/`, imported only by tests.

  Fix: move the tools to `services/api/tools/` (or document them), and delete or inline the unused items. Code.
- **F31 (low) Tests import a private symbol of meta-sam-parser.** `services/api/tests/test_live_client.py:13` and `services/api/tests/test_sam_diagnostic.py:15` import `meta_sam_parser._mask_codec._encode_raster`. A patch release can break them. Code.

## 4. Secrets and private data

### Tree and history (reachable objects)

A scan of all 4,026 reachable objects in every branch, and the tracked tree, found:

- No API key value, token, bearer string, AWS, GitHub or Slack key, private key block or certificate.
- No `.env`, `.pem`, `.key`, `.p12` or `.pfx` file, ever.
- `.env.example` sets `MODEL_API_KEY` to an empty value.
- `<repo>/services/api/.env` exists (mode 600). It holds the API key (type: Meta Model API key; value not read). It is git-ignored by `.gitignore:1` and has never been tracked.
- The "emails" the scan matched in `fixtures/recorded/*.json` are base85 mask payloads, not addresses.

### Findings

- **F01 (high) What looks like the API key sits in an unreachable git object.** Blob `349c4da0ab…` is 39 bytes, file name `probe_secret.sh`, in unreachable tree `7a073b5a77…`. It sets `MODEL_API_KEY` to a 24-character value. The value was not printed or compared. `TRACKER.html:4654` says `services/api/.env` was "recovered from the one unreachable git blob holding a MODEL_API_KEY line", so treat it as the live key. It is not in any commit, so `git push` does not send it. But it is in the original repo's object store. It was copied into every local clone made from that folder: both `scratchpad/qa-clone` and `scratchpad/judge-clone` hold it (the throwaway `qa-run` copy was pruned). A zip, an rsync or an upload of the folder with `.git` would publish it. `docs/SECURITY.md:17` says nothing was found, because its scan covered reachable history only.

  Fix:
  1. In the original repo, run `git reflog expire --expire-unreachable=now --all && git gc --prune=now`.
  2. Check with `git fsck --unreachable --no-reflogs`.
  3. Delete the scratchpad clones.
  4. Rotate the key after the demo.
  5. Make the hook test use a fake key.
  6. Extend the SECURITY.md scan to unreachable objects.

  Process and docs.
- **F08 (medium) A personal email is on every commit.** All 268 commits have author and committer `DeepakKTS <<author email>>`. Once the repo is public, the address is public and cannot be removed without a history rewrite. The tracker note at `TODO.md:419` knows about it. Fix: set `user.email` to the GitHub noreply address for future commits. Decide whether to rewrite before publishing (with `git filter-repo --mailmap`). Process.
- **F11 (medium) APPLICATION.md holds personal data.** Line 13 has a LinkedIn URL. Line 16 has the university, degree, graduation month and employer. The file also has draft application answers. Fix: remove the file or the personal lines before publishing, or confirm that sharing them is intended. Docs.
- **F32 (low) Machine and network details are in docs and history.**
  - Current tree: `TRACKER.html:4654` and `TODO.md` name the network address <LAN address>, and `TODO.md:211` and `TRACKER.html:1596` name <LAN address>.
  - Private figure file name: `services/api/app/meta/plan_eval.py:70` (`fixtures/private/<private figure file>`) and `apps/web/scripts/devserver.test.ts`.
  - The private figure's id prefix is in 36 lines of `eval/live/ledger.jsonl` (the owner decided to keep these).
  - History only: `~` and `<your-mac>.local` in older blobs of `TODO.md`, `TRACKER.html`, `docs/DEMO.md` and `eval/gate-b/README.md`. The private figure's old name and full id are also in older commits (the tracker says so).
  - No private image blob exists, reachable or not. The historical question recordings are all on the Commons brain (image digest `49198b46…`).

  Fix: scrub the addresses from the tracker notes. Accept or rewrite the history (the tracker already records the decision "no rewrite"). Docs.
- **F33 (low) The pre-commit secret check matches `.env` by exact name.** `scripts/check_secrets.py:54-55`, so `.env.local`, `.env.bak` and `env.txt` pass. It also knows only the current key, so an old key would pass. Fix: match `.env*`, and add a generic high-entropy check for `*_KEY=` assignments. Code.

## 5. Licenses

### Python runtime dependencies (services/api/uv.lock, `uv export --no-dev`)

| Package | Version | License | Notes |
|---|---|---|---|
| annotated-doc | 0.0.5 | MIT | |
| annotated-types | 0.8.0 | MIT | |
| anyio | 4.15.1 | MIT | |
| cairocffi | 1.7.1 | BSD-3-Clause | needs system Cairo (LGPL-2.1 or MPL-1.1) |
| cairosvg | 2.9.1 | LGPL-3.0-or-later | installed, not distributed: compatible |
| certifi | 2026.10.23 | MPL-2.0 | file-level copyleft, unmodified: compatible |
| cffi | 2.1.1 | MIT-0 | |
| click | 8.5.0 | BSD-3-Clause | |
| cssselect2 | 0.10.1 | BSD-3-Clause | |
| defusedxml | 0.7.1 | PSF-2.0 | |
| fastapi | 0.162.0 | MIT | |
| h11 | 0.16.0 | MIT | |
| httpcore | 1.0.9 | BSD-3-Clause | |
| httpx | 0.28.1 | BSD-3-Clause | |
| idna | 3.20 | BSD-3-Clause | |
| **meta-sam-parser** | 0.1.0 | **SAM License (Meta, not OSI)** | see below |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | wheel bundles LGPL FFmpeg; not distributed |
| opentelemetry-api | 1.45.1 | Apache-2.0 | pulled in by fastapi |
| pillow | 13.0.0 | MIT-CMU | |
| pycparser | 3.12 | BSD-3-Clause | |
| pydantic, pydantic-core | 2.14.1, 2.50.1 | MIT | |
| pypdf | 6.21.4 | BSD-3-Clause | |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0 (PDFium) | |
| python-multipart | 0.0.32 | Apache-2.0 | |
| pyyaml | 6.0.3 | MIT | |
| shapely | 2.2.0 | BSD-3-Clause | bundles GEOS (LGPL-2.1) in the wheel |
| starlette | 1.10.0 | BSD-3-Clause | |
| tinycss2 | 1.5.1 | BSD-3-Clause | |
| typing-extensions | 4.16.0 | PSF-2.0 | |
| typing-inspection | 0.4.4 | MIT | |
| uvicorn | 0.54.0 | BSD-3-Clause | |
| webencodings | 0.6.1 | BSD-3-Clause | |

System tool: liblouis 3.39.0 (Homebrew: GPL-3.0-or-later AND LGPL-2.1-or-later). `lou_translate` is run as a separate process (`services/api/app/braille/louis.py`) and is not distributed. Compatible.

### JS runtime dependencies (apps/web/package-lock.json, non-dev)

| Package | Version | License | License file in package |
|---|---|---|---|
| @mediapipe/tasks-vision | 1.1.0 | Apache-2.0 | none; the repo supplies `apps/web/public/licenses/mediapipe-tasks-vision-LICENSE` |
| ajv | 8.20.0 | MIT | yes |
| fast-deep-equal | 3.1.3 | MIT | yes |
| fast-uri | 3.1.9 | BSD-3-Clause | yes |
| json-schema-traverse | 1.0.0 | MIT | yes |
| require-from-string | 2.0.2 | MIT | yes |
| react, react-dom | 19.3.1 | MIT | yes |
| scheduler | 0.28.0 | MIT | yes |
| zod | 4.6.7 | MIT | yes |

The dev tree has 255 packages, all permissive or weak copyleft, none shipped: MIT 201, Apache-2.0 19, ISC 12, MPL-2.0 12 (lightningcss), BSD-2/3 12, BlueOak-1.0.0 4, CC-BY-4.0 1 (caniuse-lite data), Python-2.0 and PSF-2.0 (argparse), CC0 1.

### Vendored or committed third-party files

| File | License recorded | Where |
|---|---|---|
| `apps/web/public/models/hand_landmarker.task` | Apache-2.0, full text next to it | ATTRIBUTION.md, `apps/web/public/models/LICENSE` |
| `fixtures/heart.png` and derivatives | CC BY-SA 3.0, credit line | ATTRIBUTION.md, NOTICE, README:72-73 |
| `fixtures/eval/japan_regions.png` and derivatives | CC BY-SA 4.0 | ATTRIBUTION.md, NOTICE |
| `fixtures/eval/brain_lobes.png` and derivatives | CC BY 3.0 | ATTRIBUTION.md, NOTICE |
| `fixtures/eval/flower.png` and derivatives | public domain | ATTRIBUTION.md, NOTICE |
| `fixtures/control/banana.png` | CC BY-SA 3.0 | ATTRIBUTION.md, NOTICE |
| `eval/s2-bakeoff/*/reference/*.png` (16) | follow their figure | ATTRIBUTION.md |
| `fixtures/pipeline/*`, `fixtures/qa/*`, `fixtures/recorded/*` | follow their figure | ATTRIBUTION.md |
| `docs/submission/screenshots/*.png` | CC BY-SA 3.0 (heart) | ATTRIBUTION.md, README |
| `fixtures/audio/*.wav` (4) | "Apple's terms for its system voices" | ATTRIBUTION.md:76-94; **not in NOTICE** |
| `fixtures/synthetic/*`, `spikes/tracking/test-sheet.pdf`, `fixtures/regions/*`, `docs/submission/architecture.svg`, `captions.srt` | own work | ATTRIBUTION.md |

Every committed figure, audio clip and model file has its license recorded. The `eval/s2-bakeoff/*/index.html`, `v2.html` and `v2f.html` report pages (text about the figures) are not listed. That is minor.

### meta-sam-parser and the SAM License

- What it is: "SAM License, Last Updated: November 19, 2025", in `meta_sam_parser-0.1.0.dist-info/licenses/LICENSE`. Repository: `https://github.com/meta-models/meta-sam`. It grants use, reproduction, distribution and modification.
  - If you distribute the SAM Materials, you must do so under the same agreement and include a copy of it (1.b.i).
  - Research publications must acknowledge SAM (1.b.ii).
  - Use must follow trade controls, with no ITAR or military uses (1.b.iii, 1.b.v).
  - No reverse engineering of the underlying components (1.b.iv).
  - Indemnity and termination clauses apply. California law governs.
  - It is not an open-source license.
- What NOTICE says (`NOTICE:19-20`): it is a dependency installed from PyPI and is not distributed here.
- What the repo does: matches NOTICE. No source from the package is vendored or copied: `git ls-files` has no `meta_sam_parser` code, and `services/api/app/meta/sam_adapter.py:35` only imports it. `services/api/pyproject.toml:21` pins it, and `services/api/uv.lock:401-406` hash-pins it. Two tests import a private function of it (F31), which is use, not copying. The recorded SAM outputs in `fixtures/recorded/` come from the hosted API, so Meta's API terms govern them, not this license.
- Terms reproduced or linked: neither, and none is required while nothing is distributed. Apache-2.0 for this repo is therefore compatible. Two gaps:
  - **F34 (low) The SAM License is not linked or explained.** `make install` silently installs a package whose terms bind each user (trade controls, no reverse engineering). NOTICE gives the license name only, and ATTRIBUTION.md does not mention it. Anyone who ships a built image (a Docker image or a venv) would need to include the license text. Fix: link the license in NOTICE and README "Needs", list it in ATTRIBUTION.md, and add a line for redistributors. Docs.

### Other license findings

- **F09 (medium) The macOS `say` audio clips go public against the project's own note.** `ATTRIBUTION.md:84` says "Replace this clip with a recording of our own voice before anything built from it is shown publicly", and `:94` applies the same to the other three clips. Apple's terms for system voices limit their output to personal, non-commercial use, which sits badly with a public repo whose code is under Apache-2.0. NOTICE does not mention the clips at all. Fix: replace the four WAVs with the owner's own recording, or with speech from an openly licensed TTS voice, and update the recordings' digests. Otherwise, at least list them in NOTICE as "not under Apache-2.0, Apple's terms". Code (fixtures) and docs.
- **F35 (low) A built bundle has no notices for its MIT and BSD libraries.** `vite build` writes no license comments into `dist/assets/*.js`. Only the MediaPipe license is copied to `dist/licenses/`. Nothing in the repo ships `dist/`, but anyone who deploys it would be missing the notices for react, react-dom, scheduler, ajv, zod, fast-uri and others. Fix: add a license-collecting build step, or a `public/licenses/THIRD_PARTY.txt`. Code.

## 6. docs/SECURITY.md, a fresh read

What holds:

- The inputs section (figure id regex, versions, file name allowlist, question limits, WAV checks, upload limits) matches the code.
- The body guard (411 and 413 before the body is read) matches the code. Verified 411 on chunked uploads.
- The dev server file allowlist works. `/@fs/` paths to `services/api`, `data/`, `eval/live/ledger.jsonl` and `config/tactile_rules.yaml` gave 403, and only `config/explore.yaml` and the schema were served. `.certs/*.pem` gave 403 when present.
- The CSP, nosniff and no-referrer headers are present on the dev server.
- The secret check covers key files.
- pip-audit is clean, and npm has 11 moderate dev-only advisories, as stated.
- The phone's console output is as stated.

What is wrong or missing:

- **F10 (medium) Missing parts.**
  - (a) There is no way to report a vulnerability: no contact, no "use GitHub private vulnerability reporting", no SECURITY policy for a public repo. GitHub shows `SECURITY.md` as the policy, so it should say how to report.
  - (b) There is no threat model. The doc does not say that no route has authentication, so anyone who can reach the Mac's web server can upload, edit, publish and read any figure whose id they know.
  - (c) It does not mention cross-site request forgery (F02), DNS rebinding (F24), unlimited uploads (F04), the fix-cap reset (F05), or prompt injection. A question or a teacher's description goes into the Spark prompt (`ask.py:221,255`), and a "figure" answer is spoken as Spark wrote it, up to two sentences.
  - (d) Under "Logs and storage" it omits that uploaded images, published sheets and the job database stay in `data/` with no expiry. Uvicorn's own access log also prints the client address and port.
  - (e) The budget stop is per process (`services/api/app/meta/cost.py:29-32,62-72`). It starts at $0 on every restart and does not read the ledger. "Every call is metered" is true, but $150 is not a hard total.

  Fix: add a "Reporting" section and a short "Threat model and known gaps" section. Docs.
- **F03 again (medium):** `SECURITY.md:89-95` says the forwarded header "cannot be used to claim a fresh address". The app code reads the client-controlled entry. What actually protects the phone path is uvicorn's proxy-header default.
- **F36 (low) An overstated CSP claim.** `SECURITY.md:141` says "The page can send nothing to another host." Under `dev:phone`, which is the demo setup, `connect-src` adds `ws: wss:` for any host (`apps/web/vite.config.ts:59-60`). Navigation is also not limited by CSP. Fix: limit the dev websocket to the page's own host (`'self'` covers same-origin ws in current browsers), or reword the claim. Code or docs.
- **F37 (low) A stale or incomplete history scan.** `SECURITY.md:10` says "Every object in the git history (3,279)". There are 4,026 reachable objects now. The scan also skipped unreachable objects, where F01 was found. Fix: rerun the scan, include `git fsck --unreachable`, and update the count and date. Docs.
- **F38 (low) CI actions are pinned by tag, not SHA.** `.github/workflows/tests.yml:23,31,36` use `@v4` and `@v5`. Permissions are read-only, which limits the risk. Fix: pin by commit SHA once the repo is public. Code.
- **F39 (low) The budget guard resets on restart** (part of F10e). It is listed apart because it is code. Fix: seed `CostMeter.spent_usd` from `eval/live/ledger.jsonl` at start. Code.

## Notes on this review

- To avoid live calls, all probes ran in mock mode. Fix-outline previews with points were refused before any SAM call, because the points were off the figure.
- About 64 early probe requests went by mistake to 127.0.0.1:15173. That port turned out to be another session's mock Vite server (`scratchpad/judge-clone`), proxying to a mock API on :18000. The requests had `{}` bodies and were refused at validation or by the rate limit, so no model call was possible.
- Two of my servers are still running, from `scratchpad/qa-run`: the mock API on 127.0.0.1:18731 (PID 35182) and Vite on 127.0.0.1:15731 (PID 36763). They were not stopped, because of the rule against signalling processes. They can be stopped any time.
- `scratchpad/qa-clone` and `scratchpad/judge-clone` still hold the unreachable key blob (F01). They should be deleted once the reviews are done.

## All findings

| ID | Severity | Area | File:line | Finding | Suggested fix | Fix type |
|---|---|---|---|---|---|---|
| F01 | high | 4 Secrets | original repo `.git/objects`, blob 349c4da0ab (tree 7a073b5a77, `probe_secret.sh`); TRACKER.html:4654 | An unreachable blob holds a 24-character MODEL_API_KEY value (the key .env was restored from); local clones copy it | `git reflog expire --expire-unreachable=now --all && git gc --prune=now`; delete the clones; rotate the key; use a fake key in hook tests | process and docs |
| F02 | medium | 1 Server | services/api/app/routes/ask.py:36-46; routes/figures.py:71-87,150-154; main.py:90-96 | Cross-origin simple POSTs (text/plain ask, multipart upload, empty publish) are processed: CSRF on paid and state-changing routes | Require JSON Content-Type and a custom header or same-origin Origin or Sec-Fetch-Site on POST and PATCH | code |
| F03 | medium | 1 Server, 6 | services/api/app/middleware.py:142-150; tests/test_rate_limit.py:48-55; docs/SECURITY.md:89-95 | The rate limit takes the first, client-controlled X-Forwarded-For entry; only uvicorn's default proxy handling saves the phone path | Use the right-most non-loopback entry or uvicorn's value; fix the test and the doc | code and docs |
| F04 | medium | 1 Author | services/api/app/middleware.py:134-140; figures.py:410-413,438-439; config/tactile_rules.yaml:56 | Uploads are not rate limited or capped per client, and runs are unbounded; each new image can make 25 live calls; no auth | Rate-limit uploads, cap jobs per client, cap concurrent runs | code |
| F05 | medium | 1 Author | services/api/app/figures.py:298-304 | The fix-call cap starts over at every edit version, so a rename gives 30 more SAM calls | Cap per figure across versions or per day | code |
| F06 | medium | 1 Explore | apps/web/src/explore/session.ts:325-333; services/api/app/ask.py:130 | Questions never send the loaded version; answers come from the latest published version | Send the loaded version in AskRequest | code |
| F07 | medium | 1 Explore | apps/web/src/explore/loader.ts:39-48; README.md:117-118 | The saved sheet is used only when fetch throws; a 502 from the proxy shows an error; no service worker | Fall back on 5xx too; reword the offline claim | code and docs |
| F08 | medium | 4 Privacy | all 268 commits (author and committer) | A personal university email is on every commit | Use the GitHub noreply email; decide on a mailmap rewrite before publishing | process |
| F09 | medium | 5 Licenses | fixtures/audio/*.wav; ATTRIBUTION.md:76-94; NOTICE | The macOS `say` voice clips go public although ATTRIBUTION says to replace them first; NOTICE omits them | Replace them with own or openly licensed speech, or list them in NOTICE as under Apple's terms | code and docs |
| F10 | medium | 6 Security doc | docs/SECURITY.md (whole) | No vulnerability reporting route; no threat model (no auth, CSRF, DNS rebinding, uploads, prompt injection, retention, per-process budget) | Add "Reporting" and "Threat model and known gaps" sections | docs |
| F11 | medium | 4 Privacy | APPLICATION.md:13,16 | LinkedIn, university, graduation date, employer and application drafts in the repo | Remove the file or the personal lines, or confirm it is intended | docs |
| F12 | low | 1 Author | services/api/app/pipeline/s0_ingest.py:151-158,200 | A 20000 x 3 image crashes cv2.resize and gives a 500 | Refuse extreme aspect ratios with a plain message | code |
| F13 | low | 1 Questions | services/api/app/routes/ask.py:45-48 | A non-UTF-8 JSON body gives a 500 | Catch ValueError and return 422 | code |
| F14 | low | 1 Author edits | services/api/app/pipeline/edits.py:39-40; braille/louis.py:43; figures.py:67 | Control characters and em dashes are accepted; the job then fails at S4 with a technical message marked retryable | Refuse them in the edit model; replace dashes | code |
| F15 | low | 1 Author | apps/web/src/author/AuthorPage.tsx:36-38 | Progress polling stops for good after one failed poll | Retry with backoff | code |
| F16 | low | 1 Questions | apps/web/src/explore/ExplorePage.tsx:527; ask.py:131; routes/ask.py:47-48 | No maxLength on the Ask box; over 500 characters the student hears "The question request is not valid." | Add maxLength=500 and a specific sentence | code |
| F17 | low | 1 Questions | services/api/app/ask.py:176-190,327,342 | The server ignores the clip length; 2 MB allows about 65 s of billed audio | Refuse clips over 16 s | code |
| F18 | low | 1 Server | services/api/app/middleware.py:94-99 | A POST with no body and no Content-Length (for example curl to /publish) gets 411 | Treat a missing length with no Transfer-Encoding as 0, or document it | code |
| F19 | low | 1 Author | services/api/app/pipeline/s0_ingest.py:101-105 | "The PDF has 1 pages."; an encrypted PDF is called unreadable | Fix the plural; say "password protected" | code |
| F20 | low | 1 Server | middleware.py:131,156; ask.py:284-285; figures.py:388-389 | In-memory maps per client, session and figure never shrink | Evict old entries | code |
| F21 | low | 1 Explore | apps/web/src/explore/ExplorePage.tsx:4,71,138,287,300,409 | Test hooks (`?source=script`, `window.__tt`, last WAV) ship in production | Gate them behind a build flag | code |
| F22 | low | 1 Server | services/api/app/middleware.py:41-45 | API file responses (SVG, PDF) carry no CSP but are same-origin through the proxy | Add a restrictive CSP with sandbox to file responses | code |
| F23 | low | 1 Server | spikes/tracking/serve.py:42-46,62 | The Gate B server lists directories on every interface | Disable listing; allow the page's files only | code |
| F24 | low | 1 Server | services/api/app/main.py:73-97 | The API accepts any Host, so DNS rebinding is possible against 127.0.0.1:8000 | TrustedHostMiddleware for localhost and 127.0.0.1 | code |
| F25 | low | 1 Edge doc | docs/EDGE_CASES.md:4-5 and the tables | Line numbers are from 4debae0 and have drifted | Refresh them, or cite functions | docs |
| F26 | low | 1, 3 | config/explore.yaml:42; services/api/app/config.py:334; apps/web/src/shared/config.ts:69 | `health.no_hand_warn_ms` is unused | Remove it or mark it reserved | code |
| F27 | low | 2 Links | .claude/skills/add-figure-type/SKILL.md:10-11; CLAUDE.md:17,40,42,43; eval/s2-bakeoff/flower/diagnosis_v2.md:4; spikes/tracking/README.md:21 | References to files and modules that do not exist; stale statements | Update the paths and statements | docs |
| F28 | low | 2 Links | eval/s2-bakeoff/{heart,flower,japan_regions}/index.html | Images point to the git-ignored img/ folder | Note it or drop the images | docs |
| F29 | low | 2, 5 | README.md:195 | Says ATTRIBUTION.md lists every library; it lists MediaPipe only | Reword, or add the libraries | docs |
| F30 | low | 3 Stale code | services/api/app/meta/{smoke,latency_spike,cache_check,sam_diagnostic,s2_bakeoff,s2_score,s2_grades,plan_eval,qa_eval}.py; s2_grades.py:59; sam_adapter.py:169; render/svg.py:179; apps/web/src/shared/regions.ts:12; apps/web/src/explore/testkit.ts | Dev tools and test-only code in the shipped package; an unused export | Move to tools/ or document; delete the unused items | code |
| F31 | low | 3 | services/api/tests/test_live_client.py:13; tests/test_sam_diagnostic.py:15 | Tests import the private `meta_sam_parser._mask_codec._encode_raster` | Use public API, or pin and comment | code |
| F32 | low | 4 Privacy | TRACKER.html:1596,4654; TODO.md:211,419; services/api/app/meta/plan_eval.py:70; history of TODO.md, TRACKER.html, docs/DEMO.md, eval/gate-b/README.md | Network addresses, the private figure's file name, and in history the Mac user path and Bonjour name | Scrub the current tree; accept or rewrite history | docs |
| F33 | low | 4 Secrets | scripts/check_secrets.py:54-55 | Only `.env` by exact name is refused; only the current key is matched | Match `.env*`; add a generic key-assignment check | code |
| F34 | low | 5 Licenses | NOTICE:19-20; ATTRIBUTION.md; README.md:17-25 | The SAM License is named but not linked; its use terms bind every installer; ATTRIBUTION omits it | Link the license and note its terms for users and redistributors | docs |
| F35 | low | 5 Licenses | apps/web/vite.config.ts (build); dist/ | The built bundle has no MIT or BSD notices for react, ajv, zod, fast-uri and others | Add a license-collecting build step or THIRD_PARTY file | code |
| F36 | low | 6 Security doc | docs/SECURITY.md:141; apps/web/vite.config.ts:59-60 | "The page can send nothing to another host" is false under dev:phone (`ws: wss:` for any host) | Limit the dev websocket to the page's host, or reword | code or docs |
| F37 | low | 6 Security doc | docs/SECURITY.md:10,17 | Object count stale (3,279 vs 4,026); the scan skipped unreachable objects | Rerun with fsck --unreachable; update | docs |
| F38 | low | 6 Supply chain | .github/workflows/tests.yml:23,31,36 | Actions pinned by tag, not commit SHA | Pin by SHA | code |
| F39 | low | 6 Abuse | services/api/app/meta/cost.py:29-32,62-72 | The $150 budget stop is per process and starts at $0 on restart | Seed the meter from the ledger at start | code |
