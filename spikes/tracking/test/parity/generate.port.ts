// @ts-nocheck
// Writes what the shipped tracking code (apps/web/src/explore, early-start) gives for the
// inputs in inputs.mjs, so test/parity.test.mjs on main can hold the spike to it. Run it
// with vitest.config.mjs after any change to the port or to the inputs.
import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { it } from "vitest";
import { EXPLORE } from "@port/shared/config";
import { applyHomography, homographyFromPoints } from "@port/explore/homography";
import { OneEuroFilter2D, oneEuroParams } from "@port/explore/oneEuro";
import { FingertipTracker } from "@port/explore/fingertip";
import sheet from "@spike/sheet.json";
import { VIDEO, digest, landmarksPx, makeInputs } from "./inputs.mjs";

it("writes the shipped code's outputs", () => {
  const inputs = makeInputs(sheet.corners_mm);
  const [W, H] = VIDEO;
  const homography = inputs.homography.map(({ quad, points }) => {
    const toMm = homographyFromPoints(quad, sheet.corners_mm);
    return points.map((p) => applyHomography(toMm, p));
  });
  const euro = inputs.euro.map((samples) => {
    const f = new OneEuroFilter2D(oneEuroParams(EXPLORE.fingertip.one_euro));
    return samples.map(({ p, t, reset }) => {
      if (reset) f.reset();
      return f.filter(p, t);
    });
  });
  const paths = Object.fromEntries(Object.entries(inputs.paths).map(([name, runs]) => [name, runs.map(({ quad, frames }) => {
    const tracker = new FingertipTracker(EXPLORE, { dominant: "either", cameraMirrored: false });
    tracker.setCalibration(homographyFromPoints(quad, sheet.corners_mm));
    return frames.map(({ t, hands }) => {
      const worker = hands.map((h) => ({ landmarks: landmarksPx(h).map(([x, y]) => [x / W, y / H]), label: h.label, score: 0.9 }));
      const out = tracker.update(worker, W, H, t);
      return out.p ? [out.p[0], out.p[1], out.pointing] : null;
    });
  })]));
  const git = (cmd: string) => execSync(`git ${cmd}`, { cwd: process.cwd() }).toString().trim();
  const fx = EXPLORE.fingertip;
  writeFileSync(new URL("./port_outputs.json", import.meta.url), `${JSON.stringify({
    note: "Outputs of the shipped tracking code for the inputs in inputs.mjs. Made by generate.port.ts; do not edit.",
    port: { branch: git("rev-parse --abbrev-ref HEAD"), commit: git("rev-parse --short HEAD"), dirty: git("status --porcelain -- src") !== "" },
    config: { one_euro: fx.one_euro, contact_offset_mm: fx.contact_offset_mm, lost_reset_ms: fx.lost_reset_ms, min_curled: EXPLORE.hands.min_curled },
    inputsSha256: digest(inputs),
    homography,
    euro,
    paths,
  })}\n`);
});
