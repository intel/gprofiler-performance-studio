import { defineConfig, devices } from '@playwright/test';

// Drives the running console behind nginx (self-signed TLS + basic auth).
// From host:      E2E_UI_URL=https://localhost:4433 (default)
// From network:   E2E_UI_URL=https://nginx-load-balancer
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_UI_URL || 'https://localhost:4433',
    ignoreHTTPSErrors: true,
    httpCredentials: {
      username: process.env.E2E_BASIC_AUTH_USER || 'admin',
      password: process.env.E2E_BASIC_AUTH_PASSWORD || 'admin',
    },
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
