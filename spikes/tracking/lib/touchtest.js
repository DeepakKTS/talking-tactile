// Touch test logic: target order, dwell capture and error statistics.

// Each target `perTarget` times, shuffled with a seeded generator, with no
// target twice in a row (a repeat would let a resting finger score for free).
export function makeSequence(nTargets, perTarget, seed = 1) {
  let s = seed >>> 0 || 1;
  const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  for (let attempt = 0; attempt < 1000; attempt++) {
    const seq = [];
    for (let t = 0; t < nTargets; t++) for (let k = 0; k < perTarget; k++) seq.push(t);
    for (let i = seq.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [seq[i], seq[j]] = [seq[j], seq[i]];
    }
    if (seq.every((v, i) => i === 0 || v !== seq[i - 1])) return seq;
  }
  throw new Error("could not build a sequence without repeats");
}

// Fires once when the point stays slower than speedBelowMmS for holdMs
// (config/explore.yaml dwell). After firing it re-arms only when the point
// has moved rearmMm away from where it fired.
export class DwellDetector {
  constructor({ speedBelowMmS, holdMs, rearmMm }) {
    this.speedBelowMmS = speedBelowMmS;
    this.holdMs = holdMs;
    this.rearmMm = rearmMm;
    this.reset();
  }

  reset() {
    this.prev = null;
    this.slowSince = null;
    this.firedAt = null;
  }

  update([x, y], tMs) {
    if (this.firedAt && Math.hypot(x - this.firedAt[0], y - this.firedAt[1]) >= this.rearmMm) this.firedAt = null;
    let fired = false;
    if (this.prev) {
      const dt = (tMs - this.prev.t) / 1000;
      const speed = dt > 0 ? Math.hypot(x - this.prev.x, y - this.prev.y) / dt : 0;
      if (speed < this.speedBelowMmS) {
        this.slowSince ??= this.prev.t;
        if (!this.firedAt && tMs - this.slowSince >= this.holdMs) {
          this.firedAt = [x, y];
          fired = true;
        }
      } else {
        this.slowSince = null;
      }
    }
    this.prev = { x, y, t: tMs };
    return fired;
  }
}

// Nearest-rank percentile, matching spikes/meta_common.py.
export function percentile(values, p) {
  if (!values.length) return NaN;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.max(1, Math.ceil((p / 100) * s.length)) - 1];
}

export function errorStats(records) {
  const e = records.map((r) => r.errorMm);
  const mean = e.reduce((s, v) => s + v, 0) / (e.length || 1);
  const byTarget = {};
  for (const r of records) (byTarget[r.target + 1] ??= []).push(r.errorMm);
  const perTarget = Object.fromEntries(
    Object.entries(byTarget).map(([k, v]) => [k, +(v.reduce((s, x) => s + x, 0) / v.length).toFixed(2)]),
  );
  const bias = [0, 1].map((axis) => records.reduce((s, r) => s + (r.measuredMm[axis] - r.targetMm[axis]), 0) / (records.length || 1));
  return {
    n: e.length,
    meanMm: +mean.toFixed(2),
    p95Mm: +percentile(e, 95).toFixed(2),
    maxMm: +Math.max(...e).toFixed(2),
    biasMm: bias.map((b) => +b.toFixed(2)),
    perTargetMeanMm: perTarget,
  };
}

// Every frame while one target is up, from its prompt to its capture, so a session can be
// replayed: the index tip and DIP landmarks in video pixels, the contact point before the
// filter (rawMm) and after it (mm), all in sheet mm. A frame with no hand is { t, lost }.
// Only the newest `limit` frames are kept; framesDropped counts the rest.
export const FRAMES_PER_TOUCH = 600; // 20 s at 30 fps
const r3 = (p) => p.map((v) => Math.round(v * 1000) / 1000);

export class TouchWindow {
  constructor(limit = FRAMES_PER_TOUCH) {
    this.limit = limit;
    this.start(0);
  }

  start(tMs) {
    this.fromMs = Math.round(tMs);
    this.frames = [];
    this.dropped = 0;
  }

  add(tip, tMs) {
    const t = Math.round(tMs);
    this.frames.push(tip
      ? { t, tipPx: r3(tip.tipPx), dipPx: r3(tip.dipPx), rawMm: r3(tip.raw), mm: r3(tip.mm), pointing: tip.pointing }
      : { t, lost: true });
    if (this.frames.length > this.limit) {
      this.frames.shift();
      this.dropped++;
    }
  }

  take() {
    return { windowFromMs: this.fromMs, frames: this.frames, framesDropped: this.dropped };
  }
}

// The JSON the page offers when a test ends. Fields only ever get added, so
// analyze_touch.py keeps working: version 2 added calibration and each record's frames.
export function sessionResult({ startedAt, finishedAt, seed, backend, videoSize, contactOffsetMm, corners, calibration, records }) {
  return {
    kind: "touch-test",
    startedAt,
    finishedAt,
    seed,
    backend,
    videoSize,
    contactOffsetMm,
    corners,
    stats: errorStats(records),
    records,
    version: 2,
    calibration,
    framesPerTouchLimit: FRAMES_PER_TOUCH,
  };
}

export const sessionFilename = (result) => `touch-test-${result.finishedAt.replace(/[:.]/g, "-")}.json`;
export const serializeSession = (result) => JSON.stringify(result, null, 1);

export function readSession(text) {
  const s = JSON.parse(text);
  if (s.kind !== "touch-test" || !Array.isArray(s.records)) throw new Error("not a touch-test session");
  return s;
}

export function record(target, targetMm, measuredMm, extra = {}) {
  return {
    target,
    targetMm,
    measuredMm,
    errorMm: Math.hypot(measuredMm[0] - targetMm[0], measuredMm[1] - targetMm[1]),
    ...extra,
  };
}
