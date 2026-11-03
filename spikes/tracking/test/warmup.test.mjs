// The Gate B page's delegate warm-up (lib/warmup.js), the port of the shipped rules.
import { test } from "node:test";
import assert from "node:assert/strict";
import { CPU_FALLBACK_MS, Warmup } from "../lib/warmup.js";

test("a GPU that never returns is dropped 8 s after its first frame", () => {
  const w = new Warmup();
  w.ready(500);
  w.fed(1000);
  assert.equal(w.timedOut(1000 + CPU_FALLBACK_MS - 1), false);
  assert.equal(w.timedOut(1000 + CPU_FALLBACK_MS), true);
});

test("a cold start with a 10 s model load does not trigger the CPU fallback", () => {
  const w = new Warmup();
  w.fed(100); // before ready: not counted
  assert.equal(w.timedOut(10000), false);
  w.ready(10000);
  w.fed(10050);
  w.result(11550);
  assert.equal(w.timedOut(40000), false);
  assert.deepEqual([w.delegate, w.timeToFirstResultMs], ["GPU", 1500]);
});
