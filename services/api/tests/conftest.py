"""Shared fixtures: the synthetic figure run through S3 and S4. Also the network guard: no test
reaches the network unless it is marked live and LIVE=1 is set (tests/network_guard.py)."""

from collections.abc import Iterator

import pytest

from app.braille.louis import Translator
from app.config import load_explore, load_tactile_rules
from app.geometry.compose import ComposedSheet, build_sheet
from app.geometry.reconcile import reconcile
from app.geometry.scale import fit_to_page
from app.meta import sam_adapter
from app.meta.live import live_enabled
from app.synthetic.load import SyntheticFigure, load_synthetic
from tests import network_guard


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: makes real Meta calls; runs only with LIVE=1")
    network_guard.install()
    sam_adapter.cache_decodes(True)  # a recorded mask is decoded once per test session


def pytest_unconfigure(config: pytest.Config) -> None:
    network_guard.uninstall()
    sam_adapter.cache_decodes(False)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if live_enabled():
        return
    skip = pytest.mark.skip(reason="live Meta call; set LIVE=1 to run")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_outbound_requests(request: pytest.FixtureRequest) -> Iterator[None]:
    network_guard.assert_none(network_guard.take_attempts())  # from collection or setup
    if request.node.get_closest_marker("live") and live_enabled():
        with network_guard.lifted():
            yield
        return
    yield
    network_guard.assert_none(network_guard.take_attempts())


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
