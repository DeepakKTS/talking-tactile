import { describe, expect, it } from "vitest";
import { FramePump } from "./pump";

describe("frame pump", () => {
  it("keeps one frame in flight and drops the rest, never queues", async () => {
    const sent: number[] = [];
    const pump = new FramePump<number>((f) => sent.push(f));
    expect(await pump.offer(() => 1)).toBe(true);
    expect(await pump.offer(() => 2)).toBe(false);
    expect(await pump.offer(() => 3)).toBe(false);
    pump.done();
    expect(await pump.offer(() => 4)).toBe(true);
    expect(sent).toEqual([1, 4]);
    expect(pump.stats).toEqual({ offered: 4, sent: 2, dropped: 2, failed: 0 });
  });

  it("drops a frame offered while the previous one is still being captured", async () => {
    const sent: number[] = [];
    const pump = new FramePump<number>((f) => sent.push(f));
    let release: (v: number) => void = () => undefined;
    const slow = pump.offer(() => new Promise<number>((r) => (release = r)));
    expect(await pump.offer(() => 2)).toBe(false);
    release(1);
    expect(await slow).toBe(true);
    expect(sent).toEqual([1]);
  });

  it("frees the slot when capture fails", async () => {
    const pump = new FramePump<number>(() => undefined);
    await expect(pump.offer(() => Promise.reject(new Error("closed")))).rejects.toThrow("closed");
    expect(pump.busy).toBe(false);
    expect(pump.stats.failed).toBe(1);
  });
});
