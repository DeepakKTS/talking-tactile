"""S5 render: tactile.svg, print.pdf (the sheet, then any key pages), regions.json and
report.json, the rules check on the laid-out sheet and the SVG. Its cache entry is what the
figure routes serve."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.config import ExploreConfig, TactileRules
from app.geometry.compose import ComposedSheet
from app.geometry.validate import Violation, check_svg_ids, validate_sheet
from app.meta.types import Understanding
from app.models.regions import RegionsFile
from app.render.pdf import render_pdf
from app.render.regions_json import FigureInfo, build_regions_file
from app.render.svg import render_key_svgs, render_sheet_svg

SVG_FILE = "tactile.svg"
PDF_FILE = "print.pdf"
REGIONS_FILE = "regions.json"
REPORT_FILE = "report.json"


class Rendered(BaseModel):
    model_config = ConfigDict(frozen=True)

    svg: str
    pdf: bytes
    regions: RegionsFile
    report: list[Violation]


def render(
    c: ComposedSheet, u: Understanding, figure_id: str, rules: TactileRules, explore: ExploreConfig
) -> Rendered:
    svg = render_sheet_svg(c.sheet, u.title, rules, explore)
    keys = render_key_svgs(c.sheet, c.braille, c.translations, rules)
    info = FigureInfo(
        figure_id=figure_id, title=u.title, figure_type=u.figure_type, summary=u.summary
    )
    regions = build_regions_file(c.sheet, c.braille, info, rules)
    report = validate_sheet(c.sheet, rules) + check_svg_ids(svg, regions)
    return Rendered(svg=svg, pdf=render_pdf([svg, *keys]), regions=regions, report=report)


def save(r: Rendered, out: Path) -> None:
    (out / SVG_FILE).write_text(r.svg, "utf-8")
    (out / PDF_FILE).write_bytes(r.pdf)
    (out / REGIONS_FILE).write_text(json.dumps(r.regions.to_json_obj(), indent=1) + "\n", "utf-8")
    report = [v.model_dump() for v in r.report]
    (out / REPORT_FILE).write_text(json.dumps(report, indent=1) + "\n", "utf-8")


def load(src: Path) -> Rendered:
    regions = json.loads((src / REGIONS_FILE).read_text("utf-8"))
    report = json.loads((src / REPORT_FILE).read_text("utf-8"))
    return Rendered(
        svg=(src / SVG_FILE).read_text("utf-8"),
        pdf=(src / PDF_FILE).read_bytes(),
        regions=RegionsFile.from_json_obj(regions),
        report=[Violation.model_validate(v) for v in report],
    )
