import { defineConfig, devices } from '@playwright/test'

const apiPort = process.env.PLAYWRIGHT_API_PORT ?? '8000'
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? '5173'
const apiTarget = process.env.PLAYWRIGHT_API_TARGET ?? `http://127.0.0.1:${apiPort}`

export default defineConfig({
  testDir: './tests',
  use: { baseURL: `http://127.0.0.1:${webPort}`, ...devices['Desktop Chrome'] },
  webServer: [
    {
      command: `dir=$(mktemp -d /tmp/flock-energy-playwright.XXXXXX); DEMO_MODE=true DATABASE_URL=sqlite:///$dir/data.db ../../.venv/bin/python3 -m uvicorn app.main:app --app-dir ../../apps/api --port ${apiPort}`,
      url: `${apiTarget}/ready`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `API_PROXY_TARGET=${apiTarget} npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
    },
  ],
})
