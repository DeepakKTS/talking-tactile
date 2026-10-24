import { state, view, say, setHandsListener, addOverlay, clickToVideo } from "./main.js";
import { homographyFromPoints, applyHomography, isConvexQuad } from "./lib/homography.js";
import { FingertipMapper } from "./lib/fingertip.js";

const CORNER_NAMES = ["A, top left", "B, top right", "C, bottom right", "D, bottom left"];

const sheet = await (await fetch("./sheet.json")).json();
const params = new URLSearchParams(location.search);
const calib = { clicks: [], active: false, toMm: null, toPx: null };
const mapper = new FingertipMapper();

state.sheet = sheet;
state.calib = calib;
state.tip = null;

const storeKey = () => `tt-calib-${view.width}x${view.height}`;

function setCorners(px) {
  if (!isConvexQuad(px)) {
    say("Those corners cross over. Press R and click A, B, C, D in order around the sheet.");
    return false;
  }
  calib.toMm = homographyFromPoints(px, sheet.corners_mm);
  calib.toPx = homographyFromPoints(sheet.corners_mm, px);
  calib.corners = px;
  // What the touch-test JSON keeps: the clicks, the video size they were made at, the marks.
  calib.record = { cornersPx: px, videoSize: [view.width, view.height], cornersMm: sheet.corners_mm, at: new Date().toISOString() };
  mapper.setCalibration(calib.toMm);
  try {
    localStorage.setItem(storeKey(), JSON.stringify(px));
  } catch {}
  document.getElementById("test").disabled = false;
  say("Calibrated. Touch the sheet. Press T to start the touch test.");
  return true;
}

export function startCalibration() {
  calib.clicks = [];
  calib.active = true;
  say(`Click corner ${CORNER_NAMES[0]}.`);
}

view.addEventListener("click", (ev) => {
  if (!calib.active) return;
  calib.clicks.push(clickToVideo(ev));
  if (calib.clicks.length < 4) {
    say(`Click corner ${CORNER_NAMES[calib.clicks.length]}.`);
    return;
  }
  calib.active = false;
  setCorners(calib.clicks);
});

document.getElementById("calibrate").addEventListener("click", startCalibration);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "r" || ev.key === "R") startCalibration();
});

// Restore a saved calibration, or take ?corners=x1,y1,...,x4,y4 for headless checks.
export function restoreCalibration() {
  const q = params.get("corners");
  let px = null;
  if (q) {
    const n = q.split(",").map(Number);
    px = [0, 2, 4, 6].map((i) => [n[i], n[i + 1]]);
  } else {
    try {
      px = JSON.parse(localStorage.getItem(storeKey()) || "null");
    } catch {}
  }
  if (px) setCorners(px);
}
const waitForVideo = setInterval(() => {
  if (state.videoSize) {
    clearInterval(waitForVideo);
    restoreCalibration();
  }
}, 100);

// ---------- fingertip in sheet mm ----------

setHandsListener((hands) => {
  const now = performance.now();
  const px = hands.map((h) => h.landmarks.map((p) => [p.x * view.width, p.y * view.height]));
  const offset = Number(document.getElementById("offset").value) || 0;
  const tip = mapper.update(px, now, offset);
  if (calib.toMm) state.onFrame?.(tip, now);
  if (tip) state.tip = tip;
  else if (mapper.lost(now)) state.tip = null;
});

// ---------- drawing ----------

addOverlay((ctx) => {
  if (calib.active) {
    ctx.fillStyle = "#f0c";
    for (const [x, y] of calib.clicks) {
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (!calib.toPx) return;
  const P = (p) => applyHomography(calib.toPx, p);
  ctx.strokeStyle = "rgba(255, 0, 200, 0.8)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  sheet.corners_mm.forEach((c, i) => {
    const [x, y] = P(c);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.stroke();
  ctx.font = "bold 18px system-ui";
  sheet.targets_mm.forEach((t, i) => {
    const [x, y] = P(t);
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(255, 0, 200, 0.9)";
    ctx.fillText(String(i + 1), x + 10, y - 10);
  });
  if (state.tip) {
    const [x, y] = P(state.tip.mm);
    ctx.fillStyle = state.tip.pointing ? "#f22" : "#fa0";
    ctx.beginPath();
    ctx.arc(x, y, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.fillRect(8, 8, 330, 28);
    ctx.fillStyle = "#000";
    ctx.fillText(
      `finger ${state.tip.mm[0].toFixed(1)}, ${state.tip.mm[1].toFixed(1)} mm${state.tip.pointing ? "" : " (not pointing)"}`,
      14,
      28,
    );
  }
});
