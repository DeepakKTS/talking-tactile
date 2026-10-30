import { describe, expect, it } from "vitest";
import type { AudioPort } from "./audio";
import { OFFLINE_ANSWER } from "./session";
import { HOLD_MS, HoldToTalk, MAX_MS, MIC_DENIED, MIN_MS, type MicPort, POST_ROLL_MS, RATE, TOO_SHORT, VoiceAsk, encodeWav, resample } from "./voice";

describe("WAV encoder", () => {
  it("writes a RIFF WAVE header for mono 16-bit PCM at 16 kHz, then the samples", () => {
    const wav = encodeWav(new Float32Array([0, 1, -1, 0.5]));
    const v = new DataView(wav.buffer);
    const text = (at: number, n: number) => String.fromCharCode(...wav.slice(at, at + n));
    expect(wav.length).toBe(44 + 8);
    expect([text(0, 4), text(8, 4), text(12, 4), text(36, 4)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(v.getUint32(4, true)).toBe(36 + 8);
    expect([v.getUint16(20, true), v.getUint16(22, true), v.getUint32(24, true)]).toEqual([1, 1, RATE]);
    expect([v.getUint32(28, true), v.getUint16(32, true), v.getUint16(34, true), v.getUint32(40, true)]).toEqual([RATE * 2, 2, 16, 8]);
    expect([0, 1, 2, 3].map((i) => v.getInt16(44 + i * 2, true))).toEqual([0, 32767, -32768, 16384]);
  });

  it("clips samples outside -1 to 1", () => {
    const v = new DataView(encodeWav(new Float32Array([2, -3])).buffer);
    expect([v.getInt16(44, true), v.getInt16(46, true)]).toEqual([32767, -32768]);
  });
});

describe("resample", () => {
  it("takes 48 kHz to 16 kHz by averaging, keeping a steady level", () => {
    const out = resample(new Float32Array(48000).fill(0.25), 48000);
    expect(out.length).toBe(16000);
    expect(out.every((x) => Math.abs(x - 0.25) < 1e-6)).toBe(true);
  });

  it("averages away a tone above the new Nyquist", () => {
    const tone = Float32Array.from({ length: 4800 }, (_, i) => (i % 3 === 0 ? 1 : -0.5)); // 16 kHz at 48 kHz
    const out = resample(tone, 48000);
    expect(Math.max(...out.map(Math.abs))).toBeLessThan(1e-6);
  });

  it("keeps 16 kHz as it is and interpolates up from 8 kHz", () => {
    expect(Array.from(resample(new Float32Array([0.1, 0.2]), 16000))).toEqual([
      expect.closeTo(0.1), expect.closeTo(0.2),
    ]);
    const up = resample(new Float32Array([0, 1, 0, 1]), 8000);
    expect(up.length).toBe(8);
    expect(up[1]).toBeCloseTo(0.5);
  });
});

describe("hold to talk", () => {
  it("a tap does nothing", () => {
    const h = new HoldToTalk();
    h.down(0);
    expect(h.tick(HOLD_MS - 1)).toEqual([]);
    expect(h.up(HOLD_MS - 1)).toEqual([]);
    expect(h.state).toBe("idle");
  });

  it("a hold listens, and letting go sends; holds are ignored until done", () => {
    const h = new HoldToTalk();
    h.down(0);
    expect(h.tick(HOLD_MS)).toEqual(["listen"]);
    expect(h.up(HOLD_MS + MIN_MS)).toEqual(["send"]);
    expect(h.state).toBe("busy");
    h.down(5000);
    expect(h.tick(9000)).toEqual([]);
    h.done();
    expect(h.state).toBe("idle");
  });

  it("a recording under MIN_MS is too short; one that reaches MAX_MS is sent", () => {
    const short = new HoldToTalk();
    short.down(0);
    short.tick(HOLD_MS);
    expect(short.up(HOLD_MS + MIN_MS - 1)).toEqual(["too_short"]);
    const long = new HoldToTalk();
    long.down(0);
    long.tick(HOLD_MS);
    expect(long.tick(HOLD_MS + MAX_MS)).toEqual(["send"]);
    expect(long.up(HOLD_MS + MAX_MS + 10)).toEqual([]);
  });

  it("letting go late still listens first, then sends", () => {
    const h = new HoldToTalk();
    h.down(0);
    expect(h.up(HOLD_MS + 1)).toEqual(["listen", "too_short"]);
  });
});

class Sounds implements AudioPort {
  log: string[] = [];
  speaking = false;
  lastSaid = "";
  earcon() { return 0; }
  exitTick() { return 0; }
  beep() { return 0; }
  chime() { return 0; }
  listenStart() { this.log.push("listen start"); return 0; }
  listenEnd() { this.log.push("listen end"); return 0; }
  thinking(on: boolean) { this.log.push(on ? "thinking" : "thinking off"); }
  say(text: string) { this.log.push(`say ${text}`); }
  stop() { this.log.push("stop"); }
}

class Mic implements MicPort {
  opened = 0;
  constructor(private readonly deny = false) {}
  open() {
    this.opened += 1;
    return this.deny ? Promise.reject(new DOMException("denied", "NotAllowedError")) : Promise.resolve();
  }
  start() {}
  stop() { return { samples: new Float32Array(4800).fill(0.1), rate: 48000 }; }
}

function rig(opts: { deny?: boolean; online?: boolean } = {}) {
  let now = 0;
  const timers: { at: number; fn: () => void }[] = [];
  const audio = new Sounds();
  const mic = new Mic(opts.deny);
  const sent: Uint8Array[] = [];
  const v = new VoiceAsk({
    audio, mic, online: () => opts.online ?? true,
    send: (wav) => { sent.push(wav); return Promise.resolve(); },
    now: () => now,
    setTimer: (fn, ms) => { const t = { at: now + ms, fn }; timers.push(t); return t; },
    clearTimer: (t) => { const i = timers.indexOf(t as (typeof timers)[number]); if (i >= 0) timers.splice(i, 1); },
  });
  const advance = async (ms: number) => {
    now += ms;
    for (const t of timers.filter((x) => x.at <= now)) {
      timers.splice(timers.indexOf(t), 1);
      t.fn();
    }
    await new Promise((r) => setTimeout(r, 0));
  };
  return { v, audio, mic, sent, advance };
}

describe("voice ask", () => {
  it("holds, listens with an earcon, sends a 16 kHz WAV on release with the thinking tone", async () => {
    const { v, audio, sent, advance } = rig();
    v.down();
    await advance(HOLD_MS);
    expect(audio.log).toEqual(["stop", "listen start"]);
    expect(v.engaged).toBe(true);
    await advance(1000);
    v.up();
    await advance(POST_ROLL_MS);
    expect(audio.log).toEqual(["stop", "listen start", "listen end", "thinking", "thinking off"]);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.length).toBe(44 + 1600 * 2); // 0.1 s at 48 kHz, as 16 kHz samples
    expect(v.hold.state).toBe("idle");
  });

  it("says the microphone is not allowed, and keeps saying so without asking again", async () => {
    const { v, audio, mic, sent, advance } = rig({ deny: true });
    for (let i = 0; i < 2; i++) {
      v.down();
      await advance(HOLD_MS);
      v.up();
      await advance(0);
    }
    expect(audio.log).toEqual([`say ${MIC_DENIED}`, `say ${MIC_DENIED}`]);
    expect(mic.opened).toBe(1);
    expect(sent).toEqual([]);
  });

  it("offline, says questions need the network and records nothing", async () => {
    const { v, audio, mic, advance } = rig({ online: false });
    v.down();
    await advance(HOLD_MS);
    v.up();
    await advance(0);
    expect(audio.log).toEqual([`say ${OFFLINE_ANSWER}`]);
    expect(mic.opened).toBe(0);
  });

  it("a tap or a too short hold sends nothing", async () => {
    const { v, audio, sent, advance } = rig();
    v.down();
    await advance(HOLD_MS - 50);
    v.up();
    await advance(0);
    expect(audio.log).toEqual([]);
    v.down();
    await advance(HOLD_MS);
    await advance(MIN_MS - 100);
    v.up();
    await advance(0);
    expect(audio.log.slice(-2)).toEqual(["listen end", `say ${TOO_SHORT}`]);
    expect(sent).toEqual([]);
  });
});

describe("post-roll", () => {
  it("keeps capturing 250 ms after release, so the last 250 ms of the signal is in the WAV", async () => {
    let now = 0;
    let releasedAt = Infinity;
    const timers: { at: number; fn: () => void }[] = [];
    // A microphone on the clock: 16 samples a millisecond, 0.25 before release, 0.75 after.
    let startedAt = 0;
    const log: string[] = [];
    const mic: MicPort = {
      open: () => Promise.resolve(),
      start: () => { startedAt = now; },
      stop: () => {
        log.push("mic stop");
        const n = (now - startedAt) * 16;
        return { samples: Float32Array.from({ length: n }, (_, i) => (startedAt + i / 16 >= releasedAt ? 0.75 : 0.25)), rate: RATE };
      },
    };
    const audio = new Sounds();
    audio.listenEnd = () => { log.push("listen end"); return 0; };
    const sent: Uint8Array[] = [];
    const v = new VoiceAsk({
      audio, mic, online: () => true,
      send: (wav) => { sent.push(wav); return Promise.resolve(); },
      now: () => now,
      setTimer: (fn, ms) => { const t = { at: now + ms, fn }; timers.push(t); return t; },
      clearTimer: (t) => { const i = timers.indexOf(t as (typeof timers)[number]); if (i >= 0) timers.splice(i, 1); },
    });
    const advance = async (ms: number) => {
      now += ms;
      for (const t of timers.filter((x) => x.at <= now)) {
        timers.splice(timers.indexOf(t), 1);
        t.fn();
      }
      await new Promise((r) => setTimeout(r, 0));
    };
    v.down();
    await advance(HOLD_MS);
    await advance(1000);
    releasedAt = now;
    v.up();
    await advance(POST_ROLL_MS - 1);
    expect(sent).toEqual([]); // still capturing
    await advance(1);
    expect(log).toEqual(["mic stop", "listen end"]); // the release earcon after the capture
    const wav = sent[0];
    if (!wav) throw new Error("nothing sent");
    const d = new DataView(wav.buffer);
    const samples = (wav.length - 44) / 2;
    const at = (i: number) => d.getInt16(44 + 2 * i, true) / 0x7fff;
    expect(samples).toBe((1000 + POST_ROLL_MS) * 16);
    const tail = POST_ROLL_MS * 16;
    for (let i = samples - tail; i < samples; i++) expect(at(i)).toBeCloseTo(0.75, 3);
    expect(at(samples - tail - 1)).toBeCloseTo(0.25, 3);
  });
});
