import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Vite config for DocForge frontend.
// In dev (container), VITE_PROXY_TARGET points to the backend container name.
// In dev (local), falls back to localhost:8000.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      allowedHosts: true,
      // HMR WebSocket — Docker maps host:10023 → container:5173.  Vite would
      // otherwise advertise `ws://localhost:5173/` to the browser, which fails
      // because port 5173 is NOT published on the host.  We override the client
      // port so the browser opens the WS on host:10023 (which Docker forwards).
      // Without this, polling detects changes server-side but no update reaches
      // the browser — the dev server "looks healthy" while the UI never refreshes.
      hmr: {
        host: 'localhost',
        clientPort: 10023,
        protocol: 'ws',
      },
      proxy: {
        '/api': { target, changeOrigin: true },
      },
      // HMR over Docker Desktop Windows bind mounts: inotify does NOT propagate
      // host file changes into the container, so chokidar must poll.  Native
      // events still work (so dev on Linux/macOS pays nothing); polling kicks
      // in transparently when inotify reports nothing.
      //
      // `ignored` is essential — without it chokidar walks `node_modules`
      // (~120 k files) every interval, eventually crashing with EINVAL.
      // We also exclude `.vite` and `dist` to keep the watcher light.
      watch: {
        usePolling: true,
        interval: 800,
        binaryInterval: 1500,
        ignored: [
          '**/node_modules/**',
          '**/.vite/**',
          '**/dist/**',
          '**/.git/**',
        ],
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
