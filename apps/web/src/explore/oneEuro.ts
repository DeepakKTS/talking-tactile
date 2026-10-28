// 1 euro filter (Casiez, Roussel and Vogel, CHI 2012): little smoothing lag on fast moves,
// strong smoothing of jitter at rest. One filter per axis. Parameters come from
// explore.yaml fingertip.one_euro.
import type { ExploreConfig } from "../shared/config";
import type { Pt } from "./homography";

export interface OneEuroParams {
  minCutoffHz: number;
  beta: number;
  dCutoffHz: number;
}

export function oneEuroParams(c: ExploreConfig["fingertip"]["one_euro"]): OneEuroParams {
  return { minCutoffHz: c.mincutoff_hz, beta: c.beta, dCutoffHz: c.dcutoff_hz };
}

// Smoothing factor of an exponential filter with this cutoff, for a step of dt seconds.
function smoothing(cutoffHz: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * cutoffHz);
  return 1 / (1 + tau / dt);
}

export class OneEuroFilter {
  private value: number | null = null;
  private speed = 0;
  private lastT = 0;

  constructor(private readonly p: OneEuroParams) {}

  reset(): void {
    this.value = null;
    this.speed = 0;
  }

  /** The filtered value at time t, in seconds. A time at or before the last one changes
   * nothing. */
  filter(x: number, t: number): number {
    if (this.value === null) {
      this.value = x;
      this.lastT = t;
      return x;
    }
    const dt = t - this.lastT;
    if (dt <= 0) return this.value;
    this.lastT = t;
    this.speed += smoothing(this.p.dCutoffHz, dt) * ((x - this.value) / dt - this.speed);
    const cutoff = this.p.minCutoffHz + this.p.beta * Math.abs(this.speed);
    this.value += smoothing(cutoff, dt) * (x - this.value);
    return this.value;
  }
}

export class OneEuroFilter2D {
  private readonly x: OneEuroFilter;
  private readonly y: OneEuroFilter;

  constructor(p: OneEuroParams) {
    this.x = new OneEuroFilter(p);
    this.y = new OneEuroFilter(p);
  }

  reset(): void {
    this.x.reset();
    this.y.reset();
  }

  filter(p: Pt, t: number): Pt {
    return [this.x.filter(p[0], t), this.y.filter(p[1], t)];
  }
}
