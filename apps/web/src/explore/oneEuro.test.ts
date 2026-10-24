import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import { OneEuroFilter, OneEuroFilter2D, oneEuroParams } from "./oneEuro";

const PARAMS = oneEuroParams(EXPLORE.fingertip.one_euro);
const FPS = 30;

// Park-Miller, so the noise is the same every run.
function noise(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s / 2147483647 - 0.5) * 2;
  };
}

function sd(xs: number[]): number {
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
}

describe("1 euro filter", () => {
  it("takes its parameters from explore.yaml", () => {
    expect(PARAMS).toEqual({ minCutoffHz: 1.0, beta: 0.007, dCutoffHz: 1.0 });
  });

  it("passes a constant signal through unchanged", () => {
    const f = new OneEuroFilter(PARAMS);
    for (let i = 0; i < 60; i++) expect(f.filter(42, i / FPS)).toBe(42);
  });

  // At 1 Hz and 30 fps the smoothing factor is about 0.173, so white noise shrinks by about
  // sqrt((2 - a) / a), 3.25 times. Expect at least 2.5.
  it("cuts jitter at rest at least 2.5 times", () => {
    const f = new OneEuroFilter(PARAMS);
    const rand = noise(7);
    const raw: number[] = [];
    const out: number[] = [];
    for (let i = 0; i < 300; i++) {
      const x = 100 + rand() * 1.5;
      raw.push(x);
      out.push(f.filter(x, i / FPS));
    }
    expect(sd(out.slice(60))).toBeLessThan(sd(raw.slice(60)) / 2.5);
  });

  it("follows a 50 mm jump to within 1 mm after 1 second", () => {
    const f = new OneEuroFilter(PARAMS);
    let y = 0;
    for (let i = 0; i < FPS; i++) y = f.filter(0, i / FPS);
    for (let i = FPS; i < 2 * FPS; i++) y = f.filter(50, i / FPS);
    expect(Math.abs(y - 50)).toBeLessThan(1);
  });

  it("lags less on a fast move than on a slow one", () => {
    const lag = (speed: number) => {
      const f = new OneEuroFilter(PARAMS);
      let y = 0;
      for (let i = 0; i < FPS; i++) y = f.filter(speed * (i / FPS), i / FPS);
      return (speed * ((FPS - 1) / FPS) - y) / speed; // seconds behind
    };
    expect(lag(300)).toBeLessThan(lag(10));
  });

  it("ignores a repeated or older timestamp and starts over on reset", () => {
    const f = new OneEuroFilter2D(PARAMS);
    expect(f.filter([1, 2], 0)).toEqual([1, 2]);
    expect(f.filter([9, 9], 0)).toEqual([1, 2]);
    expect(f.filter([9, 9], -1)).toEqual([1, 2]);
    f.reset();
    expect(f.filter([9, 9], 5)).toEqual([9, 9]);
  });

  it("never leaves the range of what it was given", () => {
    fc.assert(
      fc.property(fc.array(fc.double({ min: -500, max: 500, noNaN: true }), { minLength: 1, maxLength: 200 }),
        (xs) => {
          const f = new OneEuroFilter(PARAMS);
          const lo = Math.min(...xs);
          const hi = Math.max(...xs);
          xs.forEach((x, i) => {
            const y = f.filter(x, i / FPS);
            expect(y).toBeGreaterThanOrEqual(lo - 1e-9);
            expect(y).toBeLessThanOrEqual(hi + 1e-9);
          });
        },
      ),
    );
  });
});
