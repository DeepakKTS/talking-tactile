"""Braille cell geometry. Sizes use the low end of each configured range: the most compact
size that is still within the standard."""

from app.braille.louis import BrailleError
from app.config import Braille

_BLANK = 0x2800
_SIX_DOT_END = 0x2840
_EIGHT_DOT_END = 0x2900
_DOTS_PER_COLUMN = 3
_SIX_DOTS = range(1, 7)


def cell_dots(ch: str) -> frozenset[int]:
    """Raised dots (1 to 6) of one Unicode braille cell."""
    code = ord(ch)
    if _SIX_DOT_END <= code < _EIGHT_DOT_END:
        raise BrailleError(f"{ch!r} is an 8-dot cell; only 6-dot braille is printed")
    if not _BLANK <= code < _SIX_DOT_END:
        raise BrailleError(f"{ch!r} is not a braille cell")
    bits = code - _BLANK
    return frozenset(d for d in _SIX_DOTS if bits & (1 << (d - 1)))


def block_size(cells: int, rules: Braille) -> tuple[float, float]:
    """Width and height in mm of the dots of one line of braille, edge to edge."""
    dot, pitch, cell = (
        rules.dot_base_diameter_mm[0],
        rules.dot_to_dot_mm[0],
        rules.cell_to_cell_mm[0],
    )
    return ((cells - 1) * cell + pitch + dot, (_DOTS_PER_COLUMN - 1) * pitch + dot)


def dot_centers(braille: str, x0: float, y0: float, rules: Braille) -> list[tuple[float, float]]:
    """Centers of the raised dots of one line whose dot block starts at (x0, y0)."""
    r = rules.dot_base_diameter_mm[0] / 2
    pitch, cell = rules.dot_to_dot_mm[0], rules.cell_to_cell_mm[0]
    out: list[tuple[float, float]] = []
    for i, ch in enumerate(braille):
        for d in sorted(cell_dots(ch)):
            col = 0 if d <= _DOTS_PER_COLUMN else 1
            row = (d - 1) % _DOTS_PER_COLUMN
            out.append((x0 + r + i * cell + col * pitch, y0 + r + row * pitch))
    return out
