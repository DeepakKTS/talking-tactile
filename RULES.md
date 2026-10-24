# RULES.md

These are hard rules. If a rule blocks you, stop and record the conflict with "python scripts/tracker.py decision". Do not work around it.

## 1. Secrets and privacy

1.1 The Meta API key lives only in `services/api/.env`. The browser never sees it.
1.2 Camera frames stay in the browser during exploring. The only frame that leaves the device is the single registration frame, sent once, with a spoken notice first. The backend never writes it to disk.
1.3 No accounts, no analytics, no third party scripts in Explore mode.
1.4 Use Standard mode for Muse Spark, not Contributor mode, for anything that includes a real student's voice.

## 2. Grounding and honesty in answers

2.1 Spoken answers come from `regions.json`, the figure summary, and the question. If the figure does not show it, the answer says so in one sentence.
2.2 Spatial facts are computed in code and passed to the model as data. The model may phrase them, never invent them.
2.3 Every region carries `source` and `verified_by_teacher`. Unverified labels are spoken with no hedging words, but the teacher review screen flags them in amber.
2.4 Never describe the figure with sight words such as "as you can see" or "the red part". Colors are mentioned only when the original figure's legend depends on them, and then as "the area marked red in print".

## 3. Tactile design rules

3.1 All numbers come from `config/tactile_rules.yaml`. No magic numbers in geometry code.
3.2 Minimum gap between two raised elements: 3.2 mm (1/8 inch).
3.3 At most 5 area textures per sheet, 3 for lower grades.
3.4 Point symbols at least 6.4 mm (1/4 inch).
3.5 Represent, do not interpret. Simplify clutter, but never add content that is not in the source figure.
3.6 The renderer fails loudly if a rule is broken. It does not silently shrink things past the minimum.

## 4. Performance budgets (targets, measured not assumed)

| Path | Target | Where it is measured |
|---|---|---|
| Fingertip enters region to earcon | under 100 ms | `explore/metrics.ts` |
| Dwell to spoken label | dwell time plus under 150 ms | `explore/metrics.ts` |
| End of question to first spoken word | under 2.0 s | `explore/metrics.ts` and api logs |
| Author one figure end to end | under 90 s | pipeline job timings |

4.1 The camera loop processes only the newest frame. If the worker is busy, drop the frame. Never queue frames.
4.2 Images go to SAM at a longest side of 2048 px or less.
4.3 Polygons are simplified to 200 vertices or fewer per region.
4.4 A budget miss is a bug. Log it with "python scripts/tracker.py issue", including the measured number.

## 5. Reliability

5.1 Every Meta call goes through `app/meta/client.py`: timeout, retry with exponential backoff and jitter on 429 and 5xx, a concurrency limit, and the cost meter.
5.2 Every Meta response used in a test or demo is recorded as a fixture so `MOCK_META=1` reproduces it.
5.3 Pipeline stages are pure functions of their inputs plus a content hash. Re-running a stage with the same inputs returns the cached result.
5.4 If the network drops during exploring, labels, earcons and guidance keep working. Only questions stop, and the app says so.

## 6. Accessibility in Explore mode

6.1 Every action works from the keyboard. Space is push-to-talk. R is recalibrate. Escape stops speech.
6.2 Every spoken sentence is also written to an `aria-live="polite"` region.
6.3 A setting chooses who speaks: the app voice, or the user's screen reader. Never both.
6.4 Audio onboarding runs on first open and can be replayed with H.
6.5 No information is carried by color alone, anywhere in the app.

## 7. Writing style for anything a user hears or reads

7.1 Short sentences. One idea each.
7.2 No em dashes or en dashes. No filler like "seamless", "robust", "leverage", "delve", "unlock", "empower".
7.3 Spoken labels are the label only. "Left ventricle", not "This is the left ventricle".
7.4 Spoken answers are one or two sentences. The student can say "more".

## 8. Scope discipline

8.1 Nothing from "Enhancements" in PLAN.md starts before Gate C passes.
8.2 Feature freeze at noon on Nov 3. After that, only bug fixes, the demo video and the README.
8.3 If a task runs over its time box by half again, stop and pick its fallback in TRACKER.html. If it has none, propose one to me before continuing.

## 9. Code

9.1 Python: 3.11, ruff, mypy on `app/`, pydantic models for every request, response and Meta structured output.
9.2 TypeScript: strict mode, no `any`, eslint clean.
9.3 Tests: pytest for geometry, rules and pipeline. vitest for homography, filter, region engine and state machine.
9.4 Small commits with a plain message saying what changed and why.
