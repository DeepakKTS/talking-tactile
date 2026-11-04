// The Gate B page's camera choice and change check on the cases Explore's copy is tested on
// (camera_cases.json; apps/web/src/explore/cameraPick.test.ts), so the two cannot drift apart.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CameraWatch, FOCUS_SETTLE_MS, cameraChanges, lockCamera, lockPlan, openCamera, pickCamera } from "../lib/camera.js";

const CASES = JSON.parse(readFileSync(new URL("./camera_cases.json", import.meta.url)));

for (const c of CASES.pick) test(`pick: ${c.why}`, () => assert.deepEqual(pickCamera(c.devices), c.expect));
for (const c of CASES.plan) test(`plan: ${c.why}`, () => assert.deepEqual(lockPlan(c.caps, c.settings), c.expect));
for (const c of CASES.changes) test(`changes: ${c.why}`, () => assert.deepEqual(cameraChanges(c.base, c.now), c.expect));

const LABELS = { triple: "Back Triple Camera", wide: "Back Camera" };
const IPHONE = [
  { kind: "videoinput", deviceId: "triple", label: "Back Triple Camera" },
  { kind: "videoinput", deviceId: "wide", label: "Back Camera" },
];

function fakeMedia({ devices, facingOpens, refuse = [] }) {
  let allowed = false;
  const calls = [];
  const stopped = [];
  const media = {
    enumerateDevices: async () => (allowed ? devices : devices.map((d) => ({ ...d, deviceId: "", label: "" }))),
    getUserMedia: async ({ video }) => {
      calls.push(video);
      const exact = video.deviceId?.exact;
      if (exact && refuse.includes(exact)) throw new Error("busy");
      allowed = true;
      const id = exact ?? facingOpens;
      const track = { label: LABELS[id] ?? id, getSettings: () => ({ deviceId: id }), stop: () => stopped.push(id) };
      return { getVideoTracks: () => [track], getTracks: () => [track] };
    },
  };
  return { media, calls, stopped };
}

test("first time on an iPhone: facingMode, then the wide lens by deviceId", async () => {
  const f = fakeMedia({ devices: IPHONE, facingOpens: "triple" });
  const o = await openCamera(f.media, { width: { ideal: 1280 } });
  assert.deepEqual([o.how, o.label, f.stopped], ["Back Camera, by deviceId", "Back Camera", ["triple"]]);
  assert.deepEqual(f.calls.map((c) => c.deviceId ?? c.facingMode), [{ ideal: "environment" }, { exact: "wide" }]);
});

test("the wide lens will not open: back to facingMode", async () => {
  const f = fakeMedia({ devices: IPHONE, facingOpens: "triple", refuse: ["wide"] });
  const o = await openCamera(f.media, {});
  assert.deepEqual([o.how, o.label], ["facingMode environment (Back Camera did not open)", "Back Triple Camera"]);
});

test("a picked camera opens by its deviceId only", async () => {
  const f = fakeMedia({ devices: IPHONE, facingOpens: "triple" });
  const o = await openCamera(f.media, {}, "triple");
  assert.deepEqual([o.how, f.calls.length], ["the camera picked", 1]);
});

test("zoom now, focus after it settles, a refusal reported", async () => {
  const applied = [];
  const waits = [];
  const track = {
    getCapabilities: () => ({ zoom: { min: 1, max: 5 }, focusMode: ["single-shot"] }),
    getSettings: () => ({ zoom: 1 }),
    applyConstraints: async (c) => {
      if ("focusMode" in c.advanced[0]) throw new Error("OverconstrainedError");
      applied.push(c.advanced[0]);
    },
  };
  const r = await lockCamera(track, async (ms) => waits.push(ms));
  assert.deepEqual([applied, waits, r.applied], [[{ zoom: 1 }], [FOCUS_SETTLE_MS], ["zoom 1"]]);
  assert.match(r.failed[0], /^focusMode single-shot: /);
});

test("the change is told once, until calibrated again", () => {
  const key = (o = {}) => ({ width: 1280, height: 720, deviceId: "w", zoom: 1, ...o });
  const w = new CameraWatch();
  assert.equal(w.check(key({ zoom: 2 })), false);
  w.rebase(key());
  assert.equal(w.check(key({ zoom: 2 })), true);
  assert.equal(w.check(key({ zoom: 3 })), false);
  w.rebase(key({ zoom: 3 }));
  assert.equal(w.check(key({ zoom: 3 })), false);
});
