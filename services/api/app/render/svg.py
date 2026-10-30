"""S5 drawing: tactile.svg (one page, in layers) and the key pages, in page millimeters.

Layers, bottom to top:
  guides    print only: corner registration marks, the 100 mm calibration bar, title and
            printing note. Not traced.
  textures  area textures, kept min_gap_mm inside each outline, min_gap_mm off children,
            and clearance_to_line_mm off braille.
  outlines  each part's raised outline, drawn outline_width_mm wide inside its edge, so the
            gap between two parts is the gap between their polygons. Point symbols filled.
  silhouette  the subject's outer contour, untextured, outline_width_mm wide on the edge,
            only where it keeps min_gap_mm from every outline (app/geometry/plan.py).
  braille   the dots.
Every outline carries data-region with the region id, which the validator matches against
regions.json. Output is deterministic: same sheet, same bytes.
"""

import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.braille.cells import block_size, dot_centers
from app.braille.models import KeyEntry
from app.braille.place import KEY_TITLE, BrailleLayout, Translations, line_entries
from app.config import ExploreConfig, TactileRules
from app.geometry.layout import LayoutRegion
from app.geometry.plan import band as contour_band
from app.geometry.sheet import Sheet
from app.models.regions import Texture, TextureId

SVG_NS = "http://www.w3.org/2000/svg"
NS = {"svg": SVG_NS}
ET.register_namespace("", SVG_NS)

_INK = "#000"
_GUIDE_TEXT = "#555"
_FONT = "Helvetica, Arial, sans-serif"
_BLANK_CELL = "⠀"
_PRINT_NOTE = "Print at actual size. The bar at the bottom must measure 100 mm."
_LINE_HEIGHT = 1.5  # print text line spacing, in text heights


def _q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


class _Fmt:
    def __init__(self, decimals: int) -> None:
        self.d = decimals

    def n(self, x: float) -> str:
        out = f"{round(x, self.d):.{self.d}f}".rstrip("0").rstrip(".")
        return "0" if out in {"-0", ""} else out

    def ring(self, coords: Iterable[tuple[float, ...]]) -> str:
        pts = list(coords)[:-1]
        return "M" + " L".join(f"{self.n(x)},{self.n(y)}" for x, y, *_ in pts) + " Z"

    def poly(self, geom: BaseGeometry) -> str:
        parts: list[str] = []
        for p in getattr(geom, "geoms", [geom]):
            if isinstance(p, Polygon) and not p.is_empty:
                parts.append(self.ring(p.exterior.coords))
                parts.extend(self.ring(i.coords) for i in p.interiors)
        return " ".join(parts)


def _root(rules: TactileRules, page: str) -> tuple[ET.Element, float, float]:
    width, height = rules.page.dimensions_mm[page]  # type: ignore[index]
    root = ET.Element(
        _q("svg"),
        {
            "width": f"{width:g}mm",
            "height": f"{height:g}mm",
            "viewBox": f"0 0 {width:g} {height:g}",
        },
    )
    return root, width, height


def _layer(root: ET.Element, name: str) -> ET.Element:
    return ET.SubElement(root, _q("g"), {"id": name})


def _text(
    parent: ET.Element, f: _Fmt, x: float, y: float, text: str, *, size: float, anchor: str
) -> None:
    el = ET.SubElement(parent, _q("text"), {
        "x": f.n(x), "y": f.n(y), "font-size": f.n(size), "font-family": _FONT,
        "fill": _GUIDE_TEXT, "text-anchor": anchor,
    })  # fmt: skip
    el.text = text


# Textures


def _clip(region: LayoutRegion, sheet: Sheet, rules: TactileRules) -> BaseGeometry:
    gap = rules.spacing.min_gap_mm
    line = rules.render.outline_width_mm
    clearance = rules.braille.clearance_to_line_mm
    clip = region.polygon.buffer(-(gap + line))
    children = [c.polygon.buffer(gap) for c in sheet.regions if c.parent == region.id]
    braille = [p.line.rect.buffer(clearance) for p in sheet.braille]
    keep_out = unary_union([*children, *braille])
    return clip.difference(keep_out) if not keep_out.is_empty else clip


def _families(texture: TextureId) -> list[tuple[float, float]]:
    """Unit directions of the line families for a line texture."""
    diag = 1 / math.sqrt(2)
    return {
        "lines": [(diag, -diag)],
        "grid": [(1.0, 0.0), (0.0, 1.0)],
        "cross": [(diag, -diag), (diag, diag)],
    }.get(texture, [])


def _pattern_lines(
    clip: BaseGeometry, texture: TextureId, spacing: float, min_piece: float
) -> list[LineString]:
    minx, miny, maxx, maxy = clip.bounds
    reach = math.hypot(maxx - minx, maxy - miny) + spacing
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    out: list[LineString] = []
    for dx, dy in _families(texture):
        nx, ny = -dy, dx  # normal; lines sit at page-anchored multiples of the spacing
        center = cx * nx + cy * ny
        first = math.floor((center - reach) / spacing)
        for k in range(first, first + int(2 * reach / spacing) + 2):
            ox, oy = k * spacing * nx, k * spacing * ny
            base = (ox + (cx - ox) * dx * dx + (cy - oy) * dx * dy,
                    oy + (cx - ox) * dx * dy + (cy - oy) * dy * dy)  # fmt: skip
            a = (base[0] - reach * dx, base[1] - reach * dy)
            b = (base[0] + reach * dx, base[1] + reach * dy)
            piece = LineString([a, b]).intersection(clip)
            for g in getattr(piece, "geoms", [piece]):
                if isinstance(g, LineString) and g.length >= min_piece:
                    out.append(g)
    return out


def _pattern_dots(clip: BaseGeometry, spacing: float, radius: float) -> list[Point]:
    inner = clip.buffer(-radius)
    if inner.is_empty:
        return []
    minx, miny, maxx, maxy = inner.bounds
    xs = np.arange(math.floor(minx / spacing) * spacing + spacing / 2, maxx + spacing, spacing)
    ys = np.arange(math.floor(miny / spacing) * spacing + spacing / 2, maxy + spacing, spacing)
    gx, gy = (a.ravel() for a in np.meshgrid(xs, ys))
    pts = np.asarray(shapely.points(gx, gy))
    shapely.prepare(inner)
    keep: list[Point] = list(pts[shapely.contains(inner, pts)])
    return keep


def _texture_parts(
    clip: BaseGeometry, texture: TextureId, rules: TactileRules
) -> tuple[list[LineString], list[Point], BaseGeometry | None]:
    r = rules.render
    if clip.is_empty:
        return [], [], None
    if texture == "solid":
        return [], [], clip
    if texture == "dots":
        return [], _pattern_dots(clip, r.texture_spacing_mm, r.texture_dot_mm / 2), None
    inner = clip.buffer(-r.texture_line_mm / 2)
    if inner.is_empty:  # thinner than one texture line: no line fits, as with dots
        return [], [], None
    lines = _pattern_lines(inner, texture, r.texture_spacing_mm, r.texture_min_piece_mm)
    return lines, [], None


def texture_geometry(region: LayoutRegion, sheet: Sheet, rules: TactileRules) -> BaseGeometry:
    """The inked area of a region's texture, for checks."""
    if region.texture is None:
        return Polygon()
    lines, dots, solid = _texture_parts(_clip(region, sheet, rules), region.texture, rules)
    r = rules.render
    shapes: list[BaseGeometry] = [
        line.buffer(r.texture_line_mm / 2, cap_style="flat") for line in lines
    ]
    shapes += [d.buffer(r.texture_dot_mm / 2) for d in dots]
    if solid is not None:
        shapes.append(solid)
    return unary_union(shapes)


def _draw_texture(parent: ET.Element, f: _Fmt, clip: BaseGeometry, texture: TextureId,
                  rules: TactileRules) -> None:  # fmt: skip
    lines, dots, solid = _texture_parts(clip, texture, rules)
    r = rules.render
    if lines:
        d = " ".join(
            "M" + " L".join(f"{f.n(x)},{f.n(y)}" for x, y in line.coords) for line in lines
        )
        ET.SubElement(parent, _q("path"), {"d": d, "fill": "none", "stroke": _INK,
                                          "stroke-width": f.n(r.texture_line_mm)})  # fmt: skip
    for dot in dots:
        attrs = {"cx": f.n(dot.x), "cy": f.n(dot.y), "r": f.n(r.texture_dot_mm / 2), "fill": _INK}
        ET.SubElement(parent, _q("circle"), attrs)
    if solid is not None:
        ET.SubElement(parent, _q("path"), {"d": f.poly(solid), "fill": _INK,
                                          "fill-rule": "evenodd"})  # fmt: skip


# The sheet


def _guides(
    root: ET.Element,
    f: _Fmt,
    size: tuple[float, float],
    title: str,
    rules: TactileRules,
    explore: ExploreConfig,
) -> None:
    width, height = size
    g = _layer(root, "guides")
    r = rules.render
    inset = explore.registration.mark_inset_mm
    arm = r.mark_arm_mm
    corners = [(inset, inset, 1, 1), (width - inset, inset, -1, 1),
               (width - inset, height - inset, -1, -1), (inset, height - inset, 1, -1)]  # fmt: skip
    for i, (x, y, sx, sy) in enumerate(corners):
        d = f"M{f.n(x + sx * arm)},{f.n(y)} L{f.n(x)},{f.n(y)} L{f.n(x)},{f.n(y + sy * arm)}"
        ET.SubElement(g, _q("path"), {"d": d, "fill": "none", "stroke": _INK,
                                     "stroke-width": f.n(r.guide_line_mm),
                                     "stroke-linecap": "square",
                                     "data-mark": "ABCD"[i]})  # fmt: skip
    bar = rules.page.calibration_bar_mm
    margin = rules.page.margin_mm
    bar_y = height - margin / 2
    bx = (width - bar) / 2
    ET.SubElement(g, _q("rect"), {"x": f.n(bx), "y": f.n(bar_y - r.bar_height_mm / 2),
                                 "width": f.n(bar), "height": f.n(r.bar_height_mm),
                                 "fill": _INK, "data-calibration": f.n(bar)})  # fmt: skip
    label_y = bar_y - r.bar_height_mm - r.print_text_mm / 2
    _text(g, f, width / 2, label_y, f"{bar:g} mm", size=r.print_text_mm, anchor="middle")
    _text(g, f, width / 2, margin / 2, title, size=r.print_text_mm, anchor="middle")
    note_y = margin / 2 + _LINE_HEIGHT * r.print_text_mm
    _text(g, f, width / 2, note_y, _PRINT_NOTE, size=r.print_text_mm, anchor="middle")


def _braille(
    parent: ET.Element, f: _Fmt, braille: str, at: tuple[float, float], rules: TactileRules
) -> None:
    x, y = at
    r = rules.braille.dot_base_diameter_mm[0] / 2
    for cx, cy in dot_centers(braille, x, y, rules.braille):
        ET.SubElement(parent, _q("circle"), {"cx": f.n(cx), "cy": f.n(cy), "r": f.n(r),
                                            "fill": _INK})  # fmt: skip


def _to_text(root: ET.Element) -> str:
    ET.indent(root, space=" ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False) + "\n"


def render_sheet_svg(sheet: Sheet, title: str, rules: TactileRules,
                     explore: ExploreConfig) -> str:  # fmt: skip
    f = _Fmt(rules.render.coordinate_decimals)
    root, width, height = _root(rules, sheet.page)
    _guides(root, f, (width, height), title, rules, explore)

    textures = _layer(root, "textures")
    for region in sheet.regions:
        if region.texture is not None:
            g = ET.SubElement(textures, _q("g"), {"data-region": region.id,
                                                 "data-texture": region.texture})  # fmt: skip
            _draw_texture(g, f, _clip(region, sheet, rules), region.texture, rules)

    outlines = _layer(root, "outlines")
    line = rules.render.outline_width_mm
    for region in sheet.regions:
        if region.kind == "point":
            band: BaseGeometry = region.polygon
        else:
            band = region.polygon.difference(region.polygon.buffer(-line, join_style="mitre"))
        ET.SubElement(outlines, _q("path"), {"d": f.poly(band), "fill": _INK,
                                            "fill-rule": "evenodd", "data-region": region.id,
                                            "data-kind": region.kind,
                                            "data-label": region.label})  # fmt: skip

    if sheet.contour:
        silhouette = _layer(root, "silhouette")
        for piece in sheet.contour:
            d = f.poly(contour_band(piece, rules))
            ET.SubElement(silhouette, _q("path"), {"d": d, "fill": _INK, "data-kind": "silhouette",
                                                  "data-label": sheet.subject})  # fmt: skip

    braille = _layer(root, "braille")
    for p in sheet.braille:
        g = ET.SubElement(braille, _q("g"), {"data-region": p.region_id, "data-text": p.line.text})
        _braille(g, f, p.line.braille, (p.line.x_mm, p.line.y_mm), rules)
    return _to_text(root)


# The key


def _wrap(braille: str, max_cells: int) -> list[str]:
    """Splits a braille line at blank cells so no line is longer than max_cells."""
    words = braille.split(_BLANK_CELL)
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + _BLANK_CELL + word
        if len(candidate) <= max_cells or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class _KeyPages:
    """Writes key rows top to bottom, starting a new page when a row does not fit."""

    def __init__(self, page: str, t: Translations, rules: TactileRules) -> None:
        self.page, self.t, self.rules = page, t, rules
        self.f = _Fmt(rules.render.coordinate_decimals)
        self.margin = rules.page.margin_mm
        _, self.width, self.height = _root(rules, page)
        self.cell = rules.braille.cell_to_cell_mm[0]
        self.line_h = block_size(1, rules.braille)[1]
        self.spacing = rules.braille.line_spacing_mm
        self.note_h = _LINE_HEIGHT * rules.render.print_text_mm  # print note under each row
        self.max_cells = int((self.width - 2 * self.margin) // self.cell)
        self.pages: list[ET.Element] = []
        self.layer: ET.Element | None = None
        self.y = self.height

    def _new_page(self) -> ET.Element:
        root, _, _ = _root(self.rules, self.page)
        self.pages.append(root)
        g = _layer(root, "key")
        size = self.rules.render.print_text_mm
        _text(g, self.f, self.width / 2, self.margin / 2, "Key", size=size, anchor="middle")
        _braille(g, self.f, self.t.braille[KEY_TITLE], (self.margin, self.margin), self.rules)
        self.y = self.margin + self.spacing
        return g

    def row(self, height: float, attrs: dict[str, str]) -> ET.Element:
        if self.layer is None or self.y + height > self.height - self.margin:
            self.layer = self._new_page()
        return ET.SubElement(self.layer, _q("g"), attrs)

    def lines(self, g: ET.Element, lines: list[str], x: float) -> None:
        for i, text in enumerate(lines):
            _braille(g, self.f, text, (x, self.y + i * self.spacing), self.rules)

    def note(self, g: ET.Element, n_lines: int, x: float, text: str) -> None:
        size = self.rules.render.print_text_mm
        y = self.y + (n_lines - 1) * self.spacing + self.line_h + size
        _text(g, self.f, x, y, text, size=size, anchor="start")

    def entry(self, e: KeyEntry) -> None:
        lead = len(e.abbrev_braille) + 1
        lines = _wrap(e.label_braille, self.max_cells - lead)
        height = len(lines) * self.spacing + self.note_h
        g = self.row(height, {"data-key": e.abbrev})
        _braille(g, self.f, e.abbrev_braille, (self.margin, self.y), self.rules)
        self.lines(g, lines, self.margin + lead * self.cell)
        self.note(g, len(lines), self.margin, f"{e.abbrev}: {e.label}")
        self.y += height

    def line(self, line_id: str, text: str) -> None:
        lines = _wrap(self.t.braille[text], self.max_cells)
        height = len(lines) * self.spacing + self.note_h
        g = self.row(height, {"data-line": line_id})
        self.lines(g, lines, self.margin)
        self.note(g, len(lines), self.margin, f"Not raised: {text}")
        self.y += height

    def texture(self, tex: Texture) -> None:
        r, gap = self.rules.render, self.rules.spacing.min_gap_mm
        sw, sh = r.key_swatch_mm
        tx = self.margin + sw + gap
        lines = _wrap(
            self.t.braille[tex.meaning], int((self.width - self.margin - tx) // self.cell)
        )
        height = max(sh + gap, len(lines) * self.spacing + self.note_h)
        g = self.row(height, {"data-texture": tex.id})
        swatch = box(self.margin, self.y, self.margin + sw, self.y + sh)
        frame = swatch.difference(swatch.buffer(-r.outline_width_mm, join_style="mitre"))
        sample = ET.SubElement(g, _q("g"), {"data-swatch": tex.id})
        ET.SubElement(sample, _q("path"), {"d": self.f.poly(frame), "fill": _INK,
                                          "fill-rule": "evenodd"})  # fmt: skip
        inner = swatch.buffer(-(r.outline_width_mm + gap))
        _draw_texture(sample, self.f, inner, tex.id, self.rules)
        self.lines(g, lines, tx)
        self.note(g, len(lines), tx, f"{tex.id}: {tex.meaning}")
        self.y += height


def render_key_svgs(
    sheet: Sheet, layout: BrailleLayout, t: Translations, rules: TactileRules
) -> list[str]:
    """Key pages: the abbreviations used on the sheet, each texture with its meaning, then
    each line part, which the sheet does not raise. Empty when the sheet needs no key."""
    lines = line_entries(sheet)
    if not layout.key and not sheet.textures and not lines:
        return []
    pages = _KeyPages(sheet.page, t, rules)
    for e in layout.key:
        pages.entry(e)
    for tex in sheet.textures:
        pages.texture(tex)
    for line, text in zip(sheet.lines, lines, strict=True):
        pages.line(line.id, text)
    return [_to_text(p) for p in pages.pages]


def sheet_ids(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    outlines = root.find("svg:g[@id='outlines']", NS)
    return [] if outlines is None else [el.get("data-region", "") for el in outlines]
