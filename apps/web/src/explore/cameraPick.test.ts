import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { CameraWatch, type CameraInfo, type CameraKey, FOCUS_SETTLE_MS, cameraChanges, lockCamera, lockPlan, openCamera, pickCamera } from "./cameraPick";

// The same cases as the Gate B page's copy (spikes/tracking/test/camera.test.mjs).
interface Cases {
  pick: { why: string; devices: CameraInfo[]; expect: { deviceId: string; label: string } | null }[];
  plan: { why: string; caps: Record<string, unknown> | null; settings: Record<string, unknown> | null; expect: Record<string, unknown> }[];
  changes: { why: string; base: CameraKey; now: CameraKey; expect: string[] }[];
}
const CASES = JSON.parse(readFileSync(new URL("../../../../spikes/tracking/test/camera_cases.json", import.meta.url), "utf8")) as Cases;

describe("shared camera cases", () => {
  it.each(CASES.pick)("pick: $why", (c) => { expect(pickCamera(c.devices)).toEqual(c.expect); });
  it.each(CASES.plan)("plan: $why", (c) => { expect(lockPlan(c.caps, c.settings)).toEqual(c.expect); });
  it.each(CASES.changes)("changes: $why", (c) => { expect(cameraChanges(c.base, c.now)).toEqual(c.expect); });
});

const IPHONE: CameraInfo[] = [
  { kind: "videoinput", deviceId: "triple", label: "Back Triple Camera" },
  { kind: "videoinput", deviceId: "wide", label: "Back Camera" },
];
const BLANK: CameraInfo[] = IPHONE.map((d) => ({ ...d, deviceId: "", label: "" }));
const LABELS: Record<string, string> = { triple: "Back Triple Camera", wide: "Back Camera", ft: "FaceTime HD Camera" };

/** getUserMedia and enumerateDevices as a phone answers them; `allowed` flips on the first open. */
function fakeMedia(o: { devices: CameraInfo[]; facingOpens: string; refuse?: string[] }) {
  let allowed = false;
  const calls: MediaTrackConstraints[] = [];
  const stopped: string[] = [];
  const media = {
    enumerateDevices: () => Promise.resolve((allowed ? o.devices : o.devices.map((d) => ({ ...d, deviceId: "", label: "" }))) as unknown as MediaDeviceInfo[]),
    getUserMedia: (c: MediaStreamConstraints) => {
      const v = c.video as MediaTrackConstraints;
      calls.push(v);
      const exact = (v.deviceId as { exact?: string } | undefined)?.exact;
      if (exact && o.refuse?.includes(exact)) return Promise.reject(new DOMException("busy", "NotReadableError"));
      allowed = true;
      const id = exact ?? o.facingOpens;
      const track = { label: LABELS[id] ?? id, getSettings: () => ({ deviceId: id }), stop: () => { stopped.push(id); } };
      return Promise.resolve({ getVideoTracks: () => [track], getTracks: () => [track] } as unknown as MediaStream);
    },
  };
  return { media, calls, stopped };
}

describe("opening the camera", () => {
  const size = { width: { ideal: 1280 } };

  it("first time on an iPhone: opens by facingMode, then reopens the wide lens by deviceId", async () => {
    const f = fakeMedia({ devices: IPHONE, facingOpens: "triple" });
    const o = await openCamera(f.media, size);
    expect(o.label).toBe("Back Camera");
    expect(o.how).toBe("Back Camera, by deviceId");
    expect(f.calls.map((c) => c.deviceId ?? c.facingMode)).toEqual([{ ideal: "environment" }, { exact: "wide" }]);
    expect(f.stopped).toEqual(["triple"]);
    expect(f.calls.every((c) => c.width !== undefined)).toBe(true);
  });

  it("once allowed: the wide lens by deviceId at once", async () => {
    const f = fakeMedia({ devices: IPHONE, facingOpens: "triple" });
    await openCamera(f.media, size);
    f.calls.length = 0;
    const o = await openCamera(f.media, size);
    expect([o.how, f.calls.length]).toEqual(["Back Camera, by deviceId", 1]);
  });

  it("no wide lens listed (a laptop, or labels in another language): facingMode keeps what it opened", async () => {
    const f = fakeMedia({ devices: [{ kind: "videoinput", deviceId: "ft", label: "FaceTime HD Camera" }], facingOpens: "ft" });
    const o = await openCamera(f.media, size);
    expect([o.how, o.label, f.calls.length, f.stopped]).toEqual(["facingMode environment (no Back Camera listed)", "FaceTime HD Camera", 1, []]);
  });

  it("the wide lens will not open: back to facingMode, said so", async () => {
    const f = fakeMedia({ devices: IPHONE, facingOpens: "triple", refuse: ["wide"] });
    const o = await openCamera(f.media, size);
    expect([o.how, o.label]).toEqual(["facingMode environment (Back Camera did not open)", "Back Triple Camera"]);
  });

  it("enumerateDevices failing is not fatal", async () => {
    const f = fakeMedia({ devices: BLANK, facingOpens: "triple" });
    f.media.enumerateDevices = () => Promise.reject(new Error("no"));
    const o = await openCamera(f.media, size);
    expect(o.how).toBe("facingMode environment (no Back Camera listed)");
  });
});

describe("fixing zoom and focus", () => {
  const track = (caps: Record<string, unknown> | undefined, refuse = "") => {
    const applied: unknown[] = [];
    return {
      applied,
      t: {
        ...(caps ? { getCapabilities: () => caps } : {}),
        getSettings: () => ({ zoom: 1 }) as MediaTrackSettings,
        applyConstraints: (c?: MediaTrackConstraints) => {
          const one = (c?.advanced ?? [])[0] as Record<string, unknown>;
          if (refuse && refuse in one) return Promise.reject(new Error("OverconstrainedError"));
          applied.push(one);
          return Promise.resolve();
        },
      },
    };
  };

  it("zoom now, focus after it settles, only what is offered", async () => {
    const waits: number[] = [];
    const { t, applied } = track({ zoom: { min: 1, max: 5 }, focusMode: ["manual", "continuous"] });
    const r = await lockCamera(t, (ms) => { waits.push(ms); return Promise.resolve(); });
    expect(applied).toEqual([{ zoom: 1 }, { focusMode: "manual" }]);
    expect(waits).toEqual([FOCUS_SETTLE_MS]);
    expect(r.applied).toEqual(["zoom 1", "focusMode manual"]);
  });

  it("no getCapabilities: nothing is set", async () => {
    const { t, applied } = track(undefined);
    const r = await lockCamera(t, () => Promise.resolve());
    expect([applied, r.capabilities]).toEqual([[], null]);
  });

  it("a refused constraint is reported, not thrown", async () => {
    const { t } = track({ zoom: { min: 1, max: 5 }, focusMode: ["single-shot"] }, "focusMode");
    const r = await lockCamera(t, () => Promise.resolve());
    expect(r.applied).toEqual(["zoom 1"]);
    expect(r.failed[0]).toMatch(/^focusMode single-shot: /);
  });
});

describe("the drift guard", () => {
  const key = (o: Partial<CameraKey> = {}): CameraKey => ({ width: 1280, height: 720, deviceId: "w", zoom: 1, ...o });

  it("tells once when the camera changes, and again only after the corners are set anew", () => {
    const w = new CameraWatch();
    expect(w.check(key({ zoom: 3 }))).toBe(false); // no corners yet
    w.rebase(key());
    expect(w.check(key())).toBe(false);
    expect(w.check(key({ deviceId: "t" }))).toBe(true);
    expect(w.changed).toEqual(["device"]);
    expect(w.check(key({ deviceId: "u" }))).toBe(false); // said once
    w.rebase(key({ deviceId: "u" }));
    expect(w.check(key({ deviceId: "u" }))).toBe(false);
    expect(w.check(key({ width: 640 }))).toBe(true);
  });
});
