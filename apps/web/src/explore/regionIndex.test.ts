import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import type { Pt } from "./homography";
import { RegionIndex, pointInPolygon, signedDistance } from "./regionIndex";
import { SYNTHETIC, sheet, square } from "./testkit";

describe("point in polygon and signed distance", () => {
  const sq = square(0, 0, 10);
  it("is positive inside, negative outside, the distance to the nearest edge", () => {
    expect(signedDistance(sq, [5, 5])).toBeCloseTo(5);
    expect(signedDistance(sq, [1, 5])).toBeCloseTo(1);
    expect(signedDistance(sq, [-2, 5])).toBeCloseTo(-2);
    expect(signedDistance(sq, [13, 14])).toBeCloseTo(-5);
    expect(pointInPolygon(sq, [5, 5])).toBe(true);
    expect(pointInPolygon(sq, [11, 5])).toBe(false);
  });

  it("handles a C shape, where the bounding box is not enough", () => {
    const c: Pt[] = [[0, 0], [30, 0], [30, 10], [10, 10], [10, 20], [30, 20], [30, 30], [0, 30]];
    expect(pointInPolygon(c, [20, 15])).toBe(false);
    expect(signedDistance(c, [20, 15])).toBeCloseTo(-5);
    expect(pointInPolygon(c, [5, 15])).toBe(true);
  });

  it("agrees with the sign of the distance everywhere", () => {
    fc.assert(
      fc.property(fc.double({ min: -20, max: 40, noNaN: true }), fc.double({ min: -20, max: 40, noNaN: true }), (x, y) => {
        const d = signedDistance(sq, [x, y]);
        if (Math.abs(d) > 1e-9) expect(d > 0).toBe(pointInPolygon(sq, [x, y]));
      }),
    );
  });
});

describe("region index", () => {
  const index = new RegionIndex(SYNTHETIC, EXPLORE);
  const byLabel = (label: string) => {
    const r = index.regions.find((x) => x.label === label);
    if (!r) throw new Error(label);
    return r;
  };

  it("orders regions smallest first", () => {
    const areas = index.regions.map((r) => r.area);
    expect(areas).toEqual([...areas].sort((a, b) => a - b));
    expect(index.regions[0]?.label).toBe("pore");
  });

  it("finds the child, not its parent, at the child's centroid", () => {
    const core = byLabel("inner core");
    expect(index.hit(core.centroid, 0)?.label).toBe("inner core");
    // The outer chamber's centroid is on its own ring, off the core.
    expect(index.hit(byLabel("outer chamber").centroid, 0)?.label).toBe("outer chamber");
  });

  it("finds every region at its own centroid, from the regions.json centroid", () => {
    for (const r of index.regions) expect(index.hit(r.centroid, EXPLORE.hysteresis.enter_shrink_mm)?.id).toBe(r.id);
  });

  it("shrinks and grows outlines by a margin", () => {
    const idx = new RegionIndex(sheet([{ id: "a", poly: square(10, 10, 40) }]), EXPLORE);
    const a = idx.regions[0];
    if (!a) throw new Error("no region");
    expect(idx.contains(a, [10.5, 30], 1)).toBe(false); // inside, but within 1 mm of the edge
    expect(idx.contains(a, [11.5, 30], 1)).toBe(true);
    expect(idx.contains(a, [8.5, 30], -2)).toBe(true); // outside, but within 2 mm
    expect(idx.contains(a, [7.5, 30], -2)).toBe(false);
    expect(idx.hit([8.5, 30], -2)?.id).toBe("a");
    expect(idx.hit([10.5, 30], 1)).toBeNull();
  });

  it("gives each region its earcon pitch from its texture, or the default", () => {
    expect(byLabel("outer chamber").earconHz).toBe(EXPLORE.earcons.texture_hz.dots);
    expect(byLabel("inner core").earconHz).toBe(EXPLORE.earcons.default_hz);
    expect(byLabel("pore").earconHz).toBe(EXPLORE.earcons.default_hz);
  });

  it("finds nothing off every region", () => {
    expect(index.hit([2, 2], 0)).toBeNull();
    expect(index.hit([-50, 400], -2)).toBeNull();
  });

  it("matches a brute force search at random points", () => {
    fc.assert(
      fc.property(fc.double({ min: 0, max: 216, noNaN: true }), fc.double({ min: 0, max: 280, noNaN: true }),
        fc.constantFrom(-2, 0, 1), (x, y, inset) => {
          const p: Pt = [x, y];
          const brute = [...index.regions]
            .filter((r) => signedDistance(r.polygon, p) >= inset)
            .sort((a, b) => a.area - b.area)[0];
          expect(index.hit(p, inset)?.id).toBe(brute?.id);
        }),
    );
  });

  it("looks up a point in well under a millisecond, also at 60 regions of 200 points", () => {
    const circle = (cx: number, cy: number, r: number): Pt[] =>
      Array.from({ length: 200 }, (_, k) => {
        const a = (2 * Math.PI * k) / 200;
        return [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const;
      });
    const dense = new RegionIndex(
      sheet(Array.from({ length: 60 }, (_, k) => ({
        id: `c${k}`,
        poly: circle(20 + (k % 6) * 33, 20 + Math.floor(k / 6) * 25, 11),
      }))),
      EXPLORE,
    );
    expect(dense.regions).toHaveLength(60);
    expect(lookupMicros(index)).toBeLessThan(100);
    expect(lookupMicros(dense)).toBeLessThan(1000);
  });
});

function lookupMicros(index: RegionIndex): number {
  const n = 20000;
  const pts: Pt[] = Array.from({ length: n }, (_, i) => [(i * 7.31) % 216, (i * 13.7) % 280]);
  const times: number[] = [];
  for (let rep = 0; rep < 5; rep++) {
    const t0 = performance.now();
    for (const p of pts) index.hit(p, 1);
    times.push(((performance.now() - t0) / n) * 1000);
  }
  const best = Math.min(...times);
  console.info(`region lookup: ${best.toFixed(2)} us per point, ${index.regions.length} regions`);
  return best;
}
