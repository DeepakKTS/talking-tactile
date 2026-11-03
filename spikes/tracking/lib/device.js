// A phone or tablet: no hover and a coarse pointer, as apps/web/src/explore/device.ts. There
// the page names what to tap, never a key.
export const TOUCH_ONLY = "(hover: none) and (pointer: coarse)";

export function touchOnly(media = typeof matchMedia === "function" ? (q) => matchMedia(q) : null) {
  return media ? media(TOUCH_ONLY).matches : false;
}
