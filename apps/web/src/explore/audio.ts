// Explore's audio: earcons, the exit tick, guidance beeps and the arrival chime, rendered
// once into AudioBuffers when Explore starts (nothing to fetch, so they work offline), and
// speech. Every sentence is written to the mirror, a role=log region. Who speaks is a
// setting (RULES 6.3), never both:
//   app            the app voice (speechSynthesis, a local voice when there is one); the
//                  mirror is aria-live=off so a running screen reader stays quiet.
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
  onerror: ((e: SpeechSynthesisErrorEvent) => void) | null;
}

export interface SpeechLike {
  readonly speaking: boolean;
  speak(u: UtteranceLike): void;
  cancel(): void;
  getVoices(): SpeechSynthesisVoice[];
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
  say(text: string): void;
  stop(): void;
  readonly speaking: boolean;
  readonly lastSaid: string;
}

const MIRROR_KEEP = 5;
const FADE_MS = 5;

export function browserAudioDeps(mirror: HTMLElement): AudioDeps {
  const synth = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
  return {
    context: () => new AudioContext({ latencyHint: "interactive" }),
    speech: synth,
    utterance: (text) => new SpeechSynthesisUtterance(text),
    mirror,
  };
}

export class AudioEngine implements AudioPort {
  private ctx: AudioContext | null = null;
  private readonly tones = new Map<number, AudioBuffer>();
  private tick: AudioBuffer | null = null;
  private beepTone: AudioBuffer | null = null;
  private chimeTone: AudioBuffer | null = null;
  private utterance: UtteranceLike | null = null;
  private said = "";

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
  }

  setMode(mode: VoiceMode): void {
    this.mode = mode;
    if (mode === "screen_reader") this.cancelSpeech();
    this.applyMode();
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

  say(text: string): void {
    this.said = text;
    this.writeMirror(text);
    const speech = this.deps.speech;
    if (this.mode !== "app" || !speech) return;
    this.cancelSpeech();
    const u = this.deps.utterance(text);
    u.voice = pickVoice(speech.getVoices());
    if (u.voice) u.lang = u.voice.lang;
    const done = () => {
      if (this.utterance === u) this.utterance = null;
    };
    u.onend = done;
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
    this.deps.mirror.setAttribute("aria-live", this.mode === "screen_reader" ? "polite" : "off");
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

/** A local English voice when there is one, since a network voice stops when offline. */
export function pickVoice(voices: readonly SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  return (
    english.find((v) => v.localService && v.default) ??
    english.find((v) => v.localService) ??
    voices.find((v) => v.localService) ??
    null
  );
}
