// The dev server that npm run dev:phone opens on the LAN serves the app and the two repo files
// it imports, and nothing else from the repo (vite.config.ts DEV_FILES).
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer, type ViteDevServer } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const ROOT = fileURLToPath(new URL("../../..", import.meta.url));
let server: ViteDevServer;
let base = "";

beforeAll(async () => {
  server = await createServer({ configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)), server: { host: "127.0.0.1", port: 0, strictPort: false }, logLevel: "silent" });
  await server.listen();
  const addr = server.httpServer?.address();
  base = `http://127.0.0.1:${typeof addr === "object" && addr ? String(addr.port) : ""}`;
}, 30000);

afterAll(async () => {
  await server.close();
});

const status = async (repoPath: string) => (await fetch(`${base}/@fs${ROOT}${repoPath}`)).status;

describe("dev server files", () => {
  it("serves the two repo files the app imports", async () => {
    expect(await status("config/explore.yaml")).toBe(200);
    expect(await status("docs/regions.schema.json")).toBe(200);
  });

  it("refuses the rest of the repo: the private figure, data, the ledger, the API, secrets", async () => {
    // Every one that exists is refused. The private ones exist only on the demo Mac, not in CI;
    // a missing file cannot be served (Vite answers with the app's page instead).
    const present = ["fixtures/private/brain_upload.png", "data/jobs.sqlite", "eval/live/ledger.jsonl",
      "services/api/app/ask.py", "services/api/.env", "apps/web/.certs/phone-key.pem", "README.md"]
      .filter((p) => existsSync(`${ROOT}${p}`));
    expect(present.length).toBeGreaterThanOrEqual(3); // the tracked ones, everywhere
    for (const p of present) expect([p, await status(p)]).toEqual([p, 403]);
  });
});
