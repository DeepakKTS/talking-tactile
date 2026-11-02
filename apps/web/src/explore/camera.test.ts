import { afterEach, describe, expect, it, vi } from "vitest";
import { askApi, askAudioApi } from "./camera";
import { AskError } from "./session";

const NOT_WORKING = "Questions are not working right now. Labels still work.";

// A server that never answers: the request ends only when its signal aborts.
function silentServer() {
  vi.stubGlobal("navigator", { onLine: true });
  vi.stubGlobal("fetch", (_url: string, init: RequestInit) =>
    new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => { reject(init.signal?.reason as Error); });
    }));
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("question timeout", () => {
  it("a typed question to a server that never answers ends in the spoken failure sentence", async () => {
    silentServer();
    const err: unknown = await askApi({ question: "What is this?" }, 20).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AskError);
    expect((err as AskError).spoken).toBe(NOT_WORKING);
  });

  it("so does a held question", async () => {
    silentServer();
    const req = { figure_id: "a".repeat(64), question: "", region_id: null, recent_region_ids: [], session_id: "s" };
    const err: unknown = await askAudioApi(new Uint8Array(44), req, 20).catch((e: unknown) => e);
    expect((err as AskError).spoken).toBe(NOT_WORKING);
  });
});
