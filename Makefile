# Talking Tactile. Run from the repo root.
API := services/api
WEB := apps/web
UV := uv run --project $(API)

.PHONY: dev api web install test test-api test-web lint typecheck eval check synthetic-sheet preflight demo-live demo-mock demo-sheets results

install:
	@command -v lou_translate > /dev/null || { echo "liblouis is missing: brew install liblouis"; exit 1; }
	cd $(API) && uv sync
	cd $(WEB) && npm ci

# api on :8000, web on :5173. Ctrl-C stops both.
dev:
	@trap 'kill 0' INT TERM; \
	(cd $(API) && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd $(WEB) && npm run dev) & \
	wait

api:
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

web:
	cd $(WEB) && npm run dev

test: test-api test-web

test-api:
	cd $(API) && uv run pytest

test-web:
	cd $(WEB) && npx vitest run

lint:
	cd $(API) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB) && npx eslint . --max-warnings 0

typecheck:
	cd $(API) && uv run mypy
	cd $(WEB) && npx tsc -b --noEmit

eval:
	$(UV) python eval/run.py

# The synthetic figure through S3 to S5, into data/synthetic/ (print.pdf to print and trace).
synthetic-sheet:
	cd $(API) && uv run python -m app.synthetic.sheet

# Everything the pre-commit hook runs for product code.
check: test lint typecheck

# Before a demo or a take: OK or FAIL per check, non-zero on any FAIL (scripts/preflight.py).
# PREFLIGHT=--live adds the live smoke, one call per Meta model.
preflight:
	python3 scripts/preflight.py $(PREFLIGHT)

# The API, the phone's web server and the Gate B page, under caffeinate -i; prints the iPhone URLs.
demo-live:
	sh scripts/demo.sh live

# Mock mode only: the heart and the Commons brain published as the question eval published them,
# into data/, so typed questions get their recorded answers (app/demo_sheets.py). Fresh clone.
demo-sheets:
	cd $(API) && env -u LIVE MOCK_META=1 uv run python -m app.demo_sheets

demo-mock:
	sh scripts/demo.sh mock

# The phone measurements (eval/gate-b/: the Gate B JSON, latency.csv, voice-latency.csv) into
# eval/gate-b/RESULTS.md, the TBDs in README and docs/submission, and the tracker's metrics.
results:
	python3 scripts/results.py
