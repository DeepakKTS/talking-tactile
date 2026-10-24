// The touch-test JSON, version 2: a session is built through the page's own path (the
// mapper and the touch window), written to a file, read back, and analyzed by the
// unchanged analyze_touch.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { applyHomography, homographyFromPoints } from "../lib/homography.js";
import { FingertipMapper, contactPoint } from "../lib/fingertip.js";
import { TouchWindow, readSession, record, serializeSession, sessionFilename, sessionResult } from "../lib/touchtest.js";
import { landmarksPx } from "./parity/inputs.mjs";

const sheet = JSON.parse(readFileSync(new URL("../sheet.json", import.meta.url)));
const VIDEO = [1280, 720];
const CORNERS = [[452, 41], [861, 77], [830, 690], [415, 652]];
const OFFSET = 4;
const OLD_RECORD_KEYS = ["target", "targetMm", "measuredMm", "errorMm", "rawMm", "pointing", "how", "at"];
const OLD_TOP_KEYS = ["kind", "startedAt", "finishedAt", "seed", "backend", "videoSize", "contactOffsetMm", "corners", "stats", "records"];

// Three touches the way the page records them: prompt, frames (one with the hand lost),
// then a capture of the newest point.
function session() {
  const toMm = homographyFromPoints(CORNERS, sheet.corners_mm);
  const toPx = homographyFromPoints(sheet.corners_mm, CORNERS);
  const mapper = new FingertipMapper();
  mapper.setCalibration(toMm);
  const win = new TouchWindow();
  const records = [];
  let t = 1000;
  for (const target of [4, 0, 8]) {
    win.start(t);
    const [tx, ty] = applyHomography(toPx, sheet.targets_mm[target]);
    let tip = null;
    for (let i = 0; i < 40; i++) {
      t += 33;
      const hands = i === 5 ? [] : [landmarksPx({ at: [tx + Math.sin(i) * 2, ty - 12 + Math.cos(i)] })];
      const got = mapper.update(hands, t, OFFSET);
      win.add(got, t);
      if (got) tip = got;
    }
    records.push(record(target, sheet.targets_mm[target], tip.mm, {
      rawMm: tip.raw, pointing: tip.pointing, how: "dwell", at: t, dwellFromMs: t - 600, ...win.take(),
    }));
    t += 500;
  }
  return sessionResult({
    startedAt: "2026-10-25T14:00:00.000Z",
    finishedAt: "2026-10-25T14:03:22.123Z",
    seed: 42,
    backend: "mediapipe GPU",
    videoSize: VIDEO,
    contactOffsetMm: OFFSET,
    corners: CORNERS,
    calibration: { cornersPx: CORNERS, videoSize: VIDEO, cornersMm: sheet.corners_mm, at: "2026-10-25T13:58:00.000Z" },
    records,
  });
}

function writeAndRead(result) {
  const dir = mkdtempSync(join(tmpdir(), "tt-session-"));
  const file = join(dir, sessionFilename(result));
  writeFileSync(file, serializeSession(result));
  return { file, back: readSession(readFileSync(file, "utf8")) };
}

test("a session with calibration and per-frame data reads back unchanged", () => {
  const result = session();
  const { file, back } = writeAndRead(result);
  assert.deepEqual(back, JSON.parse(JSON.stringify(result)));
  assert.match(file, /touch-test-2026-10-25T14-03-22-123Z\.json$/);
  for (const k of OLD_TOP_KEYS) assert.ok(k in back, `lost ${k}`);
  assert.deepEqual(back.calibration.cornersPx, back.corners);
  assert.deepEqual(back.calibration.videoSize, VIDEO);
  assert.equal(back.version, 2);
  for (const r of back.records) {
    for (const k of OLD_RECORD_KEYS) assert.ok(k in r, `lost record.${k}`);
    assert.equal(r.frames.length, 40);
    assert.equal(r.framesDropped, 0);
    assert.equal(r.frames.filter((f) => f.lost).length, 1);
    const last = r.frames.at(-1);
    assert.ok(Math.hypot(last.mm[0] - r.measuredMm[0], last.mm[1] - r.measuredMm[1]) < 0.002, "last frame is the capture");
  }
});

test("each frame's unfiltered point can be recomputed from its landmarks and the calibration", () => {
  const { back } = writeAndRead(session());
  const toMm = homographyFromPoints(back.calibration.cornersPx, back.calibration.cornersMm);
  let worst = 0, n = 0;
  for (const r of back.records) {
    for (const f of r.frames.filter((x) => !x.lost)) {
      const raw = contactPoint(applyHomography(toMm, f.tipPx), applyHomography(toMm, f.dipPx), back.contactOffsetMm);
      worst = Math.max(worst, Math.hypot(raw[0] - f.rawMm[0], raw[1] - f.rawMm[1]));
      n++;
    }
  }
  assert.equal(n, 117);
  assert.ok(worst < 0.01, `worst ${worst} mm`); // values are stored to 0.001
});

test("a long wait on one target keeps only the newest frames and counts the rest", () => {
  const win = new TouchWindow(5);
  win.start(0);
  for (let i = 0; i < 8; i++) win.add(null, i * 33);
  const w = win.take();
  assert.deepEqual([w.frames.length, w.framesDropped, w.frames[0].t], [5, 3, 99]);
});

test("analyze_touch.py reads a version 2 session as before", () => {
  const { file, back } = writeAndRead(session());
  const py = spawnSync("python3", [new URL("../analyze_touch.py", import.meta.url).pathname, file], { encoding: "utf8" });
  assert.equal(py.status, 0, py.stderr);
  const out = JSON.parse(py.stdout);
  assert.equal(out.n, 3);
  assert.equal(out.mean_mm, back.stats.meanMm);
  assert.deepEqual(out.video_size, VIDEO);
});
