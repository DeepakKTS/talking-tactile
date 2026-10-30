"""The Meta layer in mock mode: the client interface, the mock, the cost meter, and the SAM
boundary. No network and no key."""

import asyncio
import json
import re
from pathlib import Path

import numpy as np
import pytest

from app.config import load_tactile_rules
from app.meta.client import LiveClientUnavailableError, MetaClient, make_client
from app.meta.cost import BudgetExceededError, CostMeter
from app.meta.mock import MockFixtureMissingError, MockMetaClient
from app.meta.sam_adapter import parse_events, to_masks
from app.meta.types import Understanding
from app.paths import RECORDED_DIR
from app.pipeline import s1_understand, s2_ground
from app.pipeline.s0_ingest import figure_id
from app.prompts import load_prompt
from app.synthetic.load import SyntheticFigure
from tests.test_live_client import SHEET

RULES = load_tactile_rules()
SMOKE_SAM = json.loads((RECORDED_DIR / "smoke_sam_heart_left_ventricle.json").read_text())
S1 = load_prompt(s1_understand.PROMPT)
S2 = load_prompt(s2_ground.PROMPT)
APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def mock() -> MockMetaClient:
    return MockMetaClient(RULES.meta)


def test_the_mock_is_a_meta_client(mock: MockMetaClient) -> None:
    client: MetaClient = mock
    assert client.mode == "mock"


def test_understand_returns_the_synthetic_parts(mock: MockMetaClient,
                                               synthetic: SyntheticFigure) -> None:  # fmt: skip
    u = asyncio.run(mock.understand(synthetic.image, figure_id(synthetic.image), S1, S1, SHEET))
    assert isinstance(u, Understanding)
    assert u.title == synthetic.truth.title
    assert u.color_carries_meaning is True
    assert u.verdict == "make_tactile"
    phrases = [p.phrase for p in u.parts]
    assert len(phrases) == len(set(phrases))
    assert {p.label for p in synthetic.truth.parts} <= set(phrases)
    assert "right side chamber" in phrases  # a second proposal for the same part
    assert RULES.meta.text_phrase not in phrases


def test_segment_returns_every_instance_as_masks(mock: MockMetaClient,
                                                 synthetic: SyntheticFigure) -> None:  # fmt: skip
    fid = figure_id(synthetic.image)
    vessel = asyncio.run(mock.segment(synthetic.image, fid, "cross vessel", S2))
    assert len(vessel) == 2  # the part and a sliver
    assert all(m.label == "cross vessel" and m.source == "synthetic" for m in vessel)
    assert all(m.shape == synthetic.image.shape[:2] for m in vessel)
    text = asyncio.run(mock.segment(synthetic.image, fid, RULES.meta.text_phrase, S2))
    assert len(text) == len(synthetic.truth.text_labels)


def test_zero_matches_is_a_result_not_an_error(mock: MockMetaClient,
                                               synthetic: SyntheticFigure) -> None:  # fmt: skip
    fid = figure_id(synthetic.image)
    assert asyncio.run(mock.segment(synthetic.image, fid, "mitochondria", S2)) == []


def test_an_image_without_fixtures_is_refused(mock: MockMetaClient) -> None:
    other = np.full((10, 10, 3), 255, np.uint8)
    with pytest.raises(MockFixtureMissingError, match="mock mode"):
        asyncio.run(mock.understand(other, figure_id(other), S1, S1, SHEET))


def test_mock_calls_cost_nothing_and_are_logged(mock: MockMetaClient,
                                                synthetic: SyntheticFigure) -> None:  # fmt: skip
    fid = figure_id(synthetic.image)
    asyncio.run(mock.understand(synthetic.image, fid, S1, S1, SHEET))
    asyncio.run(mock.segment(synthetic.image, fid, "pore", S2))
    assert [c.call for c in mock.calls] == ["understand", "segment"]
    assert mock.meter.spent_usd == 0


def test_live_mode_is_not_built_yet() -> None:
    assert make_client(mock=True, rules=RULES.meta).mode == "mock"
    with pytest.raises(LiveClientUnavailableError, match="MOCK_META=1"):
        make_client(mock=False, rules=RULES.meta)


def test_cost_meter_prices_each_model() -> None:
    meter = CostMeter(RULES.meta)
    usd = meter.record("muse-spark-1.3", input_tokens=1_000_000, cached_tokens=200_000,
                       output_tokens=1_000)  # fmt: skip
    assert usd == pytest.approx(0.8 * 1.25 + 0.2 * 0.15 + 0.001 * 4.25)
    assert meter.record("sam-3.1", images=10) == pytest.approx(0.025)
    assert meter.record("muse-voice-transcribe-1.0", audio_seconds=1800) == pytest.approx(0.09)


def test_cost_meter_warns_once_at_each_threshold() -> None:
    meter = CostMeter(RULES.meta)
    budget = RULES.meta.budget_usd
    images_per_usd = 1 / RULES.meta.prices_usd["sam-3.1"].per_image  # type: ignore[operator]
    meter.record("sam-3.1", images=int(0.69 * budget * images_per_usd))
    assert meter.warnings == []
    meter.record("sam-3.1", images=int(0.02 * budget * images_per_usd))
    meter.record("sam-3.1", images=1)
    assert meter.warnings == [0.7]
    meter.record("sam-3.1", images=int(0.2 * budget * images_per_usd))
    assert meter.warnings == [0.7, 0.9]


def test_cost_meter_refuses_a_call_that_would_pass_the_budget() -> None:
    meter = CostMeter(RULES.meta)
    meter.record("sam-3.1", images=int(RULES.meta.budget_usd / 0.0025) - 1)
    with pytest.raises(BudgetExceededError):
        meter.check("sam-3.1", images=2)
    meter.check("sam-3.1", images=1)


def test_cost_meter_refuses_unknown_models_and_units() -> None:
    meter = CostMeter(RULES.meta)
    with pytest.raises(KeyError, match="price"):
        meter.record("muse-image", images=1)
    with pytest.raises(ValueError, match="per_image"):
        meter.record("muse-spark-1.3", images=1)


def test_zero_sam_instances_are_no_masks() -> None:
    empty = asyncio.run(parse_events(SMOKE_SAM["response"]["events"]))
    assert to_masks(empty, (10, 10), "pore") == []


def test_a_recorded_answer_becomes_one_full_size_mask_per_instance() -> None:
    rec = json.loads((RECORDED_DIR / "sam_diag_control_banana.json").read_text())
    parsed = asyncio.run(parse_events(rec["response"]["events"]))
    (mask,) = to_masks(parsed, (902, 1024), "banana")
    assert mask.data.shape == (902, 1024) and mask.label == "banana"
    assert mask.score == pytest.approx(0.977, abs=0.001)
    rows, cols = np.nonzero(mask.data)  # inside the bounds 47,44 to 978,855
    assert (cols.min(), rows.min()) >= (47, 44) and (cols.max(), rows.max()) < (978, 855)


SAM_WIRE_WORDS = re.compile(r"meta_sam_parser|one_bit|base85|<\|mask|box-local")


def test_only_the_sam_adapter_knows_the_wire_format() -> None:
    leaks = [
        str(p.relative_to(APP_DIR))
        for p in APP_DIR.rglob("*.py")
        if p.name != "sam_adapter.py" and SAM_WIRE_WORDS.search(p.read_text(encoding="utf-8"))
    ]
    assert leaks == []
    assert SAM_WIRE_WORDS.search((APP_DIR / "meta" / "sam_adapter.py").read_text())
