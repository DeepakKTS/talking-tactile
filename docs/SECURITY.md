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
