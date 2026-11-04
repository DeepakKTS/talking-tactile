"""The logo is braille "tt" as the sheets print it: liblouis, with the configured table, gives
two cells of dots 2-3-4-5, and the SVG mark raises exactly those dots
(apps/web/scripts/brand_logo.py made it)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.braille.cells import cell_dots
from app.braille.louis import Translator
from app.config import load_tactile_rules

BRAND = Path(__file__).resolve().parents[3] / "apps" / "web" / "public" / "brand"
SVG = "{http://www.w3.org/2000/svg}"


def test_liblouis_gives_two_cells_of_dots_2345() -> None:
    (cells,) = Translator(load_tactile_rules().braille).translate(["tt"])
    assert cells == "⠞⠞"
    assert [cell_dots(c) for c in cells] == [frozenset({2, 3, 4, 5})] * 2


def raised(path: Path) -> list[frozenset[int]]:
    """The raised dots of each cell drawn in an SVG, numbered as braille numbers them: the
    columns and rows come from the circles' centers, left to right and top to bottom."""
    circles = list(ET.parse(path).iter(f"{SVG}circle"))
    xs = sorted({float(c.get("cx", "")) for c in circles})
    ys = sorted({float(c.get("cy", "")) for c in circles})
    assert len(xs) == 4 and len(ys) == 3 and len(circles) == 12, path.name
    cells: list[set[int]] = [set(), set()]
    for c in circles:
        col, row = xs.index(float(c.get("cx", ""))), ys.index(float(c.get("cy", "")))
        if c.get("class") == "tt-on":
            cells[col // 2].add((col % 2) * 3 + row + 1)
        else:
            assert c.get("class") == "tt-off", path.name
    return [frozenset(s) for s in cells]


@pytest.mark.parametrize("name", ["logo-mark.svg", "logo.svg", "favicon.svg"])
def test_the_mark_raises_what_liblouis_prints(name: str) -> None:
    (cells,) = Translator(load_tactile_rules().braille).translate(["tt"])
    assert raised(BRAND / name) == [cell_dots(c) for c in cells]


def test_the_wordmark_is_outlined() -> None:
    """The logo shows with no font installed: the wordmark is paths, not text."""
    root = ET.parse(BRAND / "logo.svg").getroot()
    assert root.find(f".//{SVG}text") is None
    assert root.find(f"{SVG}path") is not None
    assert root.findtext(f"{SVG}title") == "Talking Tactile"
