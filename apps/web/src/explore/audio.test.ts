// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import { AudioEngine, type AudioDeps, type SpeechLike, type UtteranceLike } from "./audio";

class FakeBuffer {
  constructor(
    readonly channels: number,
    readonly length: number,
    readonly sampleRate: number,
  ) {
    this.data = new Float32Array(length);
  }
  data: Float32Array;
  getChannelData() {
    return this.data;
  }
}

class FakeContext {
  sampleRate = 48000;
  currentTime = 0;
  state = "running";
  destination = {};
  buffers: FakeBuffer[] = [];
  started: { buffer: FakeBuffer | null; at: number }[] = [];
  createBuffer(ch: number, len: number, rate: number) {
    const b = new FakeBuffer(ch, len, rate);
    this.buffers.push(b);
    return b;
  }
  createBufferSource() {
    const node = {
      buffer: null as FakeBuffer | null,
      connect: () => node,
      start: (at = 0) => this.started.push({ buffer: node.buffer, at }),
      stop: () => undefined,
    };
    return node;
  }
  createGain() {
    const node = { gain: { value: 1 }, connect: () => node };
    return node;
  }
  resume() {
    return Promise.resolve();
  }
}

class FakeSpeech implements SpeechLike {
  speaking = false;
  pending = false;
  said: string[] = [];
  cancels: number[] = [];
  voices = [
    { name: "Network", lang: "en-US", localService: false, default: true },
    { name: "Samantha", lang: "en-US", localService: true, default: false },
  ];
  current: UtteranceLike | null = null;
  speak(u: UtteranceLike) {
    this.said.push(u.text);
    this.speaking = true;
    this.current = u;
  }
  cancel() {
    this.cancels.push(performance.now());
    this.speaking = false;
    this.current = null;
  }
  getVoices() {
    return this.voices as unknown as SpeechSynthesisVoice[];
  }
  finish() {
    const u = this.current;
    this.speaking = false;
    this.current = null;
    u?.onend?.(new Event("end") as SpeechSynthesisEvent);
  }
}

function setup(mode: "app" | "screen_reader" = "app") {
  const ctx = new FakeContext();
  const speech = new FakeSpeech();
  const mirror = document.createElement("div");
  const deps: AudioDeps = {
    context: () => ctx as unknown as AudioContext,
    speech,
    utterance: (text) => ({ text, voice: null, rate: 1, lang: "", onend: null, onerror: null }),
    mirror,
  };
  const engine = new AudioEngine(EXPLORE, deps, mode);
  return { ctx, speech, mirror, engine };
}

const pitches = [...Object.values(EXPLORE.earcons.texture_hz), EXPLORE.earcons.default_hz];

describe("audio engine", () => {
  it("renders every earcon, the tick, the beep and the chime once, at start", async () => {
    const { ctx, engine } = setup();
    await engine.start(pitches);
    const rendered = ctx.buffers.length;
    expect(rendered).toBe(new Set(pitches).size + 3);
    for (let i = 0; i < 50; i++) {
      engine.earcon(EXPLORE.earcons.texture_hz.dots);
      engine.exitTick();
      engine.beep();
    }
    engine.chime();
    expect(ctx.buffers.length).toBe(rendered);
    expect(ctx.started).toHaveLength(151);
  });

  it("plays each earcon at its own pitch, for tone_ms", async () => {
    const { ctx, engine } = setup();
    await engine.start(pitches);
    engine.earcon(EXPLORE.earcons.texture_hz.grid);
    const b = ctx.started[0]?.buffer;
    expect(b?.length).toBe(Math.round((EXPLORE.earcons.tone_ms / 1000) * ctx.sampleRate));
    // A sine at f crosses zero going up f times a second.
    const d = b?.data ?? new Float32Array();
    let ups = 0;
    for (let i = 1; i < d.length; i++) if ((d[i - 1] ?? 0) <= 0 && (d[i] ?? 0) > 0) ups++;
    const hz = ups / (d.length / ctx.sampleRate);
    expect(Math.abs(hz - EXPLORE.earcons.texture_hz.grid)).toBeLessThan(20);
  });

  it("is silent, without failing, before start", () => {
    const { ctx, engine } = setup();
    expect(Number.isNaN(engine.earcon(440))).toBe(true);
    expect(ctx.started).toHaveLength(0);
  });

  it("speaks with a local voice, so speech works offline, and mirrors every sentence", async () => {
    const { speech, mirror, engine } = setup();
    await engine.start(pitches);
    engine.say("Left lobe");
    expect(speech.said).toEqual(["Left lobe"]);
    expect((speech.current as unknown as { voice: { name: string } }).voice.name).toBe("Samantha");
    expect(mirror.textContent).toContain("Left lobe");
    expect(mirror.getAttribute("aria-live")).toBe("off"); // the app voice speaks; a screen reader must not
  });

  it("in screen reader mode writes to a polite live region and never uses the app voice", async () => {
    const { speech, mirror, engine } = setup("screen_reader");
    await engine.start(pitches);
    engine.say("Left lobe");
    engine.say("Right lobe");
    expect(speech.said).toEqual([]);
    expect(mirror.getAttribute("aria-live")).toBe("polite");
    expect(mirror.textContent).toContain("Right lobe");
  });

  it("switching to screen reader mode silences the app voice at once", async () => {
    const { speech, mirror, engine } = setup("app");
    await engine.start(pitches);
    engine.say("A long sentence");
    engine.setMode("screen_reader");
    expect(speech.speaking).toBe(false);
    expect(mirror.getAttribute("aria-live")).toBe("polite");
    engine.setMode("app");
    expect(mirror.getAttribute("aria-live")).toBe("off");
  });

  it("a new sentence replaces the one being spoken", async () => {
    const { speech, engine } = setup();
    await engine.start(pitches);
    engine.say("Outer chamber");
    engine.say("Inner core");
    expect(speech.cancels.length).toBe(1);
    expect(speech.said).toEqual(["Outer chamber", "Inner core"]);
    expect(engine.speaking).toBe(true);
    speech.finish();
    expect(engine.speaking).toBe(false);
  });

  it("Escape stops speech within 200 ms", async () => {
    const { speech, engine } = setup();
    await engine.start(pitches);
    engine.say("A very long answer that goes on and on");
    const t0 = performance.now();
    engine.stop();
    const took = (speech.cancels.at(-1) ?? Infinity) - t0;
    expect(took).toBeLessThan(200);
    expect(engine.speaking).toBe(false);
    expect(speech.speaking).toBe(false);
  });

  it("remembers the last sentence for repeat", async () => {
    const { engine } = setup();
    await engine.start(pitches);
    engine.say("Stem");
    expect(engine.lastSaid).toBe("Stem");
  });
});
