// Registration for now: someone clicks the 4 printed corner marks on the camera view, in
// order round the sheet. Auto registration comes later (d5-1). The clicks are saved per
// camera size, so a reload with the same camera and sheet needs no new clicks.
import { type Mat3, type Pt, type Quad, homographyFromPoints, isConvexQuad, markCorners } from "./homography";

export const CORNER_NAMES = ["A, top left", "B, top right", "C, bottom right", "D, bottom left"] as const;

export type CornerStep =
  | { kind: "next"; prompt: string }
  | { kind: "done"; toMm: Mat3; corners: Quad }
  | { kind: "crossed"; prompt: string };

/** touch: a phone, where the helper taps, and there is no R key (device.ts). */
export function promptFor(i: number, touch = false): string {
  return `${touch ? "Tap" : "Click"} corner ${CORNER_NAMES[i] ?? ""}.`;
}

const CROSSED = "Those corners cross over. Press R and click A, B, C and D in order round the sheet.";
const CROSSED_TOUCH = "Those corners cross over. Tap Set corners, then tap A, B, C and D in order round the sheet.";

export class CornerClicks {
  private clicks: Pt[] = [];

  constructor(
    private readonly page: { width_mm: number; height_mm: number },
    private readonly insetMm: number,
    private readonly touch = false,
  ) {}

  get count(): number {
    return this.clicks.length;
  }

  get points(): readonly Pt[] {
    return this.clicks;
  }

  start(): CornerStep {
    this.clicks = [];
    return { kind: "next", prompt: promptFor(0, this.touch) };
  }

  click(p: Pt): CornerStep {
    this.clicks.push(p);
    if (this.clicks.length < 4) return { kind: "next", prompt: promptFor(this.clicks.length, this.touch) };
    const quad = this.clicks as unknown as Quad;
    this.clicks = [];
    return this.fromCorners(quad);
  }

  fromCorners(quad: Quad): CornerStep {
    if (!isConvexQuad(quad)) {
      return { kind: "crossed", prompt: this.touch ? CROSSED_TOUCH : CROSSED };
    }
    return { kind: "done", toMm: homographyFromPoints(quad, markCorners(this.page, this.insetMm)), corners: quad };
  }
}

const storeKey = (w: number, h: number) => `tt-corners-${w}x${h}`;

export function saveCorners(storage: Pick<Storage, "setItem"> | null, w: number, h: number, q: Quad): void {
  try {
    storage?.setItem(storeKey(w, h), JSON.stringify(q));
  } catch {
    // Blocked storage only means clicking again next time.
  }
}

export function loadCorners(storage: Pick<Storage, "getItem"> | null, w: number, h: number): Quad | null {
  try {
    const raw: unknown = JSON.parse(storage?.getItem(storeKey(w, h)) ?? "null");
    return parseQuad(raw);
  } catch {
    return null;
  }
}

/** ?corners=x1,y1,...,x4,y4 for headless runs, or a saved quad. */
export function parseQuad(raw: unknown): Quad | null {
  const nums = typeof raw === "string" ? raw.split(",").map(Number) : Array.isArray(raw) ? raw.flat() : [];
  if (nums.length !== 8 || !nums.every((n) => typeof n === "number" && Number.isFinite(n))) return null;
  const n = nums as number[];
  return [0, 2, 4, 6].map((i) => [n[i] ?? 0, n[i + 1] ?? 0] as const) as unknown as Quad;
}
