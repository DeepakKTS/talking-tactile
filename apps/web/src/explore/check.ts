// /explore?check=1: what this device can do for Explore, checked one by one after a press,
// since the camera, the microphone, speech and the wake lock all need a user gesture.
// - Secure page: the camera and the microphone need HTTPS (npm run dev:phone on the LAN).
// - Camera: opens the rear camera when there is one; says which way it faces.
// - Hand tracker: the hand worker on that camera for SAMPLE_MS: frames a second and the
//   MediaPipe delegate it got, GPU or CPU.
// - Local voice: a speech voice that works offline (localService), as Explore needs.
// - Screen Wake Lock: held and released, so the screen stays on while exploring.
// - Microphone: opened, for spoken questions.
import { pickVoice } from "./audio";

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

export function handsResult(frames: number, ms: number, backend: string, inferMs: number[]): CheckResult {
  const fps = ms > 0 ? (frames * 1000) / ms : 0;
  const infer = inferMs.length ? inferMs.reduce((a, b) => a + b, 0) / inferMs.length : NaN;
  const delegate = /\bGPU\b/.test(backend) ? "GPU" : /\bCPU\b/.test(backend) ? "CPU" : backend || "not loaded";
  const detail = `${fps.toFixed(1)} frames a second, delegate ${delegate}${Number.isFinite(infer) ? `, ${infer.toFixed(0)} ms a frame` : ""}.`;
  if (frames === 0) return { name: "Hand tracker", state: "fail", detail: `No frame came back. ${detail}` };
  return { name: "Hand tracker", state: fps >= MIN_FPS ? "ok" : "warn", detail };
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
