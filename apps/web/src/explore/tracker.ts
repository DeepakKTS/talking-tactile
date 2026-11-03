// The hand tracker the pages share: Explore, the device check, and (as a port, with the same
// Warmup rules) the Gate B touch-test page. Made when the page loads, so the model and the
// wasm download and the GPU delegate initialises before Start or Check is pressed; Start
// never triggers the download. Frames go to the worker only once it is ready. Delegate
// choice and fallback are Warmup's (warmup.ts): GPU first, CPU when the GPU gives no result
// in CPU_FALLBACK_MS from the first frame fed after it is ready, or throws.
import type { FromWorker, ToWorker } from "../workers/protocol";
import { CPU_FALLBACK_MS, type Delegate, Warmup } from "./warmup";

export const MODEL_URL = "/models/hand_landmarker.task";
const CHECK_EVERY_MS = 250;

type Result = Extract<FromWorker, { type: "result" }>;

/** What HandTracker needs from a Worker, so tests can give it a fake. */
export interface WorkerLike {
  postMessage(msg: ToWorker, transfer?: Transferable[]): void;
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null;
  terminate(): void;
}

export interface HandTrackerOptions {
  maxHands: number;
  onResult: (msg: Result) => void;
  onStatus: (text: string) => void;
  /** The frame in flight to a dropped worker will never come back. */
  onRestart?: () => void;
  stubMs?: number;
  makeWorker?: () => WorkerLike;
  now?: () => number;
  setInterval?: (fn: () => void, ms: number) => unknown;
  clearInterval?: (id: unknown) => void;
}

const browserWorker = (): WorkerLike => new Worker(new URL("../workers/hand.worker.ts", import.meta.url), { type: "module" });

export class HandTracker {
  readonly warmup = new Warmup();
  /** "loading" until a landmarker is ready, then "mediapipe GPU" or "mediapipe CPU". */
  backend = "loading";
  loadMs: number | null = null;
  private worker: WorkerLike;
  private readonly now: () => number;
  private readonly timer: unknown;
  private waiters: (() => void)[] = [];
  private stopped = false;

  constructor(private readonly o: HandTrackerOptions) {
    this.now = o.now ?? (() => performance.now());
    this.worker = this.start("GPU");
    const every = o.setInterval ?? ((fn, ms) => setInterval(fn, ms));
    this.timer = every(() => { this.check(); }, CHECK_EVERY_MS);
  }

  get delegate(): Delegate {
    return this.warmup.delegate;
  }

  get ready(): boolean {
    return this.warmup.isReady;
  }

  /** Why the GPU was dropped, or null while it is in use. */
  get fellBack(): string | null {
    return this.warmup.fellBack;
  }

  get timeToFirstResultMs(): number | null {
    return this.warmup.timeToFirstResultMs;
  }

  fps(): number {
    return this.warmup.fps(this.now());
  }

  /** Sends a frame if the tracker is ready; otherwise closes it and returns false. */
  feed(id: number, bitmap: ImageBitmap): boolean {
    if (this.stopped || !this.warmup.isReady) {
      bitmap.close();
      return false;
    }
    this.warmup.fed(this.now());
    const msg: ToWorker = { type: "frame", id, bitmap, ts: this.now() };
    this.worker.postMessage(msg, [bitmap]);
    return true;
  }

  /** Resolves at the first result on whichever delegate ends up in use, or after maxMs. */
  whenWarm(maxMs: number): Promise<boolean> {
    if (this.warmup.warm) return Promise.resolve(true);
    return new Promise((resolve) => {
      const t = setTimeout(() => { resolve(false); }, maxMs);
      this.waiters.push(() => { clearTimeout(t); resolve(true); });
    });
  }

  /** Checks the fallback timer; called every CHECK_EVERY_MS. */
  check(): void {
    if (!this.stopped && this.warmup.timedOut(this.now())) {
      this.fallBack(`no result from the GPU ${String(CPU_FALLBACK_MS / 1000)} s after its first frame`);
    }
  }

  stop(): void {
    this.stopped = true;
    (this.o.clearInterval ?? ((id) => { clearInterval(id as ReturnType<typeof setInterval>); }))(this.timer);
    this.worker.terminate();
  }

  private start(delegate: Delegate): WorkerLike {
    const w = (this.o.makeWorker ?? browserWorker)();
    w.onmessage = (e) => { this.onWorker(w, e.data); };
    const init: ToWorker = {
      type: "init", modelUrl: MODEL_URL, maxHands: this.o.maxHands, delegate,
      ...(this.o.stubMs ? { stubMs: this.o.stubMs } : {}),
    };
    w.postMessage(init);
    console.info(`hand tracker: starting ${delegate}`);
    return w;
  }

  private fallBack(reason: string): void {
    this.worker.onmessage = null;
    this.worker.terminate();
    this.warmup.fallBack(reason);
    this.backend = "loading";
    this.o.onStatus(`Hand tracker: ${reason}; using CPU.`);
    console.info(`hand tracker: GPU dropped (${reason}); CPU from now`);
    this.o.onRestart?.();
    this.worker = this.start("CPU");
  }

  private onWorker(from: WorkerLike, msg: FromWorker): void {
    if (from !== this.worker || this.stopped) return; // a dropped worker's late message
    if (msg.type === "ready") {
      this.warmup.ready(this.now());
      this.backend = msg.backend;
      this.loadMs = msg.loadMs;
      console.info(`hand tracker: ${msg.backend} ready in ${String(Math.round(msg.loadMs))} ms`);
      this.o.onStatus(`Hand tracker ready: ${msg.backend}.`);
    } else if (msg.type === "error") {
      if (this.warmup.failed()) this.fallBack(`the GPU failed (${msg.message})`);
      else this.o.onStatus(`Hand tracker error: ${msg.message}`);
    } else {
      this.warmup.result(this.now());
      for (const w of this.waiters.splice(0)) w();
      this.o.onResult(msg);
    }
  }
}
