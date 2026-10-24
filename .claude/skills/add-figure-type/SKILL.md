---
name: add-figure-type
description: Add support for a new figure type in the authoring pipeline, such as bar charts, line graphs, maps, labeled diagrams or cell diagrams. Use when a figure type is classified but renders poorly or is rejected.
---

# Add a figure type

1. Add the type to the `FigureType` enum in `app/pipeline/s1_understand.py` and to `docs/regions.schema.json`.
2. Add type-specific guidance to the S1 prompt: what counts as a part, which parts to drop, how labels are usually attached.
3. Add simplification rules in `app/geometry/rules.py` if the type needs them. Example: line graphs keep axes and data lines, drop grid lines.
4. Pick three real figures of this type with known open licenses. Put them in `eval/figures/<type>/` with a `truth.json` listing the parts a teacher would expect.
5. Run `tactile-rules-check` on all three outputs. Fix until clean.
6. Run `run-eval` for the authoring suite and record the part recall.

Hard rules
- Never let a type-specific rule break a global rule in `config/tactile_rules.yaml`.
- If a type cannot be made tactile honestly (a photograph, for example), S1 must return `recommend_description_only` instead.
