# Security pass

## Reporting a vulnerability

Please report a vulnerability privately through GitHub's private vulnerability reporting: on
the repository's Security tab, choose "Report a vulnerability"
(https://github.com/DeepakKTS/talking-tactile/security/advisories/new). Do not open a public
issue. Say what you found, how to reproduce it, and what it exposes.
This is a hackathon project maintained by one person, with no bug bounty.

In scope: the code in this repository (the API in `services/api/`, the web app in `apps/web/`,
the Gate B page in `spikes/tracking/`, the scripts). Out of scope: Meta's Model API itself,
and a deployment on a network other than the local one it is built for (see below).

## Threat model and known gaps

The build is for one Mac and one phone on a home or school network, run by the teacher. It
protects the Meta API key, the student's questions, and the credits. It is not built for the
open internet.

- No route has a login. Anyone who can reach the Mac's web server can upload, edit, publish and
  read a figure whose id they know.
- Cross-site requests (fixed Nov 3, `docs/review/QA.md` F02): a request that changes something
  and that the browser marks `Sec-Fetch-Site: cross-site` is refused with 403 before the route
  runs (`services/api/app/middleware.py` CrossSiteGuard), and a typed question must be JSON
  (415 otherwise). A request with no such header (curl, an older browser) still passes; CORS
  hides every answer (`services/api/tests/test_cross_site.py`).
- Uploads have no rate limit, and the fix-call cap starts over with each edit version
  (`docs/review/QA.md` F04, F05).
- The API on 127.0.0.1:8000 accepts any Host header, so DNS rebinding from a browser on the Mac
  is possible (F24).
- Prompt injection: a question or a teacher's description goes into Spark's prompt. The
  schema, the cited-id check and the fixed off-figure sentences limit what comes back, and all
  7 injections in the eval passed, but an answer from the figure is spoken as Spark wrote it,
  up to two sentences.
- Storage: uploaded images, published sheets and the job database stay in `data/` with no
  expiry. Uvicorn's access log prints the client's address.
- The budget stop counts per process and starts at $0 on each restart; it does not read the
  ledger (F39).

## What was checked

What was checked before the demo (Nov 3, night), what was found, and what was fixed. Each fix
is its own commit, named in the tracker. The project runs on one Mac on a home network for a
demo; nothing here is hardened for the open internet.

## Secrets

Checked:
- Every object in the git history (3,279) and the working tree, for the current Meta API key
  (compared in code, never printed), private key blocks, AWS key ids, GitHub, Slack and
  OpenAI-style tokens, bearer tokens, and the key's variable name assigned a value; and every
  path ever committed, for `.env`, `.pem`, `.key`, `.p12` and `.pfx` files.
- What the pre-commit secret check (`scripts/check_secrets.py`) covers.

Found:
- Nothing in the history or the tracked files. `services/api/.env` and `apps/web/.certs/`
  have never been committed; both are git-ignored.
- The secret check covered the key, assignments of the key's variable and `.env` files, but not
  certificate or key files: a force-added `apps/web/.certs/phone-key.pem` would have passed.

Second pass (Nov 3, review): unreachable objects too (`git fsck --unreachable --no-reflogs`).
One unreachable blob holds an earlier Meta API key, not the current one (compared in code,
never printed; that key gave 401 on Nov 3). No ref reaches it, so a push does not send it, but
a copy of the folder or a local clone does. Pruning it (`git reflog expire
--expire-unreachable=now --all && git gc --prune=now`) is the owner's call.

Fixed:
- The secret check now refuses `*.pem`, `*.key`, `*.p12` and `*.pfx` files and any staged file
  holding a private key block (tests in `scripts/test_check_secrets.py`).

## Inputs

Checked:
- Figure ids: every figure route checks the id against 64 lowercase hex characters before it
  is used (`app/routes/figures.py` `_fid`, `app/pipeline/cache.py` `is_figure_id`); questions
  check it in the request model (`app/ask.py` `AskRequest`).
- Versions: an integer of at least 1, or "latest". File names: only the listed ones
  (`MEDIA_TYPES`, `DRAFT_ONLY_TYPES`); anything else is a 404. No file path is built from free
  text, so there is no path traversal. Region ids are matched against the figure's own
  regions or validated (`RegionId`, letters, digits and _ up to 32).
- Questions: up to 500 characters; up to 10 recent parts; a session id of up to 64 safe
  characters; extra fields refused. Audio: mono 16-bit WAV at 16 or 24 kHz only.
- Uploads: 10 MB, 50 million pixels, PNG, JPEG or PDF by content (`app/pipeline/s0_ingest.py`).

Found:
- Only the figure upload had a size limit. A question, an edit or a fix call could send a body
  of any size, read whole into memory.

Fixed:
- Every request with a body must say its length and fit: the upload 10 MB, a question or a
  transcription 2 MB (a 15 s recording is about 720 KB), anything else 64 KB. A body over its
  limit is refused with 413 before it is read, one with no length with 411
  (`app/middleware.py`, tests in `services/api/tests/test_body_guard.py`).

## Network

Checked (listening sockets on the Mac, `lsof`, during the demo setup):
- The API (uvicorn) listens on 127.0.0.1:8000 only (`make dev`, `docs/DEMO.md`): the phone never
  reaches it directly, only through the web server's proxy.
- `npm run dev:phone` (Vite) listens on every interface at :5173, over HTTPS with the mkcert
  certificate, so the iPhone on the same network can open it. That is what the demo needs.
- The Gate B page's server (`spikes/tracking/serve.py`) listens on every interface at :8443,
  over HTTPS, and serves `spikes/tracking` only (Python's handler refuses paths outside its
  folder).
- CORS on the API allows only http://localhost:5173 and http://127.0.0.1:5173; the phone uses
  the proxy, same origin, so it needs none.

Found:
- The LAN dev server was allowed to read the whole repository: with Vite's default deny list it
  refused `.env`, `*.pem` and `.git`, but served any other file, among them the private test
  figure (`fixtures/private/`, not openly licensed), the job database (`data/`), the cost
  ledger and the API code. Checked on the running server: 200 for each.

Fixed:
- The dev server reads only `apps/web` and the two repo files the app imports,
  `config/explore.yaml` and `docs/regions.schema.json` (`apps/web/vite.config.ts` DEV_FILES).
  The running server now answers 403 for the private figure. Test:
  `apps/web/scripts/devserver.test.ts` starts a dev server from the project config and checks
  both lists; it fails on the old setting.

## Abuse

Checked:
- Each Explore session has 50 questions (`app/ask.py` SessionCap), counted in memory; a new
  session id starts a new count, so it limits one student, not a client that makes up ids.
- Fix outline calls have a cap per figure and edit version (30 live SAM calls).
- Every live run has a cap of calls (`config/tactile_rules.yaml` live_call_cap).

Found:
- No limit per client: a client could ask questions or send fix calls as fast as it liked,
  each a paid Meta call.

Fixed:
- Per client, at most 30 questions (`/api/ask` and `/api/transcribe` together) and 30 fix calls
  in any minute; more get 429 `rate_limited`, which Explore says as "Too many questions at once.
  Wait a moment, then ask again." The client is the connecting address or, through the web
  server's proxy on this machine (which now forwards the phone's address), the first
  X-Forwarded-For address; the header is ignored from any other machine, so it cannot be used
  to claim a fresh address (`app/middleware.py` RateLimit, `apps/web/vite.config.ts` xfwd,
  tests in `services/api/tests/test_rate_limit.py`).

Correction (Nov 3, review, `docs/review/QA.md` F03): the code takes the first X-Forwarded-For
entry, which a client on this machine can set. A phone through the proxy is still counted by
its own address only because uvicorn's default proxy-header handling replaces the client
address before RateLimit runs. A fix is queued.

## Dependencies

Checked (Nov 3): `uvx pip-audit` on every pinned Python package of `services/api/uv.lock`
(`uv export`, with the dev group), and `npm audit` on `apps/web`.

Found and fixed:
- `pypdf` 6.21.2 had 7 known vulnerabilities (CVE-2026-119203 to CVE-2026-119209), fixed in
  6.21.3 and 6.21.4. Upgraded to 6.21.4, a patch release; the render and ingest tests pass.
  pip-audit now finds no known vulnerability.

Left, with the reason:
- npm: 11 moderate advisories, no high or critical one, all in the lint tool chain (`eslint`,
  `@eslint/js`, `typescript-eslint` and their `minimatch` and `@eslint/*` dependencies), which
  never ships to the browser. Every fix npm offers is a major version change of those tools,
  which is not a patch; left for after the hackathon.

## Logs and storage

Checked:
- What a question leaves behind. `services/api/tests/test_ask_retention.py` sends a spoken
  question, a typed one, a transcription and a heard question through the real live client (a
  fake network underneath) and searches every file written and every log record: no audio, no
  transcript and no question text. The access log has the method, path, status, time and a
  request id; the cost ledger has one line per Meta call with the figure, the question's length
  (or, for audio, the number of keyword hints), the tokens, the cost and the time, not the text.
- What the phone keeps (`localStorage`): the published regions.json of each sheet opened (so
  it reopens offline), the Explore settings and the calibration corners. No question or answer.
- What the phone prints: only the hand tracker's start, ready and GPU fallback lines. The dev
  server copies the phone's console to the Mac's terminal, so nothing else is said there.

Found: nothing to fix.

## Headers

Checked: the response headers of the API, the web app (dev server and built preview) and the
Gate B page's server. None sent a Content-Security-Policy or X-Content-Type-Options.

Fixed:
- Every API response says `X-Content-Type-Options: nosniff` (`app/middleware.py`
  RequestContext, test in `services/api/tests/test_api_figures.py`).
- The web app's pages and files come with a Content-Security-Policy, nosniff and
  `Referrer-Policy: no-referrer` (`apps/web/vite.config.ts` SECURITY_HEADERS, DEV_HEADERS;
  test in `apps/web/scripts/devserver.test.ts`). Scripts, workers, connections, images and
  media only from the app's own origin (plus blob: for workers and the camera stream), no
  plugins, no framing, no other `<base>`. The page can fetch nothing from another host. Under `dev:phone`
  the policy also allows websockets to any host, for Vite's reload socket.
- The Gate B page gets the same headers, with jsDelivr (MediaPipe's bundle and wasm) and
  Google's model storage (the hand model) as the only other origins (`spikes/tracking/serve.py`;
  `spikes/tracking/e2e_check.py` serves the page through the same handler).

Left, with the reason:
- `script-src` allows `'unsafe-eval'` in the app: Ajv compiles the regions.json schema check
  with `new Function` (`src/shared/regions.ts`), and without it neither Author nor Explore loads.
  Building the check ahead of time would remove it; that changes the contract check, so it waits
  until after the hackathon. The dev server also allows inline scripts and its reload websocket,
  which Vite needs.
- `style-src` allows inline styles, which React's `style` attributes use.

Verified by running: every Gate B check (`loop`, `fallback`, `session`, `touch-session` and
`mediapipe`, which loads the real MediaPipe from the CDN and fails on any policy message), the
four app e2e flows on the built preview (Explore's device check runs the real MediaPipe on the
GPU), and the device check in Chrome against the running `dev:phone`: hand tracker on the GPU at
20 frames a second, no policy or page errors. The headless checks wait with `page.evaluate`
polling instead of Playwright's `wait_for_function`, which builds its test with eval and is
blocked by the policy.

WebKit (Nov 3): Playwright's WebKit 26.6, the engine closest to iPhone Safari, through dev:phone
and the Gate B server with the real headers: no policy violation and no blocked wasm or worker
on the device check, the heart's version 4 in Explore (Start) or the Gate B page; MediaPipe
ran on the GPU in all three, and the device check came back with the camera, hand tracker and
microphone ok. Its Wake Lock row failed only when the test granted the camera: Playwright's
permission grant in WebKit refuses every permission it does not list. With no grant, the Wake
Lock was held and released, with and without the headers. If a phone still refuses something,
`TT_CSP=off` leaves the policy out (`docs/DEMO.md`; tests in `apps/web/scripts/devserver.test.ts`).
