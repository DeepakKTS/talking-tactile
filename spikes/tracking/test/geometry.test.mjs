import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { homographyFromPoints, applyHomography, isConvexQuad } from "../lib/homography.js";
import { OneEuroFilter, OneEuroFilter2D } from "../lib/oneeuro.js";
import { pickPointingHand, contactPoint } from "../lib/fingertip.js";

const sheet = JSON.parse(readFileSync(new URL("../sheet.json", import.meta.url)));
const close = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ""} ${a} vs ${b} (tol ${tol})`);

// ---------- homography ----------

test("maps the 4 source points exactly onto the 4 destination points", () => {
  const px = [[312, 101], [988, 140], [1020, 650], [260, 610]];
  const H = homographyFromPoints(px, sheet.corners_mm);
  px.forEach((p, i) => {
    const [x, y] = applyHomography(H, p);
    close(x, sheet.corners_mm[i][0], 1e-6, "x");
    close(y, sheet.corners_mm[i][1], 1e-6, "y");
  });
});

test("recovers a known perspective transform at interior points", () => {
  const Htrue = [1.2, 0.1, 30, -0.05, 0.9, 12, 0.0004, -0.0002, 1];
  const src = [[0, 0], [640, 0], [640, 480], [0, 480]];
  const dst = src.map((p) => applyHomography(Htrue, p));
  const H = homographyFromPoints(src, dst);
  for (const p of [[100, 100], [320, 240], [600, 50], [17, 470]]) {
    const a = applyHomography(Htrue, p);
    const b = applyHomography(H, p);
    close(b[0], a[0], 1e-6);
    close(b[1], a[1], 1e-6);
  }
});

test("pixel to mm and back is the identity", () => {
  const px = [[312, 101], [988, 140], [1020, 650], [260, 610]];
  const toMm = homographyFromPoints(px, sheet.corners_mm);
  const toPx = homographyFromPoints(sheet.corners_mm, px);
  for (const t of sheet.targets_mm) {
    const back = applyHomography(toMm, applyHomography(toPx, t));
    close(back[0], t[0], 1e-6);
    close(back[1], t[1], 1e-6);
  }
});

test("collinear points are rejected", () => {
  assert.throws(() => homographyFromPoints([[0, 0], [1, 1], [2, 2], [0, 5]], sheet.corners_mm), /collinear/);
});

test("convex quad check catches corners clicked out of order", () => {
  assert.equal(isConvexQuad([[0, 0], [10, 0], [10, 10], [0, 10]]), true);
  assert.equal(isConvexQuad([[0, 0], [10, 10], [10, 0], [0, 10]]), false);
  assert.equal(isConvexQuad([[0, 0], [10, 0], [5, 1], [0, 10]]), false);
});

// ---------- 1 euro filter ----------

const params = { mincutoffHz: 1.0, beta: 0.007, dcutoffHz: 1.0 };

test("a constant signal passes through unchanged", () => {
  const f = new OneEuroFilter(params);
  for (let i = 0; i < 60; i++) assert.equal(f.filter(42, i / 30), 42);
});

// At 1 Hz cutoff and 30 fps the smoothing factor is about 0.173, so white noise
// shrinks by at most sqrt((2 - a) / a), about 3.25x. Expect at least 2.5x.
test("jitter at rest is reduced at least 2.5 times", () => {
  const f = new OneEuroFilter(params);
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 2;
  const raw = [];
  const out = [];
  for (let i = 0; i < 300; i++) {
    const x = 100 + rand() * 1.5;
    raw.push(x);
    out.push(f.filter(x, i / 30));
  }
  const sd = (a) => {
    const t = a.slice(60);
    const m = t.reduce((s, v) => s + v, 0) / t.length;
    return Math.sqrt(t.reduce((s, v) => s + (v - m) ** 2, 0) / t.length);
  };
  assert.ok(sd(out) < sd(raw) / 2.5, `filtered sd ${sd(out)} raw sd ${sd(raw)}`);
});

test("a step is followed: within 1 mm of a 50 mm jump after 1 second", () => {
  const f = new OneEuroFilter(params);
  let y = 0;
  for (let i = 0; i < 30; i++) y = f.filter(0, i / 30);
  for (let i = 30; i < 60; i++) y = f.filter(50, i / 30);
  close(y, 50, 1);
});

test("2D filter filters each axis and ignores repeated timestamps", () => {
  const f = new OneEuroFilter2D(params);
  assert.deepEqual(f.filter([1, 2], 0), [1, 2]);
  assert.deepEqual(f.filter([9, 9], 0), [1, 2]);
});

// ---------- pointing hand and contact point ----------

// Synthetic hand: wrist at origin, fingers point up (negative y).
function hand({ indexTip = 90, otherTip = 25 } = {}) {
  const pts = Array.from({ length: 21 }, () => [0, 0]);
  const fingers = [
    { x: -20, pip: 6, dip: 7, tip: 8, tipD: indexTip },
    { x: 0, pip: 10, dip: 11, tip: 12, tipD: otherTip },
    { x: 20, pip: 14, dip: 15, tip: 16, tipD: otherTip },
    { x: 40, pip: 18, dip: 19, tip: 20, tipD: otherTip },
  ];
  for (const f of fingers) {
    pts[f.pip] = [f.x, -40];
    pts[f.dip] = [f.x, -(40 + f.tipD) / 2];
    pts[f.tip] = [f.x, -f.tipD];
  }
  return pts;
}

test("a pointing hand is recognized", () => {
  assert.deepEqual(pickPointingHand([hand()]), { index: 0, pointing: true });
});

test("an open hand is found but not pointing", () => {
  assert.deepEqual(pickPointingHand([hand({ otherTip: 85 })]), { index: 0, pointing: false });
});

test("with two hands the pointing one wins", () => {
  assert.deepEqual(pickPointingHand([hand({ otherTip: 85 }), hand()]), { index: 1, pointing: true });
});

test("no hands gives null", () => {
  assert.equal(pickPointingHand([]), null);
});

test("contact point moves back toward the DIP joint by the offset", () => {
  assert.deepEqual(contactPoint([100, 100], [100, 120], 4), [100, 104]);
  assert.deepEqual(contactPoint([100, 100], [100, 102], 4), [100, 102]);
  assert.deepEqual(contactPoint([100, 100], [100, 120], 0), [100, 100]);
});
