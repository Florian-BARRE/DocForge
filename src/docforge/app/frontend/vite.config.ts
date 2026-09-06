import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies API calls to the FastAPI app; the production build (dist/) is served
// by FastAPI itself as static files, so no proxy is involved there.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // In the dev container the API is another service — the target comes from the env;
    // plain local dev keeps the localhost default.
    proxy: { "/api": process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000" },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      output: {
        // Split heavy, rarely-co-loaded vendor code out of the app bundle so the initial
        // load only pays for react/react-dom; TanStack (table+virtual) is only pulled in
        // by the corpus grid feature, itself lazy-loaded below. Matched by module id (not
        // the object-map form) because react-dom is actually imported via its `react-dom/client`
        // subpath — an exact-package-name map misses that and silently emits an empty chunk.
        manualChunks(id) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) return "vendor-react";
          if (id.includes("node_modules/@tanstack")) return "vendor-tanstack";
        },
      },
    },
  },
});
