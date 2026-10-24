// 1 euro filter (Casiez, Roussel and Vogel, CHI 2012). Smooths jitter at low
// speed and follows fast moves with little lag. Parameters come from
// config/explore.yaml (fingertip.one_euro): mincutoff_hz, beta, dcutoff_hz.

function alpha(cutoffHz, dtS) {
  const tau = 1 / (2 * Math.PI * cutoffHz);
  return 1 / (1 + tau / dtS);
}

export class OneEuroFilter {
  constructor({ mincutoffHz, beta, dcutoffHz }) {
    this.mincutoffHz = mincutoffHz;
    this.beta = beta;
    this.dcutoffHz = dcutoffHz;
    this.reset();
  }

  reset() {
    this.x = null;
    this.dx = 0;
    this.tS = null;
  }

  filter(value, tS) {
    if (this.x === null) {
      this.x = value;
      this.tS = tS;
      return value;
    }
    const dt = tS - this.tS;
    if (dt <= 0) return this.x;
    this.tS = tS;
    const rawDx = (value - this.x) / dt;
    this.dx += alpha(this.dcutoffHz, dt) * (rawDx - this.dx);
    const cutoff = this.mincutoffHz + this.beta * Math.abs(this.dx);
    this.x += alpha(cutoff, dt) * (value - this.x);
    return this.x;
  }
}

// One filter per axis, as PLAN.md section 5.1 describes.
export class OneEuroFilter2D {
  constructor(params) {
    this.fx = new OneEuroFilter(params);
    this.fy = new OneEuroFilter(params);
  }

  reset() {
    this.fx.reset();
    this.fy.reset();
  }

  filter([x, y], tS) {
    return [this.fx.filter(x, tS), this.fy.filter(y, tS)];
  }
}
