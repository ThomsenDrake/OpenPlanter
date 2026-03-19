import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // Ignore macOS resource-fork files that can appear on external volumes.
    exclude: ["e2e/**", "node_modules/**", "**/._*"],
  },
});
