import { describe, expect, it } from "vitest";
import heart from "../../../../fixtures/pipeline/heart_regions.json";
import synthetic from "../../../../fixtures/synthetic/regions.json";
import { DAMAGED, LoadError, OTHER_VERSION, loadPublished, publishedUrl } from "./loader";

const ID = "a".repeat(64);
const BODY = JSON.stringify(synthetic);

class MemoryStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
}

function fetcher(answer: (url: string) => Response | Error) {
  const urls: string[] = [];
  const f = (url: string) => {
    urls.push(url);
    const a = answer(url);
    return a instanceof Error ? Promise.reject(a) : Promise.resolve(a);
  };
  return { f, urls };
}

describe("published regions loader", () => {
  it("builds only published URLs", () => {
    expect(publishedUrl(ID, "latest")).toBe(`/api/figures/${ID}/published/latest/regions.json`);
    expect(publishedUrl(ID, 3)).toBe(`/api/figures/${ID}/published/3/regions.json`);
  });

  it.each(["", "abc", "A".repeat(64), `${"a".repeat(63)}/`, "../".repeat(22)])(
    "refuses the figure id %j before any request",
    async (bad) => {
      const { f, urls } = fetcher(() => new Response(BODY));
      await expect(loadPublished(bad, "latest", { fetch: f, storage: null })).rejects.toThrow(LoadError);
      expect(urls).toEqual([]);
    },
  );

  it.each([0, -1, 1.5])("refuses version %s", async (v) => {
    const { f, urls } = fetcher(() => new Response(BODY));
    await expect(loadPublished(ID, v, { fetch: f, storage: null })).rejects.toThrow(LoadError);
    expect(urls).toEqual([]);
  });

  it("loads and checks a published regions.json, and keeps a copy for offline use", async () => {
    const storage = new MemoryStorage();
    const { f, urls } = fetcher(() => new Response(BODY, { status: 200 }));
    const got = await loadPublished(ID, "latest", { fetch: f, storage });
    expect(urls).toEqual([publishedUrl(ID, "latest")]);
    expect(got.from).toBe("network");
    expect(got.file.title).toBe(synthetic.title);
    expect(storage.data.size).toBe(1);
  });

  it("hands Explore touchable regions only, online and from the saved copy", async () => {
    const file = structuredClone(synthetic) as { regions: { id: string; touchable: boolean }[] };
    const first = file.regions[0];
    if (!first) throw new Error("the fixture has regions");
    file.regions.push({ ...first, id: "s1", touchable: false });
    const body = JSON.stringify(file);
    const storage = new MemoryStorage();
    const got = await loadPublished(ID, "latest", { fetch: fetcher(() => new Response(body)).f, storage });
    expect(got.file.regions.map((r) => r.id)).toEqual(synthetic.regions.map((r) => r.id));
    const saved = await loadPublished(ID, "latest", { fetch: fetcher(() => new TypeError("down")).f, storage });
    expect(saved.from).toBe("saved");
    expect(saved.file.regions.some((r) => r.id === "s1")).toBe(false);
  });

  it("loads the live heart with its spill suggestion left out and its lines kept", async () => {
    // fixtures/pipeline/heart_regions.json: the live draft of Oct 30 with S1's plan for touch,
    // replayed in services/api/tests/test_e2e_heart_replay.py.
    // As published once the teacher has checked every part it draws.
    const checked = structuredClone(heart);
    for (const r of checked.regions) {
      if (!r.flags?.some((x) => x.reason === "spill")) Object.assign(r, { touchable: true, verified_by_teacher: true });
    }
    const { f } = fetcher(() => new Response(JSON.stringify(checked)));
    const got = await loadPublished(ID, 1, { fetch: f, storage: null });
    expect(heart.regions).toHaveLength(15); // 14 parts, one piece each since Oct 30, and the septum's suggestion
    expect(got.file.regions).toHaveLength(14);
    expect(got.file.regions.every((r) => r.touchable)).toBe(true);
    const labels = new Set(got.file.regions.map((r) => r.label));
    expect(labels.has("septum")).toBe(false);
    expect(got.notTouchable).toEqual(["septum"]); // lines are never named here
    expect(got.file.lines?.map((l) => l.label)).toEqual(["tricuspid valve", "chordae tendineae", "semilunar valves", "mitral valve"]);
    expect(got.file.subject?.label).toBe("heart");
  });

  it("names the parts the teacher has not checked as not touchable, and leaves them out", async () => {
    const { f } = fetcher(() => new Response(JSON.stringify(heart))); // the draft: nothing checked
    const got = await loadPublished(ID, 1, { fetch: f, storage: null });
    expect(got.file.regions).toHaveLength(0);
    expect(got.notTouchable).toContain("right atrium");
    expect(got.notTouchable).toContain("septum");
  });

  it("says when the figure is not published, and does not fall back to a draft", async () => {
    const { f, urls } = fetcher(() => new Response("{}", { status: 404 }));
    await expect(loadPublished(ID, "latest", { fetch: f, storage: new MemoryStorage() })).rejects.toThrow(
      "This figure is not published yet.",
    );
    expect(urls.every((u) => u.includes("/published/"))).toBe(true);
  });

  it("knows which version it loaded: the one asked for, or the server's for latest", async () => {
    const ok = (headers: Record<string, string> = {}) => fetcher(() => new Response(BODY, { headers })).f;
    const storage = new MemoryStorage();
    expect((await loadPublished(ID, 3, { fetch: ok(), storage })).version).toBe(3);
    expect((await loadPublished(ID, "latest", { fetch: ok({ "X-Published-Version": "5" }), storage })).version).toBe(5);
    expect((await loadPublished(ID, "latest", { fetch: ok(), storage: null })).version).toBeNull();
    expect((await loadPublished(ID, "latest", { fetch: ok({ "X-Published-Version": "x" }), storage: null })).version).toBeNull();
    const offline = fetcher(() => new TypeError("Failed to fetch")).f;
    expect((await loadPublished(ID, 3, { fetch: offline, storage })).version).toBe(3);
    expect((await loadPublished(ID, "latest", { fetch: offline, storage })).version).toBe(5);
  });

  it("uses the saved copy when the network is down", async () => {
    const storage = new MemoryStorage();
    await loadPublished(ID, "latest", { fetch: fetcher(() => new Response(BODY)).f, storage });
    const down = fetcher(() => new TypeError("Failed to fetch"));
    const got = await loadPublished(ID, "latest", { fetch: down.f, storage });
    expect(got.from).toBe("saved");
    expect(got.file.title).toBe(synthetic.title);
  });

  it.each([500, 502, 503])("uses the saved copy when the server answers %s", async (status) => {
    const storage = new MemoryStorage();
    await loadPublished(ID, 2, { fetch: fetcher(() => new Response(BODY)).f, storage });
    const got = await loadPublished(ID, 2, { fetch: fetcher(() => new Response("", { status })).f, storage });
    expect(got.from).toBe("saved");
    expect(got.version).toBe(2);
    await expect(loadPublished(ID, 2, { fetch: fetcher(() => new Response("", { status })).f, storage: new MemoryStorage() })).rejects.toThrow(
      `The sheet could not be loaded (${status}).`,
    );
  });

  it("does not use the saved copy when the server says the figure is gone or the request is wrong", async () => {
    const storage = new MemoryStorage();
    await loadPublished(ID, 2, { fetch: fetcher(() => new Response(BODY)).f, storage });
    await expect(loadPublished(ID, 2, { fetch: fetcher(() => new Response("", { status: 404 })).f, storage })).rejects.toThrow(
      "This figure is not published yet.",
    );
    await expect(loadPublished(ID, 2, { fetch: fetcher(() => new Response("", { status: 403 })).f, storage })).rejects.toThrow(
      "The sheet could not be loaded (403).",
    );
  });

  it("fails clearly offline with nothing saved", async () => {
    const down = fetcher(() => new TypeError("Failed to fetch"));
    await expect(loadPublished(ID, "latest", { fetch: down.f, storage: new MemoryStorage() })).rejects.toThrow(
      "The sheet could not be loaded. Check the network.",
    );
  });

  it("refuses a file that breaks the contract, in plain words, and does not save it", async () => {
    const storage = new MemoryStorage();
    const { f } = fetcher(() => new Response(JSON.stringify({ ...synthetic, regions: "no" })));
    await expect(loadPublished(ID, "latest", { fetch: f, storage })).rejects.toThrow(new LoadError(DAMAGED));
    expect(storage.data.size).toBe(0);
  });

  it("says a sheet from another schema version needs publishing again", async () => {
    for (const v of [2, 4]) {
      const { f } = fetcher(() => new Response(JSON.stringify({ ...synthetic, schema_version: v })));
      await expect(loadPublished(ID, "latest", { fetch: f, storage: new MemoryStorage() })).rejects.toThrow(new LoadError(OTHER_VERSION));
    }
  });
});
