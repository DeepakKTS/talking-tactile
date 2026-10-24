// Inputs for the spike vs shipped comparison (test/parity.test.mjs). Each case has its own
// seed, so adding a case never changes the others. Node and the generator that runs the
// shipped code (generate.port.ts) both build them here, so only outputs are stored.
import { createHash } from "node:crypto";

export const VIDEO = [1280, 720];

// Every shipped file the generator's results depend on, from the repo root. parity.test.mjs
// checks that this list covers their imports, and that none has changed since.
export const SHIPPED_SOURCES = [
  "apps/web/src/explore/fingertip.ts",
  "apps/web/src/explore/hands.ts",
  "apps/web/src/explore/homography.ts",
  "apps/web/src/explore/oneEuro.ts",
  "apps/web/src/shared/config.ts",
  "config/explore.yaml",
];
export const RUN_FRAMES = 150;
export const RUNS = 6;

function rng(name) {
  let s = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

// The sheet seen from above at an angle: a portrait rectangle, each corner moved up to 80 px.
function cameraQuad(rnd) {
  return [[440, 60], [840, 60], [840, 660], [440, 660]].map(([x, y]) => [x + (rnd() - 0.5) * 160, y + (rnd() - 0.5) * 160]);
}

function insideQuad(q, u, v) {
  const top = [q[0][0] + (q[1][0] - q[0][0]) * u, q[0][1] + (q[1][1] - q[0][1]) * u];
  const bot = [q[3][0] + (q[2][0] - q[3][0]) * u, q[3][1] + (q[2][1] - q[3][1]) * u];
  return [top[0] + (bot[0] - top[0]) * v, top[1] + (bot[1] - top[1]) * v];
}

// A hand drawn in pixels with its index fingertip at `at`. curled says which of middle,
// ring and pinky are curled; indexLen is the index finger's reach from the wrist line.
export function landmarksPx({ at: [x, y], curled = [true, true, true], indexLen = 270 }) {
  const lm = Array.from({ length: 21 }, () => [0, 0]);
  const base = y + indexLen;
  lm[0] = [x, base];
  [[5, 0, indexLen], [9, 24, curled[0] ? 75 : 270], [13, 48, curled[1] ? 75 : 270], [17, 72, curled[2] ? 75 : 270]]
    .forEach(([b, dx, len]) => {
      lm[b] = [x + dx, base - 90];
      lm[b + 1] = [x + dx, base - 120];
      lm[b + 2] = [x + dx, base - (120 + len) / 2];
      lm[b + 3] = [x + dx, base - len];
    });
  return lm;
}

// One pointing hand on a random walk with short dropouts. gaps: "none"; "skip", no frames at
// all for 400 ms, as when the camera or tab stalls; "empty", 400 ms of frames with no hand.
function oneHand(rnd, gaps, hand = {}) {
  let x = 600, y = 300, t = 0;
  const frames = [];
  for (let i = 0; i < RUN_FRAMES; i++) {
    t += 33.3 * (0.8 + rnd() * 0.4);
    if (rnd() < 0.3) { x += (rnd() - 0.5) * 30; y += (rnd() - 0.5) * 30; }
    const gone = rnd() < 0.03;
    frames.push({ t, hands: gone ? [] : [{ at: [x + rnd(), y + rnd()], label: "Left", ...hand }] });
    if (rnd() < 0.02) {
      if (gaps === "skip") t += 400;
      if (gaps === "empty") for (let j = 0; j < 12; j++) frames.push({ t: (t += 33.3), hands: [] });
    }
  }
  return frames;
}

// Two hands each frame, listed in a random order: `a` is the one that should be picked.
function twoHands(rnd, a, b) {
  const frames = [];
  let t = 0;
  for (let i = 0; i < RUN_FRAMES; i++) {
    t += 33.3;
    const ha = { at: [500 + rnd() * 4, 300 + rnd() * 4], label: "Left", ...a };
    const hb = { at: [800 + rnd() * 4, 350 + rnd() * 4], label: "Right", ...b };
    frames.push({ t, hands: rnd() < 0.5 ? [hb, ha] : [ha, hb] });
  }
  return frames;
}

const OPEN = { curled: [false, false, false] };
const TWO_CURLED = { curled: [false, true, true] };

export const PATH_CASES = {
  "one hand": (rnd) => oneHand(rnd, "none"),
  "one hand, frames stall for 400 ms": (rnd) => oneHand(rnd, "skip"),
  "one hand, lost for 400 ms": (rnd) => oneHand(rnd, "empty"),
  "a pointing hand and an open hand": (rnd) => twoHands(rnd, {}, OPEN),
  // Index and middle out, ring and pinky curled: not pointing with min_curled 3.
  "one hand, exactly 2 curled": (rnd) => oneHand(rnd, "none", TWO_CURLED),
  // The 2 curled hand reaches farther, so it wins on extension if it counts as pointing.
  "a pointing hand and a farther hand with exactly 2 curled": (rnd) => twoHands(rnd, {}, { ...TWO_CURLED, indexLen: 380 }),
};

export function makeInputs(cornersMm) {
  let rnd = rng("homography");
  const homography = Array.from({ length: 40 }, () => {
    const quad = cameraQuad(rnd);
    return { quad, points: Array.from({ length: 25 }, () => insideQuad(quad, rnd(), rnd())) };
  });
  rnd = rng("one euro");
  const euro = Array.from({ length: 20 }, () => {
    let x = 100, y = 100, t = 0;
    return Array.from({ length: 200 }, () => {
      x += (rnd() - 0.5) * 6; y += (rnd() - 0.5) * 6; t += (1 / 30) * (0.7 + rnd() * 0.6);
      return { p: [x + rnd(), y + rnd()], t, reset: rnd() < 0.01 };
    });
  });
  const paths = Object.fromEntries(Object.entries(PATH_CASES).map(([name, make]) => {
    rnd = rng(name);
    return [name, Array.from({ length: RUNS }, () => ({ quad: cameraQuad(rnd), frames: make(rnd) }))];
  }));
  return { cornersMm, video: VIDEO, homography, euro, paths };
}

export function digest(inputs) {
  return createHash("sha256").update(JSON.stringify(inputs)).digest("hex");
}
