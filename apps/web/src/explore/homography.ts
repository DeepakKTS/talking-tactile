// Camera pixels to sheet millimeters with a planar homography, computed once per
// registration from the 4 corner marks and applied with a few multiplications per frame.
// The points are normalized first (Hartley), so pixels near 1000 and millimeters near 200
// give a well conditioned system.

export type Pt = readonly [number, number];
export type Quad = readonly [Pt, Pt, Pt, Pt];
/** Row major 3 x 3 matrix. */
export type Mat3 = readonly [number, number, number, number, number, number, number, number, number];

export class HomographyError extends Error {
  override name = "HomographyError";
}

const EPS = 1e-12;

/** Where the 4 printed corner marks are on the page: top left, top right, bottom right,
 * bottom left, `insetMm` in from each edge (explore.yaml registration.mark_inset_mm). */
export function markCorners(page: { width_mm: number; height_mm: number }, insetMm: number): Quad {
  const r = page.width_mm - insetMm;
  const b = page.height_mm - insetMm;
  return [
    [insetMm, insetMm],
    [r, insetMm],
    [r, b],
    [insetMm, b],
  ];
}

/** True when the 4 points, in order, go round a convex quadrilateral. Corners clicked out
 * of order cross over and fail. */
export function isConvexQuad(q: readonly Pt[]): boolean {
  if (q.length !== 4) return false;
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const a = at(q, i);
    const b = at(q, i + 1);
    const c = at(q, i + 2);
    const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(cross) < 1e-9) return false;
    if (sign === 0) sign = Math.sign(cross);
    else if (Math.sign(cross) !== sign) return false;
  }
  return true;
}

function at(q: readonly Pt[], i: number): Pt {
  const p = q[i % q.length];
  if (!p) throw new HomographyError("need 4 points");
  return p;
}

/** The matrix that maps each src point onto the dst point at the same index. */
export function homographyFromPoints(src: Quad, dst: Quad): Mat3 {
  if (!isConvexQuad(src) || !isConvexQuad(dst)) {
    throw new HomographyError(
      "The 4 corners must go round the sheet in order, with no 3 in a line.",
    );
  }
  const ns = normalizer(src);
  const nd = normalizer(dst);
  const a: number[][] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = applyHomography(ns, at(src, i));
    const [u, v] = applyHomography(nd, at(dst, i));
    a.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    a.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }
  const h = solve8(a);
  const hn: Mat3 = [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
  return scale(multiply(multiply(invertHomography(nd), hn), ns));
}

export function applyHomography(H: Mat3, p: Pt): Pt {
  const w = H[6] * p[0] + H[7] * p[1] + H[8];
  if (Math.abs(w) < EPS) throw new HomographyError("The point maps to infinity.");
  return [(H[0] * p[0] + H[1] * p[1] + H[2]) / w, (H[3] * p[0] + H[4] * p[1] + H[5]) / w];
}

export function invertHomography(H: Mat3): Mat3 {
  const [a, b, c, d, e, f, g, h, i] = H;
  const A = e * i - f * h;
  const B = f * g - d * i;
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < EPS) throw new HomographyError("The matrix cannot be inverted.");
  return scale([
    A / det, (c * h - b * i) / det, (b * f - c * e) / det,
    B / det, (a * i - c * g) / det, (c * d - a * f) / det,
    C / det, (b * g - a * h) / det, (a * e - b * d) / det,
  ]);
}

function multiply(m: Mat3, n: Mat3): Mat3 {
  const [a, b, c, d, e, f, g, h, i] = m;
  const [A, B, C, D, E, F, G, H, I] = n;
  return [
    a * A + b * D + c * G, a * B + b * E + c * H, a * C + b * F + c * I,
    d * A + e * D + f * G, d * B + e * E + f * H, d * C + e * F + f * I,
    g * A + h * D + i * G, g * B + h * E + i * H, g * C + h * F + i * I,
  ];
}

function scale(m: Mat3): Mat3 {
  const k = Math.abs(m[8]) > EPS ? m[8] : 1;
  return m.map((v) => v / k) as unknown as Mat3;
}

// Moves the centroid to the origin and the mean distance from it to sqrt(2).
function normalizer(q: Quad): Mat3 {
  const cx = q.reduce((s, p) => s + p[0], 0) / 4;
  const cy = q.reduce((s, p) => s + p[1], 0) / 4;
  const mean = q.reduce((s, p) => s + Math.hypot(p[0] - cx, p[1] - cy), 0) / 4;
  const k = Math.SQRT2 / mean;
  return [k, 0, -k * cx, 0, k, -k * cy, 0, 0, 1];
}

// Gauss-Jordan with partial pivoting on an 8 x 9 augmented matrix.
function solve8(m: number[][]): [number, number, number, number, number, number, number, number] {
  const row = (r: number): number[] => {
    const v = m[r];
    if (!v) throw new HomographyError("bad system");
    return v;
  };
  for (let col = 0; col < 8; col++) {
    let piv = col;
    for (let r = col + 1; r < 8; r++) {
      if (Math.abs(row(r)[col] ?? 0) > Math.abs(row(piv)[col] ?? 0)) piv = r;
    }
    const p = row(piv);
    const pv = p[col] ?? 0;
    if (Math.abs(pv) < 1e-10) throw new HomographyError("3 or more corners are in a line.");
    m[piv] = row(col);
    m[col] = p;
    for (let r = 0; r < 8; r++) {
      if (r === col) continue;
      const rr = row(r);
      const f = (rr[col] ?? 0) / pv;
      if (f === 0) continue;
      for (let c = col; c < 9; c++) rr[c] = (rr[c] ?? 0) - f * (p[c] ?? 0);
    }
  }
  const x = (r: number) => (row(r)[8] ?? 0) / (row(r)[r] ?? 1);
  return [x(0), x(1), x(2), x(3), x(4), x(5), x(6), x(7)];
}
