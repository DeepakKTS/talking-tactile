// The spike against the shipped tracking code (apps/web/src/explore on early-start), on the
// same inputs. main has no apps/web, so the shipped code's outputs are stored in
// parity/port_outputs.json by parity/generate.port.ts; see parity/vitest.config.mjs to
// remake it. Gate B runs on the spike, so it measures the shipped math only while this passes.
// The outputs record a sha256 of each shipped file they came from, and the first test fails
// when any of those files has changed, so they cannot go stale without notice.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { applyHomography, homographyFromPoints } from "../lib/homography.js";
import { OneEuroFilter2D } from "../lib/oneeuro.js";
import { FingertipMapper, TRACKING } from "../lib/fingertip.js";
import { PATH_CASES, SHIPPED_SOURCES, VIDEO, digest, landmarksPx, makeInputs } from "./parity/inputs.mjs";

const sheet = JSON.parse(readFileSync(new URL("../sheet.json", import.meta.url)));
const port = JSON.parse(readFileSync(new URL("./parity/port_outputs.json", import.meta.url)));
const inputs = makeInputs(sheet.corners_mm);
const TOL_MM = 1e-6;
const gap = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const euroParams = ({ mincutoff_hz, beta, dcutoff_hz }) => ({ mincutoffHz: mincutoff_hz, beta, dcutoffHz: dcutoff_hz });

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const BRANCHES = ["early-start", "origin/early-start"];
const REMAKE = "cd .worktrees/early-start/apps/web && npx vitest run --config ../../../../spikes/tracking/test/parity/vitest.config.mjs";

// The shipped file: from this checkout once apps/web is here (after a merge), else from the
// early-start branch.
function shipped(path) {
  if (existsSync(join(ROOT, "apps/web"))) return { from: "this checkout", text: readFileSync(join(ROOT, path)) };
  for (const ref of BRANCHES) {
    try {
      const text = execFileSync("git", ["show", `${ref}:${path}`], { cwd: ROOT, stdio: ["ignore", "pipe", "ignore"] });
      const commit = execFileSync("git", ["rev-parse", "--short", ref], { cwd: ROOT }).toString().trim();
      return { from: `${ref} at ${commit}`, text };
    } catch {
      // try the next ref
    }
  }
  throw new Error(`Cannot read ${path}: no apps/web here and no ${BRANCHES.join(" or ")} branch. Fetch early-start.`);
}

test("the shipped tracking files are the ones the stored outputs were made from", () => {
  assert.deepEqual(Object.keys(port.port.sources ?? {}), SHIPPED_SOURCES, `port_outputs.json does not list the shipped files. Remake it: ${REMAKE}`);
  const stale = [];
  let from = "";
  for (const path of SHIPPED_SOURCES) {
    const file = shipped(path);
    from = file.from;
    const sha = createHash("sha256").update(file.text).digest("hex");
    if (sha !== port.port.sources[path]) stale.push(path);
  }
  assert.deepEqual(stale, [], `port_outputs.json is stale: ${stale.join(", ")} on ${from} changed since the outputs were made from early-start ${port.port.commit}. Remake them: ${REMAKE}`);
});

test("the list of shipped files covers everything they import", () => {
  const listed = new Set(SHIPPED_SOURCES);
  const missing = [];
  for (const path of SHIPPED_SOURCES.filter((p) => p.endsWith(".ts"))) {
    const text = shipped(path).text.toString();
    // Value imports only: a type import has no effect on the outputs.
    for (const [, spec] of text.matchAll(/^import\s+(?!type\s)[^;]*?\sfrom\s+"(\.[^"]+)"/gm)) {
      let dep = normalize(join(dirname(path), spec));
      if (!/\.\w+$/.test(dep)) dep += ".ts";
      if (!listed.has(dep)) missing.push(`${path} imports ${dep}`);
    }
  }
  assert.deepEqual(missing, [], "add these to SHIPPED_SOURCES in parity/inputs.mjs, then remake the outputs");
});

test("the stored outputs were made from these inputs and every case", () => {
  assert.equal(port.inputsSha256, digest(inputs), "inputs.mjs changed: remake port_outputs.json");
  assert.deepEqual(Object.keys(port.paths), Object.keys(PATH_CASES));
  assert.equal(port.port.dirty, false, "made from uncommitted shipped code");
});

test("the spike's constants match the shipped explore.yaml", () => {
  const c = port.config;
  assert.deepEqual(TRACKING.filter, euroParams(c.one_euro));
  assert.equal(TRACKING.lostResetMs, c.lost_reset_ms);
  assert.equal(TRACKING.minCurled, c.min_curled);
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
