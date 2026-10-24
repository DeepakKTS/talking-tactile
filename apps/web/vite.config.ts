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

// TT_API lets the headless Explore run use its own API port.
const API_PROXY = { "/api": process.env.TT_API ?? "http://127.0.0.1:8000" };

export default defineConfig({
  plugins: [react(), yamlConfig()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: API_PROXY,
    // The contract and shared fixtures live at the repo root, outside apps/web.
    fs: { allow: [fileURLToPath(new URL("../..", import.meta.url))] },
  },
  preview: { proxy: API_PROXY },
  worker: { format: "es" },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "scripts/**/*.test.ts"],
    environment: "node",
  },
});
