import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import type { WorkerHand } from "../workers/protocol";
import { FingertipTracker } from "./fingertip";
import { type Pt, homographyFromPoints, markCorners } from "./homography";

const W = 1280;
const H = 720;
const PAGE = { width_mm: 215.9, height_mm: 279.4 };
const MARKS = markCorners(PAGE, EXPLORE.registration.mark_inset_mm);
// The camera sees the marks here, in pixels: 2 px per mm, shifted.
const PX = MARKS.map(([x, y]) => [100 + 2 * x, 20 + 2 * y] as const) as unknown as typeof MARKS;
const TO_MM = homographyFromPoints(PX, MARKS);
const toPx = ([x, y]: Pt): Pt => [100 + 2 * x, 20 + 2 * y];

// A pointing hand whose index tip is at tipMm, pointing up the sheet, in normalized coords.
function pointing(tipMm: Pt, label: WorkerHand["label"] = "Left", open = false): WorkerHand {
  const lm: [number, number][] = Array.from({ length: 21 }, () => [0, 0]);
  const put = (i: number, mm: Pt) => {
    const [x, y] = toPx(mm);
    lm[i] = [x / W, y / H];
  };
  put(0, [tipMm[0], tipMm[1] + 90]);
  [[5, 0], [9, 8], [13, 16], [17, 24]].forEach(([base = 0, dx = 0], k) => {
    const x = tipMm[0] + dx;
    const len = k === 0 || open ? 90 : 25;
    put(base, [x, tipMm[1] + 60]);
    put(base + 1, [x, tipMm[1] + 50]);
    put(base + 2, [x, tipMm[1] + 90 - (50 + len) / 2]);
    put(base + 3, [x, tipMm[1] + 90 - len]);
  });
  return { landmarks: lm, label, score: 0.9 };
}

const SETTINGS = { dominant: "either", cameraMirrored: false } as const;

describe("fingertip tracker", () => {
  it("finds nothing until the corners are set", () => {
    const t = new FingertipTracker(EXPLORE, SETTINGS);
    expect(t.update([pointing([100, 100])], W, H, 0)).toEqual({ p: null, pointing: false });
  });

  it("maps the index tip to sheet mm, moved back toward the DIP by the contact offset", () => {
    const t = new FingertipTracker(EXPLORE, SETTINGS);
    t.setCalibration(TO_MM);
    const got = t.update([pointing([100, 100])], W, H, 0);
    expect(got.pointing).toBe(true);
    expect(got.p?.[0]).toBeCloseTo(100, 6);
    expect(got.p?.[1]).toBeCloseTo(100 + EXPLORE.fingertip.contact_offset_mm, 6);
  });

  it("smooths within one hand, but starts over when the hand changes", () => {
    const t = new FingertipTracker(EXPLORE, SETTINGS);
    t.setCalibration(TO_MM);
    t.update([pointing([100, 100], "Left")], W, H, 0);
    const smoothed = t.update([pointing([120, 100], "Left")], W, H, 33);
    expect(smoothed.p?.[0]).toBeLessThan(119);
    const other = t.update([pointing([60, 100], "Right")], W, H, 66);
    expect(other.p?.[0]).toBeCloseTo(60, 6);
  });

  it("starts over after the hand is lost for lost_reset_ms", () => {
    const t = new FingertipTracker(EXPLORE, SETTINGS);
    t.setCalibration(TO_MM);
    t.update([pointing([100, 100])], W, H, 0);
    expect(t.update([], W, H, 33).p).toBeNull();
    const back = t.update([pointing([150, 100])], W, H, 33 + EXPLORE.fingertip.lost_reset_ms);
    expect(back.p?.[0]).toBeCloseTo(150, 6);
  });

  it("prefers the pointing hand of two", () => {
    const t = new FingertipTracker(EXPLORE, SETTINGS);
    t.setCalibration(TO_MM);
    const got = t.update([pointing([40, 200], "Right", true), pointing([150, 120], "Left")], W, H, 0);
    expect(got.pointing).toBe(true);
    expect(got.p?.[0]).toBeCloseTo(150, 6);
  });
});
