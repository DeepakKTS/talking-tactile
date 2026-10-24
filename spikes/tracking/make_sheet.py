# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["reportlab==5.0.1"]
# ///
"""Draw spikes/tracking/test-sheet.pdf from sheet.json: US Letter, 4 lettered corner marks,
9 numbered targets and a 100 mm calibration bar. All positions come from sheet.json.

Run: uv run spikes/tracking/make_sheet.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
PT_PER_MM = 72 / 25.4


def main() -> None:
    sheet = json.loads((HERE / "sheet.json").read_text())
    w_mm, h_mm = sheet["page_mm"]
    assert abs(w_mm * PT_PER_MM - letter[0]) < 0.5 and abs(h_mm * PT_PER_MM - letter[1]) < 0.5

    def P(x_mm: float, y_mm: float) -> tuple[float, float]:
        # sheet.json has y down from the top; PDF has y up from the bottom.
        return x_mm * PT_PER_MM, (h_mm - y_mm) * PT_PER_MM

    out = HERE / "test-sheet.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setTitle("Talking Tactile touch test sheet")
    c.setAuthor("Talking Tactile")

    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(*P(w_mm / 2, 24), "Talking Tactile touch test sheet")
    c.setFont("Helvetica", 9)
    c.drawCentredString(*P(w_mm / 2, 30), "Print at 100 percent (Actual size). Tape it flat. Click corners A, B, C, D on the video, then press T.")

    cm = sheet["corner_mark"]
    c.setLineWidth(0.6)
    for (x, y), name in zip(sheet["corners_mm"], "ABCD"):
        cx, cy = P(x, y)
        c.circle(cx, cy, cm["ring_radius_mm"] * PT_PER_MM, stroke=1, fill=0)
        k = cm["cross_half_mm"] * PT_PER_MM
        c.line(cx - k, cy, cx + k, cy)
        c.line(cx, cy - k, cx, cy + k)
        c.setFont("Helvetica-Bold", 14)
        dx = 9 if x < w_mm / 2 else -9
        dy = 9 if y < h_mm / 2 else -9
        c.drawCentredString(*P(x + dx, y + dy + 1.5), name)

    tm = sheet["target_mark"]
    c.setLineWidth(0.8)
    for i, (x, y) in enumerate(sheet["targets_mm"]):
        cx, cy = P(x, y)
        c.circle(cx, cy, tm["ring_radius_mm"] * PT_PER_MM, stroke=1, fill=0)
        c.circle(cx, cy, tm["dot_radius_mm"] * PT_PER_MM, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(*P(x + 6, y - 5), str(i + 1))

    bar = sheet["calibration_bar"]
    bx, by = bar["start_mm"]
    length = bar["length_mm"]
    c.setLineWidth(1.0)
    c.line(*P(bx, by), *P(bx + length, by))
    c.setFont("Helvetica", 7)
    for k in range(0, length + 1, bar["tick_every_mm"]):
        tick = 4 if k % 50 == 0 else 2.5
        c.line(*P(bx + k, by - tick), *P(bx + k, by))
        c.drawCentredString(*P(bx + k, by + 4), str(k))
    c.setFont("Helvetica", 9)
    c.drawCentredString(*P(bx + length / 2, by + 10), "This bar must measure 100 mm. If it does not, reprint at Actual size.")

    c.setFont("Helvetica", 7)
    c.drawString(*P(18, h_mm - 6), "Geometry from spikes/tracking/sheet.json. Target centers and corner centers are in mm from the top left.")
    c.showPage()
    c.save()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
