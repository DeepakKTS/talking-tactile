# Talking Tactile. Run from the repo root.
API := services/api
WEB := apps/web
UV := uv run --project $(API)

.PHONY: dev api web install test test-api test-web lint typecheck eval check synthetic-sheet

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
