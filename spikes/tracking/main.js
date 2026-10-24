import { createFramePump } from "./lib/pump.js";

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

// ---------- worker ----------

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
const sentAt = new Map();
let inFlight = 0;
const pump = createFramePump(({ bitmap, id }) => {
  inFlight++;
  state.maxInFlight = Math.max(state.maxInFlight, inFlight);
  sentAt.set(id, performance.now());
  worker.postMessage({ type: "frame", bitmap, id, ts: Math.round(performance.now()) }, [bitmap]);
});
state.pump = pump.stats;

worker.onmessage = (e) => {
  const msg = e.data;
  if (msg.type === "ready") {
    state.backend = msg.backend;
    say(`Hand tracker ready: ${msg.backend}.`);
  } else if (msg.type === "error") {
    say(`Hand tracker error: ${msg.message}`);
  } else if (msg.type === "result") {
    inFlight--;
    pump.done();
    state.results++;
    push(state.inferMs, msg.inferMs);
    const t = sentAt.get(msg.id);
    sentAt.delete(msg.id);
    if (t !== undefined) push(state.loopMs, performance.now() - t);
    state.hands = msg.hands;
    onHands(msg.hands);
  }
};
worker.postMessage({ type: "init", stubMs: Number(params.get("stub") || 0) });

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
}

async function startCamera() {
  const deviceId = $("camera").value || undefined;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { deviceId, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
  });
  video.srcObject = stream;
  await video.play();
  view.width = video.videoWidth;
  view.height = video.videoHeight;
  state.startedAt = performance.now();
  state.videoSize = [video.videoWidth, video.videoHeight];
  await listCameras();
  $("calibrate").disabled = false;
  say(`Camera on at ${video.videoWidth} by ${video.videoHeight}.`);
  video.requestVideoFrameCallback(onVideoFrame);
  requestAnimationFrame(draw);
}

function onVideoFrame() {
  state.camFrames++;
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
    `backend ${state.backend ?? "loading"}  video ${view.width}x${view.height}`,
    `camera ${state.camFps.toFixed(1)} fps  processed ${state.procFps.toFixed(1)} fps  dropped ${s.dropped} of ${s.offered}  max in flight ${state.maxInFlight}`,
    `worker p50 ${pct(state.inferMs, 50).toFixed(1)} ms  p95 ${pct(state.inferMs, 95).toFixed(1)} ms`,
    `frame to result p50 ${pct(state.loopMs, 50).toFixed(1)} ms  p95 ${pct(state.loopMs, 95).toFixed(1)} ms`,
    `hands ${state.hands.length}`,
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
