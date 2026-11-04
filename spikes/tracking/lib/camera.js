// The camera choice, zoom and focus fixing and the change check, as Explore does them
// (apps/web/src/explore/cameraPick.ts). Both are tested on the same cases
// (test/camera_cases.json), so the Gate B page opens and guards the camera as Explore does.
// - The single wide rear lens ("Back Camera") by deviceId when enumerateDevices names it,
//   over an iPhone's virtual multi-lens cameras, which switch lenses at close range.
// - Zoom, and focus once it has settled, fixed only when getCapabilities() offers them.
// - A change of the video's size, device or zoom after calibration makes the corners wrong.

export const WIDE_LABEL = "back camera";
export const FOCUS_SETTLE_MS = 1500;

export function pickCamera(devices) {
  const d = devices.find((x) => x.kind === "videoinput" && x.deviceId && x.label.trim().toLowerCase() === WIDE_LABEL);
  return d ? { deviceId: d.deviceId, label: d.label } : null;
}

export function lockPlan(caps, settings) {
  const out = {};
  const zoom = caps?.zoom;
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

export function cameraKey(settings, width, height) {
  return {
    width,
    height,
    deviceId: typeof settings?.deviceId === "string" ? settings.deviceId : "",
    zoom: typeof settings?.zoom === "number" ? settings.zoom : null,
  };
}

export function cameraChanges(base, now) {
  const out = [];
  if (base.width !== now.width || base.height !== now.height) out.push("size");
  if (base.deviceId !== now.deviceId) out.push("device");
  if (base.zoom !== null && now.zoom !== null && Math.abs(base.zoom - now.zoom) > 1e-3) out.push("zoom");
  return out;
}

export class CameraWatch {
  base = null;
  changed = [];

  rebase(key) {
    this.base = key;
    this.changed = [];
  }

  check(key) {
    if (!this.base || this.changed.length) return false;
    const c = cameraChanges(this.base, key);
    if (!c.length) return false;
    this.changed = c;
    return true;
  }
}

export async function openCamera(media, size, deviceId) {
  const open = (which) => media.getUserMedia({ audio: false, video: { ...which, ...size } });
  const labelOf = (s) => s.getVideoTracks()[0]?.label ?? "";
  if (deviceId) {
    const s = await open({ deviceId: { exact: deviceId } });
    return { stream: s, how: "the camera picked", label: labelOf(s) };
  }
  const byId = async (id) => {
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

export async function lockCamera(track, wait = (ms) => new Promise((r) => setTimeout(r, ms))) {
  const caps = typeof track.getCapabilities === "function" ? track.getCapabilities() : null;
  const plan = lockPlan(caps, track.getSettings());
  const out = { capabilities: caps, plan, applied: [], failed: [] };
  const apply = async (name, c) => {
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
