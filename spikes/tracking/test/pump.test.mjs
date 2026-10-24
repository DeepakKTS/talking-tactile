import { test } from "node:test";
import assert from "node:assert/strict";
import { createFramePump } from "../lib/pump.js";

test("sends when idle and drops while a frame is in flight", async () => {
  const sent = [];
  const pump = createFramePump((f) => sent.push(f));
  assert.equal(await pump.offer(() => 1), true);
  assert.equal(await pump.offer(() => 2), false);
  assert.equal(await pump.offer(() => 3), false);
  assert.deepEqual(sent, [1]);
  pump.done();
  assert.equal(await pump.offer(() => 4), true);
  assert.deepEqual(sent, [1, 4]);
  assert.deepEqual(pump.stats, { offered: 4, sent: 2, dropped: 2, failed: 0 });
});

test("a frame offered during an async capture is dropped, not queued", async () => {
  const sent = [];
  const pump = createFramePump((f) => sent.push(f));
  let release;
  const slow = pump.offer(() => new Promise((r) => (release = () => r("a"))));
  assert.equal(pump.busy, true);
  assert.equal(await pump.offer(() => "b"), false);
  release();
  assert.equal(await slow, true);
  assert.deepEqual(sent, ["a"]);
});

test("a failed capture frees the slot", async () => {
  const pump = createFramePump(() => {});
  await assert.rejects(pump.offer(() => Promise.reject(new Error("no frame"))));
  assert.equal(pump.busy, false);
  assert.equal(await pump.offer(() => 1), true);
  assert.equal(pump.stats.failed, 1);
});

test("never more than one frame in flight under a burst", async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  const pump = createFramePump(() => {
    inFlight++;
    maxInFlight = Math.max(maxInFlight, inFlight);
  });
  for (let i = 0; i < 100; i++) {
    await pump.offer(() => i);
    if (i % 7 === 0) {
      inFlight--;
      pump.done();
    }
  }
  assert.equal(maxInFlight, 1);
  assert.equal(pump.stats.sent + pump.stats.dropped, 100);
});
