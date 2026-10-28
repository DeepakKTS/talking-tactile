import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import type { Pt } from "./homography";
import { RegionIndex } from "./regionIndex";
import { SYNTHETIC, sheet, square } from "./testkit";
import { TouchMachine, type TouchEvent } from "./touch";

const H = EXPLORE.hysteresis;
const D = EXPLORE.dwell;
const CAP = EXPLORE.earcons.max_per_second;
const FRAME = 1000 / 30;

// Two parts side by side 10 mm apart, and a parent with a child well inside it.
const PAIR = new RegionIndex(sheet([
  { id: "a", poly: square(50, 50, 40), label: "left part" },
  { id: "b", poly: square(100, 50, 40), label: "right part" },
  { id: "p", poly: square(40, 150, 80), label: "parent" },
  { id: "c", poly: square(70, 180, 20), label: "child" },
]), EXPLORE);

/** Feeds the machine one point per frame from `path` over [t0, t1) and collects events. */
function run(m: TouchMachine, path: (t: number) => Pt | null, t0: number, t1: number, frame = FRAME) {
  const out: TouchEvent[] = [];
  for (let t = t0; t < t1; t += frame) out.push(...m.update(path(t), t));
  return out;
}

const kinds = (es: TouchEvent[]) => es.map((e) => `${e.kind}:${e.region.id}`);

describe("touch state machine", () => {
  it("plays the earcon after enter_hold_ms inside the shrunk outline", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    expect(run(m, () => [10, 10], 0, 200)).toEqual([]);
    const es = run(m, () => [70, 70], 200, 200 + H.enter_hold_ms + 2 * FRAME);
    expect(kinds(es)).toEqual(["earcon:a"]);
    const first = es[0];
    expect(first?.t).toBeGreaterThanOrEqual(200 + H.enter_hold_ms);
    expect(first?.t).toBeLessThan(200 + H.enter_hold_ms + FRAME + 1);
  });

  it("does not enter on a point inside the outline but within enter_shrink_mm of it", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    expect(run(m, () => [50 + H.enter_shrink_mm / 2, 70], 0, 2000)).toEqual([]);
    expect(m.phase).toBe("outside");
  });

  it("gives up an entry that does not last enter_hold_ms", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    run(m, () => [70, 70], 0, H.enter_hold_ms - 2 * FRAME);
    expect(m.phase).toBe("entering");
    expect(run(m, () => [10, 10], H.enter_hold_ms - 2 * FRAME, 1000)).toEqual([]);
    expect(m.phase).toBe("outside");
  });

  it("speaks the label after dwell hold_ms below the dwell speed, once", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    const es = run(m, () => [70, 70], 0, 3000);
    expect(kinds(es)).toEqual(["earcon:a", "label:a"]);
    const [enter, label] = es;
    expect((label?.t ?? 0) - (enter?.t ?? 0)).toBeGreaterThanOrEqual(D.hold_ms);
    expect((label?.t ?? 0) - (enter?.t ?? 0)).toBeLessThan(D.hold_ms + 2 * FRAME);
    expect(m.phase).toBe("dwelled");
  });

  it("does not speak while the finger moves faster than the dwell speed", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    const v = 2 * D.speed_below_mm_s; // mm per second, back and forth over 20 mm
    const path = (t: number): Pt => {
      const s = ((t / 1000) * v) % 40;
      return [55 + (s < 20 ? s : 40 - s) + 5, 70];
    };
    expect(kinds(run(m, path, 0, 5000))).toEqual(["earcon:a"]);
  });

  it("keeps the part until the finger is exit_grow_mm out, then ticks after exit_hold_ms", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    run(m, () => [70, 70], 0, 1000);
    expect(run(m, () => [50 - H.exit_grow_mm / 2, 70], 1000, 3000)).toEqual([]);
    expect(m.region?.id).toBe("a");
    const es = run(m, () => [50 - 2 * H.exit_grow_mm, 70], 3000, 3000 + H.exit_hold_ms + 2 * FRAME);
    expect(kinds(es)).toEqual(["exit:a"]);
    expect(es[0]?.t).toBeGreaterThanOrEqual(3000 + H.exit_hold_ms);
    expect(m.phase).toBe("outside");
  });

  it("a short slip out and back is not an exit, and the label is not said again", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    run(m, () => [70, 70], 0, 2000); // earcon and label
    const out = run(m, () => [40, 70], 2000, 2000 + H.exit_hold_ms - 2 * FRAME);
    expect(m.phase).toBe("leaving");
    expect([...out, ...run(m, () => [70, 70], 2000 + H.exit_hold_ms - 2 * FRAME, 5000)]).toEqual([]);
    expect(m.phase).toBe("dwelled");
  });

  it("the child wins inside its parent; going back out ticks for the child, then plays the parent", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    expect(kinds(run(m, () => [50, 160], 0, 400))).toEqual(["earcon:p"]);
    expect(kinds(run(m, () => [80, 190], 400, 2000))).toEqual(["earcon:c", "label:c"]);
    expect(kinds(run(m, () => [50, 160], 2000, 2400))).toEqual(["exit:c", "earcon:p"]);
  });

  it("moving straight from one part to the next plays the exit tick, then the next earcon", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    run(m, () => [70, 70], 0, 400);
    const path = (t: number): Pt => [70 + Math.min(50, ((t - 400) / 1000) * 100), 70];
    expect(kinds(run(m, path, 400, 1300))).toEqual(["exit:a", "earcon:b"]);
  });

  it("forgets the hand silently after lost_reset_ms with no points", () => {
    const m = new TouchMachine(PAIR, EXPLORE);
    run(m, () => [70, 70], 0, 300);
    expect(m.region?.id).toBe("a");
    expect(run(m, () => null, 300, 300 + EXPLORE.fingertip.lost_reset_ms - FRAME)).toEqual([]);
    expect(m.region?.id).toBe("a");
    expect(run(m, () => null, 300 + EXPLORE.fingertip.lost_reset_ms - FRAME, 1000)).toEqual([]);
    expect(m.phase).toBe("outside");
    expect(kinds(run(m, () => [70, 70], 1000, 1300))).toEqual(["earcon:a"]);
  });

  it("caps earcons and exit ticks at max_per_second in any second", () => {
    // Many 4 mm parts in a row, swept at 400 mm/s.
    const row = new RegionIndex(sheet(Array.from({ length: 30 }, (_, k) => ({
      id: `k${k}`, poly: square(5 + k * 7, 100, 4 + 2 * H.enter_shrink_mm),
    }))), { ...EXPLORE, hysteresis: { ...H, enter_hold_ms: 0, exit_hold_ms: 0 } });
    const m = new TouchMachine(row, { ...EXPLORE, hysteresis: { ...H, enter_hold_ms: 0, exit_hold_ms: 0 } });
    const es = run(m, (t) => [5 + ((t / 1000) * 400) % 210, 103], 0, 3000, 1000 / 120);
    expectCapped(es);
    expect(m.droppedSounds).toBeGreaterThan(0);
  });
});

function expectCapped(es: TouchEvent[]) {
  const sounds = es.filter((e) => e.kind !== "label").map((e) => e.t);
  for (const t of sounds) {
    expect(sounds.filter((s) => s > t - 1000 && s <= t).length).toBeLessThanOrEqual(CAP);
  }
}

// ---------- properties ----------

const fps = fc.constantFrom(15, 30, 60);
const unit = fc.double({ min: -1, max: 1, noNaN: true });

describe("touch state machine properties", () => {
  // A finger resting on the border between two parts, or on a child's edge inside its parent,
  // with tracking jitter below enter_shrink_mm, after arriving from anywhere.
  const border = fc.record({
    edge: fc.constantFrom(
      { at: (u: number): Pt => [90, 70 + u * 15] }, // a's right edge, facing b
      { at: (u: number): Pt => [100, 70 + u * 15] }, // b's left edge, facing a
      { at: (u: number): Pt => [70, 190 + u * 8] }, // the child's left edge, in the parent
      { at: (u: number): Pt => [80 + u * 8, 200] }, // the child's bottom edge
    ),
    u: unit,
    from: fc.constantFrom<Pt>([70, 70], [120, 70], [95, 20], [50, 160], [80, 190], [10, 250]),
    speed: fc.double({ min: 5, max: 200, noNaN: true }),
    jitter: fc.double({ min: 0, max: 0.95 * Math.min(H.enter_shrink_mm, H.exit_grow_mm), noNaN: true }),
    seed: fc.integer({ min: 1, max: 2 ** 30 }),
    fps,
  });

  it("a finger resting on a border never flickers between two labels", () => {
    fc.assert(
      fc.property(border, ({ edge, u, from, speed, jitter, seed, fps }) => {
        const m = new TouchMachine(PAIR, EXPLORE);
        const to = edge.at(u);
        const travel = (Math.hypot(to[0] - from[0], to[1] - from[1]) / speed) * 1000;
        const rand = lcg(seed);
        const path = (t: number): Pt => {
          const k = Math.min(1, t / Math.max(travel, 1));
          const base: Pt = [from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k];
          if (k < 1) return base;
          const a = rand() * 2 * Math.PI;
          const r = Math.sqrt(rand()) * jitter;
          return [base[0] + r * Math.cos(a), base[1] + r * Math.sin(a)];
        };
        run(m, path, 0, travel, 1000 / fps);
        const rest = run(m, path, travel, travel + 6000, 1000 / fps);
        // Resting: at most one change (an exit or entry already under way), at most one label,
        // and never a label for a part other than the one the finger is on.
        expect(new Set(rest.filter((e) => e.kind !== "label").map((e) => e.t)).size).toBeLessThanOrEqual(1);
        const labels = rest.filter((e) => e.kind === "label");
        expect(labels.length).toBeLessThanOrEqual(1);
        for (const l of labels) expect(l.region.id).toBe(m.region?.id);
      }),
      { numRuns: 300 },
    );
  });

  // Scanning: straight strokes of 10 mm or more at 25 mm/s or faster, turning anywhere,
  // with jitter, over the synthetic sheet.
  const scan = fc.record({
    stops: fc.array(fc.tuple(fc.double({ min: 15, max: 200, noNaN: true }), fc.double({ min: 15, max: 265, noNaN: true })), { minLength: 2, maxLength: 12 }),
    speeds: fc.array(fc.double({ min: 25, max: 400, noNaN: true }), { minLength: 12, maxLength: 12 }),
    jitter: fc.double({ min: 0, max: 0.3, noNaN: true }),
    seed: fc.integer({ min: 1, max: 2 ** 30 }),
    fps,
  });

  it("fast scanning never speaks a label, and earcons stay capped", () => {
    const index = new RegionIndex(SYNTHETIC, EXPLORE);
    fc.assert(
      fc.property(scan, ({ stops, speeds, jitter, seed, fps }) => {
        const strokes = strokesOf(stops);
        fc.pre(strokes.length > 0);
        const rand = lcg(seed);
        const m = new TouchMachine(index, EXPLORE);
        const es: TouchEvent[] = [];
        let t = 0;
        strokes.forEach(([a, b], i) => {
          const v = speeds[i % speeds.length] ?? 25;
          const dur = (Math.hypot(b[0] - a[0], b[1] - a[1]) / v) * 1000;
          const end = t + dur;
          for (; t < end; t += 1000 / fps) {
            const k = (t - (end - dur)) / dur;
            const p: Pt = [a[0] + (b[0] - a[0]) * k + jitter * (2 * rand() - 1),
              a[1] + (b[1] - a[1]) * k + jitter * (2 * rand() - 1)];
            es.push(...m.update(p, t));
          }
        });
        expect(es.filter((e) => e.kind === "label")).toEqual([]);
        expectCapped(es);
      }),
      { numRuns: 300 },
    );
  });
});

// Consecutive stops at least 10 mm apart.
function strokesOf(stops: Pt[]): [Pt, Pt][] {
  const kept: Pt[] = [];
  for (const s of stops) {
    const last = kept[kept.length - 1];
    if (!last || Math.hypot(s[0] - last[0], s[1] - last[1]) >= 10) kept.push(s);
  }
  return kept.slice(1).map((b, i) => [kept[i] ?? b, b]);
}

function lcg(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}
