import { describe, expect, it } from "vitest";
import { TOUCH_ONLY, touchOnly } from "./device";

describe("touch-only device", () => {
  it("is a device that cannot hover and points with a finger, as an iPhone", () => {
    const asked: string[] = [];
    const phone = (q: string) => { asked.push(q); return { matches: true }; };
    expect(touchOnly(phone)).toBe(true);
    expect(asked).toEqual([TOUCH_ONLY]);
    expect(TOUCH_ONLY).toBe("(hover: none) and (pointer: coarse)");
  });

  it("a laptop, or no matchMedia at all, keeps the keyboard wording", () => {
    expect(touchOnly(() => ({ matches: false }))).toBe(false);
    expect(touchOnly(null)).toBe(false);
  });
});
