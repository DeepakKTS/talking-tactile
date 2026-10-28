// Which hand is touching, and where its fingertip pad meets the sheet.
//
// A pointing hand has the index finger extended and the other fingers curled. Of up to
// max_hands hands, a pointing hand wins; between two pointing hands the dominant hand wins,
// and with either hand allowed the one already in use stays, so the touch does not jump.
// Landmarks follow MediaPipe Hands: 0 wrist, then 4 per finger from the thumb (1 to 4):
// index 5 to 8, middle 9 to 12, ring 13 to 16, pinky 17 to 20, each MCP, PIP, DIP, tip.
import type { ExploreConfig } from "../shared/config";
import type { Pt } from "./homography";

export type Side = "left" | "right";

export interface HandObs {
  /** 21 landmarks in pixels, not normalized, so the aspect ratio is right. */
  landmarks: readonly Pt[];
  /** MediaPipe's handedness label, which assumes a mirrored image. */
  label: "Left" | "Right" | null;
}

export interface HandSettings {
  dominant: Side | "either";
  /** True when the frames given to MediaPipe are mirrored, as from a selfie view. */
  cameraMirrored: boolean;
}

export interface PickedHand {
  index: number;
  pointing: boolean;
  hand: Side | null;
}

export const WRIST = 0;
export const INDEX_DIP = 7;
export const INDEX_TIP = 8;
const INDEX = { pip: 6, tip: INDEX_TIP };
const OTHERS = [
  { pip: 10, tip: 12 },
  { pip: 14, tip: 16 },
  { pip: 18, tip: 20 },
] as const;

const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1]);

function point(pts: readonly Pt[], i: number): Pt {
  return pts[i] ?? [NaN, NaN];
}

// Tip to wrist over PIP to wrist: above 1 the finger is out, below 1 it is curled.
function extension(pts: readonly Pt[], f: { pip: number; tip: number }): number {
  const wrist = point(pts, WRIST);
  return dist(wrist, point(pts, f.tip)) / Math.max(1e-9, dist(wrist, point(pts, f.pip)));
}

export function isPointing(pts: readonly Pt[], minCurled: number): boolean {
  const curled = OTHERS.filter((f) => extension(pts, f) < 1).length;
  return extension(pts, INDEX) > 1 && curled >= minCurled;
}

function side(label: HandObs["label"], mirrored: boolean): Side | null {
  if (label === null) return null;
  const asLabelled: Side = label === "Left" ? "left" : "right";
  if (mirrored) return asLabelled;
  return asLabelled === "left" ? "right" : "left";
}

export function pickHand(
  hands: readonly HandObs[],
  cfg: ExploreConfig["hands"],
  settings: HandSettings,
  previous: Side | null,
): PickedHand | null {
  let best: PickedHand | null = null;
  let bestRank: number[] = [];
  for (const [index, h] of hands.slice(0, cfg.max_hands).entries()) {
    const pointing = isPointing(h.landmarks, cfg.min_curled);
    if (cfg.require_pointing && !pointing) continue;
    const hand = side(h.label, settings.cameraMirrored);
    const others = OTHERS.reduce((s, f) => s + extension(h.landmarks, f), 0) / OTHERS.length;
    const rank = [
      pointing ? 1 : 0,
      settings.dominant !== "either" && hand === settings.dominant ? 1 : 0,
      hand !== null && hand === previous ? 1 : 0,
      extension(h.landmarks, INDEX) - others,
    ];
    if (best === null || before(rank, bestRank)) {
      best = { index, pointing, hand };
      bestRank = rank;
    }
  }
  return best;
}

function before(a: number[], b: number[]): boolean {
  for (let i = 0; i < a.length; i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d > 0;
  }
  return false;
}

/** The pad that touches the sheet: back from the tip toward the DIP joint by offsetMm
 * (explore.yaml fingertip.contact_offset_mm), never past the joint. */
export function contactPoint(tipMm: Pt, dipMm: Pt, offsetMm: number): Pt {
  const d = dist(tipMm, dipMm);
  if (d < 1e-9 || offsetMm <= 0) return [tipMm[0], tipMm[1]];
  const k = Math.min(offsetMm, d) / d;
  return [tipMm[0] + (dipMm[0] - tipMm[0]) * k, tipMm[1] + (dipMm[1] - tipMm[1]) * k];
}
