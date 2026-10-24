// Pick the pointing hand and find the contact point under the index finger.
// Landmark indices follow MediaPipe Hands: 0 wrist; index 5 MCP, 6 PIP, 7 DIP, 8 tip;
// middle 10 PIP, 12 tip; ring 14 PIP, 16 tip; pinky 18 PIP, 20 tip.
import { applyHomography } from "./homography.js";
import { OneEuroFilter2D } from "./oneeuro.js";

// Starting values from config/explore.yaml: fingertip.one_euro, fingertip.lost_reset_ms.
export const TRACKING = {
  filter: { mincutoffHz: 1.0, beta: 0.007, dcutoffHz: 1.0 },
  lostResetMs: 300,
};

const WRIST = 0;
const INDEX = { pip: 6, dip: 7, tip: 8 };
const OTHERS = [
  { pip: 10, tip: 12 },
  { pip: 14, tip: 16 },
  { pip: 18, tip: 20 },
];

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// A finger is extended when its tip is farther from the wrist than its PIP joint.
function extension(pts, finger) {
  return dist(pts[WRIST], pts[finger.tip]) / Math.max(1e-9, dist(pts[WRIST], pts[finger.pip]));
}

// hands: arrays of 21 [x, y] points in pixels (not normalized, so aspect ratio is right).
// Returns { index, pointing } for the best hand, or null when there are no hands.
// pointing is true when the index finger is extended and at least 2 other fingers are curled.
export function pickPointingHand(hands) {
  let best = null;
  hands.forEach((pts, index) => {
    const indexExt = extension(pts, INDEX);
    const curled = OTHERS.filter((f) => extension(pts, f) < 1).length;
    const pointing = indexExt > 1 && curled >= 2;
    const score = (pointing ? 10 : 0) + indexExt - OTHERS.reduce((s, f) => s + extension(pts, f), 0) / 3;
    if (!best || score > best.score) best = { index, pointing, score };
  });
  return best && { index: best.index, pointing: best.pointing };
}

// Move from the fingertip back toward the DIP joint by offsetMm (config/explore.yaml
// fingertip.contact_offset_mm). The pad touches the sheet behind the tip landmark.
export function contactPoint(tipMm, dipMm, offsetMm) {
  const d = dist(tipMm, dipMm);
  if (d < 1e-9 || offsetMm <= 0) return [...tipMm];
  const k = Math.min(offsetMm, d) / d;
  return [tipMm[0] + (dipMm[0] - tipMm[0]) * k, tipMm[1] + (dipMm[1] - tipMm[1]) * k];
}

export const LANDMARK = { WRIST, INDEX_TIP: INDEX.tip, INDEX_DIP: INDEX.dip };

// The page's path for each worker result: pick the hand, map its tip and DIP joint to sheet
// mm, move back by the contact offset, then the 1 euro filter. test/parity.test.mjs runs
// this against the shipped code (apps/web/src/explore/fingertip.ts).
export class FingertipMapper {
  constructor({ filter, lostResetMs } = TRACKING) {
    this.filter = new OneEuroFilter2D(filter);
    this.lostResetMs = lostResetMs;
    this.toMm = null;
    this.lastHandAt = -Infinity;
  }

  setCalibration(toMm) {
    this.toMm = toMm;
    this.filter.reset();
  }

  // True once no hand has been seen for lostResetMs, whether frames came without one or
  // no frames came at all (a stalled camera or tab). Same test as the shipped code.
  lost(nowMs) {
    return nowMs - this.lastHandAt >= this.lostResetMs;
  }

  // handsPx: arrays of 21 [x, y] points in pixels. Null with no hand or no calibration.
  update(handsPx, nowMs, offsetMm) {
    if (!this.toMm || !handsPx.length) {
      if (this.lost(nowMs)) this.filter.reset();
      return null;
    }
    const pick = pickPointingHand(handsPx);
    const pts = handsPx[pick.index];
    const tipMm = applyHomography(this.toMm, pts[LANDMARK.INDEX_TIP]);
    const dipMm = applyHomography(this.toMm, pts[LANDMARK.INDEX_DIP]);
    const raw = contactPoint(tipMm, dipMm, offsetMm);
    // After a gap the filter starts over, so it never smooths across a jump.
    if (this.lost(nowMs)) this.filter.reset();
    const mm = this.filter.filter(raw, nowMs / 1000);
    this.lastHandAt = nowMs;
    return { mm, raw, pointing: pick.pointing, t: nowMs };
  }
}
