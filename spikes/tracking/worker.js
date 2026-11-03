// Hand tracking worker. Receives one ImageBitmap at a time, returns landmarks only (no pixels).
// MediaPipe Hand Landmarker, VIDEO mode, up to 2 hands, on the delegate the page asks for: the
// page starts it on GPU and moves to CPU when the GPU gives no result (lib/warmup.js).
// ?stub=<ms> in the page URL replaces the model with a fixed delay, for testing the frame loop.

const MP_VERSION = "1.1.0";
const MP_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VERSION}`;
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

let stubMs = 0;
let landmarker = null;
let lastTs = -1;

function log(text) {
  self.postMessage({ type: "log", text });
}

async function createLandmarker(delegate) {
  log(`${delegate}: importing vision_bundle.mjs`);
  const { FilesetResolver, HandLandmarker } = await import(`${MP_BASE}/vision_bundle.mjs`);
  log(`${delegate}: resolving wasm fileset`);
  // useModule: a module worker has no importScripts, so load the ES module build of the wasm loader.
  const fileset = await FilesetResolver.forVisionTasks(`${MP_BASE}/wasm`, true);
  log(`${delegate}: creating HandLandmarker`);
  return HandLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: "VIDEO",
    numHands: 2,
  });
}

async function init(msg) {
  stubMs = msg.stubMs || 0;
  if (stubMs) {
    self.postMessage({ type: "ready", backend: `stub ${stubMs} ms`, delegate: msg.delegate || "GPU" });
    return;
  }
  const t0 = performance.now();
  const delegate = msg.delegate || "GPU";
  try {
    landmarker = await createLandmarker(delegate);
    self.postMessage({ type: "ready", backend: `mediapipe ${MP_VERSION} ${delegate}`, delegate, loadMs: performance.now() - t0, errors: [] });
  } catch (err) {
    self.postMessage({ type: "error", phase: "init", message: `${delegate}: ${err?.message ?? err}` });
  }
}

function detect(msg) {
  // VIDEO mode needs strictly increasing timestamps.
  const ts = Math.max(msg.ts, lastTs + 1);
  lastTs = ts;
  const r = landmarker.detectForVideo(msg.bitmap, ts);
  return r.landmarks.map((lm, i) => ({
    landmarks: lm.map((p) => ({ x: p.x, y: p.y, z: p.z })),
    handedness: r.handedness[i]?.[0]?.categoryName ?? null,
    score: r.handedness[i]?.[0]?.score ?? null,
  }));
}

self.onmessage = async (e) => {
  const msg = e.data;
  if (msg.type === "init") {
    await init(msg);
    return;
  }
  if (msg.type !== "frame") return;
  const t0 = performance.now();
  let hands = [];
  try {
    if (stubMs) await new Promise((r) => setTimeout(r, stubMs));
    else if (landmarker) hands = detect(msg);
  } catch (err) {
    self.postMessage({ type: "error", phase: "detect", message: `detect: ${err?.message ?? err}` });
  } finally {
    msg.bitmap.close();
  }
  self.postMessage({ type: "result", id: msg.id, hands, inferMs: performance.now() - t0 });
};
