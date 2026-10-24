// When to speak (PLAN.md section 7, E3). One machine for the one tracked fingertip:
//
//   OUTSIDE  -> ENTERING  the point is inside a part's outline shrunk by enter_shrink_mm
//   ENTERING -> INSIDE    it stays enter_hold_ms                 earcon
//   INSIDE   -> DWELLED   slower than speed_below_mm_s for hold_ms   label
//   INSIDE or DWELLED -> LEAVING   the point is outside the outline grown by exit_grow_mm
//   LEAVING  -> OUTSIDE   it stays out exit_hold_ms              exit tick
//
// The smallest part wins, so a child inside its parent takes over once the finger is
// enter_shrink_mm inside it. Moving straight from one part into another plays the first
// part's exit tick, then the second part's earcon. Earcons and exit ticks together are
// capped at max_per_second in any second; a capped sound is dropped, the state still
// changes. Speed is the straight line move over speed_window_ms, so jitter at rest does not
// add up to a speed. All numbers come from explore.yaml.
import type { ExploreConfig } from "../shared/config";
import type { Pt } from "./homography";
import type { IndexedRegion, RegionIndex } from "./regionIndex";

/** t is when the event fires; since is when the change behind it began, such as the first
 * frame inside the shrunk outline for an earcon. */
export type TouchEvent =
  | { kind: "earcon"; region: IndexedRegion; t: number; since: number }
  | { kind: "exit"; region: IndexedRegion; t: number; since: number }
  | { kind: "label"; region: IndexedRegion; t: number; since: number };

export type Phase = "outside" | "entering" | "inside" | "dwelled" | "leaving";

const HISTORY = 30; // fingertip points kept, PLAN.md section 9

interface Sample {
  p: Pt;
  t: number;
}

export class TouchMachine {
  private current: IndexedRegion | null = null;
  private insideSince = 0;
  private dwelled = false;
  private pending: { target: IndexedRegion | null; since: number } | null = null;
  private slowSince: number | null = null;
  private lastSeen: number | null = null;
  private readonly history: Sample[] = [];
  private readonly sounds: number[] = [];
  /** Earcons and exit ticks dropped by the per second cap. */
  droppedSounds = 0;

  constructor(
    private readonly index: RegionIndex,
    private readonly cfg: ExploreConfig,
  ) {}

  get region(): IndexedRegion | null {
    return this.current;
  }

  get phase(): Phase {
    if (this.pending) {
      if (this.pending.target) return "entering";
      return this.current ? "leaving" : "outside";
    }
    if (!this.current) return "outside";
    return this.dwelled ? "dwelled" : "inside";
  }

  /** Forgets the finger without a sound, as after recalibrating. */
  reset(): void {
    this.current = null;
    this.dwelled = false;
    this.pending = null;
    this.slowSince = null;
    this.lastSeen = null;
    this.history.length = 0;
  }

  /** The point at time t in ms, or null when no hand was found in the frame. */
  update(p: Pt | null, t: number): TouchEvent[] {
    if (p === null) {
      if (this.lastSeen !== null && t - this.lastSeen >= this.cfg.fingertip.lost_reset_ms) this.reset();
      return [];
    }
    this.lastSeen = t;
    this.history.push({ p, t });
    if (this.history.length > HISTORY) this.history.shift();

    const events: TouchEvent[] = [];
    const want = this.wanted(p);
    if (want === this.current) {
      this.pending = null;
    } else {
      if (this.pending?.target !== want) this.pending = { target: want, since: t };
      const { enter_hold_ms, exit_hold_ms } = this.cfg.hysteresis;
      if (t - this.pending.since >= (want ? enter_hold_ms : exit_hold_ms)) {
        this.commit(want, p, t, events);
      }
    }
    this.dwell(t, events);
    return events;
  }

  // The part the finger should be on: the current part while it is within the grown
  // outline, unless a smaller part takes over; otherwise whatever it is well inside.
  private wanted(p: Pt): IndexedRegion | null {
    const { enter_shrink_mm, exit_grow_mm } = this.cfg.hysteresis;
    const hit = this.index.hit(p, enter_shrink_mm);
    const cur = this.current;
    if (cur && this.index.contains(cur, p, -exit_grow_mm)) {
      return hit && hit.area < cur.area ? hit : cur;
    }
    return hit;
  }

  private commit(to: IndexedRegion | null, p: Pt, t: number, events: TouchEvent[]): void {
    const from = this.current;
    const since = this.pending?.since ?? t;
    if (from && !this.index.contains(from, p, -this.cfg.hysteresis.exit_grow_mm)) {
      this.sound({ kind: "exit", region: from, t, since }, events);
    }
    if (to) this.sound({ kind: "earcon", region: to, t, since }, events);
    this.current = to;
    this.pending = null;
    this.dwelled = false;
    this.insideSince = t;
  }

  private sound(e: TouchEvent, events: TouchEvent[]): void {
    while (this.sounds.length && (this.sounds[0] ?? 0) <= e.t - 1000) this.sounds.shift();
    if (this.sounds.length >= this.cfg.earcons.max_per_second) {
      this.droppedSounds++;
      return;
    }
    this.sounds.push(e.t);
    events.push(e);
  }

  private dwell(t: number, events: TouchEvent[]): void {
    // A slow speed covers the whole window it was measured over, so the dwell clock starts
    // at the window's start, and dwell to label stays hold_ms rather than hold_ms plus the
    // window.
    const speed = this.speed(t);
    if (speed !== null && speed < this.cfg.dwell.speed_below_mm_s) {
      this.slowSince ??= t - this.cfg.dwell.speed_window_ms;
    } else {
      this.slowSince = null;
    }
    if (!this.current || this.dwelled || this.pending || this.slowSince === null) return;
    if (t - Math.max(this.slowSince, this.insideSince) >= this.cfg.dwell.hold_ms) {
      this.dwelled = true;
      events.push({ kind: "label", region: this.current, t, since: Math.max(this.slowSince, this.insideSince) });
    }
  }

  /** mm per second over the last speed_window_ms, or null with too little history. */
  speed(t: number): number | null {
    const now = this.history[this.history.length - 1];
    if (!now) return null;
    const since = t - this.cfg.dwell.speed_window_ms;
    let then: Sample | undefined;
    for (let i = this.history.length - 2; i >= 0; i--) {
      const s = this.history[i];
      if (s && s.t <= since) {
        then = s;
        break;
      }
    }
    if (!then) return null;
    return (Math.hypot(now.p[0] - then.p[0], now.p[1] - then.p[1]) / (now.t - then.t)) * 1000;
  }
}
