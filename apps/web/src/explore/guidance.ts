// Guidance mode: "where is the aorta?" The direction is said once in words, then beeps
// speed up as the finger nears the part, then a chime and the label on arrival. Direction
// and distance come from code, never from a model: the direction is from the finger to the
// part's centroid (a point on the part's own area), the distance is to the part's outline,
// 0 inside. Up is toward the top edge of the sheet, as the Python neighbors code has it.
import type { ExploreConfig } from "../shared/config";
import type { Direction } from "../shared/regions";
import type { Pt } from "./homography";
import { type IndexedRegion, type RegionIndex, signedDistance } from "./regionIndex";

export type Compass = Exclude<Direction, "inside" | "around">;

export type GuideEvent =
  | { kind: "say"; text: string }
  | { kind: "beep"; t: number; perSecond: number }
  | { kind: "arrived"; region: IndexedRegion; t: number };

const SECTORS: readonly Compass[] = ["right", "up_right", "up", "up_left", "left", "down_left", "down", "down_right"];

export function directionOf(from: Pt, to: Pt): Compass {
  const angle = (Math.atan2(-(to[1] - from[1]), to[0] - from[0]) * 180) / Math.PI;
  const i = (((Math.floor((angle + 22.5) / 45) % 8) + 8) % 8);
  return SECTORS[i] ?? "up";
}

export function directionWords(d: Compass): string {
  return d.replace("_", " and ");
}

export function centimeters(mm: number): number {
  return Math.max(1, Math.round(mm / 10));
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function guidanceSentence(label: string, d: Compass, cm: number): string {
  return `${capital(label)}. ${capital(directionWords(d))}, ${cm} centimeter${cm === 1 ? "" : "s"}.`;
}

/** Beeps per second: beeps_per_s_near at the outline, falling in a straight line to
 * beeps_per_s_far at far_mm and beyond. */
export function beepsPerSecond(distanceMm: number, g: ExploreConfig["guidance"]): number {
  const k = Math.min(1, Math.max(0, distanceMm / g.far_mm));
  return g.beeps_per_s_near + (g.beeps_per_s_far - g.beeps_per_s_near) * k;
}

export class Guide {
  private target: IndexedRegion | null = null;
  private told = false;
  private rate = 0;
  private rateAt = -Infinity;
  private lastBeep = -Infinity;
  private insideSince: number | null = null;

  constructor(
    private readonly index: RegionIndex,
    private readonly cfg: ExploreConfig,
  ) {}

  get active(): boolean {
    return this.target !== null;
  }

  get goal(): IndexedRegion | null {
    return this.target;
  }

  start(target: IndexedRegion, p: Pt | null, t: number): GuideEvent[] {
    this.target = target;
    this.told = false;
    this.rateAt = -Infinity;
    this.lastBeep = -Infinity;
    this.insideSince = null;
    return p ? this.update(p, t) : [];
  }

  stop(): void {
    this.target = null;
  }

  update(p: Pt | null, t: number): GuideEvent[] {
    const target = this.target;
    if (!target || !p) return [];
    const events: GuideEvent[] = [];
    if (this.index.contains(target, p, this.cfg.hysteresis.enter_shrink_mm)) {
      this.insideSince ??= t;
      if (t - this.insideSince >= this.cfg.guidance.arrive_inside_ms) {
        this.target = null;
        return [{ kind: "arrived", region: target, t }];
      }
    } else {
      this.insideSince = null;
    }
    const distance = Math.max(0, -signedDistance(target.polygon, p));
    if (!this.told) {
      this.told = true;
      if (distance > 0) {
        const d = directionOf(p, target.centroid);
        events.push({ kind: "say", text: guidanceSentence(target.label, d, centimeters(distance)) });
        this.lastBeep = t; // the first beep follows one gap after the sentence starts
      }
    }
    if (t - this.rateAt >= this.cfg.guidance.update_ms) {
      this.rate = beepsPerSecond(distance, this.cfg.guidance);
      this.rateAt = t;
    }
    const gap = 1000 / this.rate;
    if (t - this.lastBeep >= gap) {
      // Keep to the rate between frames; after a pause, start again from now.
      this.lastBeep = t - this.lastBeep > 2 * gap ? t : this.lastBeep + gap;
      events.push({ kind: "beep", t, perSecond: this.rate });
    }
    return events;
  }
}
