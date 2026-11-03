"""S0 ingest. Bytes in; a normalized RGB image (longest side normalize_max_side_px) and its
figure id (sha256 of the normalized pixels) out. Refuses with a plain message when the
upload is too large, not a PNG, JPEG or PDF, unreadable, the wrong PDF page, or blurry.
A photographed page (a bright four-sided page on a darker surface) is deskewed first.
ingest is pure: no files, no network. save and load are its form in the stage cache."""

import hashlib
import io
import json
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pypdfium2 as pdfium
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict

from app.config import Pipeline
from app.models.image import RGB

SourceType = Literal["png", "jpeg", "pdf"]
IngestCode = Literal[
    "too_large", "too_many_pixels", "unsupported_type", "unreadable", "bad_page", "blurry"
]

_MAGIC: dict[bytes, SourceType] = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"%PDF-": "pdf",
}
_BYTES_PER_MB = 1024 * 1024
_POINTS_PER_INCH = 72
_WHITE = (255, 255, 255)
_QUAD = 4
_APPROX_FRACTION = 0.02  # polygon approximation tolerance, as a share of the perimeter
_GRADIENT_PERCENTILE = 99.5
_RANGE_PERCENTILES = (1, 99)
_SOBEL_NORM = 8  # a unit step gives a Sobel response of 8 with the 3 x 3 kernel
# Checked before decoding. S0 brings every figure to 2048 px on its longest side, so more
# pixels add nothing; 50 million still takes a 48 MP phone photo (8064 x 6048). A flat PNG
# under the 10 MB limit can hold billions, and decoding one would fill memory.
MAX_PIXELS = 50_000_000
_TOO_MANY = (
    f"The image is over {MAX_PIXELS // 1_000_000} million pixels. Use a smaller scan or photo."
)


class IngestError(Exception):
    def __init__(self, code: IngestCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Ingested(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    image: RGB
    figure_id: str
    source_type: SourceType
    page_index: int
    original_size: tuple[int, int]  # width, height as decoded
    deskewed: bool
    sharpness: float


def _sniff(data: bytes) -> SourceType:
    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    raise IngestError("unsupported_type", "Upload a PNG, JPEG or PDF file.")


def _decode_image(data: bytes) -> RGB:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise IngestError("too_many_pixels", _TOO_MANY)
            opened.load()
            upright: Image.Image = ImageOps.exif_transpose(opened)
            if upright.mode in {"RGBA", "LA", "P"} or "transparency" in upright.info:
                rgba = upright.convert("RGBA")
                flat = Image.new("RGB", rgba.size, _WHITE)
                flat.paste(rgba, mask=rgba.getchannel("A"))
                upright = flat
            return np.asarray(upright.convert("RGB"), dtype=np.uint8).copy()
    except Image.DecompressionBombError as exc:  # Pillow's own limit, met at open
        raise IngestError("too_many_pixels", _TOO_MANY) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise IngestError("unreadable", "The image file could not be read.") from exc


def _decode_pdf(data: bytes, page_index: int, dpi: int) -> RGB:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise IngestError("unreadable", "The PDF file could not be read.") from exc
    try:
        if not 0 <= page_index < len(pdf):
            raise IngestError("bad_page", f"The PDF has {len(pdf)} pages. Pick one of them.")
        page = pdf[page_index]
        w, h = page.get_size()  # points
        if w * h * (dpi / _POINTS_PER_INCH) ** 2 > MAX_PIXELS:
            raise IngestError("too_many_pixels", _TOO_MANY)
        bitmap = page.render(scale=dpi / _POINTS_PER_INCH)
        return np.asarray(bitmap.to_pil().convert("RGB"), dtype=np.uint8).copy()
    finally:
        pdf.close()


def _order(quad: NDArray[np.float32]) -> NDArray[np.float32]:
    """Top-left, top-right, bottom-right, bottom-left."""
    s, d = quad.sum(axis=1), np.diff(quad, axis=1).ravel()
    corners = [quad[s.argmin()], quad[d.argmin()], quad[s.argmax()], quad[d.argmax()]]
    return np.array(corners, dtype=np.float32)


def _deskew(img: RGB, rules: Pipeline) -> RGB | None:
    """The page cut out and squared up, or None when this is not a photographed page."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    quad = cv2.approxPolyDP(biggest, _APPROX_FRACTION * cv2.arcLength(biggest, True), True)
    fraction = cv2.contourArea(quad) / (img.shape[0] * img.shape[1])
    if len(quad) != _QUAD or not cv2.isContourConvex(quad):
        return None
    if not rules.deskew_min_area_fraction <= fraction <= rules.deskew_max_area_fraction:
        return None
    inside = np.zeros_like(gray)
    cv2.fillConvexPoly(inside, quad, 255)
    contrast = float(gray[inside > 0].mean()) - float(gray[inside == 0].mean())
    if contrast < rules.deskew_min_contrast:
        return None
    tl, tr, br, bl = _order(quad.reshape(_QUAD, 2).astype(np.float32))
    w = round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    h = round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    target = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), target)
    warped = cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=_WHITE)
    return np.asarray(warped, dtype=np.uint8)


def _resize(img: RGB, side: int, allow_up: bool) -> RGB:
    h, w = img.shape[:2]
    s = side / max(h, w)
    if s == 1 or (s > 1 and not allow_up):
        return img
    size = (round(w * s), round(h * s))
    resized = cv2.resize(img, size, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    return np.asarray(resized, dtype=np.uint8)


def sharpness(img: RGB, side: int) -> float:
    """Edge steepness: the 99.5th percentile gradient over the intensity range, measured at
    the image's own resolution or reduced to `side`, never enlarged."""
    gray = cv2.cvtColor(_resize(img, side, allow_up=False), cv2.COLOR_RGB2GRAY)
    g = gray.astype(np.float32) / np.float32(np.iinfo(np.uint8).max)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3) / _SOBEL_NORM
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3) / _SOBEL_NORM
    lo, hi = np.percentile(g, _RANGE_PERCENTILES)
    if hi <= lo:
        return 0.0
    return float(np.percentile(np.hypot(gx, gy), _GRADIENT_PERCENTILE) / (hi - lo))


def figure_id(img: RGB) -> str:
    h, w, c = img.shape
    return hashlib.sha256(f"{h}x{w}x{c}:".encode() + img.tobytes()).hexdigest()


def ingest(data: bytes, page_index: int, rules: Pipeline) -> Ingested:
    if len(data) > rules.max_upload_mb * _BYTES_PER_MB:
        raise IngestError("too_large", f"The file is over {rules.max_upload_mb:g} MB.")
    kind = _sniff(data)
    if kind == "pdf":
        img = _decode_pdf(data, page_index, rules.pdf_render_dpi)
    else:
        if page_index != 0:
            raise IngestError("bad_page", "An image has one page. Use page 0.")
        img = _decode_image(data)
    original = (img.shape[1], img.shape[0])
    flat = _deskew(img, rules)
    page = img if flat is None else flat
    score = sharpness(page, rules.normalize_max_side_px)
    if score < rules.min_sharpness:
        raise IngestError(
            "blurry", "The image is too blurry to find the parts. Use a sharper scan or photo."
        )
    normalized = np.ascontiguousarray(_resize(page, rules.normalize_max_side_px, allow_up=True))
    return Ingested(
        image=normalized,
        figure_id=figure_id(normalized),
        source_type=kind,
        page_index=page_index,
        original_size=original,
        deskewed=flat is not None,
        sharpness=score,
    )


IMAGE_FILE = "normalized.png"
_INFO_FILE = "ingest.json"


def save(ing: Ingested, out: Path) -> None:
    Image.fromarray(ing.image).save(out / IMAGE_FILE)
    (out / _INFO_FILE).write_text(ing.model_dump_json(exclude={"image"}, indent=1), "utf-8")


def load(src: Path) -> Ingested:
    with Image.open(src / IMAGE_FILE) as img:
        image = np.ascontiguousarray(np.asarray(img.convert("RGB"), dtype=np.uint8))
    info = json.loads((src / _INFO_FILE).read_text("utf-8"))
    ing = Ingested(image=image, **info)
    if figure_id(image) != ing.figure_id:
        raise ValueError("the cached image does not match its figure id")
    return ing
