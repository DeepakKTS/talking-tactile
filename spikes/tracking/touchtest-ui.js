import { state, say } from "./main.js";
import { makeSequence, DwellDetector, errorStats, record } from "./lib/touchtest.js";

// Dwell values from config/explore.yaml; rearm distance keeps one rest from scoring twice.
const DWELL = { speedBelowMmS: 15, holdMs: 600, rearmMm: 15 };

const $ = (id) => document.getElementById(id);
const test = { active: false, seq: [], i: 0, records: [], seed: 0, startedAt: null };
state.touchTest = test;
const dwell = new DwellDetector(DWELL);

function speak(text) {
  say(text);
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function prompt() {
  const n = test.seq[test.i] + 1;
  $("target").textContent = String(n);
  speak(`Touch ${n}.`);
}

export function startTest() {
  if (!state.calib?.toMm) {
    say("Calibrate first. Press R.");
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
  test.records.push(
    record(target, targetMm, tip.mm, { rawMm: tip.raw, pointing: tip.pointing, how, at: Math.round(performance.now()) }),
  );
  test.i++;
  if (test.i < test.seq.length) prompt();
  else finish();
}

function finish() {
  test.active = false;
  $("target").textContent = "";
  const stats = errorStats(test.records);
  test.stats = stats;
  const result = {
    kind: "touch-test",
    startedAt: test.startedAt,
    finishedAt: new Date().toISOString(),
    seed: test.seed,
    backend: state.backend,
    videoSize: state.videoSize,
    contactOffsetMm: Number($("offset").value),
    corners: state.calib.corners,
    stats,
    records: test.records,
  };
  try {
    localStorage.setItem("tt-last-touch-test", JSON.stringify(result));
  } catch {}
  const blob = new Blob([JSON.stringify(result, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `touch-test-${result.finishedAt.replace(/[:.]/g, "-")}.json`;
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
document.addEventListener("keydown", (ev) => {
  if (ev.key === "t" || ev.key === "T") startTest();
  else if (ev.key === " " && test.active) {
    ev.preventDefault();
    capture("space");
  } else if (ev.key === "Escape" && "speechSynthesis" in window) speechSynthesis.cancel();
});
