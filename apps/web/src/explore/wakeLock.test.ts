import { describe, expect, it } from "vitest";
import { ScreenAwake, WAKE_REFUSED, type WakeDeps } from "./wakeLock";

function page(answer: () => Promise<{ release(): Promise<void> }>) {
  const asked: number[] = [];
  let onVisible: () => void = () => undefined;
  const doc = {
    visibilityState: "visible" as DocumentVisibilityState,
    addEventListener: (_: string, fn: () => void) => { onVisible = fn; },
  };
  const deps: WakeDeps = {
    wakeLock: { request: () => { asked.push(asked.length); return answer(); } },
    doc: doc as unknown as WakeDeps["doc"],
  };
  return { deps, asked, doc, show: () => { onVisible(); } };
}

describe("screen wake lock", () => {
  it("asks at once, without being awaited, and says nothing when held", async () => {
    const said: string[] = [];
    const p = page(() => Promise.resolve({ release: () => Promise.resolve() }));
    const awake = new ScreenAwake((t) => { said.push(t); }, p.deps);
    const pending = awake.request();
    expect(p.asked).toHaveLength(1); // asked synchronously, inside the tap
    expect(await pending).toBeNull();
    expect(awake.held).toBe(true);
    expect(said).toEqual([]);
  });

  it("refused, it says how to keep the screen on, once, however often it is refused", async () => {
    const said: string[] = [];
    const p = page(() => Promise.reject(new DOMException("Permission was denied.", "NotAllowedError")));
    const awake = new ScreenAwake((t) => { said.push(t); }, p.deps);
    expect(await awake.request()).toBe("NotAllowedError: Permission was denied.");
    await awake.request();
    expect(said).toEqual([WAKE_REFUSED]);
    expect(WAKE_REFUSED).toBe("To keep the screen on, set Auto-Lock to Never in Settings.");
  });

  it("asks again when the page is visible again, while it is wanted", async () => {
    const p = page(() => Promise.resolve({ release: () => Promise.resolve() }));
    const awake = new ScreenAwake(() => undefined, p.deps);
    p.show();
    expect(p.asked).toHaveLength(0); // not wanted yet: Start not pressed
    await awake.request();
    p.show();
    expect(p.asked).toHaveLength(2);
    await awake.release();
    p.show();
    expect(p.asked).toHaveLength(2);
  });

  it("with no Wake Lock API it says the same sentence", async () => {
    const said: string[] = [];
    const awake = new ScreenAwake((t) => { said.push(t); }, { doc: page(() => Promise.reject(new Error("x"))).deps.doc });
    expect(await awake.request()).toBe("Not supported here");
    expect(said).toEqual([WAKE_REFUSED]);
  });
});
