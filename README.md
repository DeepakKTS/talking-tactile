# Talking Tactile: planning kit

Drop these files into the root of the repo on Day 1.

| File | What it is for |
|---|---|
| CLAUDE.md | Read automatically by Claude Code at the repo root. The project map |
| RULES.md | Hard rules: privacy, grounding, tactile design, budgets, accessibility, style |
| SKILLS.md | Index of the project skills in `.claude/skills/` |
| TODO.md | Day by day checklist with gates and fallbacks. Generated from TRACKER.html by `python scripts/tracker.py todo` |
| PLAN.md | The full plan: architecture, pipeline, edge cases, eval, risks, demo |
| APPLICATION.md | What to type into the hackathon application |
| config/tactile_rules.yaml | Design constants with their sources |
| config/explore.yaml | Starting values for the region engine |
| docs/regions.schema.json | The contract between Author and Explore |
| .env.example | Backend settings. Copy to services/api/.env |

The PDF "Talking Tactile Build Plan" explains all of this with diagrams.

## Privacy

This build runs on free Meta Model API credits. On free credits, Meta may use the content of
requests for product improvement. This build sends a student's spoken question to Meta's API:
when a student holds the screen and asks, Explore records the question in the browser and the
backend sends that recording to Muse Voice Transcribe, then sends the transcript, with the
published figure and its image, to Muse Spark. A typed question goes to Muse Spark the same way.
Classroom use needs paid API usage without that condition.

What stays where:

- The recording is made in the browser only while the screen is held. The backend passes it to
  the transcribe endpoint and keeps no copy; the transcript comes back to Explore with the
  answer and is shown on the student's screen only.
- The cost ledger (`eval/live/ledger.jsonl`) logs every Meta call with its time and price. For a
  question it logs the figure and the question's length, never its words. (Lines from the
  question eval of Oct 30, logged before this rule, hold the eval's own synthetic questions.)
- Recordings of calls are written only when a developer sets `META_RECORD`; the ones in
  `fixtures/recorded/` are synthetic questions and synthetic speech.
- Camera frames stay in the browser (RULES.md 1.2), and the API key stays on the backend.
