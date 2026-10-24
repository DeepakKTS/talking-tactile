// One Explore session on one published sheet: fingertip points in, sounds and speech out.
// Labels, earcons, "more", "what is here", "repeat" and guidance need only regions.json and
// this code, so they keep working with the network off. Only questions go out, to
// /api/ask, and when that fails the student hears so and everything else carries on.
import type { ExploreConfig } from "../shared/config";
import type { RegionsFile } from "../shared/regions";
import type { AudioPort } from "./audio";
import { Guide } from "./guidance";
import type { Pt } from "./homography";
import { parseIntent } from "./intents";
import type { Metrics } from "./metrics";
import { type IndexedRegion, RegionIndex } from "./regionIndex";
import { TouchMachine } from "./touch";

export interface AskRequest {
  figure_id: string;
  question: string;
  region_id: string | null;
  recent_region_ids: string[];
}

/** A failed question, with the sentence to say instead of an answer. */
export class AskError extends Error {
  override name = "AskError";
  constructor(readonly spoken: string) {
    super(spoken);
  }
}

export interface SessionDeps {
  audio: AudioPort;
  metrics: Metrics;
  /** The answer text. Throws AskError with a sentence to say when the service fails, or
   * anything else when the network is not there. */
  ask: (req: AskRequest) => Promise<string>;
}

export interface FingerSample {
  /** The contact point in sheet mm, or null when no hand was found. */
  p: Pt | null;
  /** performance.now() when the landmarks for this frame reached the main thread. */
  t: number;
  receivedAt: number;
  /** performance.now() when the camera frame was captured, when known. */
  capturedAt?: number;
}

export type KeyAction = "stop" | "recalibrate" | "help" | "more" | "repeat" | "here";

const KEYS: Record<string, KeyAction> = {
  Escape: "stop",
  r: "recalibrate",
  R: "recalibrate",
  h: "help",
  H: "help",
  m: "more",
  M: "more",
  ".": "repeat",
  w: "here",
  W: "here",
};

export function keyAction(key: string): KeyAction | null {
  return KEYS[key] ?? null;
}

export const HELP =
  "Touch the sheet to hear a part. Rest your finger to hear its name. " +
  "Press M for more, period to repeat, W for what is here. " +
  "Escape stops speech. R sets the corners again. Type a question and press Enter.";
export const OFFLINE_ANSWER = "Questions need the network. Labels still work.";
const OFF_SHEET = "Your finger is off the sheet. Press R to set the corners again.";
const CANNOT_SEE = "The camera cannot see the sheet.";
const SEES_AGAIN = "The camera can see the sheet again.";
const RECENT = 2;

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const NEIGHBOR_WORDS: Record<string, string> = {
  up: "above", down: "below", left: "to the left", right: "to the right",
  up_left: "above and to the left", up_right: "above and to the right",
  down_left: "below and to the left", down_right: "below and to the right",
};

export class ExploreSession {
  readonly index: RegionIndex;
  private readonly touch: TouchMachine;
  private readonly guide: Guide;
  private last: Pt | null = null;
  private lastAt = 0;
  private recent: IndexedRegion[] = [];
  private offSheet = 0;
  private warnedOffSheet = false;
  private darkSince: number | null = null;
  private warnedDark = false;

  constructor(
    readonly file: RegionsFile,
    private readonly cfg: ExploreConfig,
    private readonly deps: SessionDeps,
  ) {
    this.index = new RegionIndex(file, cfg);
    this.touch = new TouchMachine(this.index, cfg);
    this.guide = new Guide(this.index, cfg);
  }

  /** Every earcon pitch this sheet can play, for the audio engine to render at start. */
  get pitches(): number[] {
    return [...new Set([...this.index.regions.map((r) => r.earconHz), this.cfg.earcons.default_hz])];
  }

  get region(): IndexedRegion | null {
    return this.touch.region;
  }

  intro(): void {
    this.deps.audio.say(`${this.file.title}. ${this.file.summary} Press H for help.`);
  }

  help(): void {
    this.deps.audio.say(HELP);
  }

  /** Forgets the finger, as after setting the corners again. */
  resetTouch(): void {
    this.touch.reset();
    this.offSheet = 0;
    this.warnedOffSheet = false;
  }

  finger(s: FingerSample): void {
    const { audio, metrics } = this.deps;
    if (s.p) {
      this.last = s.p;
      this.lastAt = s.t;
      this.checkOnSheet(s.p);
    } else if (s.t - this.lastAt >= this.cfg.fingertip.lost_reset_ms) {
      this.last = null; // guidance must not start from where a lost hand used to be
    }
    for (const e of this.touch.update(s.p, s.t)) {
      if (e.kind === "earcon") {
        const code = audio.earcon(e.region.earconHz) - s.receivedAt;
        const enter = e.t - e.since + code;
        metrics.frameToEarconMs.push(code);
        metrics.enterToEarconMs.push(enter);
        if (s.capturedAt !== undefined) metrics.touchToEarconMs.push(enter + s.receivedAt - s.capturedAt);
        this.remember(e.region);
      } else if (e.kind === "exit") {
        audio.exitTick();
      } else {
        audio.say(capital(e.region.label));
        metrics.dwellToLabelMs.push(performance.now() - s.receivedAt);
      }
    }
    for (const g of this.guide.update(s.p, s.t)) {
      if (g.kind === "say") audio.say(g.text);
      else if (g.kind === "beep") {
        if (!audio.speaking) audio.beep();
      } else {
        audio.chime();
        audio.say(capital(g.region.label));
      }
    }
  }

  /** Each frame's brightness (0 to 1): a camera that stays dark for dark_warn_ms is
   * covered or sees nothing, and the student hears so, once, and again when it clears. */
  sight(brightness: number, t: number): void {
    const { dark_frame_below, dark_warn_ms } = this.cfg.health;
    if (brightness >= dark_frame_below) {
      this.darkSince = null;
      if (this.warnedDark) this.deps.audio.say(SEES_AGAIN);
      this.warnedDark = false;
      return;
    }
    this.darkSince ??= t;
    if (!this.warnedDark && t - this.darkSince >= dark_warn_ms) {
      this.warnedDark = true;
      this.deps.audio.say(CANNOT_SEE);
    }
  }

  /** A typed or spoken request. */
  async command(text: string): Promise<void> {
    const intent = parseIntent(text, this.index.regions, this.cfg.intents.min_label_similarity);
    const { audio } = this.deps;
    switch (intent.kind) {
      case "none":
        return;
      case "stop":
        this.stop();
        return;
      case "repeat":
        this.repeat();
        return;
      case "more":
        this.more();
        return;
      case "here":
        this.here();
        return;
      case "where":
        this.guideTo(intent.region);
        return;
      case "where_unknown":
        audio.say(`There is no ${intent.name} on this sheet.`);
        return;
      case "ask":
        await this.ask(intent.text);
        return;
    }
  }

  stop(): void {
    this.guide.stop();
    this.deps.audio.stop();
  }

  repeat(): void {
    const { audio } = this.deps;
    audio.say(audio.lastSaid || "Nothing to repeat yet.");
  }

  here(): void {
    const r = this.touch.region;
    this.deps.audio.say(r ? capital(r.label) : "Not on a part.");
  }

  /** The part's description, or, with none, its neighbors in words, from code. */
  more(): void {
    const r = this.touch.region ?? this.recent[this.recent.length - 1] ?? null;
    const { audio } = this.deps;
    if (!r) {
      audio.say("Touch a part first.");
      return;
    }
    if (r.region.description) {
      audio.say(r.region.description);
      return;
    }
    const sentences = (r.region.neighbors ?? []).slice(0, 2).flatMap((n) => {
      const other = this.index.byId(n.id);
      if (!other) return [];
      const name = capital(other.label);
      if (n.direction === "inside") return [`${name} is inside it.`];
      if (n.direction === "around") return [`It is inside ${other.label}.`];
      return [`${name} is ${NEIGHBOR_WORDS[n.direction] ?? n.direction}.`];
    });
    audio.say(sentences.length ? sentences.join(" ") : `Nothing more about ${r.label}.`);
  }

  guideTo(region: IndexedRegion): void {
    for (const g of this.guide.start(region, this.last, this.lastAt)) {
      if (g.kind === "say") this.deps.audio.say(g.text);
    }
  }

  private async ask(question: string): Promise<void> {
    const current = this.touch.region;
    const req: AskRequest = {
      figure_id: this.file.figure_id,
      question,
      region_id: current?.id ?? null,
      recent_region_ids: this.recent.filter((r) => r !== current).slice(-RECENT).map((r) => r.id),
    };
    let answer: string;
    try {
      answer = await this.deps.ask(req);
    } catch (err) {
      answer = err instanceof AskError ? err.spoken : OFFLINE_ANSWER;
    }
    this.deps.audio.say(answer);
  }

  private remember(r: IndexedRegion): void {
    this.recent = [...this.recent.filter((x) => x !== r), r].slice(-(RECENT + 1));
  }

  private checkOnSheet(p: Pt): void {
    const { width_mm, height_mm } = this.file.page;
    const off = p[0] < 0 || p[1] < 0 || p[0] > width_mm || p[1] > height_mm;
    this.offSheet = off ? this.offSheet + 1 : 0;
    if (!off) this.warnedOffSheet = false;
    if (this.offSheet >= this.cfg.health.off_page_points_before_recal && !this.warnedOffSheet) {
      this.warnedOffSheet = true;
      this.deps.audio.say(OFF_SHEET);
    }
  }
}
