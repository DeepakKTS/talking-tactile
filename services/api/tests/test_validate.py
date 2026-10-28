"""The tactile rules validator. It must find every problem planted in the synthetic figure
before the S4 fixes run, and nothing after them."""

import math

import pytest
from shapely.geometry import Polygon, box

from app.config import load_explore, load_tactile_rules
from app.geometry.layout import (
    LayoutRegion,
    enforce_gaps,
    make_point_symbols,
    point_symbol,
    regions_from_parts,
)
from app.geometry.reconcile import ReconciledPart, reconcile
from app.geometry.scale import fit_to_page
from app.geometry.sheet import Sheet
from app.geometry.textures import assign_textures, group_by_color
from app.geometry.validate import Violation, validate_sheet
from app.models.regions import Texture
from app.synthetic.load import SyntheticFigure, load_synthetic

RULES = load_tactile_rules()
LINE = RULES.render.outline_width_mm
EARCONS = load_explore().earcons
G = RULES.spacing.min_gap_mm
AX, AY, AW, AH = RULES.page.figure_area_mm("letter")


def region(rid: str, poly: Polygon, **kw: object) -> LayoutRegion:
    return LayoutRegion(id=rid, label=rid, polygon=poly, score=0.9, source="sam", **kw)  # type: ignore[arg-type]


def sheet(regions: list[LayoutRegion], textures: list[Texture] | None = None,
          grade: str | None = "9_12") -> Sheet:  # fmt: skip
    return Sheet(page="letter", grade_band=grade, regions=regions, textures=textures or [])  # type: ignore[arg-type]


def at(x: float, y: float, w: float, h: float) -> Polygon:
    return box(AX + x, AY + y, AX + x + w, AY + y + h)


def rules_of(violations: list[Violation]) -> list[tuple[str, tuple[str, ...]]]:
    return sorted((v.rule, tuple(v.regions)) for v in violations)


def test_a_clean_sheet_passes() -> None:
    assert validate_sheet(sheet([region("a", at(0, 0, 20, 20)), region("b", at(30, 0, 20, 20))]),
                          RULES) == []  # fmt: skip


def test_gap_violation_reports_both_regions_and_the_distance() -> None:
    v = validate_sheet(sheet([region("a", at(0, 0, 20, 20)), region("b", at(22, 0, 20, 20))]),
                       RULES)  # fmt: skip
    assert rules_of(v) == [("min_gap", ("a", "b"))]
    assert v[0].measured == pytest.approx(2.0)
    assert v[0].limit == G
    assert "a" in v[0].message and "mm" in v[0].message


def test_child_too_close_to_its_parent_outline() -> None:
    p = region("p", at(0, 0, 60, 60))
    c = region("c", at(1, 20, 20, 20), parent="p")
    v = validate_sheet(sheet([p, c]), RULES)
    assert rules_of(v) == [("min_gap", ("p", "c"))]
    assert v[0].measured == pytest.approx(1.0)
    assert v[0].limit == G + LINE  # the parent's outline is drawn inside its edge


def test_child_poking_out_of_its_parent() -> None:
    p = region("p", at(0, 0, 60, 60))
    c = region("c", at(50, 20, 20, 20), parent="p")
    assert rules_of(validate_sheet(sheet([p, c]), RULES)) == [("min_gap", ("p", "c"))]


def test_small_area_region_must_be_a_point_symbol() -> None:
    v = validate_sheet(sheet([region("s", at(0, 0, 4, 3))]), RULES)
    assert rules_of(v) == [("point_symbol", ("s",))]
    assert v[0].measured == pytest.approx(4.0)


def test_point_symbol_must_be_wide_enough() -> None:
    ok = point_symbol((AX + 10, AY + 10), RULES.spacing.point_symbol_min_mm, 32)
    small = point_symbol((AX + 40, AY + 10), 5.0, 32)
    v = validate_sheet(sheet([region("ok", ok, kind="point"), region("bad", small, kind="point")]),
                       RULES)  # fmt: skip
    assert rules_of(v) == [("point_symbol", ("bad",))]
    assert v[0].measured == pytest.approx(5.0, abs=0.01)


def test_texture_count_over_the_grade_limit() -> None:
    tex = [Texture(id=t, meaning=t, earcon_hz=EARCONS.texture_hz[t])
           for t in ("dots", "lines", "grid", "cross")]  # fmt: skip
    regions = [region(t.id, at(i * 30, 0, 20, 20), texture=t.id) for i, t in enumerate(tex)]
    assert validate_sheet(sheet(regions, tex, grade="9_12"), RULES) == []
    v = validate_sheet(sheet(regions, tex, grade="k5"), RULES)
    assert rules_of(v) == [("texture_count", ())]
    assert (v[0].measured, v[0].limit) == (4, 3)


def test_region_texture_must_be_in_the_texture_list() -> None:
    v = validate_sheet(sheet([region("a", at(0, 0, 20, 20), texture="dots")]), RULES)
    assert rules_of(v) == [("texture_unknown", ("a",))]


def test_point_symbol_with_an_area_texture() -> None:
    pt = point_symbol((AX + 10, AY + 10), RULES.spacing.point_symbol_min_mm, 32)
    tex = [Texture(id="dots", meaning="m", earcon_hz=1.0)]
    v = validate_sheet(sheet([region("p", pt, kind="point", texture="dots")], tex), RULES)
    assert rules_of(v) == [("texture_on_point", ("p",))]


def test_region_outside_the_figure_area() -> None:
    v = validate_sheet(sheet([region("a", at(-5, 10, 20, 20))]), RULES)
    assert rules_of(v) == [("inside_page", ("a",))]


def test_too_many_points() -> None:
    ring = [(AX + 50 + 30 * math.cos(i / 40), AY + 50 + 30 * math.sin(i / 40)) for i in range(252)]
    v = validate_sheet(sheet([region("a", Polygon(ring))]), RULES)
    assert rules_of(v) == [("polygon", ("a",))]


def test_duplicate_ids_and_missing_parent() -> None:
    v = validate_sheet(
        sheet([region("a", at(0, 0, 20, 20)), region("a", at(40, 0, 20, 20)),
               region("b", at(80, 0, 20, 20), parent="zz")]),
        RULES,
    )  # fmt: skip
    assert rules_of(v) == [("ids", ("a",)), ("ids", ("b",))]


# The synthetic figure, before and after the fixes.


@pytest.fixture(scope="module")
def fig() -> SyntheticFigure:
    return load_synthetic()


def naive_sheet(fig: SyntheticFigure, parts: list[ReconciledPart]) -> tuple[Sheet, dict[str, int]]:
    """Vectorized and scaled, one texture per color group, no fixes."""
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    regions = regions_from_parts(parts, fit, RULES.vectorize)
    groups = group_by_color(fig.image, parts, RULES.layout.color_group_max_delta)
    regions, textures = assign_textures(regions, groups, len(set(groups.values())),
                                        RULES.textures.order, EARCONS)  # fmt: skip
    return Sheet(page="letter", grade_band=fig.truth.grade_band, regions=regions,
                 textures=textures), groups  # fmt: skip


def fixed_sheet(fig: SyntheticFigure, naive: Sheet, groups: dict[str, int]) -> Sheet:
    pts = make_point_symbols(naive.regions, RULES.spacing, RULES.layout)
    spaced, _ = enforce_gaps(pts, G, RULES.layout, LINE)
    limit = RULES.textures.limit_for(fig.truth.grade_band)
    final, textures = assign_textures(spaced, groups, limit, RULES.textures.order, EARCONS)
    return naive.model_copy(update={"regions": final, "textures": textures})


def truth_parts(fig: SyntheticFigure) -> list[ReconciledPart]:
    return [
        ReconciledPart(id=p.id, mask=fig.truth_masks[p.id], parent=p.parent)
        for p in fig.truth.parts
    ]


def planted(fig: SyntheticFigure) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for p in fig.truth.planted:
        out.append((p.rule, () if p.rule == "texture_count" else tuple(p.parts)))
    return sorted(out)


def test_validator_finds_exactly_the_planted_problems_on_the_truth(fig: SyntheticFigure) -> None:
    naive, _ = naive_sheet(fig, truth_parts(fig))
    v = validate_sheet(naive, RULES)
    assert rules_of(v) == planted(fig)
    by_rule = {x.rule: x for x in v}
    assert by_rule["min_gap"].measured == pytest.approx(2.0, abs=0.15)
    assert by_rule["point_symbol"].measured == pytest.approx(4.0, abs=0.15)
    assert by_rule["texture_count"].measured > by_rule["texture_count"].limit


def test_validator_finds_the_planted_problems_after_reconcile(fig: SyntheticFigure) -> None:
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    parts = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(parts, text, fit.mm_per_px, RULES.reconcile)
    naive, _ = naive_sheet(fig, rec.parts)
    label = {r.id: r.label for r in naive.regions}
    truth_label = {p.id: p.label for p in fig.truth.parts}
    got = sorted((v.rule, tuple(label[r] for r in v.regions)) for v in validate_sheet(naive, RULES))
    want = sorted((r, tuple(truth_label[p] for p in parts)) for r, parts in planted(fig))
    assert got == want


@pytest.mark.parametrize("source", ["truth", "reconciled"])
def test_validator_finds_nothing_after_the_fixes(fig: SyntheticFigure, source: str) -> None:
    if source == "truth":
        parts = truth_parts(fig)
    else:
        fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
        raw = [m for m in fig.raw_masks.values() if m.label != "text label"]
        text = [m for m in fig.raw_masks.values() if m.label == "text label"]
        parts = reconcile(raw, text, fit.mm_per_px, RULES.reconcile).parts
    naive, groups = naive_sheet(fig, parts)
    assert validate_sheet(fixed_sheet(fig, naive, groups), RULES) == []
