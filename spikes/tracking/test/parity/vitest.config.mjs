// Runs generate.port.ts with the shipped code, committed. From the repo root:
//   cd apps/web
//   npx vitest run --config ../../spikes/tracking/test/parity/vitest.config.mjs
// It writes port_outputs.json next to this file.
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const web = process.cwd(); // the shipped app: apps/web
const { parse } = createRequire(`${web}/`)("yaml");

export default {
  plugins: [{
    name: "yaml-config",
    transform: (code, id) => (id.endsWith(".yaml") ? { code: `export default ${JSON.stringify(parse(code))};`, map: null } : null),
  }],
  cacheDir: `${web}/node_modules/.vite-parity`,
  resolve: { alias: { "@port": `${web}/src`, "@spike": fileURLToPath(new URL("../..", import.meta.url)) } },
  server: { fs: { allow: ["/"] } },
  test: { root: here, include: ["generate.port.ts"], environment: "node" },
};
