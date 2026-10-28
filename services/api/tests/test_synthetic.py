"""The synthetic figure: exact, deterministic, and planted with exactly the problems the
geometry stages must catch and fix. Every later geometry test relies on these facts."""

import itertools
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import load_tactile_rules
from app.models.mask import BoolImage
from app.paths import FIXTURES_DIR
from app.synthetic import sheet, spec
from app.synthetic.generate import generate
from app.synthetic.load import SyntheticFigure, load_synthetic

RULES = load_tactile_rules()
MIN_GAP = RULES.spacing.min_gap_mm
POINT_MIN = RULES.spacing.point_symbol_min_mm


@pytest.fixture(scope="module")
def fig() -> SyntheticFigure:
    return load_synthetic()


def gap_mm(a: BoolImage, b: BoolImage, px_per_mm: float) -> float:
    """Smallest center-to-center distance from a pixel of a to a pixel of b, in mm."""
    dist = cv2.distanceTransform((~a).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return float(dist[b].min()) / px_per_mm


def clearance_mm(inner: BoolImage, outer: BoolImage, px_per_mm: float) -> float:
    """Distance from the inner part to the outside of the outer part, in mm."""
    dist = cv2.distanceTransform(outer.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return float(dist[inner].min()) / px_per_mm


def test_committed_fixture_matches_the_generator(fig: SyntheticFigure) -> None:
    fresh = generate()
    assert fresh.truth == fig.truth
    assert np.array_equal(fresh.image, fig.image)
    by_file = {p.mask: m for p, m in zip(fig.truth.parts, fig.truth_masks.values(), strict=True)}
    by_file |= {r.mask: m for r, m in zip(fig.truth.raw_masks, fig.raw_masks.values(), strict=True)}
    assert set(by_file) == set(fresh.masks)
    for name, mask in by_file.items():
        assert np.array_equal(mask.data, fresh.masks[name]), name


def test_image_is_normalized_and_fills_the_letter_figure_area(fig: SyntheticFigure) -> None:
    h, w, channels = fig.image.shape
    assert channels == 3
    assert max(h, w) == RULES.pipeline.normalize_max_side_px
    _, _, area_w, area_h = RULES.page.figure_area_mm("letter")
    assert abs(w - area_w * fig.truth.px_per_mm) <= 0.5
    assert abs(h - area_h * fig.truth.px_per_mm) <= 0.5
    for mask in [*fig.truth_masks.values(), *fig.raw_masks.values()]:
        assert mask.shape == (h, w)
        assert mask.source == "synthetic"


def test_about_eight_labeled_parts(fig: SyntheticFigure) -> None:
    assert len(fig.truth.parts) == 8
    assert len({p.label for p in fig.truth.parts}) == 8


def test_mask_areas_match_the_exact_shapes(fig: SyntheticFigure) -> None:
    s2 = fig.truth.px_per_mm**2
    for part in fig.truth.parts:
        measured = fig.truth_masks[part.id].area_px / s2
        assert measured == pytest.approx(part.area_mm2, rel=0.03), part.id


def test_only_the_nested_pair_overlaps(fig: SyntheticFigure) -> None:
    for a, b in itertools.combinations(fig.truth.parts, 2):
        both = fig.truth_masks[a.id].data & fig.truth_masks[b.id].data
        nested = {a.parent, b.parent} & {a.id, b.id}
        if nested:
            child = a if a.parent == b.id else b
            assert np.array_equal(both, fig.truth_masks[child.id].data)
        else:
            assert not both.any(), (a.id, b.id)


def test_nested_part_has_wide_clearance(fig: SyntheticFigure) -> None:
    s = fig.truth.px_per_mm
    core, outer = fig.truth_masks["core"].data, fig.truth_masks["outer"].data
    assert clearance_mm(core, outer, s) > 2 * MIN_GAP


def test_exactly_one_pair_is_closer_than_the_minimum_gap(fig: SyntheticFigure) -> None:
    s = fig.truth.px_per_mm
    close = []
    for a, b in itertools.combinations(fig.truth.parts, 2):
        if a.parent == b.id or b.parent == a.id:
            continue
        g = gap_mm(fig.truth_masks[a.id].data, fig.truth_masks[b.id].data, s)
        if g < MIN_GAP:
            close.append((a.id, b.id, g))
    assert [(a, b) for a, b, _ in close] == [("left_lobe", "right_lobe")]
    assert close[0][2] == pytest.approx(spec.PLANTED_GAP_MM, abs=1.5 / s)


def test_exactly_one_part_is_below_the_point_symbol_size(fig: SyntheticFigure) -> None:
    small = []
    for part in fig.truth.parts:
        ys, xs = np.nonzero(fig.truth_masks[part.id].data)
        size_mm = max(np.ptp(xs), np.ptp(ys)) / fig.truth.px_per_mm
        if size_mm < POINT_MIN:
            small.append(part.id)
    assert small == ["pore"]


def test_color_categories_exceed_the_lower_grade_texture_limit(fig: SyntheticFigure) -> None:
    assert fig.truth.grade_band in RULES.textures.lower_grade_bands
    planted = next(p for p in fig.truth.planted if p.rule == "texture_count")
    limit = RULES.textures.limit_for(fig.truth.grade_band)
    assert limit < planted.value <= RULES.textures.max_area_textures


def test_each_part_is_filled_with_its_category_color(fig: SyntheticFigure) -> None:
    kernel = np.ones((9, 9), np.uint8)
    for part in fig.truth.parts:
        own = fig.truth_masks[part.id].data.copy()
        for other in fig.truth.parts:
            if other.parent == part.id:
                own &= ~fig.truth_masks[other.id].data
        interior = cv2.erode(own.astype(np.uint8), kernel).astype(bool)
        colors = np.unique(fig.image[interior], axis=0)
        assert colors.tolist() == [list(part.color)], part.id


def test_printed_labels_sit_inside_text_masks_and_outside_parts(fig: SyntheticFigure) -> None:
    any_part = np.zeros(fig.truth_masks["outer"].shape, bool)
    for m in fig.truth_masks.values():
        any_part |= m.data
    text = np.zeros_like(any_part)
    for t in fig.truth.text_labels:
        m = fig.raw_masks[f"raw_text_{t.part}"].data
        assert not (m & any_part).any(), t.text
        text |= m
    ink = (fig.image.max(axis=2) < 128) & ~any_part
    assert ink.sum() > 0
    assert not (ink & ~text).any()


def test_raw_masks_carry_the_planted_reconcile_cases(fig: SyntheticFigure) -> None:
    s2 = fig.truth.px_per_mm**2
    raw, true = fig.raw_masks, fig.truth_masks

    dup, right = raw["raw_right_dup"].data, true["right"].data
    assert (dup & right).sum() / (dup | right).sum() > 0.8

    overlap = raw["raw_left_lobe"].data & raw["raw_right_lobe"].data
    assert overlap.sum() / s2 == pytest.approx(1.0 * 45, rel=0.05)

    speck = raw["raw_right"].data & ~right
    assert 0 < speck.sum() / s2 < 1.0

    leak = raw["raw_vessel"].data & ~true["vessel"].data
    assert np.array_equal(leak, raw["raw_text_vessel"].data)

    sliver = raw["raw_sliver"].data
    rows = np.nonzero(sliver.any(axis=1))[0]
    assert (np.ptp(rows) + 1) / fig.truth.px_per_mm < 0.5

    becomes = {r.id: r.becomes for r in fig.truth.raw_masks}
    assert {b for b in becomes.values() if b} == {p.id for p in fig.truth.parts}


def test_explore_fixture_matches_the_pipeline(tmp_path: Path) -> None:
    """fixtures/synthetic/regions.json is what Explore's tests run on. It must be exactly
    what make synthetic-sheet writes; after a geometry change, rerun it and copy the file."""
    sheet.main(out=tmp_path)
    made = json.loads((tmp_path / "regions.json").read_text("utf-8"))
    kept = json.loads((FIXTURES_DIR / "synthetic" / "regions.json").read_text("utf-8"))
    assert made == kept
