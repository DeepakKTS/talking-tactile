# CLAUDE.md

Read this first, every session. It is the map. Details live in PLAN.md, RULES.md and SKILLS.md.

## What we are building

Talking Tactile turns a printed STEM figure into a raised graphic that a blind student explores by touch. A phone camera watches the sheet, finds the student's fingertip, and speaks the name of the region under it. The student can ask questions out loud and get short answers grounded in that figure.

Two users:
- The teacher or transcriber (Author mode). Uploads a figure, reviews what the system found, prints the tactile sheet.
- The student (Explore mode). Touches the sheet, hears labels, asks questions. Must work with no screen.

## Hackathon facts that shape every decision

- Meta Global AI Developer Hackathon, Indie track, solo. Build window Oct 26 to Nov 4, 2026. Submission due Nov 4, 9:00 PM ET. Our own deadline is Nov 4, 3:00 PM ET.
- Budget: $150 of Meta Model API credits. Every call is metered by `services/api/app/meta/cost.py`.
- Code was written before Oct 26, all of it on Oct 24. The Official Rules allow pre-event work (decision of Oct 27). On main: the planning documents, `scripts/tracker.py` with its tests, the Spark, SAM and Voice spike scripts in `spikes/` (written from the docs, dry runs only, no live call yet), and the tracking spike in `spikes/tracking/` (test sheet, touch-test page, `analyze_touch.py`, `e2e_check.py`, parity tests against the shipped code). Also on main, merged from branch `early-start` on Oct 27 (the branch is kept, with no commits outside main): the FastAPI backend (regions contract, config loaders, pipeline S0 to S5 with a per-stage cache and SQLite jobs, braille through `lou_translate`, the rules validator, the figure routes with publish refusing rule violations, a Meta client interface with a mock and a SAM adapter stub only) and the React app (Author upload, review, publish and print; Explore camera, hand worker, homography, 1 euro filter, region engine, audio, guidance and local intents). S1 and S2 have only run on mocks. The ask route (spoken and typed questions) exists since Oct 30; register does not.
- Judging weights (from a guide quoting the event waiver, confirm in the Official Rules): Impact 30, Use of Meta tooling 25, Demo 25, Technical depth 20.

## Meta models we use, and why each one is here

| Model | Where | Job |
|---|---|---|
| `muse-spark-1.3` | Author S1, S3. Explore answers | Reads the figure, proposes parts as short phrases, maps labels to masks, answers questions from figure data |
| `sam-3.1` | Author S2. Explore registration | Segments every proposed part zero-shot. Finds the sheet for registration |
| `muse-voice-transcribe-1.0` | Explore voice | Streaming speech to text with keyword hints built from region labels |

Base URL `https://api.meta.ai/v1`, OpenAI compatible. Voice uses `wss://api.meta.ai/v1/asr/realtime`. Confirm exact request shapes for SAM and Voice on Day 1 with the `meta-api-spike` skill before writing feature code against them.

We do not use Muse Image. A generative model must never redraw a science figure, because a student would learn from a picture that is not the textbook's.

## Repo map (created on Day 1)

```
apps/web/            React + TypeScript + Vite. Routes /author and /explore
  src/explore/       camera loop, worker, homography, region engine, audio
  src/author/        upload, review, print
  src/workers/       hand tracker worker (MediaPipe Hand Landmarker)
services/api/        Python 3.11, FastAPI
  app/routes/        figures, ask, register, voice
  app/pipeline/      s0_ingest .. s5_render, one file per stage
  app/meta/          client, retries, cache, cost meter, mock fixtures
  app/geometry/      vectorize, rules, homography, orientation
  app/braille/       liblouis wrapper
config/tactile_rules.yaml   sourced design constants
docs/regions.schema.json    the contract between author and explore
eval/                figures, touch tests, questions, scripts
fixtures/            recorded Meta responses for MOCK_META=1
```

## Commands

```
make dev          # api on :8000, web on :5173
make test         # pytest + vitest
make lint         # ruff + eslint
make typecheck    # mypy strict on app/ + tsc
make check        # test + lint + typecheck, what the pre-commit hook runs
make eval         # runs eval/ and writes eval/RESULTS.md
uv run spikes/tracking/e2e_check.py session   # the whole touch test through the spike page, scripted hands, about 50 s. Run before Gate B
uv run apps/web/e2e/explore_e2e.py   # headless Chrome on a mock API: author flow, Explore online and offline, no local voice, camera with MediaPipe. Prints JSON, exits non-zero on a failed check
uv run apps/web/e2e/fix_e2e.py   # headless Chrome on the mock API: Fix outline of the heart's aorta from recorded clicks, publish, Explore touches it
uv run apps/web/e2e/plan_e2e.py  # headless Chrome on the mock API: the heart's merge proposal in one press, publish, Explore speaks a valve line at the crossing and "Heart" on the silhouette
cd services/api && uv run python -m app.meta.plan_eval   # S1's plan on every eval figure from live recordings, no calls; writes eval/plan/RESULTS.md
uv run apps/web/e2e/ask_e2e.py   # headless Chrome on the mock API: publish the heart as the question eval did, then a typed question answered from the figure and an off-figure one deflected
cd services/api && uv run python -m app.meta.qa_eval   # Explore's question eval on replay, no calls; --live with LIVE=1 META_RECORD=qa for a live run; writes eval/qa/RESULTS.md
MOCK_META=1 make dev   # no network, uses fixtures/ and the recordings in fixtures/recorded/replays.json, costs nothing
cd apps/web && npm run cert:phone   # once per LAN address: an mkcert server certificate for the iPhone into apps/web/.certs/ (git-ignored); the mkcert root must be trusted on the phone
cd apps/web && npm run dev:phone    # Vite over HTTPS on the LAN (API proxied as usual); on the iPhone open https://<LAN address>:5173/explore?check=1 for the device check
sh scripts/install-hooks.sh   # once per clone: pre-commit runs the tracker and tracking tests and make check on the staged content
```

Wrap every live run (LIVE=1) in `caffeinate -i`, so the Mac cannot sleep mid-run: `caffeinate -i env LIVE=1 uv run python -m app.pipeline.runner FILE`. On Oct 29 an idle sleep broke a run between two calls.

## The contract

`docs/regions.schema.json` is the single source of truth between Author and Explore. Breaking changes to regions.json need a version bump. Additive optional fields don't, but are listed in PLAN.md with the date. The version stays 3. Explore must work from `regions.json` alone, with no network, for labels and earcons.

## Definition of done for any task

1. Works in mock mode and live mode.
2. Has a test, or an eval item if it is perceptual.
3. Logged latency or cost if it touches a Meta model or the camera loop.
4. Keyboard-only flow still works in Explore.
5. Tracker updated with scripts/tracker.py, then TODO.md regenerated with python scripts/tracker.py todo.

## Never

- Put the Meta API key in the browser. All Meta calls go through the backend.
- Let the language model guess geometry. Directions, neighbors and distances come from code.
- Block the main thread with hand tracking. It runs in a Web Worker.
- Add infrastructure we do not need (see "Not building" in PLAN.md).
- Use em dashes or filler words in any text a user will hear or read.

## Tracker
TRACKER.html is the project memory. Update it only with scripts/tracker.py, never by hand.
- Start of every session: python scripts/tracker.py show
- Starting a task: python scripts/tracker.py status <id> doing
- Finishing: python scripts/tracker.py status <id> done --note "what was done and measured"
- Blocked or cut: the same command, with the reason in --note
- New task: python scripts/tracker.py add <day> TITLE [--detail TEXT] [--timebox TEXT] [--fallback TEXT] [--tags a,b]
- Numbers: tracker.py metric. Bugs: tracker.py issue. Choices: tracker.py decision. Gates: tracker.py gate.
- Run python3 scripts/tracker.py spend before the final commit of every phase; include the spent line in the phase report.
