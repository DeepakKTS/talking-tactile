import { test } from "node:test";
import assert from "node:assert/strict";
import { makeSequence, DwellDetector, percentile, errorStats, record } from "../lib/touchtest.js";

test("sequence has each target 5 times and no back to back repeats", () => {
  for (const seed of [1, 2, 3, 42, 2026]) {
    const seq = makeSequence(9, 5, seed);
    assert.equal(seq.length, 45);
    for (let t = 0; t < 9; t++) assert.equal(seq.filter((v) => v === t).length, 5);
    seq.forEach((v, i) => i && assert.notEqual(v, seq[i - 1]));
  }
});

test("sequence is reproducible from its seed", () => {
  assert.deepEqual(makeSequence(9, 5, 7), makeSequence(9, 5, 7));
  assert.notDeepEqual(makeSequence(9, 5, 7), makeSequence(9, 5, 8));
});

const dwellParams = { speedBelowMmS: 15, holdMs: 600, rearmMm: 15 };

test("dwell fires once after 600 ms below 15 mm/s", () => {
  const d = new DwellDetector(dwellParams);
  const fired = [];
  for (let t = 0; t <= 1500; t += 33) if (d.update([50 + (t % 2) * 0.1, 50], t)) fired.push(t);
  assert.equal(fired.length, 1);
  assert.ok(fired[0] >= 600 && fired[0] < 700, `fired at ${fired[0]}`);
});

test("dwell does not fire while the finger keeps moving", () => {
  const d = new DwellDetector(dwellParams);
  for (let t = 0; t <= 3000; t += 33) assert.equal(d.update([t * 0.03, 50], t), false); // 30 mm/s
});

test("dwell re-arms only after moving away", () => {
  const d = new DwellDetector(dwellParams);
  let t = 0;
  let fires = 0;
  const hold = (x, ms) => {
    for (const end = t + ms; t <= end; t += 33) if (d.update([x, 50], t)) fires++;
  };
  hold(50, 1000);
  hold(55, 1000); // 5 mm drift, still the same touch
  assert.equal(fires, 1);
  hold(80, 1000); // moved 30 mm to the next target
  assert.equal(fires, 2);
});

test("percentile is nearest rank", () => {
  const v = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  assert.equal(percentile(v, 50), 5);
  assert.equal(percentile(v, 95), 10);
  assert.equal(percentile([3], 95), 3);
});

test("error stats: mean, p95, bias and per target", () => {
  const recs = [
    record(0, [10, 10], [13, 14]), // 5 mm
    record(0, [10, 10], [10, 11]), // 1 mm
    record(1, [50, 10], [53, 10]), // 3 mm
  ];
  const s = errorStats(recs);
  assert.equal(s.n, 3);
  assert.equal(s.meanMm, 3);
  assert.equal(s.p95Mm, 5);
  assert.equal(s.maxMm, 5);
  assert.deepEqual(s.biasMm, [2, 1.67]);
  assert.deepEqual(s.perTargetMeanMm, { 1: 3, 2: 3 });
});
