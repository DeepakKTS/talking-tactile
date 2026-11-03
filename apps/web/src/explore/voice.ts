// Spoken questions in Explore: hold anywhere on the screen to talk, let go to send.
//
// - HoldToTalk is the state machine, on explicit times so it is tested without timers:
//   idle, pressed (a finger is down, not yet HOLD_MS), listening (the start earcon played,
//   the microphone records), busy (the question is out; holds are ignored until the
//   answer is spoken). A press shorter than HOLD_MS is a tap and does nothing. A recording
//   shorter than MIN_MS is too short to send; one that reaches MAX_MS is sent. Capture
//   goes on POST_ROLL_MS after letting go, then the WAV is encoded.
// - The microphone is Web Audio: a MediaStreamSource into an AudioWorklet that hands its
//   samples back in blocks, kept while listening (no MediaRecorder). It is opened on the first hold, which is a
//   user gesture, and kept open, so later questions do not lose their first word.
// - The samples are resampled to 16 kHz mono and encoded as a 16-bit PCM WAV here, the
//   transcribe endpoint's input.
// - With VoiceOver on, a double tap and hold passes the touch through to the page, so the
//   same pointer events arrive.
import type { AudioPort } from "./audio";
import { OFFLINE_ANSWER } from "./session";

export const RATE = 16000;
export const HOLD_MS = 300;
export const MIN_MS = 400;
export const MAX_MS = 15000;
/** Capture goes on this long after letting go: the last syllable often trails the finger. */
export const POST_ROLL_MS = 250;

export const MIC_DENIED =
  "The microphone is not allowed, so I cannot hear questions. Type a question instead. Labels still work.";
export const TOO_SHORT = "Hold the screen while you ask, then let go.";

export type HoldState = "idle" | "pressed" | "listening" | "busy";
export type HoldEvent = "listen" | "send" | "too_short";

export class HoldToTalk {
  state: HoldState = "idle";
  private pressedAt = 0;
  private listenedAt = 0;

  down(t: number): HoldEvent[] {
    if (this.state === "idle") {
      this.state = "pressed";
      this.pressedAt = t;
    }
    return [];
  }

  /** Called on a timer while pressed or listening. */
  tick(t: number): HoldEvent[] {
    if (this.state === "pressed" && t - this.pressedAt >= HOLD_MS) {
      this.state = "listening";
      this.listenedAt = t;
      return ["listen"];
    }
    if (this.state === "listening" && t - this.listenedAt >= MAX_MS) {
      this.state = "busy";
      return ["send"];
    }
    return [];
  }

  up(t: number): HoldEvent[] {
    const out = this.tick(t);
    if (out.includes("send")) return out;
    if (this.state === "pressed") {
      this.state = "idle"; // a tap
      return out;
    }
    if (this.state === "listening") {
      if (t - this.listenedAt < MIN_MS) {
        this.state = "idle";
        return [...out, "too_short"];
      }
      this.state = "busy";
      return [...out, "send"];
    }
    return out;
  }

  /** The answer was spoken, or the question failed: ready for the next one. */
  done(): void {
    this.state = "idle";
  }

  /** Back to idle, as when the microphone could not open. */
  reset(): void {
    this.state = "idle";
  }
}

/** Downsampled by averaging the input samples each output sample covers (a box filter, so
 * speech above the new Nyquist does not fold back), upsampled by linear interpolation. */
export function resample(input: Float32Array, from: number, to: number = RATE): Float32Array {
  if (from === to) return input.slice();
  const n = Math.floor((input.length * to) / from);
  const out = new Float32Array(n);
  const step = from / to;
  for (let i = 0; i < n; i++) {
    const a = i * step;
    if (step <= 1) {
      const j = Math.floor(a);
      const f = a - j;
      out[i] = (input[j] ?? 0) * (1 - f) + (input[Math.min(j + 1, input.length - 1)] ?? 0) * f;
      continue;
    }
    const lo = Math.floor(a);
    const hi = Math.min(input.length, Math.floor(a + step));
    let sum = 0;
    for (let j = lo; j < hi; j++) sum += input[j] ?? 0;
    out[i] = hi > lo ? sum / (hi - lo) : 0;
  }
  return out;
}

/** A RIFF WAVE file of mono 16-bit little-endian PCM. */
export function encodeWav(samples: Float32Array, rate: number = RATE): Uint8Array {
  const data = samples.length * 2;
  const buf = new ArrayBuffer(44 + data);
  const v = new DataView(buf);
  const text = (at: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i));
  };
  text(0, "RIFF");
  v.setUint32(4, 36 + data, true);
  text(8, "WAVE");
  text(12, "fmt ");
  v.setUint32(16, 16, true); // fmt chunk size
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); // bytes a second
  v.setUint16(32, 2, true); // bytes a frame
  v.setUint16(34, 16, true); // bits a sample
  text(36, "data");
  v.setUint32(40, data, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    v.setInt16(44 + i * 2, s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff), true);
  }
  return new Uint8Array(buf);
}

/** What VoiceAsk needs from a microphone. open() rejects when permission is denied. */
export interface MicPort {
  open(): Promise<void>;
  start(): void;
  stop(): { samples: Float32Array; rate: number };
}

// The worklet: posts each render quantum of input (128 samples, under 3 ms) to the page,
// so stopping loses at most one quantum of the post-roll.
const TAP = `class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice());
    return true;
  }
}
registerProcessor("tt-tap", Tap);`;

export class WebAudioMic implements MicPort {
  private ctx: AudioContext | null = null;
  private chunks: Float32Array[] = [];
  private recording = false;

  constructor(
    private readonly media: MediaDevices = navigator.mediaDevices,
    private readonly makeContext: () => AudioContext = () => new AudioContext(),
  ) {}

  async open(): Promise<void> {
    if (this.ctx) {
      if (this.ctx.state !== "running") await this.ctx.resume();
      return;
    }
    const stream = await this.media.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const ctx = this.makeContext();
    if (ctx.state !== "running") await ctx.resume();
    const url = URL.createObjectURL(new Blob([TAP], { type: "text/javascript" }));
    await ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const node = new AudioWorkletNode(ctx, "tt-tap");
    node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      if (this.recording) this.chunks.push(e.data);
    };
    ctx.createMediaStreamSource(stream).connect(node);
    node.connect(ctx.destination); // pulled only when connected; it writes silence
    this.ctx = ctx;
  }

  start(): void {
    this.chunks = [];
    this.recording = true;
  }

  stop(): { samples: Float32Array; rate: number } {
    this.recording = false;
    const n = this.chunks.reduce((s, c) => s + c.length, 0);
    const samples = new Float32Array(n);
    let at = 0;
    for (const c of this.chunks) {
      samples.set(c, at);
      at += c.length;
    }
    this.chunks = [];
    return { samples, rate: this.ctx?.sampleRate ?? RATE };
  }
}

export interface VoiceDeps {
  audio: AudioPort;
  mic: MicPort;
  online: () => boolean;
  /** Sends the WAV and speaks the answer; resolves once it is spoken or has failed. */
  send: (wav: Uint8Array, releasedAt: number) => Promise<void>;
  now?: () => number;
  /** Timers, so tests can drive time. */
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (id: unknown) => void;
}

/** Hold to talk on top of the state machine: timers, earcons, the microphone, sending. */
export class VoiceAsk {
  readonly hold = new HoldToTalk();
  private timer: unknown = null;
  private denied = false;
  /** The microphone is recording this hold. False while it is still opening. */
  private capturing = false;
  private readonly now: () => number;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (id: unknown) => void;
  /** The last question's encode time, for the latency log. */
  encodeMs = NaN;

  constructor(private readonly deps: VoiceDeps) {
    this.now = deps.now ?? (() => performance.now());
    this.setTimer = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer = deps.clearTimer ?? ((id) => { clearTimeout(id as ReturnType<typeof setTimeout>); });
  }

  /** True when the press started a question, so the page can swallow the click after it. */
  get engaged(): boolean {
    return this.hold.state === "listening" || this.hold.state === "busy";
  }

  down(): void {
    if (this.hold.state !== "idle") return;
    this.hold.down(this.now());
    this.schedule();
  }

  up(): void {
    this.cancelTimer();
    void this.run(this.hold.up(this.now()));
  }

  private schedule(): void {
    this.cancelTimer();
    const wait = this.hold.state === "pressed" ? HOLD_MS : MAX_MS;
    this.timer = this.setTimer(() => {
      this.timer = null;
      void this.run(this.hold.tick(this.now()));
    }, wait);
  }

  private cancelTimer(): void {
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
  }

  private async run(events: HoldEvent[]): Promise<void> {
    const { audio, mic } = this.deps;
    for (const e of events) {
      if (e === "listen") {
        if (!this.deps.online()) {
          this.hold.reset();
          audio.say(OFFLINE_ANSWER);
          return;
        }
        if (this.denied) {
          this.hold.reset();
          audio.say(MIC_DENIED);
          return;
        }
        try {
          await mic.open();
        } catch {
          this.denied = true;
          this.hold.reset();
          audio.say(MIC_DENIED);
          return;
        }
        if (this.hold.state !== "listening") return; // let go while the microphone opened
        audio.stop();
        mic.start();
        this.capturing = true;
        audio.listenStart();
        this.schedule();
      } else if (e === "too_short") {
        if (this.capturing) {
          mic.stop();
          audio.listenEnd();
        }
        this.capturing = false;
        audio.say(TOO_SHORT);
      } else if (!this.capturing) {
        // Let go while the microphone was still opening (the first hold asks permission):
        // nothing was recorded, so nothing is sent.
        this.hold.reset();
        audio.say(TOO_SHORT);
        return;
      } else {
        const releasedAt = this.now();
        await new Promise<void>((resolve) => { this.setTimer(resolve, POST_ROLL_MS); });
        const { samples, rate } = mic.stop();
        this.capturing = false;
        audio.listenEnd(); // after the post-roll, so the earcon is not in the recording
        const t = this.now();
        const wav = encodeWav(resample(samples, rate));
        this.encodeMs = this.now() - t;
        audio.thinking(true);
        try {
          await this.deps.send(wav, releasedAt);
        } finally {
          audio.thinking(false);
          this.hold.done();
        }
      }
    }
  }
}
