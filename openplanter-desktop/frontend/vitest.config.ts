import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    alias: {
      "@tauri-apps/api/core": "./src/__mocks__/tauri.ts",
    },
  },
});
