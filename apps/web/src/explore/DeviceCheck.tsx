// /explore?check=1: the device check (check.ts), as a page. Each result is a line of text;
// the summary is announced. A headless run reads window.__ttCheck.
import { useRef, useState } from "react";
import { EXPLORE } from "../shared/config";
import { CameraLoop } from "./camera";
import { type CheckResult, SAMPLE_MS, cameraResult, handsResult, micResult, secureResult, summary, voiceResult, wakeResult } from "./check";

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

async function wakeLock(): Promise<CheckResult> {
  if (!("wakeLock" in navigator)) return wakeResult(false);
  try {
    const lock = await navigator.wakeLock.request("screen");
    await lock.release();
    return wakeResult(true);
  } catch (err) {
    return wakeResult(true, message(err));
  }
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

async function cameraAndHands(video: HTMLVideoElement, onStatus: (s: string) => void): Promise<CheckResult[]> {
  let frames = 0;
  const infer: number[] = [];
  const loop = new CameraLoop({ video, maxHands: EXPLORE.hands.max_hands, onStatus, onHands: (f) => { frames += 1; infer.push(f.inferMs); } });
  try {
    await loop.start();
  } catch (err) {
    loop.stop();
    return [cameraResult(null, "", message(err)), handsResult(0, 1, loop.backend, [])];
  }
  const track = video.srcObject instanceof MediaStream ? video.srcObject.getVideoTracks()[0] : undefined;
  const camera = cameraResult(track?.getSettings() ?? null, track?.label ?? "");
  frames = 0;
  infer.length = 0;
  const t0 = performance.now();
  await new Promise((r) => setTimeout(r, SAMPLE_MS));
  const hands = handsResult(frames, performance.now() - t0, loop.backend, infer);
  loop.stop();
  return [camera, hands];
}

export function DeviceCheck() {
  const [results, setResults] = useState<CheckResult[]>([]);
  const [status, setStatus] = useState("Press Check this device. It asks for the camera and the microphone.");
  const [busy, setBusy] = useState(false);
  const video = useRef<HTMLVideoElement>(null);

  const run = async () => {
    const v = video.current;
    if (!v || busy) return;
    setBusy(true);
    const out: CheckResult[] = [secureResult(window.isSecureContext)];
    const show = (r: CheckResult[]) => { out.push(...r); setResults([...out]); };
    setResults([...out]);
    setStatus(`Checking the camera and the hand tracker, about ${String(SAMPLE_MS / 1000)} seconds.`);
    show(await cameraAndHands(v, () => undefined));
    show([voiceResult(await voices())]);
    show([await wakeLock()]);
    show([await microphone()]);
    window.__ttCheck = out;
    setStatus(summary(out));
    setBusy(false);
  };

  return (
    <main>
      <h1>Explore: device check</h1>
      <p role="status">{status}</p>
      <button type="button" onClick={() => void run()} disabled={busy} style={{ fontSize: "2rem", padding: "1rem 2rem" }}>
        Check this device
      </button>
      <ul aria-label="Device check">
        {results.map((r) => (
          <li key={r.name}>
            <strong>{r.name}</strong>: {r.state === "ok" ? "OK" : r.state === "warn" ? "Look at this" : "Not working"}. {r.detail}
          </li>
        ))}
      </ul>
      <video ref={video} playsInline muted style={{ maxWidth: "100%" }} />
    </main>
  );
}
