"""Braille placement: label inside, abbreviation inside, abbreviation beside, key only."""

import itertools

from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from app.braille.abbrev import abbreviations
from app.braille.louis import Translator
from app.braille.models import BrailleLine, Placement
from app.braille.place import place_braille, translate_for_sheet
from app.config import load_explore, load_tactile_rules
from app.geometry.layout import (
    LayoutRegion,
    enforce_gaps,
    make_point_symbols,
    point_symbol,
    regions_from_parts,
)
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.geometry.sheet import Sheet
from app.geometry.textures import assign_textures, group_by_color
from app.geometry.validate import validate_sheet
from app.synthetic.load import load_synthetic

RULES = load_tactile_rules()
LINE = RULES.render.outline_width_mm
B = RULES.braille
C = B.clearance_to_line_mm + RULES.render.outline_width_mm  # outlines are drawn inside edges
G = RULES.spacing.min_gap_mm
AX, AY, AW, AH = RULES.page.figure_area_mm("letter")
TR = Translator(B)
EARCONS = load_explore().earcons


def at(x: float, y: float, w: float, h: float) -> Polygon:
    return box(AX + x, AY + y, AX + x + w, AY + y + h)


def region(rid: str, label: str, poly: Polygon, **kw: object) -> LayoutRegion:
    return LayoutRegion(id=rid, label=label, polygon=poly, score=0.9, source="sam", **kw)  # type: ignore[arg-type]


def sheet(regions: list[LayoutRegion]) -> Sheet:
    return Sheet(page="letter", grade_band="9_12", regions=regions, textures=[])


def place(regions: list[LayoutRegion]):
    s = sheet(regions)
    return s, place_braille(s, translate_for_sheet(s, TR, B), RULES)


def lines_of(s: Sheet):
    return unary_union([r.polygon.exterior for r in s.regions])


def test_a_label_that_fits_goes_inside_with_clearance() -> None:
    s, out = place([region("a", "left lobe", at(0, 0, 80, 40))])
    [p] = out.placements
    assert (p.region_id, p.kind, p.inside) == ("a", "label", True)
    assert p.line.braille == TR.translate(["left lobe"])[0]
    assert p.line.rect.within(s.regions[0].polygon)
    assert p.line.rect.distance(lines_of(s)) >= C - 1e-9
    assert out.key == []


def test_a_narrow_part_gets_its_abbreviation_inside_and_a_key_entry() -> None:
    _, out = place([region("a", "right chamber", at(0, 0, 40, 60))])
    [p] = out.placements
    assert (p.kind, p.inside) == ("abbrev", True)
    assert p.line.text == "rc"
    assert [(k.abbrev, k.label) for k in out.key] == [("rc", "right chamber")]
    assert out.key[0].label_braille == TR.translate(["right chamber"])[0]


def test_a_point_symbol_gets_its_abbreviation_beside_it() -> None:
    pt = point_symbol((AX + 50, AY + 50), RULES.spacing.point_symbol_min_mm, 32)
    _, out = place([region("p", "pore", pt, kind="point")])
    [p] = out.placements
    assert (p.kind, p.inside) == ("abbrev", False)
    assert not p.line.rect.intersects(pt)
    assert p.line.rect.distance(pt) >= C - 1e-9
    assert p.line.rect.distance(pt) <= B.max_outside_offset_mm


def test_no_room_anywhere_means_key_only() -> None:
    # A small cell in the corner with a point symbol in it, and a wall around it at exactly
    # the minimum gap: no room inside the cell, and the corridor is too narrow for braille.
    cell = at(0, 0, 20, 20)
    dot = point_symbol(cell.centroid.coords[0], RULES.spacing.point_symbol_min_mm, 32)
    wall = at(0, 0, AW, AH).difference(cell.buffer(G, join_style="mitre"))
    _, out = place([
        region("w", "wall", wall),
        region("c", "cell", cell),
        region("p", "pore", dot, kind="point", parent="c"),
    ])  # fmt: skip
    assert [p.region_id for p in out.placements] == ["w"]
    assert out.key_only == ["c", "p"]
    assert out.key == []


def test_a_parent_label_keeps_clear_of_its_child() -> None:
    parent = region("p", "outer", at(0, 0, 120, 60))
    child = region("c", "core", at(40, 15, 40, 30), parent="p")
    _, out = place([parent, child])
    by = {p.region_id: p for p in out.placements}
    assert not by["p"].line.rect.intersects(child.polygon)
    assert by["p"].line.rect.distance(child.polygon.exterior) >= C - 1e-9
    assert by["c"].line.rect.within(child.polygon)


def test_labels_keep_the_minimum_gap_from_each_other() -> None:
    parent = region("p", "p", at(0, 0, 60, 60))
    pts = [region(f"q{i}", f"dot {i}", point_symbol((AX + 70, AY + 10 + 12 * i), 6.4, 32),
                  kind="point") for i in range(4)]  # fmt: skip
    _, out = place([parent, *pts])
    for a, b in itertools.combinations(out.placements, 2):
        assert a.line.rect.distance(b.line.rect) >= G - 1e-9


def test_abbreviations_are_set_once_per_label() -> None:
    _, out = place([region("a", "stem", at(0, 0, 10, 30)), region("b", "stem", at(60, 0, 10, 30))])
    assert [k.abbrev for k in out.key] == ["st"]


@st.composite
def scattered(draw: st.DrawFn) -> list[LayoutRegion]:
    words = st.sampled_from(["left", "right", "upper", "lower", "lobe", "vessel", "valve", "x"])
    regions: list[LayoutRegion] = []
    for i in range(draw(st.integers(1, 6))):
        x, y = draw(st.floats(0, AW - 50)), draw(st.floats(0, AH - 50))
        poly = at(x, y, draw(st.floats(8, 50)), draw(st.floats(8, 50)))
        label = " ".join(draw(st.lists(words, min_size=1, max_size=3)))
        if all(poly.distance(r.polygon) >= G for r in regions):
            regions.append(region(f"r{i}", label, poly))
    return regions


@settings(max_examples=40, deadline=None)
@given(scattered())
def test_placed_braille_always_passes_the_validator(regions: list[LayoutRegion]) -> None:
    s, out = place(regions)
    checked = s.model_copy(update={"braille": out.placements})
    assert [v for v in validate_sheet(checked, RULES) if v.rule.startswith("braille")] == []
    keyed = {k.label for k in out.key}
    for p in out.placements:
        if p.kind == "abbrev":
            assert next(r.label for r in regions if r.id == p.region_id) in keyed


def test_validator_catches_braille_too_close_to_a_line() -> None:
    a = region("a", "a", at(0, 0, 80, 40))
    w, h = 20.0, 6.1
    near = BrailleLine(text="x", braille="⠭", x_mm=AX + 1, y_mm=AY + 10, width_mm=w, height_mm=h)
    other = BrailleLine(text="y", braille="⠽", x_mm=AX + 22, y_mm=AY + 10, width_mm=w, height_mm=h)
    s = sheet([a]).model_copy(update={"braille": [
        Placement(region_id="a", kind="label", inside=True, line=near),
        Placement(region_id="a", kind="label", inside=True, line=other),
    ]})  # fmt: skip
    rules = sorted(v.rule for v in validate_sheet(s, RULES))
    assert rules == ["braille_clearance", "braille_gap"]


def test_synthetic_sheet_gets_braille_and_a_key_and_passes() -> None:
    fig = load_synthetic()
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, "letter", RULES.page)
    raw = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(raw, text, fit.mm_per_px, RULES.reconcile)
    regions = make_point_symbols(regions_from_parts(rec.parts, fit, RULES.vectorize),
                                 RULES.spacing, RULES.layout)  # fmt: skip
    regions, _ = enforce_gaps(regions, G, RULES.layout, LINE)
    groups = group_by_color(fig.image, rec.parts, RULES.layout.color_group_max_delta)
    regions, textures = assign_textures(regions, groups, 3, RULES.textures.order, EARCONS)
    s = Sheet(page="letter", grade_band="k5", regions=regions, textures=textures)
    out = place_braille(s, translate_for_sheet(s, TR, B), RULES)
    final = s.model_copy(update={"braille": out.placements})
    assert validate_sheet(final, RULES) == []
    label = {r.id: r.label for r in regions}
    placed = {label[p.region_id]: (p.kind, p.inside) for p in out.placements}
    # The 15 mm bar is too thin for braille once the 1 mm outline and 3.7 mm clearance
    # are taken on both sides (6.1 + 2 x 4.7 = 15.5 mm).
    assert placed["cross vessel"] == ("abbrev", False)
    assert placed["left lobe"] == ("label", True)
    assert placed["pore"] == ("abbrev", False)
    assert placed["stem"] == ("abbrev", False)
    assert placed["outer chamber"][0] == "abbrev"
    assert set(placed) == set(label.values())


def test_translations_cover_labels_and_abbreviations() -> None:
    s = sheet([region("a", "inner core", at(0, 0, 25, 25))])
    t = translate_for_sheet(s, TR, B)
    assert t.abbrevs == abbreviations(["inner core"], B.abbrev_letters)
    assert set(t.braille) == {"inner core", "ic", "key"}
