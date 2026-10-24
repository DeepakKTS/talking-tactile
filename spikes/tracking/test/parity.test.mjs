// The spike against the shipped tracking code (apps/web/src/explore on early-start), on the
// same inputs. main has no apps/web, so the shipped code's outputs are stored in
// parity/port_outputs.json by parity/generate.port.ts; see parity/vitest.config.mjs to
// remake it. Gate B runs on the spike, so it measures the shipped math only while this passes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applyHomography, homographyFromPoints } from "../lib/homography.js";
import { OneEuroFilter2D } from "../lib/oneeuro.js";
import { FingertipMapper, TRACKING } from "../lib/fingertip.js";
import { PATH_CASES, VIDEO, digest, landmarksPx, makeInputs } from "./parity/inputs.mjs";

const sheet = JSON.parse(readFileSync(new URL("../sheet.json", import.meta.url)));
const port = JSON.parse(readFileSync(new URL("./parity/port_outputs.json", import.meta.url)));
const inputs = makeInputs(sheet.corners_mm);
const TOL_MM = 1e-6;
const gap = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const euroParams = ({ mincutoff_hz, beta, dcutoff_hz }) => ({ mincutoffHz: mincutoff_hz, beta, dcutoffHz: dcutoff_hz });

test("the stored outputs were made from these inputs and every case", () => {
  assert.equal(port.inputsSha256, digest(inputs), "inputs.mjs changed: remake port_outputs.json");
  assert.deepEqual(Object.keys(port.paths), Object.keys(PATH_CASES));
  assert.equal(port.port.dirty, false, "made from uncommitted shipped code");
});

test("the spike's constants match the shipped explore.yaml", () => {
  const c = port.config;
  assert.deepEqual(TRACKING.filter, euroParams(c.one_euro));
  assert.equal(TRACKING.lostResetMs, c.lost_reset_ms);
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.equal(Number(/id="offset"[^>]*value="([\d.]+)"/.exec(html)?.[1]), c.contact_offset_mm);
});

test("homography: the same mm for the same clicks", (t) => {
  let worst = 0;
  inputs.homography.forEach(({ quad, points }, k) => {
    const toMm = homographyFromPoints(quad, sheet.corners_mm);
    points.forEach((p, i) => { worst = Math.max(worst, gap(applyHomography(toMm, p), port.homography[k][i])); });
  });
  t.diagnostic(`worst ${worst} mm`);
  assert.ok(worst < TOL_MM, `worst ${worst} mm`);
});

test("1 euro filter: the same output for the same samples, with resets", (tc) => {
  let worst = 0;
  inputs.euro.forEach((samples, k) => {
    const f = new OneEuroFilter2D(euroParams(port.config.one_euro));
    samples.forEach(({ p, t, reset }, i) => {
      if (reset) f.reset();
      worst = Math.max(worst, gap(f.filter(p, t), port.euro[k][i]));
    });
  });
  tc.diagnostic(`worst ${worst} mm`);
  assert.ok(worst < TOL_MM, `worst ${worst} mm`);
});

// The whole path, worker landmarks to the filtered contact point, frame by frame.
function comparePath(name) {
  const [W, H] = VIDEO;
  let worst = 0, frames = 0, presence = 0, pointing = 0;
  inputs.paths[name].forEach(({ quad, frames: fs }, k) => {
    const mapper = new FingertipMapper({ filter: euroParams(port.config.one_euro), lostResetMs: port.config.lost_reset_ms });
    mapper.setCalibration(homographyFromPoints(quad, sheet.corners_mm));
    fs.forEach(({ t, hands }, i) => {
      // The page's listener gets normalized landmarks and scales them by the video size.
      const px = hands.map((h) => landmarksPx(h).map(([x, y]) => [(x / W) * W, (y / H) * H]));
      const got = mapper.update(px, t, port.config.contact_offset_mm);
      const want = port.paths[name][k][i];
      if ((got === null) !== (want === null)) { presence++; return; }
      if (!got) return;
      frames++;
      worst = Math.max(worst, gap(got.mm, want));
      if (got.pointing !== want[2]) pointing++;
    });
  });
  return { worst, frames, presence, pointing };
}

for (const name of Object.keys(PATH_CASES)) {
  test(`whole path, ${name}: the same contact point every frame`, (t) => {
    const r = comparePath(name);
    t.diagnostic(`worst ${r.worst} mm over ${r.frames} frames`);
    assert.ok(r.frames > 500, `only ${r.frames} frames compared`);
    assert.equal(r.presence, 0, "a frame had a point in one and none in the other");
    assert.equal(r.pointing, 0, "frames where one called the hand pointing and the other did not");
    assert.ok(r.worst < TOL_MM, `worst ${r.worst} mm`);
  });
}
