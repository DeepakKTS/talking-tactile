// /explore?check=1: the device check (check.ts), as a page. Each result is a line of text;
// the summary is announced. A headless run reads window.__ttCheck. The hand tracker loads
// with the page (tracker.ts), so its download and GPU set-up are not part of the check; the
// Wake Lock is the first thing the Check tap asks for (wakeLock.ts).
import { useEffect, useRef, useState } from "react";
import { EXPLORE } from "../shared/config";
import { CameraLoop } from "./camera";
import { type CheckResult, SAMPLE_MS, cameraResult, handsResult, measureHands, micResult, secureResult, summary, voiceResult, wakeResult } from "./check";
import { HandTracker } from "./tracker";
import { ScreenAwake } from "./wakeLock";

declare global {
  interface Window {
    __ttCheck?: CheckResult[];
  }
}

const VOICES_WAIT_MS = 1000;
const message = (err: unknown) => (err instanceof Error ? `${err.name}: ${err.message}` : String(err));

async function voices(): Promise<SpeechSynthesisVoice[] | null> {
  if (!("speechSynthesis" in window)) return null;
  if (speechSynthesis.getVoices().length === 0) {
    await new Promise<void>((resolve) => {
      speechSynthesis.addEventListener("voiceschanged", () => { resolve(); }, { once: true });
      setTimeout(resolve, VOICES_WAIT_MS);
    });
  }
  return speechSynthesis.getVoices();
}

async function microphone(): Promise<CheckResult> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    for (const t of stream.getTracks()) t.stop();
    return micResult();
  } catch (err) {
    return micResult(message(err));
  }
}

async function cameraAndHands(video: HTMLVideoElement, tracker: HandTracker, cam: { current: CameraLoop | null }, onStatus: (s: string) => void): Promise<CheckResult[]> {
  let frames = 0;
  const infer: number[] = [];
  const loop = new CameraLoop({ video, tracker, onHands: (f) => { frames += 1; infer.push(f.inferMs); } });
  cam.current = loop;
  try {
    await loop.start();
  } catch (err) {
    loop.stop();
    cam.current = null;
    return [cameraResult(null, "", message(err)), handsResult(0, 0, tracker, [], false)];
  }
  const track = video.srcObject instanceof MediaStream ? video.srcObject.getVideoTracks()[0] : undefined;
  const camera = cameraResult(track?.getSettings() ?? null, track?.label ?? "");
  onStatus("Waiting for the hand tracker to warm up, then measuring for 5 seconds.");
  const hands = await measureHands(tracker, {
    reset: () => { frames = 0; infer.length = 0; },
    read: () => ({ frames, inferMs: [...infer] }),
  });
  loop.stop();
  cam.current = null;
  return [camera, hands];
}

export function DeviceCheck() {
  const [results, setResults] = useState<CheckResult[]>([]);
  const [status, setStatus] = useState("Press Check this device. It asks for the camera and the microphone.");
  const [busy, setBusy] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const tracker = useRef<HandTracker | null>(null);
  const camera = useRef<CameraLoop | null>(null);
  const awake = useRef<ScreenAwake | null>(null);

  // Loads with the page: the model, the wasm and the GPU delegate, before Check is pressed.
  useEffect(() => {
    const t = new HandTracker({
      maxHands: EXPLORE.hands.max_hands,
      onResult: (msg) => camera.current?.result(msg),
      onRestart: () => camera.current?.restart(),
      onStatus: () => undefined,
    });
    tracker.current = t;
    awake.current = new ScreenAwake((text) => {
      setStatus(text);
      if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    });
    return () => {
      t.stop();
      tracker.current = null;
    };
  }, []);

  const run = async () => {
    // First, before any await: Safari grants the Wake Lock only within the tap.
    const wake = awake.current?.request() ?? Promise.resolve("Not supported here");
    const v = video.current;
    const t = tracker.current;
    if (!v || !t || busy) return;
    setBusy(true);
    const out: CheckResult[] = [secureResult(window.isSecureContext)];
    const show = (r: CheckResult[]) => { out.push(...r); setResults([...out]); };
    setResults([...out]);
    setStatus(`Checking the camera and the hand tracker, about ${String(SAMPLE_MS / 1000)} seconds after it warms up.`);
    show(await cameraAndHands(v, t, camera, setStatus));
    show([voiceResult(await voices())]);
    const refused = await wake;
    if (refused === null) await awake.current?.release();
    show([refused === null ? wakeResult(true) : wakeResult(refused !== "Not supported here", refused)]);
    show([await microphone()]);
    window.__ttCheck = out;
    setStatus(summary(out));
    setBusy(false);
  };

  return (
    <main className="explore">
      <h1><img src="/brand/logo-mark.svg" alt="" width="48" height="32" />Explore: device check</h1>
      <p role="status" className="explore-status">{status}</p>
      <button type="button" onClick={() => void run()} disabled={busy} className="btn-primary btn-xl">
        Check this device
      </button>
      <ul aria-label="Device check" className="checks">
        {results.map((r) => (
          <li key={r.name} data-state={r.state}>
            <StateIcon state={r.state} />
            <span>
            <strong>{r.name}</strong>: {r.state === "ok" ? "OK" : r.state === "warn" ? "Look at this" : "Not working"}. {r.detail}
            </span>
          </li>
        ))}
      </ul>
      <video ref={video} playsInline muted className="check-video" />
    </main>
  );
}

/** A shape for each result, beside its words: a check, a triangle, a cross. */
function StateIcon({ state }: { state: CheckResult["state"] }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {state === "ok" ? (
        <><circle cx="12" cy="12" r="9.5" /><path d="M7.5 12.5l3 3 6-6.5" /></>
      ) : state === "warn" ? (
        <><path d="M12 3.5 21 20H3z" /><path d="M12 10v4.5" /><circle cx="12" cy="17.2" r="0.5" fill="currentColor" /></>
      ) : (
        <><circle cx="12" cy="12" r="9.5" /><path d="M8.5 8.5l7 7M15.5 8.5l-7 7" /></>
      )}
    </svg>
  );
}
