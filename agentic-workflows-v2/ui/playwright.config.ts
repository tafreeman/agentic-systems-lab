import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for streaming E2E (Epic 2 Story 2.2).
 *
 * - Spawns backend + frontend via `webServer` so contributors can run
 *   `npm run test:e2e` with no prior setup.
 * - Backend health check on `/api/health`.
 * - `reuseExistingServer` locally so dev servers on 8010/5173 are reused.
 * - No retries: flake rate is observable, not masked.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: 'e2e-results.json' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      name: 'backend',
      command: 'python -m uvicorn agentic_v2.server.app:app --host 127.0.0.1 --port 8010',
      cwd: '..',
      url: 'http://127.0.0.1:8010/api/health',
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      name: 'frontend',
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
