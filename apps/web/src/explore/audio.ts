// Explore's audio: earcons, the exit tick, guidance beeps and the arrival chime, rendered
// once into AudioBuffers when Explore starts (nothing to fetch, so they work offline), and
// speech. Every sentence is written to the mirror, a role=log region. Who speaks is a
// setting (RULES 6.3), never both:
//   app            the app voice (speechSynthesis with a local voice, localService true); the
//                  mirror is aria-live=off so a running screen reader stays quiet. With no
//                  local voice the app voice is off, since a network voice stops when the
//                  network does: the mirror turns polite and the page shows NO_LOCAL_VOICE.
//   screen_reader  no app voice; the mirror is aria-live=polite and the screen reader reads.
// stop() cancels speech at once (Escape, RULES 6.1).
import type { ExploreConfig } from "../shared/config";

export type VoiceMode = "app" | "screen_reader";

export interface UtteranceLike {
  text: string;
  voice: SpeechSynthesisVoice | null;
  rate: number;
  lang: string;
  onend: ((e: SpeechSynthesisEvent) => void) | null;
  onstart?: ((e: SpeechSynthesisEvent) => void) | null;
  onerror: ((e: SpeechSynthesisErrorEvent) => void) | null;
}

export interface SpeechLike {
  readonly speaking: boolean;
  speak(u: UtteranceLike): void;
  cancel(): void;
  getVoices(): SpeechSynthesisVoice[];
  addEventListener(type: "voiceschanged", listener: () => void): void;
}

export interface AudioDeps {
  /** Made on start, which must follow a user gesture. */
  context: () => AudioContext;
  speech: SpeechLike | null;
  utterance: (text: string) => UtteranceLike;
  mirror: HTMLElement;
}

/** What the rest of Explore needs from audio. */
export interface AudioPort {
  earcon(hz: number): number;
  exitTick(): number;
  beep(): number;
  chime(): number;
  /** The rising earcon when a held question starts listening, and the falling one at release. */
  listenStart(): number;
  listenEnd(): number;
  /** A soft tone repeating until turned off or until something is said. */
  thinking(on: boolean): void;
  say(text: string): void;
  stop(): void;
  readonly speaking: boolean;
  readonly lastSaid: string;
}

const MIRROR_KEEP = 5;
// Hold to talk (voice.ts): a rising two-note earcon on listening, falling on release, and a
// soft low blip about once a second while the answer is on its way.
const LISTEN_HZ = [523.25, 783.99];
const LISTEN_NOTE_MS = 70;
const THINK_HZ = 392;
const THINK_MS = 90;
const THINK_GAIN = 0.5;
const THINK_EVERY_MS = 1100;
const FADE_MS = 5;
// Chrome lists its voices a moment after the page loads.
const VOICES_WAIT_MS = 1000;

export const NO_LOCAL_VOICE =
  "This device has no voice that works offline, so the app voice is off. Each sentence is shown under What was said, for a screen reader to read.";

export function browserAudioDeps(mirror: HTMLElement): AudioDeps {
  const synth = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
  return {
    context: () => new AudioContext({ latencyHint: "interactive" }),
    speech: synth,
    utterance: (text) => new SpeechSynthesisUtterance(text),
    mirror,
  };
}

/** The words for the voice: an em or en dash becomes a pause (a comma), since some voices read it
 * out or skip it. Only what is spoken changes; the mirror and the teacher's stored text keep it.
 * Hyphens are never touched. */
export function spoken(text: string): string {
  return text.replace(/\s*[\u2014\u2013]\s*/g, ", ");
}

export class AudioEngine implements AudioPort {
  private ctx: AudioContext | null = null;
  private readonly tones = new Map<number, AudioBuffer>();
  private tick: AudioBuffer | null = null;
  private beepTone: AudioBuffer | null = null;
  private chimeTone: AudioBuffer | null = null;
  private listenUp: AudioBuffer | null = null;
  private listenDown: AudioBuffer | null = null;
  private thinkTone: AudioBuffer | null = null;
  private thinkTimer: ReturnType<typeof setInterval> | null = null;
  private utterance: UtteranceLike | null = null;
  private said = "";
  private voice: SpeechSynthesisVoice | null = null;
  private voiceKnown = false;
  /** Called when the app voice starts saying a sentence: the first spoken word. */
  onSpeechStart: ((at: number, text: string) => void) | null = null;
  /** Called when noLocalVoice changes. */
  onVoiceChange: (() => void) | null = null;

  constructor(
    private readonly cfg: ExploreConfig,
    private readonly deps: AudioDeps,
    private mode: VoiceMode,
  ) {
    deps.mirror.setAttribute("role", "log");
    this.applyMode();
  }

  get voiceMode(): VoiceMode {
    return this.mode;
  }

  get lastSaid(): string {
    return this.said;
  }

  get speaking(): boolean {
    return this.utterance !== null;
  }

  /** The app voice is chosen but cannot speak offline, so the mirror stands in for it. */
  get noLocalVoice(): boolean {
    return this.mode === "app" && this.voiceKnown && this.voice === null;
  }

  /** Makes the audio context and renders every sound once. Call from a key press or click. */
  async start(earconPitches: readonly number[]): Promise<void> {
    const ctx = this.ctx ?? this.deps.context();
    this.ctx = ctx;
    if (ctx.state !== "running") await ctx.resume();
    const e = this.cfg.earcons;
    const g = this.cfg.guidance;
    for (const hz of earconPitches) {
      if (!this.tones.has(hz)) this.tones.set(hz, this.render([hz], e.tone_ms, e.gain));
    }
    this.tick ??= this.render([e.exit_tick_hz], e.exit_tick_ms, e.exit_tick_gain);
    this.beepTone ??= this.render([g.beep_hz], g.beep_ms, e.gain);
    this.chimeTone ??= this.render(g.chime_hz, g.chime_note_ms, e.gain);
    this.listenUp ??= this.render(LISTEN_HZ, LISTEN_NOTE_MS, e.gain);
    this.listenDown ??= this.render([...LISTEN_HZ].reverse(), LISTEN_NOTE_MS, e.gain);
    this.thinkTone ??= this.render([THINK_HZ], THINK_MS, e.gain * THINK_GAIN);
    if (!this.voiceKnown) await this.findVoice();
  }

  setMode(mode: VoiceMode): void {
    const before = this.noLocalVoice;
    this.mode = mode;
    if (mode === "screen_reader") this.cancelSpeech();
    this.applyMode();
    if (this.noLocalVoice !== before) this.onVoiceChange?.();
  }

  /** Each play returns the time it was started, from performance.now(), or NaN before start. */
  earcon(hz: number): number {
    return this.play(this.tones.get(hz) ?? this.tones.get(this.cfg.earcons.default_hz) ?? null);
  }

  exitTick(): number {
    return this.play(this.tick);
  }

  beep(): number {
    return this.play(this.beepTone);
  }

  chime(): number {
    return this.play(this.chimeTone);
  }

  listenStart(): number {
    return this.play(this.listenUp);
  }

  listenEnd(): number {
    return this.play(this.listenDown);
  }

  thinking(on: boolean): void {
    if (this.thinkTimer !== null) clearInterval(this.thinkTimer);
    this.thinkTimer = null;
    if (!on) return;
    this.thinkTimer = setInterval(() => { this.play(this.thinkTone); }, THINK_EVERY_MS);
  }

  say(text: string): void {
    this.thinking(false);
    this.said = text;
    this.writeMirror(text);
    const speech = this.deps.speech;
    if (this.mode !== "app" || !speech || !this.voice) return;
    this.cancelSpeech();
    const u = this.deps.utterance(spoken(text));
    u.voice = this.voice;
    u.lang = this.voice.lang;
    const done = () => {
      if (this.utterance === u) this.utterance = null;
    };
    u.onend = done;
    u.onstart = () => this.onSpeechStart?.(performance.now(), text);
    u.onerror = done;
    this.utterance = u;
    speech.speak(u);
  }

  /** Stops speech now. A screen reader cannot be stopped from a page; it reads only what is
   * already in the mirror. */
  stop(): void {
    this.cancelSpeech();
  }

  private cancelSpeech(): void {
    if (this.utterance === null && !this.deps.speech?.speaking) return;
    this.utterance = null;
    this.deps.speech?.cancel();
  }

  private applyMode(): void {
    const mirrorSpeaks = this.mode === "screen_reader" || this.noLocalVoice;
    this.deps.mirror.setAttribute("aria-live", mirrorSpeaks ? "polite" : "off");
  }

  private async findVoice(): Promise<void> {
    const speech = this.deps.speech;
    if (speech && speech.getVoices().length === 0) {
      await new Promise<void>((resolve) => {
        speech.addEventListener("voiceschanged", () => { resolve(); });
        setTimeout(resolve, VOICES_WAIT_MS);
      });
    }
    this.chooseVoice();
    // Voices can arrive or change later, such as when a voice pack is installed.
    speech?.addEventListener("voiceschanged", () => { this.chooseVoice(); });
  }

  private chooseVoice(): void {
    const before = this.noLocalVoice;
    this.voice = this.deps.speech ? pickVoice(this.deps.speech.getVoices()) : null;
    this.voiceKnown = true;
    if (!this.voice) this.cancelSpeech();
    this.applyMode();
    if (this.noLocalVoice !== before) this.onVoiceChange?.();
  }

  private writeMirror(text: string): void {
    const m = this.deps.mirror;
    const line = m.ownerDocument.createElement("p");
    line.textContent = text;
    m.append(line);
    while (m.childElementCount > MIRROR_KEEP) m.firstElementChild?.remove();
  }

  private play(buffer: AudioBuffer | null): number {
    const ctx = this.ctx;
    if (!ctx || !buffer) return NaN;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.start(0);
    return performance.now();
  }

  // Sine notes one after another, each with a short fade in and out so it does not click.
  private render(hzs: readonly number[], noteMs: number, gain: number): AudioBuffer {
    const ctx = this.ctx;
    if (!ctx) throw new Error("audio is not started");
    const rate = ctx.sampleRate;
    const note = Math.round((noteMs / 1000) * rate);
    const buf = ctx.createBuffer(1, note * hzs.length, rate);
    const data = buf.getChannelData(0);
    const fade = Math.max(1, Math.round((FADE_MS / 1000) * rate));
    hzs.forEach((hz, k) => {
      for (let i = 0; i < note; i++) {
        const env = Math.min(1, i / fade, (note - 1 - i) / fade);
        data[k * note + i] = gain * env * Math.sin((2 * Math.PI * hz * i) / rate);
      }
    });
    return buf;
  }
}

/** A local voice (localService true), English first, since a network voice stops when
 * offline. Null when the device has none. */
export function pickVoice(voices: readonly SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  return (
    english.find((v) => v.localService && v.default) ??
    english.find((v) => v.localService) ??
    voices.find((v) => v.localService) ??
    null
  );
}
