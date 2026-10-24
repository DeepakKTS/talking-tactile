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

export default defineConfig({
  plugins: [react(), yamlConfig()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
    // The contract and shared fixtures live at the repo root, outside apps/web.
    fs: { allow: [fileURLToPath(new URL("../..", import.meta.url))] },
  },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "scripts/**/*.test.ts"],
    environment: "node",
  },
});
