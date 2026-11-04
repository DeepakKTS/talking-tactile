// /explore?figure=<id>[&version=<n>]. Works with no screen: one Start button, then keys and
// typed questions; every sentence is spoken (or left to the screen reader) and mirrored.
// The camera loop and the session live in refs, never in React state.
// Headless runs: ?source=script skips the camera and takes hands from window.__tt.inject,
// ?corners=x1,y1,...,x4,y4 sets the corners, ?stub=<ms> replaces MediaPipe with a delay.
import { useCallback, useEffect, useRef, useState } from "react";
import { EXPLORE } from "../shared/config";
import type { RegionsFile } from "../shared/regions";
import type { WorkerHand } from "../workers/protocol";
import { AudioEngine, type AudioPort, NO_LOCAL_VOICE, type VoiceMode, browserAudioDeps } from "./audio";
import { CameraLoop, type HandsFrame, askApi, askReplyApi, transcribeApi } from "./camera";
import { touchOnly } from "./device";
import { HandTracker } from "./tracker";
import { ScreenAwake } from "./wakeLock";
import { CornerClicks, loadCorners, parseQuad, saveCorners } from "./corners";
import { FingertipTracker } from "./fingertip";
import type { Side } from "./hands";
import { type Mat3, type Pt, type Quad, applyHomography, invertHomography, markCorners } from "./homography";
import { LoadError, type Version, loadPublished } from "./loader";
import { Metrics } from "./metrics";
import type { PumpStats } from "./pump";
import { DeviceCheck } from "./DeviceCheck";
import { ExploreSession, keyAction } from "./session";
import { VoiceAsk, WebAudioMic } from "./voice";

interface Settings {
  voice: VoiceMode;
  dominant: Side | "either";
  cameraMirrored: boolean;
}

const SETTINGS_KEY = "tt-explore-settings";
const DEFAULTS: Settings = { voice: "app", dominant: "either", cameraMirrored: false };
const TRACE_KEEP = 300;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function loadSettings(): Settings {
  try {
    const raw = JSON.parse(storage()?.getItem(SETTINGS_KEY) ?? "{}") as Partial<Settings>;
    return {
      voice: raw.voice === "screen_reader" ? "screen_reader" : "app",
      dominant: raw.dominant === "left" || raw.dominant === "right" ? raw.dominant : "either",
      cameraMirrored: raw.cameraMirrored === true,
    };
  } catch {
    return DEFAULTS;
  }
}

/** What a headless run reads: every sound and sentence, and the latency metrics. */
interface Trace {
  log: { kind: string; text?: string; hz?: number; at: number }[];
  metrics: Metrics;
  ready: boolean;
  started: boolean;
  calibrated: boolean;
  figure: string | null;
  camera: { readonly backend: string; readonly stats: PumpStats } | null;
  /** The page's hand tracker: the delegate in use, time to first result, frames a second. */
  tracker: HandTracker | null;
  inject: (hands: WorkerHand[], width: number, height: number, brightness?: number) => void;
  command: (text: string) => Promise<void>;
  /** The last spoken question's WAV, for a headless check of the encoding. */
  lastWav: Uint8Array | null;
}

declare global {
  interface Window {
    __tt?: Trace;
  }
}

class TracingAudio implements AudioPort {
  constructor(
    private readonly inner: AudioEngine,
    private readonly log: Trace["log"],
  ) {}
  private note(kind: string, at: number, extra: { text?: string; hz?: number } = {}): number {
    this.log.push({ kind, at, ...extra });
    if (this.log.length > TRACE_KEEP) this.log.shift();
    return at;
  }
  get speaking() {
    return this.inner.speaking;
  }
  get lastSaid() {
    return this.inner.lastSaid;
  }
  earcon(hz: number) {
    return this.note("earcon", this.inner.earcon(hz), { hz });
  }
  exitTick() {
    return this.note("exit", this.inner.exitTick());
  }
  beep() {
    return this.note("beep", this.inner.beep());
  }
  chime() {
    return this.note("chime", this.inner.chime());
  }
  listenStart() {
    return this.note("listen_start", this.inner.listenStart());
  }
  listenEnd() {
    return this.note("listen_end", this.inner.listenEnd());
  }
  thinking(on: boolean) {
    this.inner.thinking(on);
    this.note(on ? "thinking_on" : "thinking_off", performance.now());
  }
  say(text: string) {
    this.inner.say(text);
    this.note("say", performance.now(), { text });
  }
  spoke(at: number, text: string) {
    this.note("speech_start", at, { text });
  }
  stop() {
    this.inner.stop();
    this.note("stop", performance.now());
  }
}

function readParams() {
  const q = new URLSearchParams(window.location.search);
  const v = q.get("version");
  const version: Version = v && v !== "latest" ? Number(v) : "latest";
  return {
    figure: q.get("figure"),
    version,
    scripted: q.get("source") === "script",
    stubMs: Number(q.get("stub") ?? 0) || undefined,
    corners: parseQuad(q.get("corners")),
    check: q.get("check") === "1",
  };
}

export function ExplorePage() {
  const [{ check }] = useState(readParams);
  return check ? <DeviceCheck /> : <ExploreSheet />;
}

function ExploreSheet() {
  const [{ figure, version, scripted, stubMs, corners: given }] = useState(readParams);
  const [touch] = useState(() => touchOnly()); // a phone: say "tap", name no key

  const [file, setFile] = useState<RegionsFile | null>(null);
  const [notTouchable, setNotTouchable] = useState<string[]>([]);
  const [loadedVersion, setLoadedVersion] = useState<number | null>(null);
  const [status, setStatus] = useState(figure ? "Loading the sheet." : "");
  // A sheet that cannot load is said in an alert: Start stays off, so nothing else speaks.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [question, setQuestion] = useState("");
  const [noLocalVoice, setNoLocalVoice] = useState(false);
  const [heard, setHeard] = useState("");
  const voice = useRef<VoiceAsk | null>(null);

  const mirror = useRef<HTMLDivElement>(null);
  const startButton = useRef<HTMLButtonElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const session = useRef<ExploreSession | null>(null);
  const engine = useRef<AudioEngine | null>(null);
  const audio = useRef<AudioPort | null>(null);
  const camera = useRef<CameraLoop | null>(null);
  const handTracker = useRef<HandTracker | null>(null);
  const awake = useRef<ScreenAwake | null>(null);
  const tracker = useRef(new FingertipTracker(EXPLORE, { dominant: settings.dominant, cameraMirrored: settings.cameraMirrored }));
  const corners = useRef<CornerClicks | null>(null);
  const clicking = useRef(false);
  const view = useRef<{ toPx: Mat3 | null; quad: Quad | null; tip: Pt | null; pointing: boolean }>({
    toPx: null,
    quad: null,
    tip: null,
    pointing: false,
  });
  const trace = useRef<Trace>({
    log: [],
    metrics: new Metrics(),
    ready: false,
    started: false,
    calibrated: false,
    figure,
    camera: null,
    tracker: null,
    inject: () => undefined,
    command: () => Promise.resolve(),
    lastWav: null,
  });

  const say = useCallback((text: string) => {
    setStatus(text);
    audio.current?.say(text);
  }, []);

  // Load the published sheet. Explore never asks for a draft.
  useEffect(() => {
    if (!figure) return;
    let live = true;
    loadPublished(figure, version, { fetch: (u) => fetch(u), storage: storage() })
      .then(({ file: f, from, notTouchable: missing, version: loaded }) => {
        if (!live) return;
        setFile(f);
        setLoadedVersion(loaded);
        setNotTouchable(missing);
        setStatus(`${f.title}. ${from === "saved" ? "Opened the saved copy; the network is down. " : ""}Press Start.`);
        trace.current.ready = true;
      })
      .catch((err: unknown) => {
        if (live) setLoadError(err instanceof LoadError ? err.message : "The sheet could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, [figure, version]);

  // Start is disabled until the sheet loads, and a disabled button cannot take focus, so
  // focus it once it is ready: a keyboard user then only presses Enter.
  useEffect(() => {
    if (file && !started) startButton.current?.focus();
  }, [file, started]);

  const setCorners = useCallback((quad: Quad, w: number, h: number) => {
    if (!file) return;
    const c = new CornerClicks(file.page, EXPLORE.registration.mark_inset_mm, touch);
    const step = c.fromCorners(quad);
    if (step.kind !== "done") {
      say(step.prompt);
      return;
    }
    tracker.current.setCalibration(step.toMm);
    session.current?.resetTouch();
    view.current.toPx = invertHomography(step.toMm);
    view.current.quad = quad;
    trace.current.calibrated = true;
    saveCorners(storage(), w, h, quad);
  }, [file, say, touch]);

  const startCorners = useCallback(() => {
    if (!file) return;
    corners.current = new CornerClicks(file.page, EXPLORE.registration.mark_inset_mm, touch);
    clicking.current = true;
    const step = corners.current.start();
    if (step.kind === "next") say(`A helper sets the corners. ${step.prompt}`);
  }, [file, say, touch]);

  const onHands = useCallback((f: HandsFrame) => {
    const s = session.current;
    if (!s) return;
    trace.current.metrics.captureToLandmarksMs.push(f.receivedAt - f.capturedAt);
    s.sight(f.brightness, f.receivedAt);
    const tip = tracker.current.update(f.hands, f.width, f.height, f.receivedAt);
    view.current.tip = tip.p;
    view.current.pointing = tip.pointing;
    s.finger({ p: tip.p, t: f.receivedAt, receivedAt: f.receivedAt, capturedAt: f.capturedAt });
  }, []);

  const start = useCallback(async () => {
    if (!file || started) return;
    // First, before any await: Safari grants the Wake Lock only within the tap. Not awaited.
    void awake.current?.request();
    const m = mirror.current;
    if (!m) return;
    const eng = new AudioEngine(EXPLORE, browserAudioDeps(m), settings.voice);
    engine.current = eng;
    eng.onVoiceChange = () => { setNoLocalVoice(eng.noLocalVoice); };
    const port = new TracingAudio(eng, trace.current.log);
    audio.current = port;
    const s = new ExploreSession(file, EXPLORE, { audio: port, metrics: trace.current.metrics, ask: askApi, transcribe: transcribeApi, askReply: askReplyApi, notTouchable, touch, ...(loadedVersion === null ? {} : { version: loadedVersion }) });
    session.current = s;
    eng.onSpeechStart = (at, text) => {
      s.speechStarted(at, text);
      port.spoke(at, text);
    };
    const asker: VoiceAsk = new VoiceAsk({
      audio: port,
      mic: new WebAudioMic(),
      online: () => navigator.onLine,
      send: async (wav, releasedAt) => {
        trace.current.lastWav = wav;
        await s.askSpoken(wav, releasedAt, asker.encodeMs);
        setHeard(s.heard);
      },
    });
    voice.current = asker;
    await eng.start(s.pitches);
    setStarted(true);
    setStatus(`${file.title}. Exploring.`);
    trace.current.started = true;
    s.intro();

    if (scripted) {
      trace.current.inject = (hands, width, height, brightness = 1) => {
        const receivedAt = performance.now();
        onHands({ hands, width, height, capturedAt: receivedAt, receivedAt, inferMs: 0, brightness });
      };
      if (given) setCorners(given, 0, 0);
      return;
    }
    const v = video.current;
    if (!v) return;
    const t = handTracker.current;
    if (!t) return;
    const loop = new CameraLoop({ video: v, tracker: t, onHands });
    camera.current = loop;
    trace.current.camera = loop;
    try {
      await loop.start();
    } catch {
      // Start comes back (and takes the focus), so pressing it again retries the camera.
      loop.stop();
      camera.current = null;
      setStarted(false);
      say("The camera did not start. Allow the camera and press Start again.");
      return;
    }
    const saved = given ?? loadCorners(storage(), v.videoWidth, v.videoHeight);
    if (saved) setCorners(saved, v.videoWidth, v.videoHeight);
    else startCorners();
  }, [file, notTouchable, loadedVersion, started, settings.voice, scripted, given, onHands, say, setCorners, startCorners, touch]);

  // Keys work everywhere except while typing, where only Escape does.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = session.current;
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement;
      const action = keyAction(e.key);
      if (!s || !action || (typing && action !== "stop")) return;
      e.preventDefault();
      if (action === "stop") s.stop();
      else if (action === "recalibrate") startCorners();
      else if (action === "help") s.help();
      else if (action === "more") s.more();
      else if (action === "repeat") s.repeat();
      else s.here();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [startCorners]);

  // No text selection and no long-press callout on the page: holding to ask must not start
  // an iOS selection (seen on an iPhone: handles on "Set corners"). The body too, while
  // Explore is open. Text fields keep their own (FIELD_STYLE); no touch or pointer event is
  // cancelled, so VoiceOver's double tap and hold still reaches the page.
  useEffect(() => {
    const b = document.body.style;
    const props = ["user-select", "-webkit-user-select", "-webkit-touch-callout"];
    const before = props.map((k) => b.getPropertyValue(k));
    for (const k of props) b.setProperty(k, "none");
    const select = (e: Event) => {
      if (!inField(e.target)) e.preventDefault();
    };
    document.addEventListener("selectstart", select);
    return () => {
      document.removeEventListener("selectstart", select);
      props.forEach((k, i) => { b.setProperty(k, before[i] ?? ""); });
    };
  }, []);

  // Hold anywhere to ask out loud (voice.ts), except in a text field or a list to choose
  // from. A hold that started a question swallows the click its release would make.
  useEffect(() => {
    if (!started) return;
    const typing = (t: EventTarget | null) =>
      t instanceof HTMLInputElement || t instanceof HTMLSelectElement || t instanceof HTMLTextAreaElement;
    let swallow = false;
    const down = (e: PointerEvent) => {
      if (e.isPrimary && !typing(e.target)) voice.current?.down();
    };
    const up = (e: PointerEvent) => {
      if (!e.isPrimary || !voice.current) return;
      swallow = voice.current.engaged;
      voice.current.up();
    };
    const click = (e: MouseEvent) => {
      if (!swallow) return;
      swallow = false;
      e.preventDefault();
      e.stopPropagation();
    };
    const menu = (e: Event) => {
      if (!inField(e.target)) e.preventDefault(); // a long press opens no menu, but in the Ask box
    };
    document.addEventListener("pointerdown", down);
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", up);
    document.addEventListener("click", click, true);
    document.addEventListener("contextmenu", menu);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", up);
      document.removeEventListener("click", click, true);
      document.removeEventListener("contextmenu", menu);
    };
  }, [started]);

  useEffect(() => {
    trace.current.command = (text) => session.current?.command(text) ?? Promise.resolve();
    window.__tt = trace.current;
  }, []);

  useEffect(() => {
    try {
      storage()?.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      // Settings just do not persist.
    }
    engine.current?.setMode(settings.voice);
    tracker.current.setSettings({ dominant: settings.dominant, cameraMirrored: settings.cameraMirrored });
  }, [settings]);

  useEffect(() => () => camera.current?.stop(), []);

  // The hand tracker loads with the page (the model, the wasm, the GPU delegate), so Start
  // never waits for the download. Script mode has no camera and no tracker.
  useEffect(() => {
    if (scripted) return;
    const t = new HandTracker({
      maxHands: EXPLORE.hands.max_hands,
      onResult: (msg) => camera.current?.result(msg),
      onRestart: () => camera.current?.restart(),
      onStatus: setStatus,
      ...(stubMs ? { stubMs } : {}),
    });
    handTracker.current = t;
    trace.current.tracker = t;
    return () => {
      t.stop();
      handTracker.current = null;
    };
  }, [scripted, stubMs]);

  useEffect(() => {
    awake.current = new ScreenAwake(say);
  }, [say]);

  // The camera view, for the helper who clicks the corners.
  useEffect(() => {
    if (!started || scripted) return;
    let raf = 0;
    const draw = () => {
      const c = canvas.current;
      const v = video.current;
      const ctx = c?.getContext("2d");
      if (c && v && ctx && v.videoWidth) {
        if (c.width !== v.videoWidth) {
          c.width = v.videoWidth;
          c.height = v.videoHeight;
        }
        ctx.drawImage(v, 0, 0, c.width, c.height);
        drawOverlay(ctx, view.current, corners.current?.points ?? [], file);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [started, scripted, file]);

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = canvas.current;
    const cc = corners.current;
    if (!c || !cc || !clicking.current) return;
    const r = c.getBoundingClientRect();
    const p: Pt = [((e.clientX - r.left) / r.width) * c.width, ((e.clientY - r.top) / r.height) * c.height];
    const step = cc.click(p);
    if (step.kind === "next") {
      say(step.prompt);
      return;
    }
    clicking.current = false;
    if (step.kind === "crossed") {
      say(step.prompt);
      return;
    }
    setCorners(step.corners, c.width, c.height);
    say("Corners set. Touch the sheet.");
  };

  const onAsk = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = question;
    setQuestion("");
    void session.current?.command(text);
  };

  if (!figure) {
    return (
      <main>
        <h1>Explore</h1>
        <form method="get" action="/explore">
          <label>
            Figure id <input name="figure" required pattern="[0-9a-f]{64}" autoComplete="off" />
          </label>
          <button type="submit">Open sheet</button>
        </form>
      </main>
    );
  }

  return (
    <main style={{ WebkitTouchCallout: "none", WebkitUserSelect: "none", userSelect: "none", minHeight: "100vh" }}>
      <h1>Explore{file ? `: ${file.title}` : ""}</h1>
      {loadError ? <p role="alert">{loadError}</p> : <p>{status}</p>}
      {!started && (
        <button ref={startButton} type="button" onClick={() => void start()} disabled={!file} style={{ fontSize: "2rem", padding: "1rem 2rem" }}>
          Start exploring
        </button>
      )}
      {started && noLocalVoice && <p role="alert">{NO_LOCAL_VOICE}</p>}
      {started && (
        <>
          <form onSubmit={onAsk}>
            <label>
              Ask, or say where is, more, repeat, stop, what is here{" "}
              <input value={question} onChange={(e) => { setQuestion(e.target.value); }} autoComplete="off" style={FIELD_STYLE} />
            </label>
            <button type="submit">Ask</button>
          </form>
          <p>Hold anywhere on the screen to ask out loud, and let go when you are done.</p>
          {heard && <p aria-live="off">You asked: {heard}</p>}
          {!touch && <p>Keys: Escape stops speech. R sets the corners. H help. M more. Period repeats. W what is here.</p>}
          {!scripted && (
            <section aria-label="Camera view">
              <button type="button" onClick={startCorners}>Set corners (R)</button>
              <canvas ref={canvas} onClick={onCanvasClick} style={{ maxWidth: "100%", display: "block" }}
                aria-label={`Camera view. A helper ${touch ? "taps" : "clicks"} the four corner marks here, in order A, B, C, D.`} />
            </section>
          )}
        </>
      )}
      <video ref={video} playsInline muted hidden />
      <fieldset>
        <legend>Settings</legend>
        <label>
          Who speaks{" "}
          <select value={settings.voice} onChange={(e) => { setSettings({ ...settings, voice: e.target.value === "screen_reader" ? "screen_reader" : "app" }); }}>
            <option value="app">The app voice</option>
            <option value="screen_reader">My screen reader</option>
          </select>
        </label>{" "}
        <label>
          Pointing hand{" "}
          <select value={settings.dominant} onChange={(e) => { setSettings({ ...settings, dominant: e.target.value === "left" || e.target.value === "right" ? e.target.value : "either" }); }}>
            <option value="either">Either</option>
            <option value="right">Right</option>
            <option value="left">Left</option>
          </select>
        </label>{" "}
        <label>
          <input type="checkbox" checked={settings.cameraMirrored} onChange={(e) => { setSettings({ ...settings, cameraMirrored: e.target.checked }); }} />{" "}
          Camera image is mirrored
        </label>
      </fieldset>
      <h2>What was said</h2>
      <div ref={mirror} />
    </main>
  );
}

// The Ask box stays selectable and editable inside the unselectable page.
const FIELD_STYLE = { WebkitUserSelect: "text", userSelect: "text", WebkitTouchCallout: "default" } as const;

/** A text field or a list, where selection and the callout keep working. */
function inField(t: EventTarget | null): boolean {
  const el = t instanceof Element ? t : t instanceof Node ? t.parentElement : null;
  return el?.closest("input, textarea, select") != null;
}

function drawOverlay(
  ctx: CanvasRenderingContext2D,
  v: { toPx: Mat3 | null; quad: Quad | null; tip: Pt | null; pointing: boolean },
  clicks: readonly Pt[],
  file: RegionsFile | null,
): void {
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#ff00c8";
  ctx.font = "bold 20px system-ui";
  ctx.fillStyle = "#ff00c8";
  clicks.forEach(([x, y], i) => {
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, 2 * Math.PI);
    ctx.stroke();
    ctx.fillText("ABCD"[i] ?? "", x + 10, y - 10);
  });
  const toPx = v.toPx;
  if (!toPx || !file) return;
  ctx.beginPath();
  markCorners(file.page, EXPLORE.registration.mark_inset_mm).forEach((c, i) => {
    const [x, y] = applyHomography(toPx, c);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.stroke();
  if (v.tip) {
    const [x, y] = applyHomography(toPx, v.tip);
    ctx.beginPath();
    ctx.arc(x, y, 9, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillText(v.pointing ? "pointing" : "hand", x + 12, y + 6);
  }
}
