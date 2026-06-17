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
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
