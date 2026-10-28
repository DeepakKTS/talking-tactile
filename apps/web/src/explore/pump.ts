// Newest frame only (RULES 4.1): at most one frame in flight to the worker. A frame offered
// while the worker is busy is dropped, never queued.

export interface PumpStats {
  offered: number;
  sent: number;
  dropped: number;
  failed: number;
}

export class FramePump<F> {
  readonly stats: PumpStats = { offered: 0, sent: 0, dropped: 0, failed: 0 };
  private inFlight = false;

  constructor(private readonly send: (frame: F) => void) {}

  get busy(): boolean {
    return this.inFlight;
  }

  /** makeFrame may be async, as createImageBitmap is. The slot is taken before it runs,
   * so an offer during capture is dropped too. */
  async offer(makeFrame: () => F | Promise<F>): Promise<boolean> {
    this.stats.offered++;
    if (this.inFlight) {
      this.stats.dropped++;
      return false;
    }
    this.inFlight = true;
    try {
      this.send(await makeFrame());
      this.stats.sent++;
      return true;
    } catch (err) {
      this.inFlight = false;
      this.stats.failed++;
      throw err;
    }
  }

  /** The worker answered for the frame in flight. */
  done(): void {
    this.inFlight = false;
  }
}
