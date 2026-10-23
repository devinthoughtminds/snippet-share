import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [
      react(),
      babel({ presets: [reactCompilerPreset()] })
    ],
    // Dev only: same /api paths as behind the gateway, so no CORS.
    server: {
      proxy: { '/api': env.API_PROXY_TARGET ?? 'http://localhost:8000' },
    },
  }
})
