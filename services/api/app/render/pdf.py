"""print.pdf: each SVG page through cairosvg at its stated size in mm, joined with pypdf."""

import io
from collections.abc import Sequence

import cairosvg
from pypdf import PdfReader, PdfWriter


def render_pdf(svg_pages: Sequence[str]) -> bytes:
    writer = PdfWriter()
    for svg in svg_pages:
        pdf = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
        for page in PdfReader(io.BytesIO(pdf)).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
