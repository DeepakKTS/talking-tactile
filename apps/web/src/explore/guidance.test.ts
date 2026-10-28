import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import {
  Guide,
  type GuideEvent,
  beepsPerSecond,
  centimeters,
  directionOf,
  directionWords,
  guidanceSentence,
} from "./guidance";
import type { Pt } from "./homography";
import { RegionIndex } from "./regionIndex";
import { SYNTHETIC, sheet, square } from "./testkit";

const G = EXPLORE.guidance;
const FRAME = 1000 / 30;
const INDEX = new RegionIndex(sheet([
  { id: "a", poly: square(100, 100, 20), label: "aorta", centroid: [110, 110] },
]), EXPLORE); // the target, 20 mm square centered at 110, 110

function run(g: Guide, path: (t: number) => Pt | null, t0: number, t1: number): GuideEvent[] {
  const out: GuideEvent[] = [];
  for (let t = t0; t < t1; t += FRAME) out.push(...g.update(path(t), t));
  return out;
}

describe("direction and distance from code", () => {
  it.each([
    [[1, 0], "right"], [[-1, 0], "left"], [[0, -1], "up"], [[0, 1], "down"],
    [[1, -1], "up_right"], [[-1, -1], "up_left"], [[1, 1], "down_right"], [[-1, 1], "down_left"],
    [[10, -3], "right"], [[3, -10], "up"], [[10, -5], "up_right"],
  ] as const)("a page vector %j is %s, as in the Python neighbors code", (v, want) => {
    expect(directionOf([0, 0], v)).toBe(want);
  });

  it("says directions in plain words", () => {
    expect(directionWords("up_left")).toBe("up and left");
    expect(directionWords("down")).toBe("down");
  });

  it("rounds to whole centimeters, never below 1", () => {
    expect(centimeters(64)).toBe(6);
    expect(centimeters(66)).toBe(7);
    expect(centimeters(2)).toBe(1);
  });

  it("speaks the label, the direction and the distance, short", () => {
    expect(guidanceSentence("Left lobe", "up_left", 6)).toBe("Left lobe. Up and left, 6 centimeters.");
    expect(guidanceSentence("pore", "down", 1)).toBe("Pore. Down, 1 centimeter.");
  });

  it("is exactly reversed when the two points swap", () => {
    const opposite: Record<string, string> = {
      up: "down", down: "up", left: "right", right: "left",
      up_left: "down_right", down_right: "up_left", up_right: "down_left", down_left: "up_right",
    };
    const coord = fc.double({ min: -300, max: 300, noNaN: true });
    fc.assert(
      fc.property(coord, coord, coord, coord, (a, b, c, d) => {
        const ang = (Math.atan2(-(d - b), c - a) * 180) / Math.PI;
        fc.pre(Math.hypot(c - a, d - b) > 1e-6 && Math.abs(((ang + 22.5) % 45 + 45) % 45) > 1e-6);
        expect(opposite[directionOf([a, b], [c, d])]).toBe(directionOf([c, d], [a, b]));
      }),
    );
  });
});

describe("beep rate", () => {
  it("runs from beeps_per_s_near at the edge to beeps_per_s_far at far_mm and beyond", () => {
    expect(beepsPerSecond(0, G)).toBe(G.beeps_per_s_near);
    expect(beepsPerSecond(G.far_mm, G)).toBe(G.beeps_per_s_far);
    expect(beepsPerSecond(10 * G.far_mm, G)).toBe(G.beeps_per_s_far);
  });

  it("rises as the distance shrinks", () => {
    const d = fc.double({ min: 0, max: 400, noNaN: true });
    fc.assert(
      fc.property(d, d, (x, y) => {
        const [near, far] = x < y ? [x, y] : [y, x];
        expect(beepsPerSecond(near, G)).toBeGreaterThanOrEqual(beepsPerSecond(far, G));
      }),
    );
  });
});

describe("guide", () => {
  it("says the direction once, from the finger to the part's centroid", () => {
    const g = new Guide(INDEX, EXPLORE);
    const target = INDEX.byId("a");
    if (!target) throw new Error("no target");
    expect(g.start(target, [50, 170], 0)).toEqual([
      { kind: "say", text: "Aorta. Up and right, 7 centimeters." },
    ]);
    const later = run(g, () => [50, 170], 0, 3000);
    expect(later.filter((e) => e.kind === "say")).toEqual([]);
  });

  it("waits for a finger before saying where to go", () => {
    const g = new Guide(INDEX, EXPLORE);
    const target = INDEX.byId("a");
    if (!target) throw new Error("no target");
    expect(g.start(target, null, 0)).toEqual([]);
    expect(run(g, () => null, 0, 1000)).toEqual([]);
    expect(run(g, () => [110, 200], 1000, 1040).filter((e) => e.kind === "say")).toEqual([
      { kind: "say", text: "Aorta. Up, 8 centimeters." },
    ]);
  });

  it("beeps faster as the finger gets closer", () => {
    const rate = (p: Pt) => {
      const g = new Guide(INDEX, EXPLORE);
      const target = INDEX.byId("a");
      if (!target) throw new Error("no target");
      g.start(target, p, 0);
      return run(g, () => p, 0, 6000).filter((e) => e.kind === "beep").length / 6;
    };
    const far = rate([110, 270]);
    const mid = rate([110, 180]);
    const near = rate([110, 125]);
    expect(far).toBeLessThan(mid);
    expect(mid).toBeLessThan(near);
    expect(near).toBeLessThanOrEqual(G.beeps_per_s_near + 1);
  });

  it("arrives after arrive_inside_ms inside the part, once, and stops beeping", () => {
    const g = new Guide(INDEX, EXPLORE);
    const target = INDEX.byId("a");
    if (!target) throw new Error("no target");
    g.start(target, [110, 200], 0);
    run(g, () => [110, 200], 0, 1000);
    const es = run(g, () => [110, 110], 1000, 3000);
    const arrived = es.filter((e) => e.kind === "arrived");
    expect(arrived).toHaveLength(1);
    expect(arrived[0]?.t).toBeGreaterThanOrEqual(1000 + G.arrive_inside_ms);
    expect(arrived[0]?.t).toBeLessThan(1000 + G.arrive_inside_ms + 2 * FRAME);
    expect(es.filter((e) => e.kind === "beep" && e.t > (arrived[0]?.t ?? 0))).toEqual([]);
    expect(g.active).toBe(false);
  });

  it("does not arrive when the finger only passes through", () => {
    const g = new Guide(INDEX, EXPLORE);
    const target = INDEX.byId("a");
    if (!target) throw new Error("no target");
    g.start(target, [110, 200], 0);
    // 200 mm/s straight up through the 20 mm part: about 100 ms inside.
    const es = run(g, (t) => [110, 200 - (t / 1000) * 200], 0, 900);
    expect(es.filter((e) => e.kind === "arrived")).toEqual([]);
  });

  it("guides to a parent's own ring, not into its child", () => {
    const index = new RegionIndex(SYNTHETIC, EXPLORE);
    const outer = index.regions.find((r) => r.label === "outer chamber");
    if (!outer) throw new Error("no outer chamber");
    expect(index.hit(outer.centroid, EXPLORE.hysteresis.enter_shrink_mm)?.id).toBe(outer.id);
    const g = new Guide(index, EXPLORE);
    g.start(outer, [150, 250], 0);
    const es = run(g, () => outer.centroid, 0, 1000);
    expect(es.filter((e) => e.kind === "arrived")).toHaveLength(1);
  });
});
