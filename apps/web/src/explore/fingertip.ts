// Worker landmarks to one contact point in sheet mm: the hand picker, the homography for
// the tip and the DIP joint, the contact offset, then the 1 euro filter. The filter starts
// over when the hand changes or is lost for lost_reset_ms, so it never smooths a jump.
import type { ExploreConfig } from "../shared/config";
import type { WorkerHand } from "../workers/protocol";
import { type HandSettings, INDEX_DIP, INDEX_TIP, type Side, contactPoint, pickHand } from "./hands";
import { type Mat3, type Pt, applyHomography } from "./homography";
import { OneEuroFilter2D, oneEuroParams } from "./oneEuro";

export interface Fingertip {
  p: Pt | null;
  pointing: boolean;
}

export class FingertipTracker {
  private toMm: Mat3 | null = null;
  private readonly filter: OneEuroFilter2D;
  private side: Side | null = null;
  private lastIndex = -1;
  private lastSeen = -Infinity;

  constructor(
    private readonly cfg: ExploreConfig,
    private settings: HandSettings,
  ) {
    this.filter = new OneEuroFilter2D(oneEuroParams(cfg.fingertip.one_euro));
  }

  setCalibration(toMm: Mat3 | null): void {
    this.toMm = toMm;
    this.filter.reset();
  }

  setSettings(settings: HandSettings): void {
    this.settings = settings;
    this.side = null;
    this.filter.reset();
  }

  get calibrated(): boolean {
    return this.toMm !== null;
  }

  /** hands as the worker sends them, the frame size in pixels, t in ms. */
  update(hands: readonly WorkerHand[], width: number, height: number, t: number): Fingertip {
    const toMm = this.toMm;
    const obs = hands.map((h) => ({
      landmarks: h.landmarks.map(([x, y]) => [x * width, y * height] as const),
      label: h.label,
    }));
    const pick = toMm ? pickHand(obs, this.cfg.hands, this.settings, this.side) : null;
    const hand = pick ? obs[pick.index] : undefined;
    const tip = hand?.landmarks[INDEX_TIP];
    const dip = hand?.landmarks[INDEX_DIP];
    if (!toMm || !pick || !tip || !dip) {
      if (t - this.lastSeen >= this.cfg.fingertip.lost_reset_ms) this.filter.reset();
      return { p: null, pointing: false };
    }
    const same = pick.hand !== null ? pick.hand === this.side : pick.index === this.lastIndex;
    if (!same || t - this.lastSeen >= this.cfg.fingertip.lost_reset_ms) this.filter.reset();
    this.side = pick.hand;
    this.lastIndex = pick.index;
    this.lastSeen = t;
    const raw = contactPoint(applyHomography(toMm, tip), applyHomography(toMm, dip), this.cfg.fingertip.contact_offset_mm);
    return { p: this.filter.filter(raw, t / 1000), pointing: pick.pointing };
  }
}
