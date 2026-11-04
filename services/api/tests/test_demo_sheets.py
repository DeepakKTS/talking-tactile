"""make demo-sheets (app/demo_sheets.py): from an empty data folder, in mock mode, the heart and
the Commons brain are published exactly as the question eval's version 4, a rerun changes
nothing, and the question eval's replay finds them by content."""

import asyncio
from pathlib import Path

import pytest

from app import demo_sheets
from app.config import load_tactile_rules
from app.main import create_app
from app.meta import qa_eval
from app.meta.mock import MockMetaClient
from tests.recorded_png import mac_pixels


@mac_pixels
def test_demo_sheets_publish_the_eval_sheets_once_and_the_eval_finds_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = asyncio.run(demo_sheets.main_async(tmp_path))
    assert [(name, fid, v) for name, fid, v in made] == [
        ("heart", qa_eval.FIGURES["heart"], 1),
        ("brain_lobes", qa_eval.FIGURES["brain_lobes"], 1),
    ]
    assert asyncio.run(demo_sheets.main_async(tmp_path)) == made  # nothing new published

    monkeypatch.setattr(qa_eval, "DATA_DIR", tmp_path)
    rows = asyncio.run(qa_eval.run(False, ["heart"], only="off_figure"))
    assert rows and all(r["source_correct"] for r in rows)


def test_without_the_eval_sheet_the_eval_says_to_run_demo_sheets(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, client=MockMetaClient(load_tactile_rules().meta))
    with pytest.raises(demo_sheets.SheetError, match="make demo-sheets"):
        demo_sheets.eval_version(app.state.figure_service(), qa_eval.FIGURES["heart"], "heart")
