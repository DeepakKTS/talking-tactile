// Generates src/shared/regions.gen.ts from docs/regions.schema.json.
// Run with: npm run gen:types. scripts/gen-regions-types.test.ts fails when the file is stale.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { compileFromFile } from "json-schema-to-typescript";

export const SCHEMA_PATH = fileURLToPath(new URL("../../../docs/regions.schema.json", import.meta.url));
export const OUT_PATH = fileURLToPath(new URL("../src/shared/regions.gen.ts", import.meta.url));

const BANNER = [
  "// Generated from docs/regions.schema.json by scripts/gen-regions-types.ts.",
  "// Do not edit by hand. Run npm run gen:types after changing the schema.",
].join("\n");

export function generateRegionsTypes(): Promise<string> {
  return compileFromFile(SCHEMA_PATH, {
    bannerComment: BANNER,
    additionalProperties: false,
    maxItems: 2,
    style: { semi: true, singleQuote: false, printWidth: 100 },
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(OUT_PATH, await generateRegionsTypes());
  console.log(`wrote ${OUT_PATH}`);
}
