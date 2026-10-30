"""S4 in one call: reconciled parts in, a laid-out sheet with braille out. Pure apart from
the braille translator, which runs lou_translate."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from app.braille.louis import Translator
from app.braille.place import BrailleLayout, Translations, place_braille, translate_for_sheet
from app.config import Earcons, TactileRules
from app.geometry.layout import (
    drop_small_pieces,
    enforce_gaps,
    make_point_symbols,
    one_symbol_per_spot,
    regions_from_parts,
)
from app.geometry.plan import SheetPlan, contour, silhouette_polygon
from app.geometry.reconcile import ReconciledPart
from app.geometry.scale import PageFit
from app.geometry.sheet import Sheet
from app.geometry.textures import assign_textures, group_by_color
from app.models.regions import GradeBand


class ComposedSheet(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    sheet: Sheet  # with braille placed
    braille: BrailleLayout
    translations: Translations
    unresolved_gaps: list[tuple[str, str]]


def build_sheet(  # noqa: PLR0913  keyword-only inputs, each from S4
    *,
    parts: Sequence[ReconciledPart],
    image: NDArray[np.uint8],
    fit: PageFit,
    grade_band: GradeBand | None,
    color_carries_meaning: bool,
    rules: TactileRules,
    earcons: Earcons,
    translator: Translator,
    plan: SheetPlan | None = None,
) -> ComposedSheet:
    """plan: S1's lines and merge proposals, mapped to parts, and the subject's silhouette.
    The silhouette's contour is raised last, clear of every outline and braille block."""
    plan = plan or SheetPlan()
    regions = regions_from_parts(parts, fit, rules.vectorize)
    inset = rules.render.outline_width_mm / 2  # the raised outline takes this from the edge
    regions = drop_small_pieces(regions, rules.spacing, rules.layout, inset)
    regions = make_point_symbols(regions, rules.spacing, rules.layout, inset)
    regions = one_symbol_per_spot(regions, rules.spacing.min_gap_mm)
    regions, unresolved = enforce_gaps(
        regions, rules.spacing.min_gap_mm, rules.layout, rules.render.outline_width_mm
    )
    groups = (
        group_by_color(image, parts, rules.layout.color_group_max_delta)
        if color_carries_meaning
        else {}
    )
    limit = rules.textures.limit_for(grade_band)
    regions, textures = assign_textures(regions, groups, limit, rules.textures.order, earcons)
    sheet = Sheet(
        page=fit.page,
        grade_band=grade_band,
        regions=regions,
        textures=textures,
        lines=plan.lines,
        merges=plan.merges,
        subject=plan.subject,
        groups=plan.groups,
    )
    translations = translate_for_sheet(sheet, translator, rules.braille)
    braille = place_braille(sheet, translations, rules)
    outline = None if plan.silhouette is None else silhouette_polygon(plan.silhouette, fit, rules)
    raised = [] if outline is None else contour(outline, regions, braille.placements, rules)
    return ComposedSheet(
        sheet=sheet.model_copy(
            update={"braille": braille.placements, "silhouette": outline, "contour": raised}
        ),
        braille=braille,
        translations=translations,
        unresolved_gaps=unresolved,
    )
