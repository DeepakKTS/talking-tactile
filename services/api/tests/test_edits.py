"""Teacher edits replayed on reconciled parts, their annotations, and their SQLite store."""

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.geometry.reconcile import ReconciledPart
from app.models.mask import Mask
from app.pipeline.edits import (
    EDIT,
    AddEdit,
    DeleteEdit,
    DescribeEdit,
    EditError,
    EditStore,
    LabelEdit,
    MergeEdit,
    annotations,
    apply_edits,
    edits_digest,
)

SIZE = (40, 40)
CONTAIN = 0.95


def box(r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
    data = np.zeros(SIZE, dtype=bool)
    data[r0:r1, c0:c1] = True
    return data


def part(pid: str, data: np.ndarray, label: str, parent: str | None = None) -> ReconciledPart:
    mask = Mask(data=data, label=label, score=0.9, source="sam")
    return ReconciledPart(id=pid, mask=mask, parent=parent)


def mask(data: np.ndarray, label: str) -> Mask:
    return Mask(data=data, label=label, score=0.8, source="sam")


# r1 holds r2, which holds r3. r4 stands alone.
PARTS = [
    part("r1", box(0, 30, 0, 30), "outer"),
    part("r2", box(5, 20, 5, 20), "middle", parent="r1"),
    part("r3", box(8, 12, 8, 12), "core", parent="r2"),
    part("r4", box(32, 38, 32, 38), "island"),
]


def by_id(parts: list[ReconciledPart]) -> dict[str, ReconciledPart]:
    return {p.id: p for p in parts}


def test_a_label_edit_renames_the_part() -> None:
    out = by_id(apply_edits(PARTS, [LabelEdit(op="label", region="r4", label="isle")], {}, CONTAIN))
    assert out["r4"].mask.label == "isle"
    assert out["r1"].mask.label == "outer"


def test_a_piece_id_names_its_part() -> None:
    out = by_id(apply_edits(PARTS, [LabelEdit(op="label", region="r4_2", label="isle")], {},
                            CONTAIN))  # fmt: skip
    assert out["r4"].mask.label == "isle"


def test_delete_moves_children_up_to_the_parent() -> None:
    out = by_id(apply_edits(PARTS, [DeleteEdit(op="delete", region="r2")], {}, CONTAIN))
    assert "r2" not in out
    assert out["r3"].parent == "r1"


def test_merge_joins_pixels_and_adopts_children() -> None:
    edits = [MergeEdit(op="merge", region="r2", into="r4")]
    out = by_id(apply_edits(PARTS, edits, {}, CONTAIN))
    assert "r2" not in out
    r4 = out["r4"]
    assert r4.mask.label == "island"
    assert r4.merged == ["middle"]
    assert r4.mask.area_px == PARTS[1].mask.area_px + PARTS[3].mask.area_px
    assert out["r3"].parent == "r4"


def test_merging_a_part_into_its_own_descendant_makes_no_cycle() -> None:
    out = by_id(apply_edits(PARTS, [MergeEdit(op="merge", region="r1", into="r3")], {}, CONTAIN))
    assert "r1" not in out
    assert out["r3"].parent is None
    assert out["r2"].parent == "r3"


def test_merging_a_part_into_itself_is_refused() -> None:
    with pytest.raises(EditError, match="same part"):
        apply_edits(PARTS, [MergeEdit(op="merge", region="r4", into="r4_2")], {}, CONTAIN)


def test_an_added_part_inside_another_becomes_its_child() -> None:
    added = {"dot": [mask(box(22, 26, 22, 26), "dot")]}
    out = by_id(apply_edits(PARTS, [AddEdit(op="add", name="dot")], added, CONTAIN))
    assert out["t1"].parent == "r1"
    assert out["t1"].mask.area_px == 16
    assert list(out)[-1] == "t1"


def test_an_added_part_takes_only_free_pixels_and_adopts_what_it_holds() -> None:
    # Overlaps the corner of r1 and holds all of r4.
    added = {"sea": [mask(box(28, 40, 28, 40), "sea")]}
    out = by_id(apply_edits(PARTS, [AddEdit(op="add", name="sea")], added, CONTAIN))
    sea = out["t1"]
    assert sea.parent is None
    assert not (sea.mask.data & out["r1"].mask.data).any()
    assert out["r4"].parent == "t1"
    assert out["r1"].mask.area_px == PARTS[0].mask.area_px


def test_an_added_part_with_no_match_or_no_free_pixels_is_refused() -> None:
    with pytest.raises(EditError, match="No part called"):
        apply_edits(PARTS, [AddEdit(op="add", name="ghost")], {"ghost": []}, CONTAIN)
    covered = {"core again": [mask(box(5, 20, 5, 20), "core again")]}
    with pytest.raises(EditError, match="already belongs"):
        apply_edits(PARTS, [AddEdit(op="add", name="core again")], covered, CONTAIN)


def test_an_edit_on_a_region_that_is_gone_is_refused() -> None:
    edits = [DeleteEdit(op="delete", region="r4"), LabelEdit(op="label", region="r4", label="x")]
    with pytest.raises(EditError, match="no region r4"):
        apply_edits(PARTS, edits, {}, CONTAIN)


def test_annotations_follow_the_same_numbering_as_apply() -> None:
    edits = [
        LabelEdit(op="label", region="r1", label="shell"),
        DescribeEdit(op="describe", region="r2_3", description="The middle layer."),
        MergeEdit(op="merge", region="r3", into="r4"),
        AddEdit(op="add", name="a"),
        AddEdit(op="add", name="b"),
        DeleteEdit(op="delete", region="r1"),
    ]
    notes = annotations(edits)
    assert notes.descriptions == {"r2": "The middle layer."}
    assert notes.verified == {"r1", "r2", "r4", "t1", "t2"}


def test_edits_are_validated_before_they_are_stored() -> None:
    assert (
        EDIT.validate_python({"op": "label", "region": "r1", "label": "  aorta "}).label == "aorta"
    )
    for bad in [
        {"op": "label", "region": "../etc", "label": "x"},
        {"op": "label", "region": "r1", "label": ""},
        {"op": "label", "region": "r1", "label": "x", "extra": 1},
        {"op": "merge", "region": "r1"},
        {"op": "paint", "region": "r1"},
    ]:
        with pytest.raises(ValidationError):
            EDIT.validate_python(bad)


def test_the_digest_follows_order_and_content() -> None:
    a = LabelEdit(op="label", region="r1", label="x")
    b = DeleteEdit(op="delete", region="r2")
    assert edits_digest([a, b]) != edits_digest([b, a])
    assert edits_digest([a]) == edits_digest([LabelEdit(op="label", region="r1", label="x")])
    assert edits_digest([]) != edits_digest([a])


def test_the_store_numbers_edits_per_figure(tmp_path: Path) -> None:
    store = EditStore(tmp_path / "jobs.sqlite")
    f, g = "a" * 64, "b" * 64
    assert store.version(f) == 0
    a = LabelEdit(op="label", region="r1", label="x")
    b = AddEdit(op="add", name="pore")
    assert store.append(f, a) == 1
    assert store.append(f, b) == 2
    assert store.append(g, a) == 1
    assert store.list(f, 2) == [a, b]
    assert store.list(f, 1) == [a]
    assert EditStore(tmp_path / "jobs.sqlite").version(f) == 2
