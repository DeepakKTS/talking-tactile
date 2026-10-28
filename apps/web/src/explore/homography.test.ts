import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  HomographyError,
  applyHomography,
  homographyFromPoints,
  invertHomography,
  isConvexQuad,
  markCorners,
  type Mat3,
  type Pt,
  type Quad,
} from "./homography";

const LETTER = { width_mm: 215.9, height_mm: 279.4 };
const MARKS = markCorners(LETTER, 12.7);
const near = (a: Pt, b: Pt, tol: number) => {
  expect(Math.abs(a[0] - b[0])).toBeLessThanOrEqual(tol);
  expect(Math.abs(a[1] - b[1])).toBeLessThanOrEqual(tol);
};

describe("homography", () => {
  it("puts the 4 marks 12.7 mm in from each page corner, clockwise from top left", () => {
    const want: Pt[] = [[12.7, 12.7], [203.2, 12.7], [203.2, 266.7], [12.7, 266.7]];
    MARKS.forEach((p, i) => { near(p, want[i] ?? [NaN, NaN], 1e-9); });
  });

  it("maps the 4 clicked corners exactly onto the 4 marks", () => {
    const px: Quad = [[312, 101], [988, 140], [1020, 650], [260, 610]];
    const H = homographyFromPoints(px, MARKS);
    px.forEach((p, i) => { near(applyHomography(H, p), MARKS[i] ?? [NaN, NaN], 1e-6); });
  });

  it("recovers a known perspective transform at interior points", () => {
    const truth: Mat3 = [1.2, 0.1, 30, -0.05, 0.9, 12, 0.0004, -0.0002, 1];
    const src: Quad = [[0, 0], [1280, 0], [1280, 720], [0, 720]];
    const dst = src.map((p) => applyHomography(truth, p)) as unknown as Quad;
    const H = homographyFromPoints(src, dst);
    for (const p of [[100, 100], [640, 360], [1200, 50], [17, 700]] as const) {
      near(applyHomography(H, p), applyHomography(truth, p), 1e-6);
    }
  });

  it("the inverse maps mm back to pixels", () => {
    const px: Quad = [[312, 101], [988, 140], [1020, 650], [260, 610]];
    const toMm = homographyFromPoints(px, MARKS);
    const toPx = invertHomography(toMm);
    for (const p of [[107.95, 139.7], [40, 250], [200, 20]] as const) {
      near(applyHomography(toMm, applyHomography(toPx, p)), p, 1e-6);
    }
  });

  it("refuses 3 collinear corners", () => {
    expect(() => homographyFromPoints([[0, 0], [1, 1], [2, 2], [0, 5]], MARKS)).toThrow(
      HomographyError,
    );
  });

  it("refuses corners clicked out of order", () => {
    expect(isConvexQuad([[0, 0], [10, 0], [10, 10], [0, 10]])).toBe(true);
    expect(isConvexQuad([[0, 0], [10, 10], [10, 0], [0, 10]])).toBe(false);
    expect(isConvexQuad([[0, 0], [10, 0], [5, 1], [0, 10]])).toBe(false);
    expect(() => homographyFromPoints([[0, 0], [10, 10], [10, 0], [0, 10]], MARKS)).toThrow(
      /order/,
    );
  });

  // A sheet seen by a camera: the page corners pushed around by up to 30 percent of the frame.
  const jitter = fc.double({ min: -0.3, max: 0.3, noNaN: true });
  const cameraQuad = fc
    .tuple(jitter, jitter, jitter, jitter, jitter, jitter, jitter, jitter)
    .map(([a, b, c, d, e, f, g, h]): Quad => [
      [320 + a * 640, 180 + b * 360],
      [960 + c * 640, 180 + d * 360],
      [960 + e * 640, 540 + f * 360],
      [320 + g * 640, 540 + h * 360],
    ])
    .filter(isConvexQuad);

  it("any convex view of the sheet maps corners exactly and round trips", () => {
    fc.assert(
      fc.property(cameraQuad, fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }), (px, u, v) => {
          const H = homographyFromPoints(px, MARKS);
          px.forEach((p, i) => { near(applyHomography(H, p), MARKS[i] ?? [NaN, NaN], 1e-6); });
          const mm: Pt = [u * LETTER.width_mm, v * LETTER.height_mm];
          near(applyHomography(H, applyHomography(invertHomography(H), mm)), mm, 1e-6);
        },
      ),
    );
  });
});
