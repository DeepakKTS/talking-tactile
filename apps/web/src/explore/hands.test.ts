import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import type { Pt } from "./homography";
import { type HandObs, type HandSettings, contactPoint, isPointing, pickHand } from "./hands";

const CFG = EXPLORE.hands;
const ANY: HandSettings = { dominant: "either", cameraMirrored: false };

// A synthetic hand in pixels: wrist at the origin, fingers along -y, then rotated, scaled
// and moved. Tip distances from the wrist: index 90 and the others 25 is a pointing hand.
function hand(
  { index = 90, middle = 25, ring = 25, pinky = 25 } = {},
  { angle = 0, scale = 1, dx = 400, dy = 400 } = {},
): Pt[] {
  const pts: Pt[] = Array.from({ length: 21 }, () => [0, 0] as const);
  const fingers = [
    { x: -20, base: 5, tip: index },
    { x: 0, base: 9, tip: middle },
    { x: 20, base: 13, tip: ring },
    { x: 40, base: 17, tip: pinky },
  ];
  for (const f of fingers) {
    pts[f.base] = [f.x, -30]; // MCP
    pts[f.base + 1] = [f.x, -40]; // PIP
    pts[f.base + 2] = [f.x, -(40 + f.tip) / 2]; // DIP
    pts[f.base + 3] = [f.x, -f.tip]; // tip
  }
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return pts.map(([x, y]) => [dx + scale * (c * x - s * y), dy + scale * (s * x + c * y)] as const);
}

const obs = (landmarks: Pt[], label: "Left" | "Right" | null = null): HandObs => ({
  landmarks,
  label,
});

describe("pointing hand picker", () => {
  it("recognizes a pointing hand: index out, the other three curled", () => {
    expect(isPointing(hand(), CFG.min_curled)).toBe(true);
    expect(isPointing(hand({ middle: 85 }), CFG.min_curled)).toBe(CFG.min_curled < 3);
    expect(isPointing(hand({ middle: 85, ring: 85, pinky: 85 }), CFG.min_curled)).toBe(false);
    expect(isPointing(hand({ index: 30 }), CFG.min_curled)).toBe(false);
  });

  it("follows min_curled from explore.yaml", () => {
    expect(CFG.min_curled).toBe(3);
    expect(isPointing(hand({ pinky: 85 }), 2)).toBe(true);
    expect(isPointing(hand({ pinky: 85 }), 3)).toBe(false);
  });

  it("does not care how the hand is turned, how big it is or where it is", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -Math.PI, max: Math.PI, noNaN: true }),
        fc.double({ min: 0.3, max: 4, noNaN: true }),
        fc.integer({ min: 0, max: 1280 }),
        fc.integer({ min: 0, max: 720 }),
        (angle, scale, dx, dy) => {
          const where = { angle, scale, dx, dy };
          expect(isPointing(hand({}, where), 3)).toBe(true);
          expect(isPointing(hand({ middle: 85, ring: 85, pinky: 85 }, where), 3)).toBe(false);
        },
      ),
    );
  });

  it("finds nothing when there are no hands", () => {
    expect(pickHand([], CFG, ANY, null)).toBeNull();
  });

  it("picks the pointing hand of two", () => {
    const open = obs(hand({ middle: 85, ring: 85, pinky: 85 }, { dx: 200 }), "Left");
    const point = obs(hand({}, { dx: 900 }), "Left");
    expect(pickHand([open, point], CFG, ANY, null)).toMatchObject({ index: 1, pointing: true });
    expect(pickHand([point, open], CFG, ANY, null)).toMatchObject({ index: 0, pointing: true });
  });

  it("uses a hand that is not pointing unless require_pointing is set", () => {
    const open = obs(hand({ middle: 85, ring: 85, pinky: 85 }));
    expect(pickHand([open], CFG, ANY, null)).toMatchObject({ index: 0, pointing: false });
    expect(pickHand([open], { ...CFG, require_pointing: true }, ANY, null)).toBeNull();
  });

  // MediaPipe labels hands as if the image were mirrored. Our frames are not, so its "Left"
  // is the student's right hand.
  it("prefers the dominant hand when both point, reading MediaPipe labels as mirrored", () => {
    const mpLeft = obs(hand({}, { dx: 200 }), "Left"); // the student's right hand
    const mpRight = obs(hand({}, { dx: 900 }), "Right"); // the student's left hand
    const right: HandSettings = { dominant: "right", cameraMirrored: false };
    const left: HandSettings = { dominant: "left", cameraMirrored: false };
    expect(pickHand([mpLeft, mpRight], CFG, right, null)).toMatchObject({ index: 0, hand: "right" });
    expect(pickHand([mpLeft, mpRight], CFG, left, null)).toMatchObject({ index: 1, hand: "left" });
    const mirrored: HandSettings = { dominant: "right", cameraMirrored: true };
    expect(pickHand([mpLeft, mpRight], CFG, mirrored, null)).toMatchObject({ index: 1, hand: "right" });
  });

  it("the dominant hand never beats a pointing hand that is not dominant", () => {
    const domOpen = obs(hand({ middle: 85, ring: 85, pinky: 85 }), "Left");
    const otherPointing = obs(hand({}, { dx: 900 }), "Right");
    const right: HandSettings = { dominant: "right", cameraMirrored: false };
    expect(pickHand([domOpen, otherPointing], CFG, right, null)).toMatchObject({ index: 1 });
  });

  it("with either hand allowed, keeps the hand it had so two pointing hands do not swap", () => {
    const a = obs(hand({}, { dx: 200 }), "Left");
    const b = obs(hand({ index: 120 }, { dx: 900 }), "Right"); // the stronger point
    expect(pickHand([a, b], CFG, ANY, null)).toMatchObject({ index: 1, hand: "left" });
    expect(pickHand([a, b], CFG, ANY, "right")).toMatchObject({ index: 0, hand: "right" });
    expect(pickHand([b, a], CFG, ANY, "right")).toMatchObject({ index: 1, hand: "right" });
  });

  it("looks at max_hands hands at most", () => {
    const open = obs(hand({ middle: 85, ring: 85, pinky: 85 }));
    const point = obs(hand());
    expect(pickHand([open, open, point], CFG, ANY, null)).toMatchObject({ pointing: false });
  });
});

describe("contact point", () => {
  it("moves back from the tip toward the DIP joint by the offset", () => {
    expect(contactPoint([100, 100], [100, 120], 4)).toEqual([100, 104]);
    expect(contactPoint([100, 100], [100, 102], 4)).toEqual([100, 102]);
    expect(contactPoint([100, 100], [100, 120], 0)).toEqual([100, 100]);
    expect(contactPoint([100, 100], [100, 100], 4)).toEqual([100, 100]);
  });

  it("takes the offset from explore.yaml", () => {
    expect(EXPLORE.fingertip.contact_offset_mm).toBe(4);
  });
});
