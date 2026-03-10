import { defineConfig } from '@playwright/test';

const DEFAULT_PUBLIC_URL = 'http://107.174.231.22:8888';
const DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000;
const DEFAULT_EXPECT_TIMEOUT_MS = 15_000;
const DEFAULT_TEST_TIMEOUT_MS = 60_000;

function getNumberEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsedValue = Number(rawValue);
  return Number.isNaN(parsedValue) ? fallback : parsedValue;
}

const baseURL = process.env.NEXUS_PUBLIC_URL || DEFAULT_PUBLIC_URL;
const navigationTimeout = getNumberEnv('NEXUS_PLAYWRIGHT_TIMEOUT_MS', DEFAULT_NAVIGATION_TIMEOUT_MS);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: Math.max(
    navigationTimeout + DEFAULT_NAVIGATION_TIMEOUT_MS,
    DEFAULT_TEST_TIMEOUT_MS,
  ),
  expect: {
    timeout: DEFAULT_EXPECT_TIMEOUT_MS,
  },
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL,
    headless: true,
    ignoreHTTPSErrors: true,
    actionTimeout: DEFAULT_EXPECT_TIMEOUT_MS,
    navigationTimeout,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
});
