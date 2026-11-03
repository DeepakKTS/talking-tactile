import { afterEach, describe, expect, it, vi } from "vitest";
import { askApi, transcribeApi } from "./camera";
import { AskError, type AskRequest, TOO_LONG } from "./session";

const NOT_WORKING = "Questions are not working right now. Labels still work.";
const REQ: AskRequest = { figure_id: "a".repeat(64), question: "What is this?", region_id: null, recent_region_ids: [], session_id: "s" };

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
  it("a typed question to a server that never answers ends in the too-long sentence", async () => {
    silentServer();
    const err: unknown = await askApi(REQ, 20).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AskError);
    expect((err as AskError).spoken).toBe(TOO_LONG);
    expect(TOO_LONG).toBe("That took too long. Please ask again.");
  });

  it("so does a held question", async () => {
    silentServer();
    const err: unknown = await transcribeApi(new Uint8Array(44), REQ, 20).catch((e: unknown) => e);
    expect((err as AskError).spoken).toBe(TOO_LONG);
  });
});

function server(status: number, body: string) {
  vi.stubGlobal("navigator", { onLine: true });
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(body, { status })));
}

const said = async () => {
  const err: unknown = await askApi(REQ).catch((e: unknown) => e);
  return (err as AskError).spoken;
};

describe("what a failed question says", () => {
  it("says the ask route's own sentences as sent", async () => {
    const capped = "That is 50 questions for this session. Ask your teacher.";
    server(429, JSON.stringify({ error: { code: "question_cap", message: capped, retryable: false } }));
    expect(await said()).toBe(capped);
  });

  it("never says a message not written for a student", async () => {
    for (const [status, code, message] of [
      [500, "internal", "Something went wrong."],
      [503, "unavailable", "Live Meta calls need LIVE=1 in the environment."],
      [404, "not_found", "No published version 4."],
    ] as const) {
      server(status, JSON.stringify({ error: { code, message, retryable: true } }));
      expect(await said()).toBe(NOT_WORKING);
    }
    server(502, "<html>Bad gateway</html>");
    expect(await said()).toBe(NOT_WORKING);
  });

  it("a 200 that is not JSON is not mistaken for the network being down", async () => {
    server(200, "<html>captive portal</html>");
    expect(await said()).toBe(NOT_WORKING);
  });
});
