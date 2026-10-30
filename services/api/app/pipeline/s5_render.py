"""S5 render: tactile.svg, print.pdf (the sheet, then any key pages), regions.json and
report.json, the rules check on the laid-out sheet and the SVG, and warnings.json, the
overlap warnings for the teacher (app/geometry/overlap.py), never published. Its cache entry
is what the figure routes serve."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.config import ExploreConfig, TactileRules
from app.geometry.compose import ComposedSheet
from app.geometry.overlap import OverlapWarning
from app.geometry.reconcile import Reconciled
from app.geometry.scale import PageFit
from app.geometry.validate import Violation, check_svg_ids, validate_sheet
from app.geometry.vectorize import mask_to_polygons_mm
from app.meta.types import Understanding
from app.models.mask import Mask
from app.models.regions import Flag, RegionsFile, TeacherEntry, TeacherReason
from app.pipeline.edits import Annotations
from app.pipeline.s2_types import Grounded
from app.render.pdf import render_pdf
from app.render.regions_json import FigureInfo, Suggestion, TeacherInfo, build_regions_file
from app.render.svg import render_key_svgs, render_sheet_svg

SVG_FILE = "tactile.svg"
PDF_FILE = "print.pdf"
REGIONS_FILE = "regions.json"
REPORT_FILE = "report.json"
WARNINGS_FILE = "warnings.json"


class Rendered(BaseModel):
    model_config = ConfigDict(frozen=True)

    svg: str
    pdf: bytes
    regions: RegionsFile
    report: list[Violation]
    warnings: list[OverlapWarning] = []


THIN = "Spark marked it thin; how the sheet shows it is decided later"


def teacher_info(g: Grounded, rec: Reconciled, fit: PageFit, rules: TactileRules) -> TeacherInfo:
    """S2's flags on the touchable parts, its spill masks outlined as suggestions, and every
    listed part with no shape: S2's, and S3's dropped parts."""
    flags = {
        p.id: [Flag(reason="thin", detail=THIN)]
        for p in rec.parts
        if "thin" in g.flags.get(p.mask.label, [])
    }
    suggestions: list[Suggestion] = []
    needs: list[tuple[str, TeacherReason, str]] = []
    for t in g.teacher:
        polys = []
        if t.suggestion is not None:
            mask = Mask(data=t.suggestion, label=t.phrase, score=1.0, source="sam")
            polys = mask_to_polygons_mm(mask, fit, rules.vectorize)
        if polys:
            outlines = [[(x, y) for x, y in list(p.exterior.coords)[:-1]] for p in polys]
            suggestions.append(Suggestion(label=t.phrase, polygons_mm=outlines, detail=t.detail))
            continue
        reason: TeacherReason = "no_points" if t.reason == "no_points" else "no_mask"
        needs.append((t.phrase, reason, t.detail))
    needs += [(d.label, "dropped", d.reason) for d in rec.dropped]
    entries = [
        TeacherEntry(id=f"n{i}", label=label, reason=reason, detail=detail)
        for i, (label, reason, detail) in enumerate(needs, 1)
    ]
    return TeacherInfo(flags=flags, suggestions=suggestions, needs_teacher=entries)


def render(
    c: ComposedSheet,
    u: Understanding,
    figure_id: str,
    notes: Annotations,
    rules: TactileRules,
    explore: ExploreConfig,
    teacher: TeacherInfo | None = None,
) -> Rendered:
    svg = render_sheet_svg(c.sheet, u.title, rules, explore)
    keys = render_key_svgs(c.sheet, c.braille, c.translations, rules)
    info = FigureInfo(
        figure_id=figure_id, title=u.title, figure_type=u.figure_type, summary=u.summary
    )
    regions = build_regions_file(
        c.sheet, c.braille, info, rules, notes.descriptions, notes.verified, teacher
    )
    report = validate_sheet(c.sheet, rules) + check_svg_ids(svg, regions)
    return Rendered(svg=svg, pdf=render_pdf([svg, *keys]), regions=regions, report=report)


def save(r: Rendered, out: Path) -> None:
    (out / SVG_FILE).write_text(r.svg, "utf-8")
    (out / PDF_FILE).write_bytes(r.pdf)
    (out / REGIONS_FILE).write_text(json.dumps(r.regions.to_json_obj(), indent=1) + "\n", "utf-8")
    report = [v.model_dump() for v in r.report]
    (out / REPORT_FILE).write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    warnings = [{**w.model_dump(mode="json"), "text": w.text} for w in r.warnings]
    (out / WARNINGS_FILE).write_text(json.dumps(warnings, indent=1) + "\n", "utf-8")


def load(src: Path) -> Rendered:
    regions = json.loads((src / REGIONS_FILE).read_text("utf-8"))
    report = json.loads((src / REPORT_FILE).read_text("utf-8"))
    path = src / WARNINGS_FILE
    warned = json.loads(path.read_text("utf-8")) if path.exists() else []
    return Rendered(
        svg=(src / SVG_FILE).read_text("utf-8"),
        pdf=(src / PDF_FILE).read_bytes(),
        regions=RegionsFile.from_json_obj(regions),
        report=[Violation.model_validate(v) for v in report],
        warnings=[OverlapWarning.model_validate(w) for w in warned],
    )
