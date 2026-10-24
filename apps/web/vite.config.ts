import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
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
