import { defineConfig, devices } from '@playwright/test'

// End-to-end: real browser, real Vite dev server, real backend and Postgres (the dev db must be running).
// Pastes created here land in the dev database (DATABASE_URL in backend/.env).
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // Reuses servers that are already running (e.g. your own `bun run dev`).
  webServer: [
    {
      command: 'uv run uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/api/docs',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'bun run dev --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
