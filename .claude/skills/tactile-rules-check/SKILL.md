---
name: tactile-rules-check
description: Validate a rendered tactile SVG and its regions.json against the sourced design rules (gaps, texture count, point symbol size, braille spacing, page bounds). Use after any geometry, layout or rendering change.
---

# Tactile rules check

1. Run `python -m app.geometry.validate <figure_id>`.
2. The validator loads `config/tactile_rules.yaml` and checks:
   - every pair of raised elements is at least `min_gap_mm` apart
   - distinct area textures do not exceed the limit for the grade level
   - point symbols are at least `point_symbol_min_mm`
   - braille labels keep their clearance and never overlap lines
   - every region polygon is valid, closed and inside the page
   - every region in the SVG exists in regions.json and the reverse
3. Report each violation with region id, rule name, measured value and limit.
4. Fix the cause in geometry code. Never loosen a rule to make a figure pass.
