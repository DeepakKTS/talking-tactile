import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { OUT_PATH, generateRegionsTypes } from "./gen-regions-types";

describe("regions.gen.ts", () => {
  it("matches the schema, so the TypeScript types cannot drift from docs/regions.schema.json", async () => {
    expect(readFileSync(OUT_PATH, "utf8")).toBe(await generateRegionsTypes());
  });
});
