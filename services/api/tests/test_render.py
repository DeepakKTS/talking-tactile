"""S5 render: tactile.svg in layers, the key page, print.pdf at exact scale, regions.json."""

import io
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from PIL import Image
from pypdf import PdfReader
from shapely.geometry import Point, box
from shapely.ops import unary_union

from app.braille.cells import cell_dots
from app.config import load_explore, load_tactile_rules
from app.geometry.compose import ComposedSheet
from app.geometry.validate import check_svg_ids, validate_sheet
from app.models.regions import RegionsFile, check_references
from app.paths import REGIONS_SCHEMA
from app.render.pdf import render_pdf
from app.render.regions_json import FigureInfo, build_regions_file
from app.render.svg import (
    NS,
    _texture_parts,
    render_key_svgs,
    render_sheet_svg,
    texture_geometry,
)

RULES = load_tactile_rules()
EXPLORE = load_explore()
INFO = FigureInfo(figure_id="ab" * 32, title="Synthetic test figure", figure_type="labeled_diagram",
                  summary="A test figure with eight parts.")  # fmt: skip
MM_PER_INCH = 25.4
DPI = 300


@pytest.fixture(scope="module")
def svg(composed: ComposedSheet) -> str:
    return render_sheet_svg(composed.sheet, INFO.title, RULES, EXPLORE)


@pytest.fixture(scope="module")
def key_svg(composed: ComposedSheet) -> str:
    pages = render_key_svgs(composed.sheet, composed.braille, composed.translations, RULES)
    assert len(pages) == 1
    return pages[0]


@pytest.fixture(scope="module")
def regions(composed: ComposedSheet) -> RegionsFile:
    return build_regions_file(composed.sheet, composed.braille, INFO, RULES)


def layer(root: ET.Element, name: str) -> ET.Element:
    g = root.find(f"svg:g[@id='{name}']", NS)
    assert g is not None, name
    return g


def test_svg_is_one_page_at_exact_size(svg: str) -> None:
    root = ET.fromstring(svg)
    assert (root.get("width"), root.get("height")) == ("215.9mm", "279.4mm")
    assert root.get("viewBox") == "0 0 215.9 279.4"


def test_svg_has_the_layers_in_order(svg: str) -> None:
    root = ET.fromstring(svg)
    ids = [g.get("id") for g in root.findall("svg:g", NS)]
    assert ids == ["guides", "textures", "outlines", "braille"]


def test_every_region_is_drawn_once_with_its_id(svg: str, composed: ComposedSheet) -> None:
    outlines = layer(ET.fromstring(svg), "outlines")
    drawn = [el.get("data-region") for el in outlines]
    assert sorted(drawn) == sorted(r.id for r in composed.sheet.regions)


def test_svg_ids_check_finds_missing_and_extra(svg: str, regions: RegionsFile) -> None:
    assert check_svg_ids(svg, regions) == []
    fewer = regions.model_copy(update={"regions": regions.regions[1:]})
    [v] = check_svg_ids(svg, fewer)
    assert v.rule == "svg_ids" and v.regions == [regions.regions[0].id]


def test_braille_dots_match_the_placed_cells(svg: str, composed: ComposedSheet) -> None:
    dots = layer(ET.fromstring(svg), "braille").findall(".//svg:circle", NS)
    expected = sum(len(cell_dots(c)) for p in composed.sheet.braille for c in p.line.braille)
    assert len(dots) == expected
    r = RULES.braille.dot_base_diameter_mm[0] / 2
    assert {float(d.get("r", "0")) for d in dots} == {r}


def test_textures_stay_clear_of_outlines_children_and_braille(composed: ComposedSheet) -> None:
    sheet = composed.sheet
    gap, line = RULES.spacing.min_gap_mm, RULES.render.outline_width_mm
    clearance = RULES.braille.clearance_to_line_mm
    braille = unary_union([p.line.rect for p in sheet.braille])
    textured = [r for r in sheet.regions if r.texture is not None]
    assert textured
    for r in textured:
        geom = texture_geometry(r, sheet, RULES)
        assert not geom.is_empty, r.id
        assert geom.within(r.polygon.buffer(-(gap + line) + 1e-6)), r.id
        assert geom.distance(braille) >= clearance - 1e-6, r.id
        for child in (c for c in sheet.regions if c.parent == r.id):
            assert geom.distance(child.polygon) >= gap - 1e-6, (r.id, child.id)


def test_svg_is_deterministic(composed: ComposedSheet, svg: str) -> None:
    assert render_sheet_svg(composed.sheet, INFO.title, RULES, EXPLORE) == svg


def test_key_page_lists_abbreviations_and_textures(key_svg: str, composed: ComposedSheet) -> None:
    root = ET.fromstring(key_svg)
    entries = root.findall(".//svg:g[@data-key]", NS)
    assert [e.get("data-key") for e in entries] == [k.abbrev for k in composed.braille.key]
    swatches = root.findall(".//svg:g[@data-texture]", NS)
    assert [s.get("data-texture") for s in swatches] == [t.id for t in composed.sheet.textures]
    for swatch in swatches:
        sample = swatch.find("svg:g[@data-swatch]", NS)
        assert sample is not None
        assert len(sample) >= 2, f"{swatch.get('data-texture')}: a frame and some texture"


def test_regions_json_matches_the_schema_and_the_sheet(
    regions: RegionsFile, composed: ComposedSheet
) -> None:
    obj = regions.to_json_obj()
    schema = json.loads(REGIONS_SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(obj)) == []
    assert check_references(regions) == []
    assert [r.id for r in regions.regions] == [r.id for r in composed.sheet.regions]
    abbreviated = {p.region_id for p in composed.sheet.braille if p.kind == "abbrev"}
    for r in regions.regions:
        assert (r.abbrev is not None) == (r.id in abbreviated), r.id
        assert r.centroid_mm is not None
        poly = next(x.polygon for x in composed.sheet.regions if x.id == r.id)
        assert poly.contains(Point(r.centroid_mm))
        assert r.verified_by_teacher is False
    assert regions.page.width_mm == 215.9
    assert regions.textures == composed.sheet.textures


def test_print_pdf_has_the_sheet_and_the_key(svg: str, key_svg: str) -> None:
    pdf = render_pdf([svg, key_svg])
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 2
    for page in reader.pages:
        assert (float(page.mediabox.width), float(page.mediabox.height)) == pytest.approx(
            (612, 792), abs=0.01
        )


def test_the_whole_sheet_still_passes_the_rules(composed: ComposedSheet) -> None:
    assert validate_sheet(composed.sheet, RULES) == []


@pytest.mark.skipif(
    shutil.which("pdftoppm") is None, reason="needs pdftoppm (brew install poppler)"
)
def test_print_scale_measured_at_300_dpi(svg: str, composed: ComposedSheet, tmp_path: Path) -> None:
    """The same check as the touch test sheet: render at 300 dpi and measure in pixels."""
    pdf = tmp_path / "print.pdf"
    pdf.write_bytes(render_pdf([svg]))
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", "-singlefile", str(pdf),
                    str(tmp_path / "page")], check=True)  # fmt: skip
    img = np.asarray(Image.open(tmp_path / "page.png").convert("L"))
    px_per_mm = DPI / MM_PER_INCH
    assert img.shape == (3300, 2550)

    # The calibration bar: the longest dark horizontal run in the bottom margin.
    margin_rows = img[int((279.4 - RULES.page.margin_mm) * px_per_mm) :]
    dark = margin_rows < 128
    runs = [np.diff(np.flatnonzero(np.diff(np.r_[0, row, 0].astype(int)))) for row in dark]
    longest = max((r[::2].max() for r in runs if r.size), default=0)
    bar_mm = longest / px_per_mm
    assert bar_mm == pytest.approx(RULES.page.calibration_bar_mm, abs=0.2)

    # A raised outline lands where regions.json says it is.
    lobe = next(r for r in composed.sheet.regions if r.label == "left lobe")
    x0, y0, _, y1 = lobe.polygon.bounds
    cols = np.flatnonzero(img[int((y0 + y1) / 2 * px_per_mm)] < 128)
    left_edge = cols[cols > x0 * px_per_mm - 20][0] / px_per_mm
    assert left_edge == pytest.approx(x0, abs=0.2)

    # The top-left registration mark corner.
    inset = EXPLORE.registration.mark_inset_mm
    patch = img[: int((inset + 3) * px_per_mm), : int((inset + 3) * px_per_mm)] < 128
    ys, xs = np.nonzero(patch)
    assert xs.min() / px_per_mm == pytest.approx(inset - RULES.render.guide_line_mm / 2, abs=0.2)
    assert ys.min() / px_per_mm == pytest.approx(inset - RULES.render.guide_line_mm / 2, abs=0.2)


@pytest.mark.parametrize("texture", ["lines", "grid", "cross", "dots"])
def test_a_region_thinner_than_a_texture_line_gets_no_texture(texture: str) -> None:
    """Found live on the heart, Oct 30: a clipped region thinner than one texture line left
    an empty area whose centre was NaN, and S5 failed."""
    lines, dots, solid = _texture_parts(box(0, 0, 40, 0.3), texture, RULES)  # type: ignore[arg-type]
    assert (lines, dots, solid) == ([], [], None)


def test_regions_json_names_each_members_group(composed: ComposedSheet) -> None:
    first = composed.sheet.regions[0]
    sheet = composed.sheet.model_copy(update={"groups": {first.group_key: "stamen"}})
    out = build_regions_file(sheet, composed.braille, INFO, RULES)
    named = {r.id: r.group for r in out.regions}
    assert named[first.id] == "stamen"
    assert all(g is None for rid, g in named.items() if rid.partition("_")[0] != first.group_key)
    assert out.to_json_obj()["regions"][0]["group"] == "stamen"
