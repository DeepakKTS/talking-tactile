// The camera loop, outside React: getUserMedia, newest frame only to the hand worker, and
// each result handed on with the time it was captured and the time it came back.
import type { FromWorker, ToWorker, WorkerHand } from "../workers/protocol";
import { FramePump } from "./pump";
import { AskError, type AskReply, type AskRequest } from "./session";

export interface HandsFrame {
  hands: WorkerHand[];
  width: number;
  height: number;
  capturedAt: number;
  receivedAt: number;
  inferMs: number;
  /** 0 to 1, from the worker; 1 when not measured. */
  brightness: number;
}

export interface CameraLoopOptions {
  video: HTMLVideoElement;
  maxHands: number;
  onHands: (f: HandsFrame) => void;
  onStatus: (text: string) => void;
  stubMs?: number;
}

const MODEL_URL = "/models/hand_landmarker.task";

export class CameraLoop {
  private readonly worker: Worker;
  private readonly pump: FramePump<{ bitmap: ImageBitmap; id: number }>;
  private readonly capturedAt = new Map<number, number>();
  private frameId = 0;
  private running = false;
  backend = "loading";

  constructor(private readonly o: CameraLoopOptions) {
    this.worker = new Worker(new URL("../workers/hand.worker.ts", import.meta.url), { type: "module" });
    this.pump = new FramePump(({ bitmap, id }) => {
      const msg: ToWorker = { type: "frame", id, bitmap, ts: performance.now() };
      this.worker.postMessage(msg, [bitmap]);
    });
    this.worker.onmessage = (e: MessageEvent<FromWorker>) => {
      this.onWorker(e.data);
    };
    const init: ToWorker = { type: "init", modelUrl: MODEL_URL, maxHands: o.maxHands, ...(o.stubMs ? { stubMs: o.stubMs } : {}) };
    this.worker.postMessage(init);
  }

  get stats() {
    return this.pump.stats;
  }

  async start(deviceId?: string): Promise<void> {
    const v = this.o.video;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      // The rear camera on a phone, which looks down at the sheet; a laptop's one camera
      // ignores the ideal.
      video: {
        ...(deviceId ? { deviceId } : { facingMode: { ideal: "environment" } }),
        width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 },
      },
    });
    v.srcObject = stream;
    v.muted = true;
    await v.play();
    this.running = true;
    const tick = (now: number) => {
      if (!this.running) return;
      const id = ++this.frameId;
      this.capturedAt.set(id, now);
      this.pump
        .offer(async () => ({ bitmap: await createImageBitmap(v), id }))
        .then((sent) => {
          if (!sent) this.capturedAt.delete(id);
        })
        .catch(() => this.capturedAt.delete(id));
      v.requestVideoFrameCallback(tick);
    };
    v.requestVideoFrameCallback(tick);
  }

  stop(): void {
    this.running = false;
    const stream = this.o.video.srcObject;
    if (stream instanceof MediaStream) for (const t of stream.getTracks()) t.stop();
    this.worker.terminate();
  }

  private onWorker(msg: FromWorker): void {
    if (msg.type === "ready") {
      this.backend = msg.backend;
      this.o.onStatus(`Hand tracker ready: ${msg.backend}.`);
    } else if (msg.type === "error") {
      this.o.onStatus(`Hand tracker error: ${msg.message}`);
    } else {
      this.pump.done();
      const receivedAt = performance.now();
      const capturedAt = this.capturedAt.get(msg.id) ?? receivedAt;
      this.capturedAt.delete(msg.id);
      const v = this.o.video;
      this.o.onHands({ hands: msg.hands, width: v.videoWidth, height: v.videoHeight, capturedAt, receivedAt, inferMs: msg.inferMs, brightness: msg.brightness });
    }
  }
}

const NOT_WORKING = "Questions are not working right now. Labels still work.";

// A server error's message is written to be spoken (services/api/app/routes/ask.py).
async function spokenError(res: Response): Promise<AskError> {
  const body = (await res.json().catch(() => ({}))) as { error?: { message?: unknown } };
  const message = body.error?.message;
  return new AskError(res.status !== 404 && typeof message === "string" ? message : NOT_WORKING);
}

/** A held question: the WAV and the touch context, as multipart. */
export async function askAudioApi(wav: Uint8Array, req: AskRequest): Promise<AskReply> {
  if (!navigator.onLine) throw new TypeError("offline");
  const form = new FormData();
  form.append("request", JSON.stringify({ ...req, question: undefined }));
  form.append("audio", new Blob([new Uint8Array(wav)], { type: "audio/wav" }), "question.wav");
  const res = await fetch("/api/ask", { method: "POST", body: form });
  if (!res.ok) throw await spokenError(res);
  const body = (await res.json()) as Partial<AskReply>;
  if (typeof body.answer !== "string") throw new AskError(NOT_WORKING);
  return { answer: body.answer, transcript: body.transcript ?? "", timings_ms: body.timings_ms ?? {} };
}

export async function askApi(req: unknown): Promise<string> {
  if (!navigator.onLine) throw new TypeError("offline");
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw await spokenError(res);
  const body = (await res.json()) as { answer?: unknown };
  if (typeof body.answer !== "string") throw new AskError(NOT_WORKING);
  return body.answer;
}
