// A phone or tablet: no mouse to hover with and a finger to point with, and almost always no
// keyboard. There the page says "tap" and names its buttons, never keys (an iPhone matches;
// a laptop, even with a touch screen, has a fine pointer that hovers).
export const TOUCH_ONLY = "(hover: none) and (pointer: coarse)";

export function touchOnly(media: ((q: string) => { matches: boolean }) | null = typeof matchMedia === "function" ? (q) => matchMedia(q) : null): boolean {
  return media?.(TOUCH_ONLY).matches ?? false;
}
