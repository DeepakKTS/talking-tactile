// Explore's measured latencies (RULES 4). Each is a ring of recent samples in ms with p50
// and p95. The page puts them on window.__tt so a headless run can read them.

const RING = 500;

export class Samples {
  private readonly values: number[] = [];

  push(v: number): void {
    if (!Number.isFinite(v)) return;
    this.values.push(v);
    if (this.values.length > RING) this.values.shift();
  }

  get count(): number {
    return this.values.length;
  }

  get p50(): number {
    return this.pct(50);
  }

  get p95(): number {
    return this.pct(95);
  }

  pct(p: number): number {
    if (!this.values.length) return NaN;
    const s = [...this.values].sort((a, b) => a - b);
    return s[Math.max(0, Math.ceil((p / 100) * s.length) - 1)] ?? NaN;
  }

  summary(): { count: number; p50: number; p95: number } {
    return { count: this.count, p50: this.p50, p95: this.p95 };
  }
}

export class Metrics {
  /** Camera frame captured to its landmarks back on the main thread. */
  readonly captureToLandmarksMs = new Samples();
  /** Landmarks of the frame that fires an earcon, to the earcon starting. Code only. */
  readonly frameToEarconMs = new Samples();
  /** First frame inside a part's shrunk outline to its earcon: enter_hold_ms plus code. */
  readonly enterToEarconMs = new Samples();
  /** Touch to earcon as the student hears it: capture to landmarks plus enter to earcon. */
  readonly touchToEarconMs = new Samples();
  /** Dwell met to the label being handed to speech. */
  readonly dwellToLabelMs = new Samples();

  summary(): Record<string, { count: number; p50: number; p95: number }> {
    return {
      captureToLandmarksMs: this.captureToLandmarksMs.summary(),
      frameToEarconMs: this.frameToEarconMs.summary(),
      enterToEarconMs: this.enterToEarconMs.summary(),
      touchToEarconMs: this.touchToEarconMs.summary(),
      dwellToLabelMs: this.dwellToLabelMs.summary(),
    };
  }
}
