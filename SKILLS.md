# SKILLS.md

Repeatable procedures for this project. Each one also exists as a Claude Code project skill in `.claude/skills/<name>/SKILL.md`, so Claude Code can load it when the task matches. This file is the human index.

| Skill | Use it when | Output |
|---|---|---|
| `meta-api-spike` | Touching a Meta endpoint for the first time, or a call behaves oddly | A latency note, a saved fixture, a confirmed request shape |
| `add-figure-type` | Supporting a new kind of figure (bar chart, map, cell diagram) | Prompt changes, rule checks, three eval items |
| `tactile-rules-check` | After any change to geometry or rendering | A pass or a list of violations with locations |
| `run-eval` | Before a gate, and before recording the demo | Updated `eval/RESULTS.md` |
| `demo-readiness` | Day 9, before recording | A checked list and a go or no-go |
| `accessibility-pass` | After any Explore UI change | Keyboard and screen reader results |

## How to use them

Ask in plain words, for example "run the tactile rules check on the heart figure". Claude Code picks the matching skill from its description. If it does not, name the skill directly.

## Adding a new skill

Make a folder `.claude/skills/<name>/` with a `SKILL.md` that starts with YAML front matter holding `name` and `description`. Keep the description specific, because it decides when the skill fires. Add a row to the table above.
