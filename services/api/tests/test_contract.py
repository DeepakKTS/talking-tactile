"""regions.json contract: the pydantic models must accept exactly what docs/regions.schema.json
accepts, and the golden fixture must pass both."""

import copy
import json
from typing import Any, get_args

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.models import regions as rm
from app.paths import GOLDEN_REGIONS, REGION_CASES, REGIONS_SCHEMA

SCHEMA: dict[str, Any] = json.loads(REGIONS_SCHEMA.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
GOLDEN: dict[str, Any] = json.loads(GOLDEN_REGIONS.read_text(encoding="utf-8"))
REGION_PROPS = SCHEMA["properties"]["regions"]["items"]["properties"]


def schema_ok(obj: Any) -> bool:
    return VALIDATOR.is_valid(obj)


def model_ok(obj: Any) -> bool:
    try:
        rm.RegionsFile.from_json_obj(obj)
    except ValidationError:
        return False
    return True


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_golden_passes_schema_and_models() -> None:
    assert schema_ok(GOLDEN)
    assert model_ok(GOLDEN)


def test_golden_round_trips_exactly() -> None:
    assert rm.RegionsFile.from_json_obj(GOLDEN).to_json_obj() == GOLDEN


def test_model_output_passes_schema() -> None:
    assert schema_ok(rm.RegionsFile.from_json_obj(GOLDEN).to_json_obj())


def test_enums_match_schema() -> None:
    assert get_args(rm.FigureType) == tuple(SCHEMA["properties"]["figure_type"]["enum"])
    assert get_args(rm.GradeBand) == tuple(SCHEMA["properties"]["grade_band"]["enum"])
    assert get_args(rm.PageSize) == tuple(
        SCHEMA["properties"]["page"]["properties"]["size"]["enum"]
    )
    texture_ids = SCHEMA["properties"]["textures"]["items"]["properties"]["id"]["enum"]
    assert get_args(rm.TextureId) == tuple(texture_ids)
    directions = REGION_PROPS["neighbors"]["items"]["properties"]["direction"]["enum"]
    assert get_args(rm.Direction) == tuple(directions)
    assert get_args(rm.RegionSource) == tuple(REGION_PROPS["source"]["enum"])


def test_limits_come_from_schema() -> None:
    assert rm.MAX_POLYGON_POINTS == REGION_PROPS["polygon_mm"]["maxItems"] == 200
    assert rm.MIN_POLYGON_POINTS == REGION_PROPS["polygon_mm"]["minItems"] == 3
    assert rm.MAX_TEXTURES == SCHEMA["properties"]["textures"]["maxItems"] == 5


CASES: list[dict[str, Any]] = json.loads(REGION_CASES.read_text(encoding="utf-8"))["cases"]


def apply_case(case: dict[str, Any]) -> Any:
    obj = copy.deepcopy(GOLDEN)
    target: Any = obj
    for key in case["path"][:-1]:
        target = target[key]
    if case["op"] == "delete":
        del target[case["path"][-1]]
    else:
        target[case["path"][-1]] = case["value"]
    return obj


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_shared_edge_cases(case: dict[str, Any]) -> None:
    obj = apply_case(case)
    assert schema_ok(obj) is case["valid"], "the schema disagrees with cases.json"
    assert model_ok(obj) is case["valid"], "pydantic disagrees with the schema"


def test_top_level_list_is_rejected() -> None:
    assert not schema_ok([GOLDEN])
    assert not model_ok([GOLDEN])


def test_golden_references_are_consistent() -> None:
    assert rm.check_references(rm.RegionsFile.from_json_obj(GOLDEN)) == []


def test_reference_problems_are_found() -> None:
    obj = copy.deepcopy(GOLDEN)
    obj["regions"][1]["id"] = "r1"
    obj["regions"][2]["parent"] = "r9"
    obj["regions"][3]["parent"] = "r4"
    obj["regions"][0]["neighbors"].append({"id": "nope", "direction": "up"})
    problems = rm.check_references(rm.RegionsFile.from_json_obj(obj))
    assert problems == [
        "duplicate region id r1",
        "r1: neighbor r2 does not exist",
        "r1: neighbor nope does not exist",
        "r1: is its own parent",
        "r3: parent r9 does not exist",
        "r4: is its own parent",
    ]


def all_paths(obj: Any, prefix: tuple[str | int, ...] = ()) -> list[tuple[str | int, ...]]:
    paths: list[tuple[str | int, ...]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            paths.append((*prefix, key))
            paths.extend(all_paths(value, (*prefix, key)))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            paths.append((*prefix, i))
            paths.extend(all_paths(value, (*prefix, i)))
    return paths


PATHS = all_paths(GOLDEN)
VALUE_POOL: list[Any] = [
    None,
    True,
    False,
    0,
    -1,
    1.5,
    2,
    1000,
    "",
    "x",
    "dots",
    "sam",
    "teacher",
    "up",
    "inside",
    "letter",
    "a4",
    "k5",
    "other",
    [],
    {},
    [0, 0],
    [0, 0, 0],
    [[0, 0]] * 3,
    [[0, 0]] * 201,
    {"id": "r9", "direction": "up"},
    {"id": "solid", "meaning": "m", "earcon_hz": 1},
]


@st.composite
def mutated_golden(draw: st.DrawFn) -> Any:
    obj = copy.deepcopy(GOLDEN)
    for _ in range(draw(st.integers(min_value=1, max_value=3))):
        path = draw(st.sampled_from(PATHS))
        parent: Any = obj
        try:
            for key in path[:-1]:
                parent = parent[key]
            last = path[-1]
            if isinstance(parent, dict):
                op = draw(st.sampled_from(["replace", "delete", "add"]))
                if op == "delete":
                    parent.pop(last, None)
                elif op == "add":
                    parent[draw(st.sampled_from(["extra", "zz"]))] = draw(
                        st.sampled_from(VALUE_POOL)
                    )
                else:
                    parent[last] = copy.deepcopy(draw(st.sampled_from(VALUE_POOL)))
            elif isinstance(parent, list) and isinstance(last, int) and last < len(parent):
                op = draw(st.sampled_from(["replace", "delete", "duplicate"]))
                if op == "delete":
                    parent.pop(last)
                elif op == "duplicate":
                    parent.extend([copy.deepcopy(parent[last])] * draw(st.integers(1, 6)))
                else:
                    parent[last] = copy.deepcopy(draw(st.sampled_from(VALUE_POOL)))
        except (KeyError, IndexError, TypeError):
            pass  # an earlier mutation removed this path; the object is still a valid test input
    return obj


@settings(max_examples=600, deadline=None)
@given(mutated_golden())
def test_models_accept_exactly_what_the_schema_accepts(obj: Any) -> None:
    assert model_ok(obj) == schema_ok(obj)


def test_lines_name_touchable_regions_and_merge_proposals_regions_on_the_sheet() -> None:
    obj = copy.deepcopy(GOLDEN)
    obj["lines"][0]["separates"] = ["r1", "s9"]
    obj["lines"][1]["parent"] = "r8"
    obj["lines"][1]["id"] = "r2"
    obj["merge_proposals"][0]["region_ids"] = ["r3", "x"]
    problems = rm.check_references(rm.RegionsFile.from_json_obj(obj))
    assert problems == [
        "duplicate region id r2",
        "l1: separates s9, which is not a touchable region",
        "r2: parent r8 does not exist",
        "merge vessel and valve: x is not a region drawn on the sheet",
    ]
