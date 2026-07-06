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
  build: { outDir: "dist" },
});
