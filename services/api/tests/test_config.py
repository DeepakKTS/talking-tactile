"""Config loaders: the real files load, and every kind of bad value is refused with a
message that names the file and the field."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import ConfigError, load_explore, load_tactile_rules
from app.main import create_app
from app.models.regions import MAX_TEXTURES
from app.paths import EXPLORE_YAML, TACTILE_RULES_YAML


def write(tmp_path: Path, data: Any, name: str = "c.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def raw(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def edit(data: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    keys = dotted.split(".")
    target = data
    for key in keys[:-1]:
        target = target[key]
    if value is DELETE:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value
    return data


DELETE = object()


def test_real_tactile_rules_load() -> None:
    rules = load_tactile_rules(TACTILE_RULES_YAML)
    assert rules.spacing.min_gap_mm == 3.2
    assert rules.spacing.point_symbol_min_mm == 6.4
    assert rules.textures.max_area_textures == 5
    assert rules.textures.max_area_textures_lower_grades == 3
    assert rules.braille.cell_to_cell_mm == (6.1, 7.6)
    assert rules.page.calibration_bar_mm == 100
    assert rules.page.dimensions_mm["letter"] == (215.9, 279.4)
    assert rules.pipeline.normalize_max_side_px == 2048


def test_texture_limit_depends_on_grade_band() -> None:
    textures = load_tactile_rules(TACTILE_RULES_YAML).textures
    assert textures.limit_for("k5") == 3
    assert textures.limit_for("9_12") == 5
    assert textures.limit_for(None) == 5


def test_figure_area_is_the_page_inside_the_margin() -> None:
    page = load_tactile_rules(TACTILE_RULES_YAML).page
    x, y, w, h = page.figure_area_mm("letter")
    assert (x, y) == (25.4, 25.4)
    assert w == pytest.approx(215.9 - 50.8)
    assert h == pytest.approx(279.4 - 50.8)


def test_real_explore_config_loads() -> None:
    cfg = load_explore(EXPLORE_YAML)
    assert cfg.hysteresis.enter_hold_ms == 120
    assert cfg.dwell.speed_below_mm_s == 15
    assert cfg.fingertip.one_euro.beta == 0.007
    assert cfg.health.off_page_points_before_recal == 15


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_explore(tmp_path / "nope.yaml")


def test_yaml_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("dwell: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape("bad.yaml")):
        load_explore(path)


def test_top_level_must_be_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mapping"):
        load_tactile_rules(write(tmp_path, [1, 2]))


TACTILE_BAD = [
    ("spacing", DELETE, "spacing"),
    ("spacing.min_gap_mm", DELETE, "min_gap_mm"),
    ("spacing.min_gap_mm", 0, "min_gap_mm"),
    ("spacing.min_gap_mm", -3.2, "min_gap_mm"),
    ("spacing.min_gap_mm", "3.2", "min_gap_mm"),
    ("spacing.min_gap_mm", True, "min_gap_mm"),
    ("spacing.mni_gap_mm", 3.2, "mni_gap_mm"),
    ("textures.max_area_textures", 0, "max_area_textures"),
    ("textures.max_area_textures", 2.5, "max_area_textures"),
    ("textures.max_area_textures", MAX_TEXTURES + 1, "regions.schema.json"),
    ("textures.max_area_textures_lower_grades", 6, "lower_grades"),
    ("textures.lower_grade_bands", ["k3"], "lower_grade_bands"),
    ("braille.cell_to_cell_mm", [7.6, 6.1], "cell_to_cell_mm"),
    ("braille.cell_to_cell_mm", [6.1], "cell_to_cell_mm"),
    ("braille.dot_base_diameter_mm", [0, 1.6], "dot_base_diameter_mm"),
    ("braille.table", "", "table"),
    ("braille.dot_to_dot_mm", [2.5, 2.3], "dot_to_dot_mm"),
    ("braille.cell_to_cell_mm", [3.0, 7.6], "between braille cells"),
    ("braille.abbrev_letters", 0, "abbrev_letters"),
    ("page.sizes", ["letter", "legal"], "sizes"),
    ("page.sizes", [], "sizes"),
    ("page.calibration_bar_mm", -100, "calibration_bar_mm"),
    ("page.dimensions_mm.a4", DELETE, "a4"),
    ("page.dimensions_mm.legal", [216, 356], "legal"),
    ("page.dimensions_mm.letter", [215.9], "letter"),
    ("page.margin_mm", 105, "no figure area"),
    ("page.margin_mm", 0, "margin_mm"),
    ("pipeline", DELETE, "pipeline"),
    ("reconcile.duplicate_iou", 1.2, "duplicate_iou"),
    ("reconcile.duplicate_iou", 0, "duplicate_iou"),
    ("reconcile.contain_fraction", DELETE, "contain_fraction"),
    ("reconcile.speck_max_area_mm2", -1, "speck_max_area_mm2"),
    ("vectorize.simplify_tolerance_mm", 0, "simplify_tolerance_mm"),
    ("textures.order", ["dots", "dots", "lines", "grid", "cross"], "twice"),
    ("textures.order", ["dots", "lines"], "at least"),
    ("textures.order", ["dots", "lines", "grid", "cross", "stripes"], "order"),
    ("layout.point_symbol_vertices", 4, "point_symbol_vertices"),
    ("layout.gap_max_passes", 0, "gap_max_passes"),
    ("render.outline_width_mm", 0, "outline_width_mm"),
    ("render", DELETE, "render"),
    ("pipeline.normalize_max_side_px", 2048.5, "normalize_max_side_px"),
    ("principles", "spacing", "principles"),
]


@pytest.mark.parametrize(
    ("dotted", "value", "message"), TACTILE_BAD, ids=[c[0] for c in TACTILE_BAD]
)
def test_tactile_rules_refuse_bad_values(
    tmp_path: Path, dotted: str, value: Any, message: str
) -> None:
    data = edit(raw(TACTILE_RULES_YAML), dotted, value)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_tactile_rules(write(tmp_path, data))


EXPLORE_BAD = [
    ("hysteresis", DELETE, "hysteresis"),
    ("hysteresis.enter_hold_ms", DELETE, "enter_hold_ms"),
    ("hysteresis.enter_hold_ms", -1, "enter_hold_ms"),
    ("hysteresis.enter_shrink_mm", -0.5, "enter_shrink_mm"),
    ("hysteresis.exit_grow_mm", "2", "exit_grow_mm"),
    ("dwell.hold_ms", 0, "hold_ms"),
    ("dwell.speed_below_mm_s", None, "speed_below_mm_s"),
    ("earcons.max_per_second", 0, "max_per_second"),
    ("earcons.texture_hz.solid", DELETE, "solid"),
    ("earcons.texture_hz.dots", -1, "dots"),
    ("earcons.default_hz", DELETE, "default_hz"),
    ("fingertip.filter", "kalman", "filter"),
    ("fingertip.one_euro.beta", -0.1, "beta"),
    ("fingertip.one_euro.mincutoff_hz", 0, "mincutoff_hz"),
    ("fingertip.one_euro.typo", 1, "typo"),
    ("guidance.update_ms", 0, "update_ms"),
    ("health.off_page_points_before_recal", 1.5, "off_page_points_before_recal"),
    ("registration.mark_inset_mm", -1, "mark_inset_mm"),
]


@pytest.mark.parametrize(
    ("dotted", "value", "message"), EXPLORE_BAD, ids=[c[0] for c in EXPLORE_BAD]
)
def test_explore_config_refuses_bad_values(
    tmp_path: Path, dotted: str, value: Any, message: str
) -> None:
    data = edit(raw(EXPLORE_YAML), dotted, value)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_explore(write(tmp_path, data))


def test_error_names_the_file(tmp_path: Path) -> None:
    data = edit(raw(EXPLORE_YAML), "dwell.hold_ms", -5)
    path = write(tmp_path, data, name="explore_broken.yaml")
    with pytest.raises(ConfigError, match=re.escape("explore_broken.yaml")):
        load_explore(path)


def test_app_refuses_to_start_with_bad_config(tmp_path: Path) -> None:
    data = edit(raw(EXPLORE_YAML), "dwell.hold_ms", -5)
    with pytest.raises(ConfigError):
        create_app(explore_path=write(tmp_path, data))
