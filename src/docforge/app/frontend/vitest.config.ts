import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts (rather than merging via `mergeConfig`) so the production
// build config never carries test-only wiring — the two run in fully disjoint commands (`build`
// vs `test`) and gain nothing by sharing one file.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
