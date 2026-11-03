// Which MediaPipe delegate tracks the hand, and when to give up on the GPU. Shared by Explore,
// the device check (tracker.ts) and, as a port, the Gate B touch-test page
// (spikes/tracking/lib/warmup.js, held to this file by spikes/tracking/test/parity.test.mjs).
//
// GPU is the first choice. A cold start on an iPhone (the model and wasm downloads, the GPU
// delegate's set-up, the first frames compiling shaders) can take many seconds, and must not
// count against the GPU: the fallback timer starts only once the GPU landmarker has finished
// initialising and a frame has been fed to it, whichever is later. If no result comes back
// within CPU_FALLBACK_MS of that, or the GPU delegate throws, the tracker drops it for CPU.
// CPU is never dropped. Times are milliseconds on any one clock.

export const CPU_FALLBACK_MS = 8000;
/** The window for frames a second. */
export const FPS_WINDOW_MS = 5000;

export type Delegate = "GPU" | "CPU";

export class Warmup {
  delegate: Delegate = "GPU";
  /** Why the GPU was dropped, or null while it is in use. */
  fellBack: string | null = null;
  private readyAt: number | null = null;
  private armedAt: number | null = null;
  private firstResultAt: number | null = null;
  private results: number[] = [];

  constructor(private readonly fallbackMs: number = CPU_FALLBACK_MS) {}

  /** The landmarker for the current delegate finished initialising. */
  ready(now: number): void {
    this.readyAt ??= now;
  }

  /** Frames go to the tracker only once it is ready. */
  get isReady(): boolean {
    return this.readyAt !== null;
  }

  /** A frame went to the tracker. The first one after ready starts the fallback timer. */
  fed(now: number): void {
    if (this.readyAt !== null) this.armedAt ??= now;
  }

  /** A result came back for a frame. */
  result(now: number): void {
    this.firstResultAt ??= now;
    this.results.push(now);
    while (this.results.length && (this.results[0] ?? now) < now - FPS_WINDOW_MS) this.results.shift();
  }

  /** True once a result has come back on the delegate in use. */
  get warm(): boolean {
    return this.firstResultAt !== null;
  }

  /** True when the GPU should be dropped for CPU now: armed, no result, past the timer. */
  timedOut(now: number): boolean {
    return (
      this.delegate === "GPU" &&
      this.firstResultAt === null &&
      this.armedAt !== null &&
      now - this.armedAt >= this.fallbackMs
    );
  }

  /** The delegate threw. True when that means dropping the GPU for CPU. */
  failed(): boolean {
    return this.delegate === "GPU";
  }

  /** Start over on CPU. */
  fallBack(reason: string): void {
    this.delegate = "CPU";
    this.fellBack = reason;
    this.readyAt = null;
    this.armedAt = null;
    this.firstResultAt = null;
    this.results = [];
  }

  /** From the first frame fed (once ready) to the first result, on the delegate in use. */
  get timeToFirstResultMs(): number | null {
    return this.armedAt !== null && this.firstResultAt !== null ? this.firstResultAt - this.armedAt : null;
  }

  /** Results a second over the last FPS_WINDOW_MS, or since the first result if sooner. */
  fps(now: number): number {
    const since = this.results.filter((t) => t >= now - FPS_WINDOW_MS);
    const first = since[0];
    if (first === undefined) return 0;
    const span = Math.min(FPS_WINDOW_MS, now - first);
    return span > 0 ? (since.length * 1000) / span : 0;
  }
}
