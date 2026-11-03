// Hand tracking off the main thread (CLAUDE.md: never block the main thread with it).
// MediaPipe Hand Landmarker in VIDEO mode, on the delegate the page asks for: the page
// starts it on GPU and moves to CPU when the GPU gives no result (explore/warmup.ts,
// explore/tracker.ts). The wasm and the model are served by the app itself, not a CDN, so
// Explore keeps tracking offline.
// One frame at a time: the page sends the next only after this one's result.
import { HandLandmarker } from "@mediapipe/tasks-vision";
import wasmBinaryPath from "@mediapipe/tasks-vision/vision_wasm_module_internal.wasm?url";
import wasmLoaderPath from "@mediapipe/tasks-vision/vision_wasm_module_internal.js?url";
import type { FromWorker, ToWorker, WorkerHand } from "./protocol";

interface WorkerScope {
  postMessage(message: FromWorker): void;
  onmessage: ((e: MessageEvent<ToWorker>) => void) | null;
}
const scope = self as unknown as WorkerScope;

let landmarker: HandLandmarker | null = null;
let stubMs = 0;
let lastTs = -1;

async function init(msg: Extract<ToWorker, { type: "init" }>): Promise<void> {
  stubMs = msg.stubMs ?? 0;
  if (stubMs) {
    scope.postMessage({ type: "ready", backend: `stub ${stubMs} ms`, delegate: msg.delegate, loadMs: 0, errors: [] });
    return;
  }
  const t0 = performance.now();
  const delegate = msg.delegate;
  try {
    landmarker = await HandLandmarker.createFromOptions(
      { wasmLoaderPath, wasmBinaryPath },
      { baseOptions: { modelAssetPath: msg.modelUrl, delegate }, runningMode: "VIDEO", numHands: msg.maxHands },
    );
    scope.postMessage({ type: "ready", backend: `mediapipe ${delegate}`, delegate, loadMs: performance.now() - t0, errors: [] });
  } catch (err) {
    scope.postMessage({ type: "error", phase: "init", message: `${delegate}: ${err instanceof Error ? err.message : String(err)}` });
  }
}

const SAMPLE_W = 16;
const SAMPLE_H = 12;
let sampler: OffscreenCanvasRenderingContext2D | null = null;

// Mean luma of a tiny copy of the frame: cheap, and enough to tell a covered camera.
function brightness(bitmap: ImageBitmap): number {
  sampler ??= new OffscreenCanvas(SAMPLE_W, SAMPLE_H).getContext("2d", { willReadFrequently: true });
  if (!sampler) return 1;
  sampler.drawImage(bitmap, 0, 0, SAMPLE_W, SAMPLE_H);
  const d = sampler.getImageData(0, 0, SAMPLE_W, SAMPLE_H).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += 0.2126 * (d[i] ?? 0) + 0.7152 * (d[i + 1] ?? 0) + 0.0722 * (d[i + 2] ?? 0);
  return sum / (SAMPLE_W * SAMPLE_H * 255);
}

function detect(bitmap: ImageBitmap, ts: number): WorkerHand[] {
  if (!landmarker) return [];
  const t = Math.max(Math.round(ts), lastTs + 1); // VIDEO mode needs rising timestamps
  lastTs = t;
  const r = landmarker.detectForVideo(bitmap, t);
  return r.landmarks.map((lm, i) => {
    const cat = r.handedness[i]?.[0];
    const name = cat?.categoryName;
    return {
      landmarks: lm.map((p) => [p.x, p.y]),
      label: name === "Left" || name === "Right" ? name : null,
      score: cat?.score ?? null,
    };
  });
}

scope.onmessage = (e) => {
  const msg = e.data;
  if (msg.type === "init") {
    void init(msg);
    return;
  }
  const t0 = performance.now();
  let hands: WorkerHand[] = [];
  let light = 1;
  const finish = () => {
    msg.bitmap.close();
    scope.postMessage({ type: "result", id: msg.id, hands, inferMs: performance.now() - t0, brightness: light });
  };
  try {
    light = brightness(msg.bitmap);
    hands = detect(msg.bitmap, msg.ts);
  } catch (err) {
    scope.postMessage({ type: "error", phase: "detect", message: `detect: ${err instanceof Error ? err.message : String(err)}` });
  }
  if (stubMs) setTimeout(finish, stubMs);
  else finish();
};
