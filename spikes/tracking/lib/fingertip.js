// Pick the pointing hand and find the contact point under the index finger.
// Landmark indices follow MediaPipe Hands: 0 wrist; index 5 MCP, 6 PIP, 7 DIP, 8 tip;
// middle 10 PIP, 12 tip; ring 14 PIP, 16 tip; pinky 18 PIP, 20 tip.

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
