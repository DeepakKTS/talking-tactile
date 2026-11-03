// The port of apps/web/src/explore/warmup.ts, the shipped delegate policy, held to it by
// test/parity.test.mjs: GPU first; the CPU fallback timer starts at the later of the GPU
// landmarker being ready and the first frame fed; no result within CPU_FALLBACK_MS of that,
// or a GPU error, drops the GPU for CPU; CPU is never dropped.

export const CPU_FALLBACK_MS = 8000;
export const FPS_WINDOW_MS = 5000;

export class Warmup {
  constructor(fallbackMs = CPU_FALLBACK_MS) {
    this.fallbackMs = fallbackMs;
    this.delegate = "GPU";
    this.fellBack = null;
    this.readyAt = null;
    this.armedAt = null;
    this.firstResultAt = null;
    this.results = [];
  }

  ready(now) {
    this.readyAt ??= now;
  }

  get isReady() {
    return this.readyAt !== null;
  }

  fed(now) {
    if (this.readyAt !== null) this.armedAt ??= now;
  }

  result(now) {
    this.firstResultAt ??= now;
    this.results.push(now);
    while (this.results.length && this.results[0] < now - FPS_WINDOW_MS) this.results.shift();
  }

  get warm() {
    return this.firstResultAt !== null;
  }

  timedOut(now) {
    return this.delegate === "GPU" && this.firstResultAt === null && this.armedAt !== null && now - this.armedAt >= this.fallbackMs;
  }

  failed() {
    return this.delegate === "GPU";
  }

  fallBack(reason) {
    this.delegate = "CPU";
    this.fellBack = reason;
    this.readyAt = null;
    this.armedAt = null;
    this.firstResultAt = null;
    this.results = [];
  }

  get timeToFirstResultMs() {
    return this.armedAt !== null && this.firstResultAt !== null ? this.firstResultAt - this.armedAt : null;
  }

  fps(now) {
    const since = this.results.filter((t) => t >= now - FPS_WINDOW_MS);
    if (!since.length) return 0;
    const span = Math.min(FPS_WINDOW_MS, now - since[0]);
    return span > 0 ? (since.length * 1000) / span : 0;
  }
}
