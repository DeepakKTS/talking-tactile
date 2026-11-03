import { describe, expect, it } from "vitest";
import { CPU_FALLBACK_MS, Warmup } from "./warmup";

describe("delegate warm-up", () => {
  it("a GPU that never returns a result is dropped 8 s after its first frame, not before", () => {
    const w = new Warmup();
    w.ready(1000);
    w.fed(1200); // the first frame: the timer starts here
    expect(w.timedOut(1200 + CPU_FALLBACK_MS - 1)).toBe(false);
    expect(w.timedOut(1200 + CPU_FALLBACK_MS)).toBe(true);
  });

  it("a cold start with a 10 s model load does not count against the GPU", () => {
    const w = new Warmup();
    // The page loads at 0; the model, the wasm and the GPU take 10 s. Frames before then
    // are not fed, and the timer has not started.
    w.fed(500);
    for (const t of [2000, 9000, 10000]) expect(w.timedOut(t)).toBe(false);
    w.ready(10000);
    expect(w.timedOut(10000 + CPU_FALLBACK_MS + 5000)).toBe(false); // ready, but no frame fed yet
    w.fed(20000);
    w.result(21500); // the first GPU frame took 1.5 s (shaders compiling)
    expect(w.timedOut(40000)).toBe(false);
    expect([w.delegate, w.timeToFirstResultMs]).toEqual(["GPU", 1500]);
  });

  it("ready long before Start: the timer waits for the first frame", () => {
    const w = new Warmup();
    w.ready(3000); // preloaded with the page
    expect(w.timedOut(60000)).toBe(false); // Start not pressed yet
    w.fed(60000);
    expect(w.timedOut(60000 + CPU_FALLBACK_MS)).toBe(true);
  });

  it("a GPU error means CPU; CPU is never dropped", () => {
    const w = new Warmup();
    expect(w.failed()).toBe(true);
    w.fallBack("the GPU failed");
    expect([w.delegate, w.isReady, w.warm, w.fellBack]).toEqual(["CPU", false, false, "the GPU failed"]);
    w.ready(100);
    w.fed(100);
    expect(w.timedOut(100 + 10 * CPU_FALLBACK_MS)).toBe(false);
    expect(w.failed()).toBe(false);
  });

  it("frames a second over the last 5 s", () => {
    const w = new Warmup();
    w.ready(0);
    w.fed(0);
    for (let t = 1000; t <= 7000; t += 50) w.result(t);
    expect(w.fps(7000)).toBeCloseTo(20, 0);
  });
});
