# Security pass

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
- The Gate B page's server listens on every interface at :8443, over HTTPS, and serves
  `spikes/tracking` only (Python's handler refuses paths outside its folder).
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
