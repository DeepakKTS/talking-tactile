import { describe, expect, it } from "vitest";
import { EXPLORE } from "../shared/config";
import { CornerClicks, loadCorners, parseQuad, saveCorners } from "./corners";
import { applyHomography } from "./homography";

const PAGE = { width_mm: 215.9, height_mm: 279.4 };
const INSET = EXPLORE.registration.mark_inset_mm;

describe("corner clicks", () => {
  it("asks for A to D in order, then maps the clicks onto the printed marks", () => {
    const c = new CornerClicks(PAGE, INSET);
    expect(c.start()).toEqual({ kind: "next", prompt: "Click corner A, top left." });
    expect(c.click([300, 100])).toEqual({ kind: "next", prompt: "Click corner B, top right." });
    c.click([1000, 120]);
    expect(c.click([1020, 650])).toEqual({ kind: "next", prompt: "Click corner D, bottom left." });
    const done = c.click([280, 620]);
    expect(done.kind).toBe("done");
    if (done.kind !== "done") return;
    const [x, y] = applyHomography(done.toMm, [300, 100]);
    expect(x).toBeCloseTo(INSET, 6);
    expect(y).toBeCloseTo(INSET, 6);
  });

  it("says so when the clicks cross over, and starts again", () => {
    const c = new CornerClicks(PAGE, INSET);
    c.start();
    [[300, 100], [1020, 650], [1000, 120]].forEach((p) => c.click(p as [number, number]));
    expect(c.click([280, 620]).kind).toBe("crossed");
    expect(c.count).toBe(0);
  });

  it("saves the corners per camera size", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    const q = parseQuad("1,2,30,2,30,40,1,40");
    if (!q) throw new Error("no quad");
    saveCorners(storage, 1280, 720, q);
    expect(loadCorners(storage, 1280, 720)).toEqual(q);
    expect(loadCorners(storage, 640, 480)).toBeNull();
  });

  it("reads ?corners= and refuses anything but 8 numbers", () => {
    expect(parseQuad("0,0,640,0,640,480,0,480")).toEqual([[0, 0], [640, 0], [640, 480], [0, 480]]);
    expect(parseQuad("0,0,640")).toBeNull();
    expect(parseQuad("a,b,c,d,e,f,g,h")).toBeNull();
    expect(parseQuad(null)).toBeNull();
  });
});
