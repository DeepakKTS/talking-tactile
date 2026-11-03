import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { parse } from "yaml";
import { defineConfig } from "vitest/config";

// Turns an import of config/*.yaml into a JSON module. ?raw imports are left to Vite.
function yamlConfig(): Plugin {
  return {
    name: "yaml-config",
    transform(code, id) {
      if (!id.endsWith(".yaml")) return null;
      return { code: `export default ${JSON.stringify(parse(code))};`, map: null };
    },
  };
}

// HTTPS=1 (npm run dev:phone): served over HTTPS on every interface, so an iPhone on the
// LAN can open the camera and the microphone, which need a secure page. The certificate is
// made by npm run cert:phone from the local mkcert root CA, into the git-ignored .certs/.
export function phoneHttps(env: NodeJS.ProcessEnv, dir: URL): { key: Buffer; cert: Buffer } | undefined {
  if (env.HTTPS !== "1") return undefined;
  const key = new URL("phone-key.pem", dir);
  const cert = new URL("phone.pem", dir);
  if (!existsSync(key) || !existsSync(cert)) {
    throw new Error("HTTPS=1 needs apps/web/.certs/phone.pem and phone-key.pem: run npm run cert:phone");
  }
  return { key: readFileSync(key), cert: readFileSync(cert) };
}
const HTTPS = phoneHttps(process.env, new URL("./.certs/", import.meta.url));

export const DEV_FILES = [
  fileURLToPath(new URL(".", import.meta.url)),
  fileURLToPath(new URL("../../config/explore.yaml", import.meta.url)),
  fileURLToPath(new URL("../../docs/regions.schema.json", import.meta.url)),
];

// TT_API lets the headless Explore run use its own API port. xfwd passes the phone's address
// on (X-Forwarded-For), so the API's rate limit counts each client apart.
const API_PROXY = { "/api": { target: process.env.TT_API ?? "http://127.0.0.1:8000", xfwd: true } };

export default defineConfig({
  plugins: [react(), yamlConfig()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: API_PROXY,
    ...(HTTPS ? { https: HTTPS, host: true } : {}),
    // The app and the two repo files it imports, nothing else: dev:phone serves this on the
    // LAN, and the repo root also holds the job database, the cost ledger and a private test
    // figure. (.env, *.pem and .git are in Vite's default deny list as well.)
    fs: { allow: DEV_FILES },
  },
  preview: { proxy: API_PROXY },
  worker: { format: "es" },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "scripts/**/*.test.ts"],
    environment: "node",
  },
});
