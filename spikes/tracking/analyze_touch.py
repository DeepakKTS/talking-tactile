"""Analyze a touch test JSON from the tracking page. Standard library only.

  python3 spikes/tracking/analyze_touch.py touch-test-....json

Recomputes the error stats from the raw records (it does not trust the page's
summary), decides Gate B (mean error 4 mm or less), and tests whether x and y
behave differently:
  - signed bias per axis in sheet mm, with a 95 percent interval
  - scale per axis in camera pixels about the frame center, fitted from targets
    to measurements. A frame aspect ratio bug in landmark projection would show
    as a scale ratio away from 1 between x and y.
"""

from __future__ import annotations

import json
import math
import sys

GATE_B_MEAN_MM = 4.0  # TRACKER.html gate B and RULES targets
SCALE_RATIO_TOL = 0.02  # flag x and y scales that differ by more than 2 percent


def percentile(v: list[float], p: float) -> float:
    s = sorted(v)
    return s[max(1, math.ceil(p / 100 * len(s))) - 1]


def solve(A: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def homography(src: list[list[float]], dst: list[list[float]]) -> list[float]:
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    return solve(A, b) + [1.0]


def apply(H: list[float], p: list[float]) -> list[float]:
    x, y = p
    w = H[6] * x + H[7] * y + H[8]
    return [(H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w]


def mean_ci(v: list[float]) -> tuple[float, float]:
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else 0.0
    return m, 1.96 * sd / math.sqrt(len(v))


def scale_about(c: float, t: list[float], m: list[float]) -> float:
    """Least squares s in (m - c) = s * (t - c)."""
    num = sum((ti - c) * (mi - c) for ti, mi in zip(t, m))
    den = sum((ti - c) ** 2 for ti in t)
    return num / den


def analyze(result: dict, corners_mm: list[list[float]]) -> dict:
    recs = result["records"]
    err = [math.hypot(r["measuredMm"][0] - r["targetMm"][0], r["measuredMm"][1] - r["targetMm"][1]) for r in recs]
    dx = [r["measuredMm"][0] - r["targetMm"][0] for r in recs]
    dy = [r["measuredMm"][1] - r["targetMm"][1] for r in recs]
    bx, cx = mean_ci(dx)
    by, cy = mean_ci(dy)
    out = {
        "n": len(recs),
        "mean_mm": round(sum(err) / len(err), 2),
        "p95_mm": round(percentile(err, 95), 2),
        "max_mm": round(max(err), 2),
        "gate_b": "pass" if sum(err) / len(err) <= GATE_B_MEAN_MM else "fail",
        "bias_x_mm": [round(bx, 2), round(cx, 2)],
        "bias_y_mm": [round(by, 2), round(cy, 2)],
        "mean_abs_x_mm": round(sum(map(abs, dx)) / len(dx), 2),
        "mean_abs_y_mm": round(sum(map(abs, dy)) / len(dy), 2),
        "bias_differs": abs(bx - by) > math.hypot(cx, cy),
        "not_pointing": sum(1 for r in recs if not r.get("pointing")),
        "page_summary": result.get("stats"),
    }
    corners_px = result.get("corners")
    size = result.get("videoSize")
    if corners_px and size:
        to_px = homography(corners_mm, corners_px)
        tp = [apply(to_px, r["targetMm"]) for r in recs]
        mp = [apply(to_px, r["measuredMm"]) for r in recs]
        sx = scale_about(size[0] / 2, [p[0] for p in tp], [p[0] for p in mp])
        sy = scale_about(size[1] / 2, [p[1] for p in tp], [p[1] for p in mp])
        out.update({
            "video_size": size,
            "frame_aspect": round(size[0] / size[1], 4),
            "scale_x_px": round(sx, 4),
            "scale_y_px": round(sy, 4),
            "scale_ratio_x_over_y": round(sx / sy, 4),
            "aspect_suspect": abs(sx / sy - 1) > SCALE_RATIO_TOL,
        })
    return out


def main() -> None:
    from pathlib import Path

    result = json.loads(Path(sys.argv[1]).read_text())
    sheet = json.loads((Path(__file__).resolve().parent / "sheet.json").read_text())
    print(json.dumps(analyze(result, sheet["corners_mm"]), indent=1))


if __name__ == "__main__":
    main()
