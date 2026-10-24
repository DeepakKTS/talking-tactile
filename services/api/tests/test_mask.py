import numpy as np
import pytest
from pydantic import ValidationError

from app.models.mask import Mask, region_source


def grid(h: int = 4, w: int = 6) -> np.ndarray:
    data = np.zeros((h, w), dtype=bool)
    data[1:3, 2:5] = True
    return data


def test_mask_holds_a_boolean_image_and_metadata() -> None:
    m = Mask(data=grid(), label="left ventricle", score=0.9, source="sam")
    assert m.shape == (4, 6)
    assert m.area_px == 6
    assert m.label == "left ventricle"


def test_mask_data_is_a_read_only_copy() -> None:
    src = grid()
    m = Mask(data=src, label="a", score=1.0, source="teacher")
    src[0, 0] = True
    assert not m.data[0, 0]
    with pytest.raises(ValueError, match="read-only"):
        m.data[0, 0] = True


@pytest.mark.parametrize(
    "data",
    [
        np.zeros((4, 6), dtype=np.uint8),
        np.zeros((4, 6), dtype=float),
        np.zeros(6, dtype=bool),
        np.zeros((4, 6, 3), dtype=bool),
        np.zeros((0, 6), dtype=bool),
        [[True, False]],
    ],
    ids=["uint8", "float", "1-d", "3-d", "empty", "list"],
)
def test_mask_refuses_anything_but_a_2d_bool_array(data: object) -> None:
    with pytest.raises(ValidationError):
        Mask(data=data, label="a", score=0.5, source="sam")  # type: ignore[arg-type]


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan")])
def test_score_must_be_between_0_and_1(score: float) -> None:
    with pytest.raises(ValidationError):
        Mask(data=grid(), label="a", score=score, source="sam")


def test_label_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        Mask(data=grid(), label="  ", score=0.5, source="sam")


def test_source_is_one_of_three() -> None:
    with pytest.raises(ValidationError):
        Mask(data=grid(), label="a", score=0.5, source="spark")  # type: ignore[arg-type]


def test_with_data_keeps_metadata() -> None:
    m = Mask(data=grid(), label="a", score=0.7, source="synthetic")
    n = m.with_data(np.ones((4, 6), dtype=bool))
    assert (n.label, n.score, n.source, n.area_px) == ("a", 0.7, "synthetic", 24)


def test_with_data_refuses_a_different_size() -> None:
    m = Mask(data=grid(), label="a", score=0.7, source="sam")
    with pytest.raises(ValueError, match="size"):
        m.with_data(np.ones((5, 6), dtype=bool))


def test_region_source_maps_segmentation_to_sam() -> None:
    assert region_source("sam") == "sam"
    assert region_source("synthetic") == "sam"
    assert region_source("teacher") == "teacher"
