import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page, type APIRequestContext, type Response } from '@playwright/test';

type MetricsPayload = {
  success: boolean;
  data: {
    total_sessions: number;
    by_agent: Record<string, number>;
    by_status: Record<string, number>;
    total_tokens: number;
    last_updated: string;
  };
};

type SessionRecord = {
  session_id: string;
  agent_type: string;
  status: string;
};

type SessionsPayload = {
  total: number;
  limit: number;
  offset: number;
  sessions: SessionRecord[];
};

type LatestSessionPayload = {
  meta: {
    scanned_providers: number;
    scanned_files: number;
  };
  query: {
    timezone: string;
  };
  latest: {
    provider: string;
    path: string;
    relative_path: string;
    filename: string;
    session_id: string;
    format: string;
    modified_at: string;
    modified_at_local: string;
    modified_human: string;
    age_seconds: number;
    age_human: string;
    activity_state: string;
    record_count: number;
    parse_errors: number;
    user_message_count: number;
    first_user_message: string;
    last_user_message: string;
    duration_seconds?: number;
    duration_human?: string;
    started_at?: string;
    started_at_local?: string;
    intent_evolution?: string[];
    intent_summary_source?: 'ai' | 'local_fallback';
    intent_summary_provider?: string;
  } | null;
  errors: Array<{
    detail: string;
  }>;
};

type AuthStatusPayload = {
  authenticated: boolean;
  password_required: boolean;
  auth_required?: boolean;
  telegram_enabled?: boolean;
};

type FailedRequest = {
  method: string;
  url: string;
  error: string;
};

type DashboardVisit = {
  response: Response | null;
  failedRequests: FailedRequest[];
};

const LOADING_INDICATOR_TEXT = '⏳ Загрузка...';
const METRICS_API_PATH = '/api/metrics';
const SESSIONS_API_PATH = '/api/sessions';
const LATEST_API_PATH = '/api/latest-session';
const PREFERRED_AGENT_ORDER = ['qwen', 'codex', 'pi', 'kimi', 'claude', 'gemini'];

function getRootEnvValue(name: string): string {
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

function getLoginPassword(): string {
  return process.env.NEXUS_E2E_PASSWORD
    || process.env.NEXUS_PASSWORD
    || getRootEnvValue('NEXUS_PASSWORD');
}

function getTelegramIdToken(): string {
  return process.env.NEXUS_E2E_TELEGRAM_ID_TOKEN || '';
}

function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function buildSessionsUrl(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      searchParams.set(key, String(value));
    }
  }

  const query = searchParams.toString();
  return `/api/sessions${query ? `?${query}` : ''}`;
}

function isSuccessfulApiResponse(
  response: Response,
  path: string,
  requiredFragments: string[] = [],
): boolean {
  const url = response.url();
  return response.status() === 200
    && url.includes(path)
    && requiredFragments.every((fragment) => url.includes(fragment));
}

async function expectJson<T>(responsePromise: Promise<Response>): Promise<T> {
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

async function expectDashboardContent(page: Page): Promise<void> {
  const sectionHeaders = page.locator('[data-testid$="-section-header"]');
  const emptyState = page.getByTestId('empty-state');

  if (await sectionHeaders.count() > 0) {
    await expect(sectionHeaders.first()).toBeVisible();
    return;
  }

  await expect(emptyState).toBeVisible();
}

async function gotoDashboard(page: Page): Promise<DashboardVisit> {
  const failedRequests: FailedRequest[] = [];

  page.on('requestfailed', (request) => {
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      error: request.failure()?.errorText || 'unknown',
    });
  });

  const response = await page.goto('/', {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: '🤖 Agent Nexus' })).toBeVisible();

  return {
    response,
    failedRequests,
  };
}

async function expectLoadedDashboard(page: Page): Promise<void> {
  await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
  await expect(page.getByTestId('latest-session-card')).toBeVisible();
  await expect(page.getByTestId('latest-only-hint')).toBeVisible();
  await expect(page.getByTestId('metric-total-sessions-card')).toHaveCount(0);
}

async function expandDashboard(page: Page): Promise<void> {
  const sessionsResponsePromise = page.waitForResponse((response) => {
    return isSuccessfulApiResponse(response, SESSIONS_API_PATH);
  });
  const metricsResponsePromise = page.waitForResponse((response) => {
    return isSuccessfulApiResponse(response, METRICS_API_PATH);
  });

  await page.getByTestId('date-filter').selectOption('all');
  await Promise.all([sessionsResponsePromise, metricsResponsePromise]);
  await expect(page.getByTestId('metric-total-sessions-value')).toBeVisible();
  await expectDashboardContent(page);
}

async function maybeAuthenticateThroughUi(
  page: Page,
): Promise<void> {
  const authStatus = await getJson<AuthStatusPayload>(
    page.context().request,
    '/api/auth/status',
  );

  if (!authStatus.auth_required || authStatus.authenticated) {
    return;
  }

  await expect(page.getByTestId('login-form')).toBeVisible();

  const latestResponsePromise = page.waitForResponse((response) => {
    return isSuccessfulApiResponse(response, LATEST_API_PATH);
  });

  if (!authStatus.password_required && authStatus.telegram_enabled) {
    const telegramIdToken = getTelegramIdToken();
    test.skip(!telegramIdToken, 'NEXUS_E2E_TELEGRAM_ID_TOKEN is required when Telegram-only auth is enabled');

    const loginResponse = await page.context().request.post('/api/auth/telegram/login', {
      data: {
        id_token: telegramIdToken,
      },
    });
    expect(loginResponse.ok()).toBeTruthy();

    await page.reload({
      waitUntil: 'domcontentloaded',
    });
    await latestResponsePromise;
    return;
  }

  const password = getLoginPassword();
  test.skip(!password, 'NEXUS_E2E_PASSWORD or NEXUS_PASSWORD is required when password auth is enabled');

  await page.getByTestId('auth-password-input').fill(password);
  await page.getByTestId('login-button').click();
  await latestResponsePromise;
}

async function maybeAuthenticateApiRequest(request: APIRequestContext): Promise<void> {
  const authStatus = await getJson<AuthStatusPayload>(
    request,
    '/api/auth/status',
  );

  if (!authStatus.auth_required || authStatus.authenticated) {
    return;
  }

  if (!authStatus.password_required && authStatus.telegram_enabled) {
    const telegramIdToken = getTelegramIdToken();
    test.skip(!telegramIdToken, 'NEXUS_E2E_TELEGRAM_ID_TOKEN is required when Telegram-only auth is enabled');

    const loginResponse = await request.post('/api/auth/telegram/login', {
      data: {
        id_token: telegramIdToken,
      },
    });
    expect(loginResponse.ok()).toBeTruthy();
    return;
  }

  const password = getLoginPassword();
  test.skip(!password, 'NEXUS_E2E_PASSWORD or NEXUS_PASSWORD is required when password auth is enabled');

  const loginResponse = await request.post('/api/auth/login', {
    data: {
      password,
    },
  });

  expect(loginResponse.ok()).toBeTruthy();
}

async function getJson<T>(request: APIRequestContext, url: string): Promise<T> {
  const response = await request.get(url);
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

async function expectMetricValue(page: Page, testId: string, value: number): Promise<void> {
  await expect(page.getByTestId(testId)).toHaveText(String(value));
}

async function expectSessionCardsToMatch(
  page: Page,
  attributes: Record<string, string>,
): Promise<void> {
  const sessionCards = page.getByTestId('session-card');
  const cardCount = await sessionCards.count();

  for (let index = 0; index < cardCount; index += 1) {
    for (const [name, value] of Object.entries(attributes)) {
      await expect(sessionCards.nth(index)).toHaveAttribute(name, value);
    }
  }
}

async function chooseActiveAgent(request: APIRequestContext): Promise<string | null> {
  await maybeAuthenticateApiRequest(request);
  const metrics = await getJson<MetricsPayload>(request, METRICS_API_PATH);

  for (const agent of PREFERRED_AGENT_ORDER) {
    if (!metrics.data.by_agent[agent]) {
      continue;
    }

    const sessions = await getJson<SessionsPayload>(
      request,
      buildSessionsUrl({ status: 'active', agent, changed_date: getTodayDateString(), limit: 1 }),
    );

    if (sessions.total > 0) {
      return agent;
    }
  }

  return null;
}

test.describe('Published URL end-to-end', () => {
  test('renders dashboard without failed network requests', async ({ page, request }) => {
    const { response, failedRequests } = await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);

    expect(response?.status()).toBe(200);
    expect(failedRequests).toEqual([]);
    await expect(page.getByTestId('latest-session-card')).toBeVisible();
  });

  test('renders a valid empty dashboard when the API returns no sessions', async ({ page }) => {
    await page.route('**/api/auth/status', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          password_required: false,
          auth_required: false,
          password_enabled: false,
          telegram_enabled: false,
          telegram_configured: false,
          telegram_client_id: null,
          telegram_request_phone: false,
          auth_method: 'none',
        }),
      });
    });

    await page.route('**/api/latest-session', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          meta: {
            scanned_providers: 6,
            scanned_files: 0,
          },
          query: {
            timezone: 'Europe/Moscow',
          },
          latest: null,
          errors: [],
        } satisfies LatestSessionPayload),
      });
    });

    await page.goto('/', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
    await expect(page.getByTestId('latest-session-empty')).toBeVisible();
    await expect(page.getByTestId('latest-only-hint')).toBeVisible();
    await expect(page.getByTestId('empty-state')).toHaveCount(0);
    await expect(page.locator('[data-testid$="-section-header"]')).toHaveCount(0);
  });

  test('shows collapsed intent evolution and expands it on demand', async ({ page }) => {
    await page.route('**/api/auth/status', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          password_required: false,
          auth_required: false,
          password_enabled: false,
          telegram_enabled: false,
          telegram_configured: false,
          telegram_client_id: null,
          telegram_request_phone: false,
          auth_method: 'none',
        }),
      });
    });

    await page.route('**/api/latest-session', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          meta: {
            scanned_providers: 6,
            scanned_files: 1,
          },
          query: {
            timezone: 'Europe/Moscow',
          },
          latest: {
            provider: 'codex',
            path: '/home/pets/.codex/sessions/2026/03/10/rollout-demo.jsonl',
            relative_path: '2026/03/10/rollout-demo.jsonl',
            filename: 'rollout-demo.jsonl',
            session_id: 'rollout-demo',
            format: 'jsonl',
            modified_at: '2026-03-10T08:50:16.071986+00:00',
            modified_at_local: '2026-03-10 11:50:16 MSK',
            modified_human: 'today at 11:50',
            age_seconds: 1,
            age_human: '1 second ago',
            activity_state: 'live',
            record_count: 42,
            parse_errors: 0,
            user_message_count: 4,
            first_user_message: 'починить фильтр сегодня',
            last_user_message: 'усилить playwright проверку',
            started_at: '2026-03-10T08:00:00+00:00',
            started_at_local: '2026-03-10 11:00:00 MSK',
            duration_seconds: 9000,
            duration_human: '2 ч 30 мин',
            intent_summary_source: 'ai',
            intent_summary_provider: 'qwen',
            intent_evolution: [
              'починить фильтр сегодня',
              'исправить latest карточку',
              'показать полный путь файла',
              'усилить playwright проверку',
            ],
          },
          errors: [],
        } satisfies LatestSessionPayload),
      });
    });

    await page.goto('/', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
    await expect(page.getByTestId('latest-session-card')).toBeVisible();
    await expect(page.getByTestId('latest-duration-value')).toHaveText('2 ч 30 мин');
    await expect(page.getByTestId('latest-intent-step-0')).toHaveText('1. починить фильтр сегодня');
    await expect(page.getByTestId('latest-intent-step-1')).toHaveText('2. исправить latest карточку');
    await expect(page.getByTestId('latest-intent-step-2')).toHaveCount(0);
    await expect(page.getByTestId('latest-intent-toggle')).toHaveText('ещё 2 шага');

    await page.getByTestId('latest-intent-toggle').click();
    await expect(page.getByTestId('latest-intent-step-2')).toHaveText('3. показать полный путь файла');
    await expect(page.getByTestId('latest-intent-step-3')).toHaveText('4. усилить playwright проверку');
    await expect(page.getByTestId('latest-intent-toggle')).toHaveText('свернуть');
  });

  test('shows metrics that match the backend payload', async ({ page, request }) => {
    await maybeAuthenticateApiRequest(request);
    const apiMetrics = await getJson<MetricsPayload>(request, METRICS_API_PATH);

    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);
    await expandDashboard(page);

    await expectMetricValue(page, 'metric-total-sessions-value', apiMetrics.data.total_sessions);
    await expectMetricValue(page, 'metric-active-value', apiMetrics.data.by_status.active || 0);
    await expectMetricValue(page, 'metric-errors-value', apiMetrics.data.by_status.error || 0);

    for (const agent of Object.keys(apiMetrics.data.by_agent).slice(0, 3)) {
      await expect(page.getByTestId(`metric-agent-${agent}`)).toBeVisible();
    }
  });

  test('status filter narrows the dashboard to error sessions only', async ({ page, request }) => {
    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);

    const filteredResponsePromise = page.waitForResponse((response) => {
      return isSuccessfulApiResponse(response, SESSIONS_API_PATH, ['status=error']);
    });

    await page.getByTestId('status-filter').selectOption('error');
    const filteredPayload = await expectJson<SessionsPayload>(filteredResponsePromise);

    if (filteredPayload.sessions.length === 0) {
      await expect(page.getByTestId('empty-state')).toBeVisible();
      await expect(page.getByTestId('session-card')).toHaveCount(0);
      return;
    }

    await expect(page.getByTestId('error-section')).toBeVisible();
    await expect(page.getByTestId('session-card')).toHaveCount(filteredPayload.sessions.length);
    await expectSessionCardsToMatch(page, { 'data-session-status': 'error' });
  });

  test('combined status and agent filters stay aligned with API results', async ({ page, request }) => {
    const activeAgent = await chooseActiveAgent(request);
    test.skip(!activeAgent, 'No active agent with sessions available for E2E filter coverage');

    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);

    const activeResponsePromise = page.waitForResponse((response) => {
      return isSuccessfulApiResponse(response, SESSIONS_API_PATH, ['status=active']);
    });

    await page.getByTestId('status-filter').selectOption('active');
    await activeResponsePromise;

    const agentResponsePromise = page.waitForResponse((response) => {
      return isSuccessfulApiResponse(response, SESSIONS_API_PATH, [
        'status=active',
        `agent=${activeAgent!}`,
      ]);
    });

    await page.getByTestId('agent-filter').selectOption(activeAgent!);
    const filteredPayload = await expectJson<SessionsPayload>(agentResponsePromise);

    expect(filteredPayload.sessions.length).toBeGreaterThan(0);
    await expect(page.getByTestId('session-card')).toHaveCount(filteredPayload.sessions.length);
    await expectSessionCardsToMatch(page, {
      'data-session-status': 'active',
      'data-agent-type': activeAgent!,
    });
  });

  test('refresh button triggers both sessions and metrics refetches', async ({ page, request }) => {
    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);
    await expandDashboard(page);

    const sessionsResponsePromise = page.waitForResponse((response) => {
      return isSuccessfulApiResponse(response, SESSIONS_API_PATH);
    });
    const metricsResponsePromise = page.waitForResponse((response) => {
      return isSuccessfulApiResponse(response, METRICS_API_PATH);
    });

    await page.getByTestId('refresh-button').click();
    await Promise.all([sessionsResponsePromise, metricsResponsePromise]);

    await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
    await expect(page.getByTestId('metric-total-sessions-value')).toBeVisible();
  });

  test('API auth flow establishes and clears a session cookie on the published URL', async ({ request }) => {
    const authStatus = await getJson<AuthStatusPayload>(
      request,
      '/api/auth/status',
    );
    const e2ePassword = getLoginPassword();
    const telegramIdToken = getTelegramIdToken();

    if (authStatus.auth_required && !authStatus.password_required && authStatus.telegram_enabled && !telegramIdToken) {
      test.skip(true, 'NEXUS_E2E_TELEGRAM_ID_TOKEN is required to verify the Telegram API auth flow');
    }

    if (authStatus.password_required && !e2ePassword) {
      test.skip(true, 'NEXUS_E2E_PASSWORD is required to verify the password API auth flow');
    }

    if (!authStatus.auth_required) {
      const me = await getJson<{ is_authenticated: boolean }>(request, '/api/auth/me');
      expect(me.is_authenticated).toBe(true);
      return;
    }

    const loginResponse = authStatus.password_required
      ? await request.post('/api/auth/login', {
        data: {
          password: e2ePassword,
        },
      })
      : await request.post('/api/auth/telegram/login', {
        data: {
          id_token: telegramIdToken,
        },
      });

    expect(loginResponse.ok()).toBeTruthy();
    expect(loginResponse.headers()['set-cookie']).toContain('session_id=');

    const meAfterLogin = await getJson<{ is_authenticated: boolean; username: string }>(
      request,
      '/api/auth/me',
    );
    expect(meAfterLogin.is_authenticated).toBe(true);
    expect(meAfterLogin.username).toBe('admin');

    const logoutResponse = await request.post('/api/auth/logout');
    expect(logoutResponse.ok()).toBeTruthy();

    const meAfterLogout = await getJson<{ is_authenticated: boolean }>(request, '/api/auth/me');
    expect(meAfterLogout.is_authenticated).toBe(false);
  });

  test('session detail endpoint serves a real session from the published API', async ({ request }) => {
    await maybeAuthenticateApiRequest(request);
    const sessions = await getJson<SessionsPayload>(request, buildSessionsUrl({ limit: 1 }));
    const [firstSession] = sessions.sessions;

    test.skip(!firstSession, 'No sessions available for session detail coverage');

    const sessionDetail = await getJson<SessionRecord>(
      request,
      `/api/sessions/${firstSession!.session_id}`,
    );

    expect(sessionDetail.session_id).toBe(firstSession!.session_id);
    expect(sessionDetail.agent_type).toBeTruthy();
    expect(sessionDetail.status).toBeTruthy();
  });
});
