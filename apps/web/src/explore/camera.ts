// The camera loop, outside React: getUserMedia, newest frame only to the page's hand tracker
// (tracker.ts), and each result handed on with the time it was captured and the time it came
// back.
import type { FromWorker, WorkerHand } from "../workers/protocol";
import { CameraWatch, type LockResult, type OpenedCamera, cameraKey, lockCamera, openCamera } from "./cameraPick";
import { FramePump } from "./pump";
import { ASK_TIMEOUT_MS, AskError, type AskReply, type AskRequest, type Heard, TOO_LONG } from "./session";
import type { HandTracker } from "./tracker";

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
  /** Made when the page loaded (tracker.ts), so Start never waits for the model download. */
  tracker: HandTracker;
  onHands: (f: HandsFrame) => void;
  /** The video's size, device or zoom changed since the corners were set (cameraPick.ts). */
  onCameraChange?: (changes: string[]) => void;
}

/** How often the camera is compared with the one the corners were set on. */
const WATCH_MS = 500;

type Result = Extract<FromWorker, { type: "result" }>;

export class CameraLoop {
  private readonly pump: FramePump<{ bitmap: ImageBitmap; id: number }>;
  private readonly capturedAt = new Map<number, number>();
  private frameId = 0;
  private running = false;
  private readonly watch = new CameraWatch();
  private watchedAt = 0;
  /** Which camera opened and how it was chosen. */
  opened: OpenedCamera | null = null;
  /** Zoom and focus, fixed when the camera offers them; settles FOCUS_SETTLE_MS after start. */
  lock: Promise<LockResult> | null = null;

  constructor(private readonly o: CameraLoopOptions) {
    this.pump = new FramePump(({ bitmap, id }) => {
      if (!o.tracker.feed(id, bitmap)) this.pump.done(); // not ready: the frame is dropped
    });
  }

  get backend(): string {
    return this.o.tracker.backend;
  }

  get stats() {
    return this.pump.stats;
  }

  async start(deviceId?: string): Promise<void> {
    const v = this.o.video;
    // The rear camera on a phone, which looks down at the sheet, its single wide lens when
    // listed (cameraPick.ts); a laptop's one camera ignores the ideal.
    this.opened = await openCamera(navigator.mediaDevices, { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } }, deviceId);
    const stream = this.opened.stream;
    v.srcObject = stream;
    v.muted = true;
    await v.play();
    this.running = true;
    const track = stream.getVideoTracks()[0];
    this.lock = track ? lockCamera(track) : null;
    void this.lock?.then(() => { this.rebaseWatch(); });
    const tick = (now: number) => {
      if (!this.running) return;
      v.requestVideoFrameCallback(tick);
      if (now - this.watchedAt >= WATCH_MS) {
        this.watchedAt = now;
        if (this.watch.check(this.key())) this.o.onCameraChange?.(this.watch.changed);
      }
      if (!this.o.tracker.ready) return; // still warming up: no frame is fed, none is lost
      const id = ++this.frameId;
      this.capturedAt.set(id, now);
      this.pump
        .offer(async () => ({ bitmap: await createImageBitmap(v), id }))
        .then((sent) => {
          if (!sent) this.capturedAt.delete(id);
        })
        .catch(() => this.capturedAt.delete(id));
    };
    v.requestVideoFrameCallback(tick);
  }

  private key() {
    const track = this.o.video.srcObject instanceof MediaStream ? this.o.video.srcObject.getVideoTracks()[0] : undefined;
    return cameraKey((track?.getSettings() ?? null) as Record<string, unknown> | null, this.o.video.videoWidth, this.o.video.videoHeight);
  }

  /** The corners were set on the camera as it is now. */
  rebaseWatch(): void {
    this.watch.rebase(this.key());
  }

  /** Stops the camera. The tracker is the page's, and keeps running. */
  stop(): void {
    this.running = false;
    const stream = this.o.video.srcObject;
    if (stream instanceof MediaStream) for (const t of stream.getTracks()) t.stop();
  }

  /** A result from the tracker, for the frame in flight. */
  result(msg: Result): void {
    this.pump.done();
    const receivedAt = performance.now();
    const capturedAt = this.capturedAt.get(msg.id) ?? receivedAt;
    this.capturedAt.delete(msg.id);
    const v = this.o.video;
    this.o.onHands({ hands: msg.hands, width: v.videoWidth, height: v.videoHeight, capturedAt, receivedAt, inferMs: msg.inferMs, brightness: msg.brightness });
  }

  /** The tracker dropped a worker (GPU to CPU) with a frame in flight that will not return. */
  restart(): void {
    this.pump.done();
    this.capturedAt.clear();
  }
}

const NOT_WORKING = "Questions are not working right now. Labels still work.";

// The ask route's own errors carry a sentence written to be spoken
// (services/api/app/routes/ask.py). Any other error (a 500, a 503 naming a server setting, a
// proxy's page) is said as NOT_WORKING.
const SPOKEN_CODES = new Set(["invalid_request", "audio_invalid", "question_cap", "answer_failed", "rate_limited"]);

async function spokenError(res: Response): Promise<AskError> {
  const body = (await res.json().catch(() => ({}))) as { error?: { code?: unknown; message?: unknown } };
  const { code, message } = body.error ?? {};
  const spoken = typeof code === "string" && SPOKEN_CODES.has(code) && typeof message === "string";
  return new AskError(spoken ? message : NOT_WORKING);
}

async function post(path: string, init: RequestInit, timeoutMs: number): Promise<Record<string, unknown>> {
  if (!navigator.onLine) throw new TypeError("offline");
  try {
    const res = await fetch(path, { ...init, signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) throw await spokenError(res);
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") throw new AskError(TOO_LONG);
    if (err instanceof SyntaxError) throw new AskError(NOT_WORKING); // a 200 that is not JSON
    throw err;
  }
}

/** A held question's words (POST /api/transcribe): the WAV and the touch context, as
 * multipart. The session parses them on the device before asking (session.ts). */
export async function transcribeApi(wav: Uint8Array, req: AskRequest, timeoutMs = ASK_TIMEOUT_MS): Promise<Heard> {
  const form = new FormData();
  form.append("request", JSON.stringify({ ...req, question: undefined }));
  form.append("audio", new Blob([new Uint8Array(wav)], { type: "audio/wav" }), "question.wav");
  const body = (await post("/api/transcribe", { method: "POST", body: form }, timeoutMs)) as Partial<Heard>;
  if (typeof body.transcript !== "string") throw new AskError(NOT_WORKING);
  return { transcript: body.transcript, timings_ms: body.timings_ms ?? {} };
}

/** A question as text, with the server's times. */
export async function askReplyApi(req: AskRequest, timeoutMs = ASK_TIMEOUT_MS): Promise<AskReply> {
  const body = (await post(
    "/api/ask",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) },
    timeoutMs,
  )) as Partial<AskReply>;
  if (typeof body.answer !== "string") throw new AskError(NOT_WORKING);
  return { answer: body.answer, transcript: body.transcript ?? "", timings_ms: body.timings_ms ?? {} };
}

export async function askApi(req: AskRequest, timeoutMs = ASK_TIMEOUT_MS): Promise<string> {
  return (await askReplyApi(req, timeoutMs)).answer;
}
