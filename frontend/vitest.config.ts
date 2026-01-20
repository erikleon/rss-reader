import { defineConfig } from "vitest/config";

// Pure-function unit tests; no DOM needed. TZ is pinned so date-grouping
// assertions are deterministic across local machines and CI.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test-setup.ts"],
  },
});
