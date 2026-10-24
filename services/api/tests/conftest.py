"""Shared fixtures: the synthetic figure run through S3 and S4."""

import pytest

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.geometry.compose import ComposedSheet, build_sheet
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.synthetic.load import SyntheticFigure, load_synthetic


@pytest.fixture(scope="session")
def synthetic() -> SyntheticFigure:
    return load_synthetic()


@pytest.fixture(scope="session")
def composed(synthetic: SyntheticFigure) -> ComposedSheet:
    rules = load_tactile_rules()
    fig = synthetic
    fit = fit_to_page(fig.truth.width_px, fig.truth.height_px, fig.truth.page, rules.page)
    raw = [m for m in fig.raw_masks.values() if m.label != "text label"]
    text = [m for m in fig.raw_masks.values() if m.label == "text label"]
    rec = reconcile(raw, text, fit.mm_per_px, rules.reconcile)
    return build_sheet(
        parts=rec.parts,
        image=fig.image,
        fit=fit,
        grade_band=fig.truth.grade_band,
        color_carries_meaning=fig.truth.color_carries_meaning,
        rules=rules,
        earcons=load_explore().earcons,
        translator=Translator(rules.braille),
    )
