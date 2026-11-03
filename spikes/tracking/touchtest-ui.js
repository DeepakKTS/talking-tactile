import { state, say } from "./main.js";
import { makeSequence, DwellDetector, TouchWindow, record, serializeSession, sessionFilename, sessionResult } from "./lib/touchtest.js";
import { touchOnly } from "./lib/device.js";

// A phone: every key has a button (Record now for Space, Stop speech for Escape), and the
// buttons drop their key hints.
const TOUCH = touchOnly();

// Dwell values from config/explore.yaml; rearm distance keeps one rest from scoring twice.
const DWELL = { speedBelowMmS: 15, holdMs: 600, rearmMm: 15 };

const $ = (id) => document.getElementById(id);
const test = { active: false, seq: [], i: 0, records: [], seed: 0, startedAt: null };
state.touchTest = test;
const dwell = new DwellDetector(DWELL);
const touchWindow = new TouchWindow();
state.onFrame = (tip, t) => {
  if (test.active) touchWindow.add(tip, t);
};

function speak(text) {
  say(text);
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function prompt() {
  const n = test.seq[test.i] + 1;
  $("target").textContent = String(n);
  touchWindow.start(performance.now());
  speak(`Touch ${n}.`);
}

export function startTest() {
  if (!state.calib?.toMm) {
    say(TOUCH ? "Calibrate first: tap Calibrate." : "Calibrate first. Press R.");
    return;
  }
  const sheet = state.sheet;
  test.seed = Number(new URLSearchParams(location.search).get("seed")) || Math.floor(Math.random() * 1e9);
  test.seq = makeSequence(sheet.targets_mm.length, sheet.touches_per_target, test.seed);
  test.i = 0;
  test.records = [];
  test.active = true;
  test.startedAt = new Date().toISOString();
  dwell.reset();
  $("results").textContent = "";
  $("record").disabled = false;
  prompt();
}

function capture(how) {
  const tip = state.tip;
  if (!tip) {
    speak("No finger seen. Try again.");
    return;
  }
  const target = test.seq[test.i];
  const targetMm = state.sheet.targets_mm[target];
  const dwellFromMs = how === "dwell" && dwell.slowSince !== null ? Math.round(dwell.slowSince) : null;
  test.records.push(
    record(target, targetMm, tip.mm, {
      rawMm: tip.raw, pointing: tip.pointing, how, at: Math.round(performance.now()),
      dwellFromMs, ...touchWindow.take(),
    }),
  );
  test.i++;
  if (test.i < test.seq.length) prompt();
  else finish();
}

function finish() {
  test.active = false;
  document.getElementById("record").disabled = true;
  $("target").textContent = "";
  const result = sessionResult({
    startedAt: test.startedAt,
    finishedAt: new Date().toISOString(),
    seed: test.seed,
    backend: state.backend,
    videoSize: state.videoSize,
    contactOffsetMm: Number($("offset").value),
    corners: state.calib.corners,
    calibration: state.calib.record,
    records: test.records,
  });
  const stats = result.stats;
  test.stats = stats;
  try {
    localStorage.setItem("tt-last-touch-test", JSON.stringify(result));
  } catch {}
  const blob = new Blob([serializeSession(result)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = sessionFilename(result);
  a.textContent = "Download the raw results (JSON)";
  $("results").textContent = [
    `Touches ${stats.n}. Mean error ${stats.meanMm} mm. p95 ${stats.p95Mm} mm. Max ${stats.maxMm} mm.`,
    `Bias x ${stats.biasMm[0]} mm, y ${stats.biasMm[1]} mm (positive x is right, positive y is down).`,
    `Per target mean mm: ${JSON.stringify(stats.perTargetMeanMm)}`,
    "",
    "Tracker commands:",
    `python scripts/tracker.py metric touch-mean ${stats.meanMm} --source live`,
    `python scripts/tracker.py metric touch-p95 ${stats.p95Mm} --source live`,
    "",
  ].join("\n");
  $("results").append(a);
  speak(`Done. Mean error ${stats.meanMm} millimeters. p95 ${stats.p95Mm}.`);
}

// Dwell capture runs on every new fingertip estimate.
const tick = () => {
  if (test.active && state.tip && state.tip.t !== tick.lastT) {
    tick.lastT = state.tip.t;
    if (dwell.update(state.tip.mm, state.tip.t)) capture("dwell");
  }
  requestAnimationFrame(tick);
};
requestAnimationFrame(tick);

$("test").addEventListener("click", startTest);
$("record").addEventListener("click", () => { if (test.active) capture("button"); });
$("hush").addEventListener("click", () => { if ("speechSynthesis" in window) speechSynthesis.cancel(); });
if (TOUCH) {
  $("calibrate").textContent = "Calibrate";
  $("test").textContent = "Touch test";
  $("keys").hidden = true;
}
document.addEventListener("keydown", (ev) => {
  if (ev.key === "t" || ev.key === "T") startTest();
  else if (ev.key === " " && test.active) {
    ev.preventDefault();
    capture("space");
  } else if (ev.key === "Escape" && "speechSynthesis" in window) speechSynthesis.cancel();
});
