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

// The ask route's own errors carry a sentence written to be spoken
// (services/api/app/routes/ask.py). Any other error (a 500, a 503 naming a server setting, a
// proxy's page) is said as NOT_WORKING.
const SPOKEN_CODES = new Set(["invalid_request", "audio_invalid", "question_cap", "answer_failed"]);

async function spokenError(res: Response): Promise<AskError> {
  const body = (await res.json().catch(() => ({}))) as { error?: { code?: unknown; message?: unknown } };
  const { code, message } = body.error ?? {};
  const spoken = typeof code === "string" && SPOKEN_CODES.has(code) && typeof message === "string";
  return new AskError(spoken ? message : NOT_WORKING);
}

/** The server stops a question at 30 s and says so (services/api/app/ask.py DEADLINE_S), so
 * its sentence normally arrives first; 5 s more covers the phone's network. This is for a
 * server or network that never answers: the student hears that questions are not working and
 * the next hold works. The thinking tone plays all the while. */
export const ASK_TIMEOUT_MS = 35000;

async function postAsk(init: RequestInit, timeoutMs: number): Promise<Record<string, unknown>> {
  if (!navigator.onLine) throw new TypeError("offline");
  try {
    const res = await fetch("/api/ask", { ...init, signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) throw await spokenError(res);
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") throw new AskError(NOT_WORKING);
    if (err instanceof SyntaxError) throw new AskError(NOT_WORKING); // a 200 that is not JSON
    throw err;
  }
}

/** A held question: the WAV and the touch context, as multipart. */
export async function askAudioApi(wav: Uint8Array, req: AskRequest, timeoutMs = ASK_TIMEOUT_MS): Promise<AskReply> {
  const form = new FormData();
  form.append("request", JSON.stringify({ ...req, question: undefined }));
  form.append("audio", new Blob([new Uint8Array(wav)], { type: "audio/wav" }), "question.wav");
  const body = (await postAsk({ method: "POST", body: form }, timeoutMs)) as Partial<AskReply>;
  if (typeof body.answer !== "string") throw new AskError(NOT_WORKING);
  return { answer: body.answer, transcript: body.transcript ?? "", timings_ms: body.timings_ms ?? {} };
}

export async function askApi(req: unknown, timeoutMs = ASK_TIMEOUT_MS): Promise<string> {
  const body = await postAsk(
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) },
    timeoutMs,
  );
  if (typeof body.answer !== "string") throw new AskError(NOT_WORKING);
  return body.answer;
}
