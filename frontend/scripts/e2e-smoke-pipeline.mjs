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

function getBooleanEnv(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  return !['0', 'false', 'False', 'FALSE', 'no', 'No', 'NO'].includes(rawValue);
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

function getLoginPassword() {
  return process.env.NEXUS_E2E_PASSWORD
    || process.env.NEXUS_PASSWORD
    || getRootEnvValue('NEXUS_PASSWORD');
}

function getTelegramIdToken() {
  return process.env.NEXUS_E2E_TELEGRAM_ID_TOKEN || '';
}

function getPublishedUrl() {
  const explicitUrl = process.env.NEXUS_PUBLIC_URL
    || process.env.PUBLIC_URL
    || getRootEnvValue('NEXUS_PUBLIC_URL')
    || getRootEnvValue('PUBLIC_URL');

  if (explicitUrl) {
    return explicitUrl;
  }

  const publicHost = process.env.NEXUS_PUBLIC_HOST || getRootEnvValue('NEXUS_PUBLIC_HOST');
  const publicPort = process.env.NEXUS_PUBLIC_PORT || getRootEnvValue('NEXUS_PUBLIC_PORT');

  if (publicHost && publicPort) {
    return `http://${publicHost}:${publicPort}`;
  }

  return '';
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

function ensureDirectory(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function timestampId() {
  return new Date().toISOString().replaceAll(':', '-').replace(/\..+/, 'Z');
}

function commandExists(command) {
  const result = spawnSync('bash', ['-lc', `command -v ${command}`], {
    stdio: 'ignore',
    env: process.env,
  });
  return result.status === 0;
}

function sendFileViaT2me(filePath, caption, sendT2me) {
  if (!sendT2me) {
    return { sent: false, reason: 'disabled' };
  }

  if (!commandExists('t2me')) {
    return { sent: false, reason: 't2me_not_found' };
  }

  const result = spawnSync('t2me', ['send', '--file', filePath, '--caption', caption], {
    encoding: 'utf8',
    env: process.env,
  });

  if (result.status !== 0) {
    return {
      sent: false,
      reason: 'send_failed',
      stderr: result.stderr?.trim() || '',
      stdout: result.stdout?.trim() || '',
    };
  }

  return {
    sent: true,
    output: result.stdout?.trim() || '',
  };
}

async function waitForVisible(locator, timeout) {
  try {
    await locator.waitFor({ state: 'visible', timeout });
    return true;
  } catch {
    return false;
  }
}

async function waitForAnyStage(page, timeoutMs) {
  const candidates = [
    ['login-form', page.getByTestId('login-form')],
    ['latest-card', page.getByTestId('latest-session-card')],
    ['latest-empty', page.getByTestId('latest-session-empty')],
    ['latest-error', page.getByTestId('latest-session-error')],
    ['load-error', page.getByTestId('dashboard-load-error')],
    ['loading', page.getByText('⏳ Загрузка...')],
  ];

  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    for (const [name, locator] of candidates) {
      if (await locator.count() > 0) {
        return name;
      }
    }
    await page.waitForTimeout(250);
  }

  return 'none';
}

function emitStep(index, title, extra = '') {
  const suffix = extra ? ` :: ${extra}` : '';
  console.log(`[step ${String(index).padStart(2, '0')}] ${title}${suffix}`);
}

function getPipelineMode() {
  const cliModeIndex = process.argv.indexOf('--mode');
  if (cliModeIndex >= 0 && process.argv[cliModeIndex + 1]) {
    return process.argv[cliModeIndex + 1];
  }

  return process.env.NEXUS_E2E_PIPELINE_MODE || 'smoke';
}

async function main() {
  const positionalArgs = process.argv.slice(2).filter((arg, index, all) => {
    if (arg === '--mode') {
      return false;
    }
    if (index > 0 && all[index - 1] === '--mode') {
      return false;
    }
    return !arg.startsWith('--');
  });
  const publicUrl = positionalArgs[0] || getPublishedUrl();
  assert(publicUrl, 'NEXUS_PUBLIC_URL, PUBLIC_URL, or argv[2] is required');

  const executablePath = ensureChromiumExecutable();
  const timeoutMs = getRequiredEnvNumber('NEXUS_PLAYWRIGHT_TIMEOUT_MS', 30000);
  const hydrationWaitMs = getRequiredEnvNumber('NEXUS_PLAYWRIGHT_HYDRATION_WAIT_MS', 4000);
  const sendT2me = getBooleanEnv('NEXUS_E2E_SEND_T2ME', true);
  const pipelineMode = getPipelineMode();
  const expandDashboard = pipelineMode === 'smoke' && getBooleanEnv('NEXUS_E2E_EXPAND_DASHBOARD', true);
  const outputRoot = path.resolve(
    process.cwd(),
    '..',
    'tmp',
    pipelineMode === 'login' ? 'e2e-login' : 'e2e-smoke',
    `run-${timestampId()}`,
  );

  ensureDirectory(outputRoot);

  const browser = await chromium.launch({
    executablePath,
    headless: true,
  });

  const context = await browser.newContext({
    viewport: {
      width: 1512,
      height: 982,
    },
  });

  const page = await context.newPage();
  const apiResponses = [];
  const failedRequests = [];
  const screenshots = [];
  const steps = [];

  page.on('response', (response) => {
    if (response.url().includes('/api/')) {
      apiResponses.push({
        status: response.status(),
        url: response.url(),
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

  async function captureStepScreenshot(stepNumber, slug, caption) {
    const filePath = path.join(outputRoot, `${String(stepNumber).padStart(2, '0')}-${slug}.jpg`);
    await page.screenshot({
      path: filePath,
      type: 'jpeg',
      quality: 90,
      fullPage: false,
    });

    const sendResult = sendFileViaT2me(filePath, caption, sendT2me);
    screenshots.push({
      step: stepNumber,
      slug,
      file_path: filePath,
      caption,
      t2me: sendResult,
    });
  }

  try {
    emitStep(1, 'open-published-url', publicUrl);
    const response = await page.goto(publicUrl, {
      waitUntil: 'domcontentloaded',
      timeout: timeoutMs,
    });

    steps.push({
      step: 1,
      name: 'open-published-url',
      status: response?.status() || 0,
    });
    await captureStepScreenshot(1, 'open-url', 'E2E smoke step 1: published URL opened.');

    const authStatus = await fetch(new URL('/api/auth/status', publicUrl)).then((res) => res.json());
    const initialStage = await waitForAnyStage(page, timeoutMs);

    emitStep(2, 'initial-stage-detected', initialStage);
    steps.push({
      step: 2,
      name: 'initial-stage-detected',
      stage: initialStage,
      auth_required: authStatus.auth_required,
      password_required: authStatus.password_required,
    });

    if (initialStage === 'login-form' && authStatus.password_required) {
      await captureStepScreenshot(2, 'login-form', 'E2E smoke step 2: login form visible before auth.');

      emitStep(3, 'password-login');
      const password = getLoginPassword();
      assert(password, 'Password required but NEXUS_E2E_PASSWORD/NEXUS_PASSWORD is not set');

      const loginResponsePromise = page.waitForResponse(
        (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/auth/login'),
        { timeout: timeoutMs },
      );

      await page.getByTestId('auth-password-input').fill(password);
      await page.getByTestId('login-button').click();
      await loginResponsePromise;
      await page.waitForLoadState('domcontentloaded', { timeout: timeoutMs }).catch(() => {});

      steps.push({
        step: 3,
        name: 'password-login',
        status: 'ok',
      });
    } else if (initialStage === 'login-form' && authStatus.auth_required && authStatus.telegram_enabled) {
      emitStep(3, 'telegram-login');
      const telegramIdToken = getTelegramIdToken();
      assert(telegramIdToken, 'Telegram-only auth is enabled but NEXUS_E2E_TELEGRAM_ID_TOKEN is not set');

      const loginResponse = await context.request.post(new URL('/api/auth/telegram/login', publicUrl).toString(), {
        data: {
          id_token: telegramIdToken,
        },
      });
      assert(loginResponse.ok(), `Telegram login failed with ${loginResponse.status()}`);

      await page.reload({
        waitUntil: 'domcontentloaded',
        timeout: timeoutMs,
      });

      steps.push({
        step: 3,
        name: 'telegram-login',
        status: loginResponse.status(),
      });
    } else {
      steps.push({
        step: 3,
        name: 'login-skipped',
        reason: initialStage,
      });
    }

    const loadingIndicator = page.getByText('⏳ Загрузка...');
    if (await loadingIndicator.count() > 0) {
      await loadingIndicator.waitFor({
        state: 'hidden',
        timeout: hydrationWaitMs,
      }).catch(() => {});
    }

    const postLoginStage = await waitForAnyStage(page, timeoutMs);
    emitStep(4, 'post-login-stage', postLoginStage);
    steps.push({
      step: 4,
      name: 'post-login-stage',
      stage: postLoginStage,
    });

    await captureStepScreenshot(4, 'post-login', `E2E smoke step 4: stage after login is ${postLoginStage}.`);

    if (expandDashboard && await page.getByTestId('latest-only-hint').count() > 0) {
      emitStep(5, 'expand-dashboard-via-filter');
      const sessionsResponsePromise = page.waitForResponse(
        (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/sessions'),
        { timeout: timeoutMs },
      );
      const metricsResponsePromise = page.waitForResponse(
        (currentResponse) => currentResponse.status() === 200 && currentResponse.url().includes('/api/metrics'),
        { timeout: timeoutMs },
      );

      await page.getByTestId('date-filter').selectOption('all');
      await Promise.all([sessionsResponsePromise, metricsResponsePromise]);
      await captureStepScreenshot(5, 'expanded-dashboard', 'E2E smoke step 5: dashboard expanded after changing filters.');

      steps.push({
        step: 5,
        name: 'expand-dashboard-via-filter',
        status: 'ok',
      });
    }

    if (await page.getByTestId('session-card').count() > 0) {
      emitStep(6, 'capture-first-session-card');
      const firstCard = page.getByTestId('session-card').first();
      await firstCard.scrollIntoViewIfNeeded();

      const cardPath = path.join(outputRoot, '06-first-session-card.jpg');
      await firstCard.screenshot({
        path: cardPath,
        type: 'jpeg',
        quality: 92,
      });

      const sendResult = sendFileViaT2me(
        cardPath,
        'E2E smoke step 6: first session card after dashboard expansion.',
        sendT2me,
      );
      screenshots.push({
        step: 6,
        slug: 'first-session-card',
        file_path: cardPath,
        caption: 'E2E smoke step 6: first session card after dashboard expansion.',
        t2me: sendResult,
      });

      steps.push({
        step: 6,
        name: 'capture-first-session-card',
        status: 'ok',
      });
    }

    const summary = {
      pipeline_mode: pipelineMode,
      public_url: publicUrl,
      chromium: executablePath,
      output_root: outputRoot,
      send_t2me: sendT2me,
      expand_dashboard: expandDashboard,
      steps,
      screenshots,
      api_responses: apiResponses,
      failed_requests: failedRequests,
      section_headers: await page.locator('[data-testid$="-section-header"]').allInnerTexts().catch(() => []),
      latest_only_hint_visible: await page.getByTestId('latest-only-hint').count().catch(() => 0),
      latest_card_visible: await page.getByTestId('latest-session-card').count().catch(() => 0),
      dashboard_load_error: await page.getByTestId('dashboard-load-error').allInnerTexts().catch(() => []),
    };

    fs.writeFileSync(
      path.join(outputRoot, 'summary.json'),
      `${JSON.stringify(summary, null, 2)}\n`,
    );

    console.log(JSON.stringify(summary, null, 2));

    assert(response?.status() === 200, `Published page returned ${response?.status()}`);
    assert(failedRequests.length === 0, `Failed requests detected: ${JSON.stringify(failedRequests)}`);
    assert(summary.latest_card_visible > 0 || summary.dashboard_load_error.length > 0, 'No latest card or dashboard state was detected.');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
