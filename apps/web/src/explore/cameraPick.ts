// Which camera Explore opens, what it fixes on it, and when it changed under the corners.
// The Gate B page runs a JS copy (spikes/tracking/lib/camera.js); both are tested on the same
// cases (spikes/tracking/test/camera_cases.json), so they choose and guard alike.
//
// - An iPhone's default rear camera is a virtual one ("Back Triple Camera", "Back Dual Wide
//   Camera") that switches lenses at close range, which moves the picture under calibrated
//   corners. The single wide lens, "Back Camera", does not switch, so it is chosen by deviceId
//   when enumerateDevices names it. Labels are empty until a camera is allowed, so the first
//   open goes by facingMode and the camera is reopened by deviceId once it is named.
// - Zoom, and focus once it has settled, are fixed only when getCapabilities() offers them,
//   with the names the Media Capture spec gives (zoom; focusMode "manual" or "single-shot").
// - A change of the video's size, device or zoom after the corners are set makes them wrong.

export const WIDE_LABEL = "back camera";
/** Continuous focus gets this long to settle before it is fixed. */
export const FOCUS_SETTLE_MS = 1500;

export interface CameraInfo {
  deviceId: string;
  label: string;
  kind: string;
}

/** The single wide rear lens, or null: then facingMode "environment" chooses. */
export function pickCamera(devices: readonly CameraInfo[]): { deviceId: string; label: string } | null {
  const d = devices.find((x) => x.kind === "videoinput" && x.deviceId && x.label.trim().toLowerCase() === WIDE_LABEL);
  return d ? { deviceId: d.deviceId, label: d.label } : null;
}

export interface LockPlan {
  zoom?: number;
  focusMode?: string;
}

interface Range {
  min?: number;
  max?: number;
}

/** What to fix, from what the track reports; nothing it does not offer. */
export function lockPlan(caps: Record<string, unknown> | null, settings: Record<string, unknown> | null): LockPlan {
  const out: LockPlan = {};
  const zoom = caps?.zoom as Range | undefined;
  if (zoom && typeof zoom.min === "number" && typeof zoom.max === "number") {
    const now = typeof settings?.zoom === "number" ? settings.zoom : 1;
    out.zoom = Math.min(zoom.max, Math.max(zoom.min, now));
  }
  const modes = caps?.focusMode;
  if (Array.isArray(modes)) {
    if (modes.includes("manual")) out.focusMode = "manual";
    else if (modes.includes("single-shot")) out.focusMode = "single-shot";
  }
  return out;
}

export interface CameraKey {
  width: number;
  height: number;
  deviceId: string;
  zoom: number | null;
}

export function cameraKey(settings: Record<string, unknown> | null, width: number, height: number): CameraKey {
  return {
    width,
    height,
    deviceId: typeof settings?.deviceId === "string" ? settings.deviceId : "",
    zoom: typeof settings?.zoom === "number" ? settings.zoom : null,
  };
}

/** The fields that differ; empty when the camera is the one the corners were set on. */
export function cameraChanges(base: CameraKey, now: CameraKey): string[] {
  const out: string[] = [];
  if (base.width !== now.width || base.height !== now.height) out.push("size");
  if (base.deviceId !== now.deviceId) out.push("device");
  if (base.zoom !== null && now.zoom !== null && Math.abs(base.zoom - now.zoom) > 1e-3) out.push("zoom");
  return out;
}

export const CAMERA_CHANGED_TOUCH = "The camera changed. Tap Set corners to set them again.";
export const CAMERA_CHANGED_KEYS = "The camera changed. Press Set corners, or R, to set them again.";

/** Says once that the camera changed; quiet again once the corners are set on the new one. */
export class CameraWatch {
  private base: CameraKey | null = null;
  changed: string[] = [];

  rebase(key: CameraKey): void {
    this.base = key;
    this.changed = [];
  }

  /** True only on the check that first finds a change. */
  check(key: CameraKey): boolean {
    if (!this.base || this.changed.length) return false;
    const c = cameraChanges(this.base, key);
    if (!c.length) return false;
    this.changed = c;
    return true;
  }
}

export interface OpenedCamera {
  stream: MediaStream;
  /** "Back Camera, by deviceId" or "facingMode environment (no Back Camera listed)". */
  how: string;
  label: string;
}

type Media = Pick<MediaDevices, "getUserMedia" | "enumerateDevices">;

/** Opens the wide rear lens when it is listed, else the rear camera by facingMode. */
export async function openCamera(media: Media, size: MediaTrackConstraints, deviceId?: string): Promise<OpenedCamera> {
  const open = (which: MediaTrackConstraints) => media.getUserMedia({ audio: false, video: { ...which, ...size } });
  const labelOf = (s: MediaStream) => s.getVideoTracks()[0]?.label ?? "";
  if (deviceId) {
    const s = await open({ deviceId: { exact: deviceId } });
    return { stream: s, how: "the camera picked", label: labelOf(s) };
  }
  const byId = async (id: string): Promise<MediaStream | null> => {
    try {
      return await open({ deviceId: { exact: id } });
    } catch {
      return null;
    }
  };
  const listed = pickCamera(await media.enumerateDevices().catch(() => []));
  if (listed) {
    const s = await byId(listed.deviceId);
    if (s) return { stream: s, how: "Back Camera, by deviceId", label: labelOf(s) };
    const f = await open({ facingMode: { ideal: "environment" } });
    return { stream: f, how: "facingMode environment (Back Camera did not open)", label: labelOf(f) };
  }
  const first = await open({ facingMode: { ideal: "environment" } });
  // Allowed now, so the labels are filled in.
  const named = pickCamera(await media.enumerateDevices().catch(() => []));
  if (!named) return { stream: first, how: "facingMode environment (no Back Camera listed)", label: labelOf(first) };
  if (named.deviceId === first.getVideoTracks()[0]?.getSettings().deviceId) {
    return { stream: first, how: "Back Camera, by facingMode", label: labelOf(first) };
  }
  for (const t of first.getTracks()) t.stop();
  const s = await byId(named.deviceId);
  if (s) return { stream: s, how: "Back Camera, by deviceId", label: labelOf(s) };
  const again = await open({ facingMode: { ideal: "environment" } });
  return { stream: again, how: "facingMode environment (Back Camera did not open)", label: labelOf(again) };
}

type Track = Pick<MediaStreamTrack, "applyConstraints"> & {
  getCapabilities?: () => object;
  getSettings: () => MediaTrackSettings;
};

export interface LockResult {
  capabilities: Record<string, unknown> | null;
  plan: LockPlan;
  applied: string[];
  failed: string[];
}

/** Fixes the zoom now and the focus after FOCUS_SETTLE_MS, each only when offered. */
export async function lockCamera(track: Track, wait: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms))): Promise<LockResult> {
  const caps = typeof track.getCapabilities === "function" ? (track.getCapabilities() as Record<string, unknown>) : null;
  const plan = lockPlan(caps, track.getSettings() as Record<string, unknown>);
  const out: LockResult = { capabilities: caps, plan, applied: [], failed: [] };
  const apply = async (name: string, c: Record<string, unknown>) => {
    try {
      await track.applyConstraints({ advanced: [c] });
      out.applied.push(name);
    } catch (err) {
      out.failed.push(`${name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  };
  if (plan.zoom !== undefined) await apply(`zoom ${String(plan.zoom)}`, { zoom: plan.zoom });
  if (plan.focusMode) {
    await wait(FOCUS_SETTLE_MS);
    await apply(`focusMode ${plan.focusMode}`, { focusMode: plan.focusMode });
  }
  return out;
}

/** The device check's line for the camera's zoom and focus, as the track reports them. */
export function lockDetail(r: LockResult, settings: Record<string, unknown> | null): string {
  const caps = r.capabilities;
  if (!caps) return "getCapabilities() is not supported here: zoom and focus are left to the camera.";
  const zoom = caps.zoom as Range | undefined;
  const shown = (v: unknown) => (typeof v === "number" || typeof v === "string" ? String(v) : "unknown");
  const modes = caps.focusMode;
  const parts = [
    zoom ? `zoom ${shown(zoom.min)} to ${shown(zoom.max)}, now ${shown(settings?.zoom)}` : "no zoom control",
    Array.isArray(modes) ? `focus modes ${modes.map(shown).join(", ")}, now ${shown(settings?.focusMode)}` : "no focus control",
    r.applied.length ? `fixed: ${r.applied.join(", ")}` : "nothing fixed",
    ...(r.failed.length ? [`refused: ${r.failed.join("; ")}`] : []),
  ];
  return `${parts.join(". ")}.`;
}
