"""Renders the synthetic figure through S3 to S5 into data/synthetic/ for printing:

    make synthetic-sheet

Writes print.pdf (sheet and key), tactile.svg, regions.json and report.json (the rules
check, which must be empty).
"""

import json
from pathlib import Path

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.geometry.compose import build_sheet
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.geometry.validate import check_svg_ids, validate_sheet
from app.paths import REPO_ROOT
from app.render.pdf import render_pdf
from app.render.regions_json import FigureInfo, build_regions_file
from app.render.svg import render_key_svgs, render_sheet_svg
from app.synthetic.load import load_synthetic

OUT = REPO_ROOT / "data" / "synthetic"
TEXT_PHRASE = "text label"


def main(out: Path = OUT) -> None:
    rules, explore, fig = load_tactile_rules(), load_explore(), load_synthetic()
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, fig.truth.page, rules.page)
    parts = [m for m in fig.raw_masks.values() if m.label != TEXT_PHRASE]
    text = [m for m in fig.raw_masks.values() if m.label == TEXT_PHRASE]
    rec = reconcile(parts, text, fit.mm_per_px, rules.reconcile)
    composed = build_sheet(
        parts=rec.parts,
        image=fig.image,
        fit=fit,
        grade_band=fig.truth.grade_band,
        color_carries_meaning=fig.truth.color_carries_meaning,
        rules=rules,
        earcons=explore.earcons,
        translator=Translator(rules.braille),
    )
    svg = render_sheet_svg(composed.sheet, fig.truth.title, rules, explore)
    keys = render_key_svgs(composed.sheet, composed.braille, composed.translations, rules)
    info = FigureInfo(figure_id="synthetic", title=fig.truth.title,
                      figure_type="labeled_diagram", summary=fig.truth.summary)  # fmt: skip
    # As published once the teacher has checked every part: Explore's tests touch them all.
    checked = frozenset(r.group_key for r in composed.sheet.regions)
    regions = build_regions_file(composed.sheet, composed.braille, info, rules, verified=checked)
    report = [v.model_dump() for v in validate_sheet(composed.sheet, rules)]
    report += [v.model_dump() for v in check_svg_ids(svg, regions)]
    out.mkdir(parents=True, exist_ok=True)
    (out / "tactile.svg").write_text(svg, encoding="utf-8")
    (out / "print.pdf").write_bytes(render_pdf([svg, *keys]))
    (out / "regions.json").write_text(json.dumps(regions.to_json_obj(), indent=1) + "\n",
                                      encoding="utf-8")  # fmt: skip
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {1 + len(keys)} pages, {len(report)} rule violations")


if __name__ == "__main__":
    main()
