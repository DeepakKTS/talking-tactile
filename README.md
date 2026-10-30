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

This build sends a student's spoken question to Meta's API: when a student holds the screen
and asks, Explore records the question in the browser and the backend sends that recording to
Muse Voice Transcribe, then sends the transcript, with the published figure and its image, to
Muse Spark. A typed question goes to Muse Spark the same way.

What Meta's docs say (read on Oct 30, 2026 at dev.meta.ai; RULES.md 1.4):

- The mode is chosen by the model in each request, not by a request field: on pay-as-you-go
  you "switch between the two by choosing the model ID" (docs/models), and the Terms of
  Service say "the designation of the Services as Contributor Services or Standard Services is
  determined by the designation of the Model you are using" (section 1).
- Standard: "In Standard mode, you pay standard prices and your content is not used to train
  Meta models" (docs/pricing-rate-limits). Under the Terms, Meta "will not use Content
  submitted in a request to the Standard Services to train Meta Models" (section 5.1).
- Contributor: "discounted pricing or more usage in exchange for permission to use your
  content", meaning "the prompts, code, files, and context you send, plus the model responses
  you get back", "to train future Meta models" (docs/pricing-rate-limits). The Terms add "You
  must not submit sensitive, confidential, or personal information to the Contributor
  Services" and "the Contributor Services do not offer a mechanism to exclude specific traffic
  from training" (section 6.2).
- Which models: Muse Spark has both (`muse-spark-1.3` Standard, `muse-spark-1.3-contributor`
  Contributor). "Contributor mode isn't available for Muse Voice Transcribe." SAM 3.1 and Muse
  Voice Transcribe are listed as Standard Models (legal/geographic-use-policy).
- Coding harness subscriptions (Muse Code) are Contributor by default "regardless of which
  Meta Model you select"; Standard there needs "the applicable setting in your Account"
  (Terms, section 3.3).
- Credits: the docs read do not say that free or promotional credits change how request
  content is used; the mode does. The Terms mention promotional credits (section 13.3) and
  leave use "through promotional credits" out of Meta's indemnity for the Standard Services
  (section 17.2). An earlier version of this section said that on free credits Meta may use
  request content for product improvement; the docs read on Oct 30 do not say that.
- Retention: the pricing page mentions zero data retention ("priced at parity with Standard
  mode" for Muse Voice Transcribe); the pages read do not say how to get it.

What this build does: every call uses a Standard model (`muse-spark-1.3`, `sam-3.1`,
`muse-voice-transcribe-1.0`), and the backend refuses to start with a Contributor model id
(`app/config.py`, MetaModels).

What the teacher or school must do before a class uses it:

- Run it with an API key on the Model API, not through a Muse Code or other coding harness
  subscription, or set that account to Standard (Terms, section 3.3).
- Keep the models in `config/tactile_rules.yaml` as they are.
- Read Meta's terms for retention and promotional credits themselves, or ask Meta: the pages
  above do not settle how long request content is kept, or how to get zero data retention.

What stays where:

- The recording is made in the browser only while the screen is held, and a quarter second
  after. The backend passes it to
  the transcribe endpoint and keeps no copy; the transcript comes back to Explore with the
  answer and is shown on the student's screen only.
- The cost ledger (`eval/live/ledger.jsonl`) logs every Meta call with its time and price. For a
  question it logs the figure and the question's length, never its words. (Lines from the
  question eval of Oct 30, logged before this rule, hold the eval's own synthetic questions.)
- Recordings of calls are written only when a developer sets `META_RECORD`; the ones in
  `fixtures/recorded/` are synthetic questions and synthetic speech.
- Camera frames stay in the browser (RULES.md 1.2), and the API key stays on the backend.
