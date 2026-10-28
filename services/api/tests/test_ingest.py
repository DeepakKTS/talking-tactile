"""S0 ingest: bytes in, a normalized RGB image and its sha256 out, or a plain error."""

import hashlib
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app.config import load_tactile_rules
from app.pipeline.s0_ingest import IngestError, ingest, sharpness
from app.synthetic.load import SyntheticFigure

RULES = load_tactile_rules().pipeline
SIDE = RULES.normalize_max_side_px


def encode(img: np.ndarray, fmt: str, **kw: object) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format=fmt, **kw)
    return buf.getvalue()


def pdf_of(*pages: np.ndarray) -> bytes:
    buf = io.BytesIO()
    first, *rest = [Image.fromarray(p) for p in pages]
    first.save(buf, format="PDF", save_all=True, append_images=rest, resolution=200)
    return buf.getvalue()


def code_of(data: bytes, page: int = 0) -> str:
    with pytest.raises(IngestError) as err:
        ingest(data, page, RULES)
    return err.value.code


def test_png_passes_through_unchanged(synthetic: SyntheticFigure) -> None:
    out = ingest(encode(synthetic.image, "PNG"), 0, RULES)
    assert out.image.shape == synthetic.image.shape
    assert np.array_equal(out.image, synthetic.image)
    assert (out.source_type, out.deskewed) == ("png", False)
    h, w, _ = synthetic.image.shape
    expected = hashlib.sha256(f"{h}x{w}x3:".encode() + synthetic.image.tobytes()).hexdigest()
    assert out.figure_id == expected


def test_the_id_depends_on_pixels_not_on_the_file(synthetic: SyntheticFigure) -> None:
    a = ingest(encode(synthetic.image, "PNG"), 0, RULES)
    b = ingest(encode(synthetic.image, "PNG", optimize=True, compress_level=1), 0, RULES)
    assert a.figure_id == b.figure_id


def test_jpeg_is_accepted(synthetic: SyntheticFigure) -> None:
    out = ingest(encode(synthetic.image, "JPEG", quality=95), 0, RULES)
    assert out.source_type == "jpeg"
    assert out.image.shape == synthetic.image.shape


def test_small_images_are_scaled_up_to_the_normalized_size() -> None:
    img = np.full((400, 500, 3), 255, np.uint8)
    cv2.rectangle(img, (50, 50), (300, 200), (0, 0, 0), 3)
    out = ingest(encode(img, "PNG"), 0, RULES)
    assert out.image.shape == (round(400 * SIDE / 500), SIDE, 3)


def test_transparency_becomes_white() -> None:
    rgba = np.zeros((300, 200, 4), np.uint8)
    rgba[100:200, 50:150] = (0, 0, 0, 255)
    out = ingest(encode(rgba, "PNG"), 0, RULES)
    assert tuple(out.image[5, 5]) == (255, 255, 255)
    assert tuple(out.image[out.image.shape[0] // 2, out.image.shape[1] // 2]) == (0, 0, 0)


def test_pdf_page_is_rendered(synthetic: SyntheticFigure) -> None:
    out = ingest(pdf_of(synthetic.image), 0, RULES)
    assert out.source_type == "pdf"
    assert max(out.image.shape[:2]) == SIDE
    h, w = out.image.shape[:2]
    assert w / h == pytest.approx(synthetic.image.shape[1] / synthetic.image.shape[0], rel=0.01)


def test_pdf_page_is_picked_by_index(synthetic: SyntheticFigure) -> None:
    blank = np.full((600, 800, 3), 255, np.uint8)
    cv2.circle(blank, (400, 300), 150, (0, 0, 0), 6)
    out = ingest(pdf_of(synthetic.image, blank), 1, RULES)
    assert out.image.shape[1] == SIDE  # the second page is landscape
    assert code_of(pdf_of(synthetic.image), 1) == "bad_page"
    assert code_of(pdf_of(synthetic.image), -1) == "bad_page"


def test_uploads_over_the_limit_are_refused_before_decoding() -> None:
    limit = int(RULES.max_upload_mb * 1024 * 1024)
    assert code_of(b"\x89PNG\r\n\x1a\n" + b"\0" * limit) == "too_large"


@pytest.mark.parametrize(
    "data",
    [b"GIF89a" + b"\0" * 100, b"hello", b"", b"\x00\x01\x02" * 40],
    ids=["gif", "text", "empty", "binary"],
)
def test_unsupported_types_are_refused_by_content(data: bytes) -> None:
    assert code_of(data) == "unsupported_type"


def test_a_truncated_png_is_unreadable(synthetic: SyntheticFigure) -> None:
    data = encode(synthetic.image, "PNG")
    assert code_of(data[: len(data) // 3]) == "unreadable"


def test_a_broken_pdf_is_unreadable() -> None:
    assert code_of(b"%PDF-1.7\nnot really a pdf") == "unreadable"


@pytest.mark.parametrize(("sigma", "ok"), [(0, True), (1, True), (2, True), (4, False), (6, False)])
def test_blurry_images_are_refused(synthetic: SyntheticFigure, sigma: float, ok: bool) -> None:
    img = synthetic.image if sigma == 0 else cv2.GaussianBlur(synthetic.image, (0, 0), sigma)
    data = encode(img, "PNG")
    if ok:
        assert ingest(data, 0, RULES).sharpness >= RULES.min_sharpness
    else:
        assert code_of(data) == "blurry"


def test_a_small_sharp_image_is_judged_at_its_own_size(synthetic: SyntheticFigure) -> None:
    # Scaling a small figure up blurs it; sharpness is measured before that.
    small = cv2.resize(synthetic.image, None, fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA)
    assert sharpness(small, SIDE) == pytest.approx(sharpness(synthetic.image, SIDE), rel=0.25)
    assert ingest(encode(small, "PNG"), 0, RULES).image.shape[0] == SIDE


def photo_of(page: np.ndarray) -> np.ndarray:
    """The page photographed on a dark desk: turned 6 degrees, top edge 1 percent narrower."""
    h, w = page.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    corners = [(-w / 2 * 0.99, -h / 2), (w / 2 * 0.99, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    a = np.radians(6)
    cx, cy = w / 2 + 200, h / 2 + 250
    dst = np.float32([(cx + x * np.cos(a) - y * np.sin(a), cy + x * np.sin(a) + y * np.cos(a))
                      for x, y in corners])  # fmt: skip
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(page, m, (w + 400, h + 500), borderValue=(70, 60, 50))


def test_a_photographed_page_is_deskewed(synthetic: SyntheticFigure) -> None:
    out = ingest(encode(photo_of(synthetic.image), "PNG"), 0, RULES)
    assert out.deskewed
    h, w = synthetic.image.shape[:2]
    oh, ow = out.image.shape[:2]
    assert ow / oh == pytest.approx(w / h, rel=0.03)
    # The recovered page lines up with the original: dark ink lands in the same places.
    back = cv2.resize(out.image, (w, h), interpolation=cv2.INTER_AREA)
    ink_a = synthetic.image.max(axis=2) < 100
    ink_b = back.max(axis=2) < 100
    near = cv2.dilate(ink_a.astype(np.uint8), np.ones((21, 21), np.uint8)).astype(bool)
    assert (ink_b & near).sum() / ink_b.sum() > 0.9


def test_a_figure_with_a_big_frame_is_not_cropped() -> None:
    chart = np.full((1500, 2000, 3), 255, np.uint8)
    cv2.rectangle(chart, (150, 150), (1850, 1350), (0, 0, 0), 4)  # axes box, 70 percent of the area
    cv2.line(chart, (150, 1000), (1850, 400), (200, 30, 30), 6)
    out = ingest(encode(chart, "PNG"), 0, RULES)
    assert not out.deskewed
    assert out.image.shape == (round(1500 * SIDE / 2000), SIDE, 3)
