import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

import { chromium } from 'playwright-core';

function getRequiredEnvNumber(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsedValue = Number(rawValue);
  return Number.isNaN(parsedValue) ? fallback : parsedValue;
}

function getRootEnvValue(name) {
  const envPath = path.resolve(process.cwd(), '..', '.env');
  if (!fs.existsSync(envPath)) {
    return '';
  }

  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    if (line.startsWith(`${name}=`)) {
      return line.slice(name.length + 1).trim();
    }
  }

  return '';
}

function getBooleanEnv(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  return !['0', 'false', 'False', 'FALSE', 'no', 'No', 'NO'].includes(rawValue);
}

function getLoginPassword() {
  return process.env.NEXUS_E2E_PASSWORD
    || process.env.NEXUS_PASSWORD
    || getRootEnvValue('NEXUS_PASSWORD');
}

function getTelegramIdToken() {
  return process.env.NEXUS_E2E_TELEGRAM_ID_TOKEN || '';
}

function findFirstExistingPath(paths) {
  for (const filePath of paths) {
    if (filePath && fs.existsSync(filePath)) {
      return filePath;
    }
  }

  return null;
}

function findChromiumInPlaywrightCache() {
  const cacheRoot = path.join(os.homedir(), '.cache', 'ms-playwright');
  if (!fs.existsSync(cacheRoot)) {
    return null;
  }

  const chromiumDirs = fs.readdirSync(cacheRoot)
    .filter((entry) => entry.startsWith('chromium-'))
    .sort()
    .reverse();

  for (const dirName of chromiumDirs) {
    const executablePath = path.join(cacheRoot, dirName, 'chrome-linux64', 'chrome');
    if (fs.existsSync(executablePath)) {
      return executablePath;
    }
  }

  const headlessShellDirs = fs.readdirSync(cacheRoot)
    .filter((entry) => entry.startsWith('chromium_headless_shell-'))
    .sort()
    .reverse();

  for (const dirName of headlessShellDirs) {
    const executablePath = path.join(
      cacheRoot,
      dirName,
      'chrome-headless-shell-linux64',
      'chrome-headless-shell',
    );
    if (fs.existsSync(executablePath)) {
      return executablePath;
    }
  }

  return null;
}

function resolveChromiumExecutable() {
  const configuredPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  if (configuredPath && fs.existsSync(configuredPath)) {
    return configuredPath;
  }

  const systemPath = findFirstExistingPath([
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
  ]);

  if (systemPath) {
    return systemPath;
  }

  return findChromiumInPlaywrightCache();
}

function installChromium() {
  const result = spawnSync('npx', ['playwright', 'install', 'chromium'], {
    stdio: 'inherit',
    env: process.env,
  });

  if (result.status !== 0) {
    throw new Error(
      'Unable to install Playwright Chromium automatically. ' +
      'Run `cd frontend && npx playwright install chromium` manually.',
    );
  }
}

function ensureChromiumExecutable() {
  const executablePath = resolveChromiumExecutable();
  if (executablePath) {
    return executablePath;
  }

  if (!getBooleanEnv('NEXUS_PLAYWRIGHT_AUTO_INSTALL', true)) {
    throw new Error(
      'Chromium executable not found. Set PLAYWRIGHT_CHROMIUM_EXECUTABLE, ' +
      'install a Chromium binary, or enable NEXUS_PLAYWRIGHT_AUTO_INSTALL=1.',
    );
  }

  console.log('Chromium executable not found. Installing Playwright Chromium...');
  installChromium();

  const installedExecutablePath = resolveChromiumExecutable();
  if (installedExecutablePath) {
    return installedExecutablePath;
  }

  throw new Error('Chromium installation completed, but no executable was found afterwards.');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function main() {
  const publicUrl = process.argv[2] || process.env.NEXUS_PUBLIC_URL;
  assert(publicUrl, 'NEXUS_PUBLIC_URL or argv[2] is required');

  const executablePath = ensureChromiumExecutable();

  const timeoutMs = getRequiredEnvNumber('NEXUS_PLAYWRIGHT_TIMEOUT_MS', 30000);
  const hydrationWaitMs = getRequiredEnvNumber('NEXUS_PLAYWRIGHT_HYDRATION_WAIT_MS', 4000);

  const browser = await chromium.launch({
    executablePath,
    headless: true,
  });

  const context = await browser.newContext();
  const page = await context.newPage();
  const apiResponses = [];
  const failedRequests = [];
  const loadingIndicator = page.getByText('⏳ Загрузка...');
  const authStatus = await fetch(new URL('/api/auth/status', publicUrl)).then((response) => response.json());

  page.on('response', (response) => {
    const url = response.url();
    if (url.includes('/api/')) {
      apiResponses.push({
        status: response.status(),
        url,
      });
    }
  });

  page.on('requestfailed', (request) => {
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      error: request.failure()?.errorText || 'unknown',
    });
  });

  const response = await page.goto(publicUrl, {
    waitUntil: 'domcontentloaded',
    timeout: timeoutMs,
  });

  if (authStatus.password_required) {
    const password = getLoginPassword();
    assert(password, 'Password required but NEXUS_E2E_PASSWORD/NEXUS_PASSWORD is not set');

    const sessionsResponsePromise = page.waitForResponse(
      (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/sessions'),
      { timeout: timeoutMs },
    );
    const metricsResponsePromise = page.waitForResponse(
      (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/metrics'),
      { timeout: timeoutMs },
    );

    await page.getByTestId('auth-password-input').fill(password);
    await page.getByTestId('login-button').click();
    await Promise.all([sessionsResponsePromise, metricsResponsePromise]);
  } else if (authStatus.auth_required && authStatus.telegram_enabled) {
    const telegramIdToken = getTelegramIdToken();
    assert(
      telegramIdToken,
      'Telegram-only auth is enabled but NEXUS_E2E_TELEGRAM_ID_TOKEN is not set',
    );

    const loginResponse = await context.request.post(new URL('/api/auth/telegram/login', publicUrl).toString(), {
      data: {
        id_token: telegramIdToken,
      },
    });
    assert(loginResponse.ok(), `Telegram login failed with ${loginResponse.status()}`);

    const sessionsResponsePromise = page.waitForResponse(
      (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/sessions'),
      { timeout: timeoutMs },
    );
    const metricsResponsePromise = page.waitForResponse(
      (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/metrics'),
      { timeout: timeoutMs },
    );

    await page.reload({
      waitUntil: 'domcontentloaded',
      timeout: timeoutMs,
    });
    await Promise.all([sessionsResponsePromise, metricsResponsePromise]);
  }

  await loadingIndicator.waitFor({
    state: 'hidden',
    timeout: hydrationWaitMs,
  });

  const loadingCount = await loadingIndicator.count();
  const sectionHeaders = await page.locator('[data-testid$="-section-header"]').allInnerTexts();
  const emptyStateVisible = await page.getByTestId('empty-state').count() > 0;
  const sessionsApiOk = apiResponses.some(
    (entry) => entry.status === 200 && entry.url.includes('/api/sessions'),
  );
  const metricsApiOk = apiResponses.some(
    (entry) => entry.status === 200 && entry.url.includes('/api/metrics'),
  );

  assert(response?.status() === 200, `Published page returned ${response?.status()}`);
  assert(loadingCount === 0, 'Loading spinner is still visible after hydration wait');
  assert(failedRequests.length === 0, `Failed requests detected: ${JSON.stringify(failedRequests)}`);
  assert(sessionsApiOk, `Missing successful /api/sessions response: ${JSON.stringify(apiResponses)}`);
  assert(metricsApiOk, `Missing successful /api/metrics response: ${JSON.stringify(apiResponses)}`);
  assert(
    sectionHeaders.length > 0 || emptyStateVisible,
    'Dashboard rendered neither session sections nor the empty state',
  );

  console.log(`Published URL check passed: ${publicUrl}`);
  console.log(`Chromium: ${executablePath}`);
  console.log(`Dashboard: ${sectionHeaders.length > 0 ? sectionHeaders.join(' | ') : 'empty state'}`);

  await context.close();
  await browser.close();
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
