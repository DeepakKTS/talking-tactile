import { createFramePump } from "./lib/pump.js";
import { CPU_FALLBACK_MS, Warmup } from "./lib/warmup.js";
import { ScreenAwake } from "./lib/wakelock.js";

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const video = $("video");
const view = $("view");
const ctx = view.getContext("2d");

const RING = 120;
const state = {
  backend: null,
  camFrames: 0,
  results: 0,
  startedAt: 0,
  inferMs: [],
  loopMs: [],
  hands: [],
  frameId: 0,
  maxInFlight: 0,
  framesWithHands: 0,
  loadMs: null,
};
// Read by e2e_check.py.
window.__tt = state;

function push(arr, v) {
  arr.push(v);
  if (arr.length > RING) arr.shift();
}

function pct(arr, p) {
  if (!arr.length) return NaN;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.max(0, Math.ceil((p / 100) * s.length) - 1)];
}

export function say(text) {
  $("status").textContent = text;
}

const awake = new ScreenAwake((text) => {
  say(text);
  if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(text));
});

// ---------- worker ----------
// Made when the page loads, so the model and wasm download and the GPU initialises before
// Start camera is pressed. Frames go to it only once it is ready. GPU first; the CPU fallback
// is lib/warmup.js's, the port of the shipped rules (apps/web/src/explore/warmup.ts).

const warmup = new Warmup();
const sentAt = new Map();
let inFlight = 0;
let worker = makeWorker(params.get("delegate") || "GPU");
const pump = createFramePump(({ bitmap, id }) => {
  inFlight++;
  state.maxInFlight = Math.max(state.maxInFlight, inFlight);
  sentAt.set(id, performance.now());
  warmup.fed(performance.now());
  worker.postMessage({ type: "frame", bitmap, id, ts: Math.round(performance.now()) }, [bitmap]);
});
state.pump = pump.stats;
state.warmup = warmup;
if (params.get("delegate") === "CPU") warmup.fallBack("asked for CPU in the URL");

function makeWorker(delegate) {
  const w = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  w.onmessage = (e) => { if (w === worker) onWorker(e.data); };
  w.postMessage({ type: "init", stubMs: Number(params.get("stub") || 0), delegate });
  console.log(`hand tracker: starting ${delegate}`);
  return w;
}

function fallBack(reason) {
  worker.onmessage = null;
  worker.terminate();
  warmup.fallBack(reason);
  state.backend = null;
  // The frame in flight to the dropped worker will never come back.
  inFlight = 0;
  sentAt.clear();
  pump.done();
  console.log(`hand tracker: GPU dropped (${reason}); CPU from now`);
  say(`Hand tracker: ${reason}; using CPU.`);
  worker = makeWorker("CPU");
}

setInterval(() => {
  if (warmup.timedOut(performance.now())) fallBack(`no result from the GPU ${CPU_FALLBACK_MS / 1000} s after its first frame`);
}, 250);

function onWorker(msg) {
  if (msg.type === "ready") {
    warmup.ready(performance.now());
    state.backend = msg.backend;
    state.loadMs = msg.loadMs ?? null;
    state.backendErrors = msg.errors ?? [];
    console.log(`hand tracker: ${msg.backend} ready in ${Math.round(msg.loadMs ?? 0)} ms`);
    say(`Hand tracker ready: ${msg.backend}.`);
  } else if (msg.type === "log") {
    console.log(`worker: ${msg.text}`);
  } else if (msg.type === "error") {
    if (warmup.failed()) fallBack(`the GPU failed (${msg.message})`);
    else say(`Hand tracker error: ${msg.message}`);
  } else if (msg.type === "result") {
    inFlight--;
    pump.done();
    warmup.result(performance.now());
    state.results++;
    push(state.inferMs, msg.inferMs);
    const t = sentAt.get(msg.id);
    sentAt.delete(msg.id);
    if (t !== undefined) push(state.loopMs, performance.now() - t);
    state.hands = msg.hands;
    if (msg.hands.length) state.framesWithHands++;
    onHands(msg.hands);
  }
}

// Filled in by later steps: calibration, filtering and the touch test.
let onHands = () => {};
export function setHandsListener(fn) {
  onHands = fn;
}

// ---------- camera ----------

async function listCameras() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const sel = $("camera");
  sel.innerHTML = "";
  for (const d of devices.filter((d) => d.kind === "videoinput")) {
    const o = document.createElement("option");
    o.value = d.deviceId;
    o.textContent = d.label || `Camera ${sel.length + 1}`;
    sel.append(o);
  }
  // Keep the camera in use selected, so pressing Start again does not switch cameras.
  const live = video.srcObject?.getVideoTracks()[0]?.getSettings().deviceId;
  if (live) sel.value = live;
}

async function startCamera() {
  // First, before any await: Safari grants the Wake Lock only within the tap. Not awaited.
  awake.request();
  // A phone's default camera faces the user: ask for the rear one until a camera is picked.
  const deviceId = $("camera").value || undefined;
  const which = deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } };
  video.srcObject?.getTracks().forEach((t) => t.stop());
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { ...which, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
  });
  video.srcObject = stream;
  await video.play();
  view.width = video.videoWidth;
  view.height = video.videoHeight;
  state.startedAt = performance.now();
  state.camFrames = state.results = state.framesWithHands = 0; // rates since this Start
  state.videoSize = [video.videoWidth, video.videoHeight];
  await listCameras();
  $("calibrate").disabled = false;
  say(`Camera on at ${video.videoWidth} by ${video.videoHeight}.`);
  if (state.looping) return; // a second Start swaps the camera; the loops keep running
  state.looping = true;
  video.requestVideoFrameCallback(onVideoFrame);
  requestAnimationFrame(draw);
}

function onVideoFrame() {
  state.camFrames++;
  if (!warmup.isReady) {
    // Still warming up: no frame is fed, so none waits on a landmarker that is not there.
    video.requestVideoFrameCallback(onVideoFrame);
    return;
  }
  pump
    .offer(async () => ({ bitmap: await createImageBitmap(video), id: ++state.frameId }))
    .catch((err) => say(`Frame capture failed: ${err.message}`));
  video.requestVideoFrameCallback(onVideoFrame);
}

// ---------- drawing ----------

const overlays = [];
export function addOverlay(fn) {
  overlays.push(fn);
}

function draw() {
  ctx.drawImage(video, 0, 0, view.width, view.height);
  for (const hand of state.hands) {
    ctx.fillStyle = "#0c6";
    for (const p of hand.landmarks) {
      ctx.beginPath();
      ctx.arc(p.x * view.width, p.y * view.height, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  for (const fn of overlays) fn(ctx, view);
  drawStats();
  requestAnimationFrame(draw);
}

function drawStats() {
  const secs = (performance.now() - state.startedAt) / 1000;
  const s = pump.stats;
  state.camFps = state.camFrames / secs;
  state.procFps = state.results / secs;
  $("stats").textContent = [
    `backend ${state.backend ?? "loading"}${state.loadMs ? ` (loaded in ${Math.round(state.loadMs)} ms)` : ""}  video ${view.width}x${view.height}`,
    `delegate ${warmup.delegate}${warmup.fellBack ? ` (GPU dropped: ${warmup.fellBack})` : ""}  first result ${warmup.timeToFirstResultMs === null ? "not yet" : `${Math.round(warmup.timeToFirstResultMs)} ms after the first frame`}  ${warmup.fps(performance.now()).toFixed(1)} results a second`,
    `camera ${state.camFps.toFixed(1)} fps  processed ${state.procFps.toFixed(1)} fps  dropped ${s.dropped} of ${s.offered}  max in flight ${state.maxInFlight}`,
    `worker p50 ${pct(state.inferMs, 50).toFixed(1)} ms  p95 ${pct(state.inferMs, 95).toFixed(1)} ms`,
    `frame to result p50 ${pct(state.loopMs, 50).toFixed(1)} ms  p95 ${pct(state.loopMs, 95).toFixed(1)} ms`,
    `hands ${state.hands.length}  frames with hands ${state.framesWithHands} of ${state.results}`,
  ].join("\n");
}

// Pixel position on the video for a click on the scaled canvas.
export function clickToVideo(ev) {
  const r = view.getBoundingClientRect();
  return [((ev.clientX - r.left) / r.width) * view.width, ((ev.clientY - r.top) / r.height) * view.height];
}

$("start").addEventListener("click", () => startCamera().catch((err) => say(`Camera failed: ${err.message}`)));
listCameras().catch(() => {});

export { state, view, video };
