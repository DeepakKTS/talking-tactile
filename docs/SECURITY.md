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
