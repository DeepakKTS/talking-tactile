"""Braille translation through lou_translate, cell geometry and abbreviations."""

import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.braille.abbrev import abbreviations
from app.braille.cells import block_size, cell_dots, dot_centers
from app.braille.louis import BrailleError, BrailleUnavailableError, Translator
from app.config import load_tactile_rules

BRAILLE = load_tactile_rules().braille


@pytest.fixture(scope="module")
def tr() -> Translator:
    return Translator(BRAILLE)


def test_ueb_grade_2_translations(tr: Translator) -> None:
    got = tr.translate(["left ventricle", "Aorta", "3 valves", "inner core", "b", ""])
    assert got == [
        "⠇⠑⠋⠞⠀⠧⠢⠞⠗⠊⠉⠇⠑",  # "en" contracted
        "⠠⠁⠕⠗⠞⠁",  # capital sign
        "⠼⠉⠀⠧⠁⠇⠧⠑⠎",  # number sign
        "⠔⠝⠻⠀⠉⠕⠗⠑",  # "in" and "er" contracted
        "⠰⠃",  # a letter alone needs the grade 1 indicator
        "",
    ]


def test_one_process_for_many_labels(tr: Translator) -> None:
    labels = [f"part {i}" for i in range(60)]
    start = time.perf_counter()
    out = tr.translate(labels)
    elapsed = time.perf_counter() - start
    assert len(out) == 60 and all(out)
    assert elapsed < 1.0


def test_no_labels_needs_no_process(tr: Translator) -> None:
    assert tr.translate([]) == []


@pytest.mark.parametrize("bad", ["two\nlines", "tab\there", "carriage\rreturn"])
def test_control_characters_are_refused(tr: Translator, bad: str) -> None:
    with pytest.raises(BrailleError, match="control"):
        tr.translate([bad])


def test_missing_binary_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(BrailleUnavailableError, match="brew install liblouis"):
        Translator(BRAILLE, binary=str(tmp_path / "lou_translate"))


def test_cell_dots() -> None:
    assert cell_dots("⠇") == frozenset({1, 2, 3})
    assert cell_dots("⠿") == frozenset({1, 2, 3, 4, 5, 6})
    assert cell_dots("⠀") == frozenset()
    with pytest.raises(BrailleError):
        cell_dots("a")
    with pytest.raises(BrailleError, match="8-dot"):
        cell_dots("⡀")


def test_block_size_uses_the_low_end_of_each_range() -> None:
    dot, pitch, cell = (BRAILLE.dot_base_diameter_mm[0], BRAILLE.dot_to_dot_mm[0],
                        BRAILLE.cell_to_cell_mm[0])  # fmt: skip
    assert block_size(1, BRAILLE) == pytest.approx((pitch + dot, 2 * pitch + dot))
    assert block_size(5, BRAILLE) == pytest.approx((4 * cell + pitch + dot, 2 * pitch + dot))


def test_dot_centers_for_a_word() -> None:
    dots = dot_centers("⠁⠃", 10.0, 20.0, BRAILLE)  # a = dot 1, b = dots 1 and 2
    r = BRAILLE.dot_base_diameter_mm[0] / 2
    pitch, cell = BRAILLE.dot_to_dot_mm[0], BRAILLE.cell_to_cell_mm[0]
    assert dots == pytest.approx(
        [(10 + r, 20 + r), (10 + r + cell, 20 + r), (10 + r + cell, 20 + r + pitch)]
    )


def test_abbreviations_are_short_unique_and_stable() -> None:
    got = abbreviations(["left lobe", "right lobe", "left ventricle", "aorta", "Pore"], 2)
    assert got == {"left lobe": "ll", "right lobe": "rl", "left ventricle": "lv",
                   "aorta": "ao", "Pore": "po"}  # fmt: skip


def test_colliding_abbreviations_grow_until_unique() -> None:
    got = abbreviations(["left lobe", "left lung", "liver lobe"], 2)
    assert len(set(got.values())) == 3
    assert all(v.isalpha() and v.islower() for v in got.values())
    assert got["left lobe"].startswith("l")


def test_abbreviations_ignore_digits_and_punctuation() -> None:
    got = abbreviations(["T-cell (type 2)", "3rd ventricle"], 2)
    assert all(v.isalpha() for v in got.values())
    assert len(set(got.values())) == 2


def test_same_label_twice_shares_one_abbreviation() -> None:
    assert abbreviations(["stem", "stem"], 2) == {"stem": "st"}


def test_labels_with_the_same_letters_still_get_different_abbreviations() -> None:
    got = abbreviations(["T-cell", "t cell", "T cell!"], 2)
    assert len(set(got.values())) == 3
    many = abbreviations([f"cell {'-' * i}" for i in range(60)], 2)
    assert len(set(many.values())) == 60
    assert all(v.isalpha() for v in got.values())


@settings(max_examples=200, deadline=None)
@given(st.lists(st.text(alphabet="abcdefghijkl -(2)", min_size=0, max_size=14), max_size=25))
def test_abbreviations_are_always_unique_letters(labels: list[str]) -> None:
    got = abbreviations(labels, BRAILLE.abbrev_letters)
    assert set(got) == set(labels)
    assert len(set(got.values())) == len(got)
    assert all(v.isalpha() and v.islower() for v in got.values())
