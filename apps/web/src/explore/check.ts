// /explore?check=1: what this device can do for Explore, checked one by one after a press,
// since the camera, the microphone, speech and the wake lock all need a user gesture.
// - Secure page: the camera and the microphone need HTTPS (npm run dev:phone on the LAN).
// - Camera: opens the rear camera when there is one; says which way it faces.
// - Camera choice, zoom and focus: which lens opened and why, what zoom and focus the camera
//   offers and what was fixed, and the raw capabilities and settings (cameraPick.ts).
// - Hand tracker: the page's tracker (loaded with the page), on that camera. The check waits
//   for it to warm up (a first result, on GPU or after the fallback to CPU), then measures
//   SAMPLE_MS: frames a second, ms a frame, the delegate in use, time to first result.
// - Local voice: a speech voice that works offline (localService), as Explore needs.
// - Screen Wake Lock: requested first in the tap, held, then released (wakeLock.ts).
// - Microphone: opened, for spoken questions.
import { pickVoice } from "./audio";
import { type LockResult, lockDetail } from "./cameraPick";
import type { Delegate } from "./warmup";

export type CheckState = "ok" | "warn" | "fail";

export interface CheckResult {
  name: string;
  state: CheckState;
  detail: string;
}

export const SAMPLE_MS = 5000;
const MIN_FPS = 10;

export function cameraResult(settings: MediaTrackSettings | null, label: string, error?: string): CheckResult {
  if (!settings) return { name: "Camera", state: "fail", detail: `The camera did not open${error ? `: ${error}` : ""}.` };
  const size = settings.width && settings.height ? `${String(settings.width)} x ${String(settings.height)}` : "size unknown";
  const facing = settings.facingMode;
  if (facing === "environment") return { name: "Camera", state: "ok", detail: `Rear camera, ${size}${label ? `, ${label}` : ""}.` };
  const which = facing === "user" ? "the front camera" : "a camera that does not say which way it faces";
  return { name: "Camera", state: "warn", detail: `Opened ${which}, ${size}${label ? `, ${label}` : ""}. Explore needs the rear camera looking down at the sheet.` };
}

/** Which camera opened and how it was chosen (cameraPick.ts). A virtual multi-lens camera
 * switches lenses at close range, which moves the picture under the corners. */
export function choiceResult(how: string, label: string, settings: MediaTrackSettings | null): CheckResult {
  const s = settings ?? {};
  const size = s.width && s.height ? `${String(s.width)} x ${String(s.height)}` : "size unknown";
  const fps = typeof s.frameRate === "number" ? ` at ${s.frameRate.toFixed(0)} fps` : "";
  const detail = `${label || "No label"}, chosen by ${how}; ${size}${fps}.`;
  const multi = /\b(triple|dual)\b/i.test(label);
  return multi
    ? { name: "Camera choice", state: "warn", detail: `${detail} A multi-lens camera can switch lenses close to the sheet.` }
    : { name: "Camera choice", state: "ok", detail };
}

/** Zoom and focus as the camera reports them, and what was fixed (cameraPick.ts). */
export function zoomFocusResult(lock: LockResult | null, settings: MediaTrackSettings | null): CheckResult {
  if (!lock) return { name: "Zoom and focus", state: "warn", detail: "No camera track to read." };
  const detail = lockDetail(lock, settings as Record<string, unknown> | null);
  const ok = lock.applied.length > 0 && lock.failed.length === 0;
  return { name: "Zoom and focus", state: ok ? "ok" : "warn", detail };
}

/** The raw capabilities and settings, as the device reported them. */
export function reportsResult(lock: LockResult | null, settings: MediaTrackSettings | null): CheckResult {
  return { name: "Camera reports", state: "ok", detail: JSON.stringify({ capabilities: lock?.capabilities ?? null, settings }) };
}

/** The tracker as the check reads it, after warm-up (tracker.ts). */
export interface WarmTracker {
  delegate: Delegate;
  timeToFirstResultMs: number | null;
  fellBack: string | null;
}

/** Frames and ms a frame over the sample, after warm-up; never "loading": a tracker that
 * gave no result within the warm-up wait is a failure with its delegate. */
export function handsResult(frames: number, ms: number, t: WarmTracker, inferMs: number[], warm = true): CheckResult {
  if (!warm) {
    return { name: "Hand tracker", state: "fail", detail: `No result within ${String(WARM_MAX_MS / 1000)} s of warming up, on the ${t.delegate}.` };
  }
  const fps = ms > 0 ? (frames * 1000) / ms : 0;
  const infer = inferMs.length ? inferMs.reduce((a, b) => a + b, 0) / inferMs.length : NaN;
  const first = t.timeToFirstResultMs;
  const detail = [
    `${fps.toFixed(1)} frames a second`,
    `delegate ${t.delegate}${t.fellBack ? ` (GPU dropped: ${t.fellBack})` : ""}`,
    ...(Number.isFinite(infer) ? [`${infer.toFixed(0)} ms a frame`] : []),
    ...(first !== null ? [`first result ${(first / 1000).toFixed(1)} s after the first frame`] : []),
  ].join(", ") + ".";
  if (frames === 0) return { name: "Hand tracker", state: "fail", detail: `No frame came back. ${detail}` };
  return { name: "Hand tracker", state: fps >= MIN_FPS ? "ok" : "warn", detail };
}

/** How long the check waits for the first result: the GPU's fallback time, a CPU start
 * after it, and a cold model download on a slow network. */
export const WARM_MAX_MS = 30000;

export interface HandSample {
  reset(): void;
  read(): { frames: number; inferMs: number[] };
}

/** Waits for the tracker to warm up (a first result, on GPU or after the fallback to CPU),
 * then measures for SAMPLE_MS. Nothing before the first result counts. */
export async function measureHands(
  t: WarmTracker & { whenWarm(maxMs: number): Promise<boolean> },
  sample: HandSample,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
  now: () => number = () => performance.now(),
): Promise<CheckResult> {
  const warm = await t.whenWarm(WARM_MAX_MS);
  if (!warm) return handsResult(0, 0, t, [], false);
  sample.reset();
  const t0 = now();
  await sleep(SAMPLE_MS);
  const { frames, inferMs } = sample.read();
  return handsResult(frames, now() - t0, t, inferMs);
}

export function voiceResult(voices: readonly SpeechSynthesisVoice[] | null): CheckResult {
  if (!voices) return { name: "Local voice", state: "fail", detail: "This browser has no speech synthesis." };
  const v = pickVoice(voices);
  if (!v) return { name: "Local voice", state: "fail", detail: `No voice works offline (${String(voices.length)} voices, all need the network). Use a screen reader.` };
  return { name: "Local voice", state: "ok", detail: `${v.name} (${v.lang}), works offline.` };
}

export function wakeResult(supported: boolean, error?: string): CheckResult {
  if (!supported) return { name: "Screen Wake Lock", state: "fail", detail: "Not supported here: set Auto-Lock to Never while exploring." };
  if (error) return { name: "Screen Wake Lock", state: "fail", detail: `Refused: ${error}.` };
  return { name: "Screen Wake Lock", state: "ok", detail: "Held and released: the screen can stay on while exploring." };
}

export function micResult(error?: string): CheckResult {
  return error
    ? { name: "Microphone", state: "fail", detail: `Not allowed or not found: ${error}. Spoken questions will not work; typed ones will.` }
    : { name: "Microphone", state: "ok", detail: "Opened: spoken questions can work." };
}

export function secureResult(secure: boolean): CheckResult {
  return secure
    ? { name: "Secure page", state: "ok", detail: "A secure page (HTTPS, or this computer): the camera and the microphone are allowed to ask." }
    : { name: "Secure page", state: "fail", detail: "Not HTTPS: the camera and the microphone are blocked. On the LAN, run npm run dev:phone." };
}

export function summary(results: readonly CheckResult[]): string {
  const bad = results.filter((r) => r.state !== "ok").map((r) => r.name);
  return bad.length ? `${String(bad.length)} of ${String(results.length)} checks need a look: ${bad.join(", ")}.` : `All ${String(results.length)} checks pass.`;
}
