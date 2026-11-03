# Contributing

Thank you for helping. Talking Tactile is small, and every change is held to the same checks.

## Set up

Needs macOS or Linux, [uv](https://docs.astral.sh/uv/), Node 24 and liblouis
(`brew install liblouis`, or `apt install liblouis-bin liblouis-data`).

```
make install
sh scripts/install-hooks.sh     # once per clone: the pre-commit hook
MOCK_META=1 make dev            # API on :8000, web on :5173, no network, no key
```

Mock mode answers from the recordings in `fixtures/recorded/`. Live mode needs a Meta Model API
key in `services/api/.env` (copy `.env.example`); never put it anywhere else.

## Tests

```
make check                                        # pytest, vitest, ruff, eslint, mypy, tsc
python3 -m unittest scripts/test_*.py             # tracker, secret check, hook, results tools
cd spikes/tracking && node --test test/*.test.mjs # the Gate B page, held to the app's code
```

The pre-commit hook runs all three on the staged content and refuses a commit that holds the
API key. CI (`.github/workflows/tests.yml`) runs them on Linux with no key and no network.

## The gates

A change is ready when all of these pass:

1. `make check` and the two commands above.
2. The graded figures are unchanged. Run `cd services/api && uv run python -m app.meta.plan_eval`
   and check that `git diff eval/plan` is empty. If your change is meant to move a score,
   say which and why in the pull request.
3. The touch checks: `uv run spikes/tracking/e2e_check.py session`.
4. The browser tests, in headless Chrome on the mock API: `uv run apps/web/e2e/explore_e2e.py`,
   `fix_e2e.py`, `plan_e2e.py` and `ask_e2e.py` in the same folder.
5. CI is green.

Stage with `git add`, then run `git commit`. Do not commit with a path (`git commit <path>`,
`-o` or `-i`): the hook then runs on a temporary index.

## Add a figure to the eval set

1. Use an openly licensed figure. Put it in `fixtures/eval/` and add its title, author,
   source, license and credit line to `ATTRIBUTION.md` (and to `NOTICE` if it is share-alike).
2. Run it live once through the pipeline with recording on, so the eval can replay it at no
   cost: `caffeinate -i env LIVE=1 META_RECORD=plan_NAME uv run python -m app.pipeline.runner FILE`
   from `services/api`. Check that the recordings in `fixtures/recorded/` hold no key.
3. Add it to `FIGURES` in `services/api/app/meta/plan_eval.py`, rerun the plan eval, and
   commit the new section of `eval/plan/RESULTS.md`.
4. For questions, add lines to `eval/qa/questions.jsonl` (see `eval/qa/README.md` for the
   categories and the scoring rule) and run `app.meta.qa_eval` live once with
   `META_RECORD=qa`.

## Style

Short, concrete sentences in anything a user will hear or read. No em dashes. Directions,
neighbors and distances come from code, never from a model. See `RULES.md`.

## Security

Report a vulnerability privately, as `docs/SECURITY.md` describes. Please do not open a public
issue for it.
