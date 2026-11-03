import { describe, expect, it } from "vitest";
import type { FromWorker, ToWorker } from "../workers/protocol";
import { HandTracker, type WorkerLike } from "./tracker";
import { CPU_FALLBACK_MS } from "./warmup";

class FakeWorker implements WorkerLike {
  sent: ToWorker[] = [];
  terminated = false;
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null = null;
  postMessage(msg: ToWorker): void {
    this.sent.push(msg);
  }
  terminate(): void {
    this.terminated = true;
  }
  say(msg: FromWorker): void {
    this.onmessage?.({ data: msg } as MessageEvent<FromWorker>);
  }
  get delegate(): string | undefined {
    const init = this.sent.find((m) => m.type === "init");
    return init?.type === "init" ? init.delegate : undefined;
  }
}

const ready = (delegate: "GPU" | "CPU"): FromWorker => ({ type: "ready", backend: `mediapipe ${delegate}`, delegate, loadMs: 1, errors: [] });
const result = (id: number): FromWorker => ({ type: "result", id, hands: [], inferMs: 20, brightness: 1 });
const bitmap = () => {
  const b = { closed: false, close() { b.closed = true; } };
  return b;
};

function rig() {
  let now = 0;
  let tick: () => void = () => undefined;
  const workers: FakeWorker[] = [];
  const status: string[] = [];
  let restarts = 0;
  let results = 0;
  const t = new HandTracker({
    maxHands: 2,
    onResult: () => { results += 1; },
    onStatus: (s) => { status.push(s); },
    onRestart: () => { restarts += 1; },
    makeWorker: () => { const w = new FakeWorker(); workers.push(w); return w; },
    now: () => now,
    setInterval: (fn) => { tick = fn; return 1; },
    clearInterval: () => undefined,
  });
  // Moves the clock in 250 ms steps, checking the fallback timer each step, as the page does.
  const advance = (to: number) => {
    while (now < to) {
      now = Math.min(to, now + 250);
      tick();
    }
  };
  return { t, workers, status, advance, at: () => now, restarts: () => restarts, results: () => results };
}

describe("hand tracker: GPU first, CPU fallback", () => {
  it("starts the GPU as soon as it is made, before any Start", () => {
    const { workers } = rig();
    expect(workers).toHaveLength(1);
    expect(workers[0]?.delegate).toBe("GPU");
  });

  it("a GPU landmarker that never returns is dropped for CPU 8 s after its first frame", () => {
    const r = rig();
    const gpu = r.workers[0];
    gpu?.say(ready("GPU"));
    r.advance(1000);
    expect(r.t.feed(1, bitmap() as unknown as ImageBitmap)).toBe(true); // the first frame
    r.advance(1000 + CPU_FALLBACK_MS - 250);
    expect(r.workers).toHaveLength(1);
    r.advance(1000 + CPU_FALLBACK_MS);
    expect(gpu?.terminated).toBe(true);
    expect(r.workers[1]?.delegate).toBe("CPU");
    expect(r.restarts()).toBe(1);
    expect(r.t.delegate).toBe("CPU");
    expect(r.status.at(-1)).toBe("Hand tracker: no result from the GPU 8 s after its first frame; using CPU.");
    gpu?.say(result(1)); // a late answer from the dropped worker is ignored
    expect(r.results()).toBe(0);
    const cpu = r.workers[1];
    cpu?.say(ready("CPU"));
    r.t.feed(2, bitmap() as unknown as ImageBitmap);
    r.advance(r.at() + 400);
    cpu?.say(result(2));
    expect(r.results()).toBe(1);
    expect(r.t.timeToFirstResultMs).toBe(400);
    r.advance(r.at() + 10 * CPU_FALLBACK_MS);
    expect(r.workers).toHaveLength(2); // CPU is never dropped
  });

  it("a cold start with a 10 s model load does not trigger the CPU fallback", () => {
    const r = rig();
    const gpu = r.workers[0];
    const early = bitmap();
    expect(r.t.feed(1, early as unknown as ImageBitmap)).toBe(false); // not ready: not fed
    expect(early.closed).toBe(true);
    r.advance(10000); // model, wasm and GPU set-up
    expect(r.workers).toHaveLength(1);
    gpu?.say(ready("GPU"));
    r.t.feed(2, bitmap() as unknown as ImageBitmap);
    r.advance(10000 + 1500); // the first GPU frame is slow too
    gpu?.say(result(2));
    r.advance(30000);
    expect(r.workers).toHaveLength(1);
    expect([r.t.delegate, r.t.timeToFirstResultMs, r.t.backend]).toEqual(["GPU", 1500, "mediapipe GPU"]);
  });

  it("a GPU that throws goes to CPU at once", () => {
    const r = rig();
    r.workers[0]?.say({ type: "error", phase: "init", message: "GPU: WebGL not available" });
    expect(r.workers[1]?.delegate).toBe("CPU");
    expect(r.t.fellBack).toBe("the GPU failed (GPU: WebGL not available)");
  });

  it("whenWarm resolves at the first result, after a fallback too", async () => {
    const r = rig();
    const warm = r.t.whenWarm(60000);
    r.workers[0]?.say(ready("GPU"));
    r.t.feed(1, bitmap() as unknown as ImageBitmap);
    r.advance(CPU_FALLBACK_MS);
    r.workers[1]?.say(ready("CPU"));
    r.t.feed(2, bitmap() as unknown as ImageBitmap);
    r.workers[1]?.say(result(2));
    expect(await warm).toBe(true);
  });
});
