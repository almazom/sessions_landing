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
  source_file?: string;
  route?: {
    harness: string;
    id: string;
    href: string;
  };
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
    route?: {
      harness: string;
      id: string;
      href: string;
    };
  } | null;
  errors: Array<{
    detail: string;
  }>;
};

type SessionArtifactPayload = {
  meta: {
    timezone: string;
    live_within_minutes: number;
    active_within_minutes: number;
  };
  session: {
    provider: string;
    path: string;
    filename: string;
    session_id: string;
    cwd: string;
    first_user_message: string;
    last_user_message: string;
    user_messages?: string[];
    started_at?: string | null;
    started_at_local?: string | null;
    ended_at?: string | null;
    ended_at_local?: string | null;
    duration_seconds?: number | null;
    duration_human?: string | null;
    time_window?: {
      source: string;
      started_at?: string | null;
      started_at_local?: string | null;
      ended_at?: string | null;
      ended_at_local?: string | null;
      duration_seconds?: number | null;
      duration_human?: string | null;
      scope_summary: string;
    };
    message_anchors?: {
      first: string;
      middle: string[];
      last: string;
    };
    intent_evolution: string[];
    topic_threads?: string[];
    state_model?: {
      labels: string[];
      safety_mode: 'read-only' | 'ask-only' | 'resume-allowed';
      summary: string;
      rationale: string[];
      capabilities?: {
        can_ask: boolean;
        can_resume: boolean;
        can_restore: boolean;
      };
      ask_session?: {
        available: boolean;
        label: string;
        detail: string;
      };
      resume_session?: {
        available: boolean;
        label: string;
        detail: string;
      };
    };
    evidence_sparsity?: {
      is_sparse: boolean;
      summary: string;
      present_layers: string[];
      missing_layers: string[];
    };
    route: {
      harness: string;
      id: string;
      href: string;
    };
    tool_calls: string[];
    files_modified: string[];
    git_repository_root?: string | null;
    git_commits?: Array<{
      hash: string;
      short_hash: string;
      title: string;
      author_name: string;
      committed_at: string;
      committed_at_local?: string;
    }>;
    token_usage: {
      total_tokens: number;
      input_tokens: number;
      output_tokens: number;
    };
    timeline?: Array<{
      timestamp: string;
      event_type: string;
      description: string;
      icon?: string;
      details?: string | null;
    }>;
  };
};

type SessionAskPayload = {
  meta: {
    tool: string;
    tool_version: string;
    generated_at: string;
    answer_source: 'local_artifact';
    reasoning_mode: 'lexical_evidence_match';
  };
  source: {
    harness_provider?: string;
    format: 'json' | 'jsonl';
    record_count: number;
    snippet_count: number;
    user_message_count: number;
  };
  question: {
    text: string;
  };
  answer: {
    mode: 'ask-only';
    response: string;
    confidence: number;
    evidence: Array<{
      kind: 'user_message' | 'assistant_message' | 'timeline' | 'artifact_field';
      label: string;
      excerpt: string;
      score: number;
    }>;
    limitations: string[];
  };
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
const SESSION_ARTIFACTS_API_PATH = '/api/session-artifacts';
const PREFERRED_AGENT_ORDER = ['qwen', 'codex', 'pi', 'kimi', 'claude', 'gemini'];
const AUTHENTICATED_STATUS = {
  authenticated: true,
  password_required: false,
  auth_required: false,
  password_enabled: false,
  telegram_enabled: false,
  telegram_configured: false,
  telegram_client_id: null,
  telegram_request_phone: false,
  auth_method: 'none',
};

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

function isIgnorableRequestFailure(url: string, error: string): boolean {
  return error === 'net::ERR_ABORTED' && url.includes('_rsc=');
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
    const error = request.failure()?.errorText || 'unknown';
    if (isIgnorableRequestFailure(request.url(), error)) {
      return;
    }
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      error,
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
  await expect(page.getByTestId('latest-only-hint')).toHaveCount(0);
  await expect(page.getByTestId('metric-total-sessions-card')).toBeVisible();
}

async function expandDashboard(page: Page): Promise<void> {
  await expect(page.getByTestId('metric-total-sessions-value')).toBeVisible();
  await expectDashboardContent(page);
}

async function mockDashboardApis(
  page: Page,
  payloads: {
    latest: LatestSessionPayload;
    sessions: SessionsPayload;
    metrics: MetricsPayload;
    detail?: SessionArtifactPayload;
    ask?: SessionAskPayload;
  },
): Promise<void> {
  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(AUTHENTICATED_STATUS),
    });
  });

  await page.route('**/api/latest-session', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(payloads.latest),
    });
  });

  await page.route('**/api/sessions**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(payloads.sessions),
    });
  });

  await page.route('**/api/metrics', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(payloads.metrics),
    });
  });

  if (payloads.detail) {
    await page.route(`**${SESSION_ARTIFACTS_API_PATH}/**`, async (route) => {
      const request = route.request();
      const isAskRequest = request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/ask');

      if (isAskRequest) {
        if (!payloads.ask) {
          await route.fulfill({
            status: 404,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Ask flow is not mocked for this test.' }),
          });
          return;
        }

        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify(payloads.ask),
        });
        return;
      }

      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(payloads.detail),
      });
    });
  }
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
    await mockDashboardApis(page, {
      latest: {
        meta: {
          scanned_providers: 6,
          scanned_files: 0,
        },
        query: {
          timezone: 'Europe/Moscow',
        },
        latest: null,
        errors: [],
      },
      sessions: {
        total: 0,
        limit: 100,
        offset: 0,
        sessions: [],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 0,
          by_agent: {},
          by_status: {},
          total_tokens: 0,
          last_updated: '2026-03-12T00:00:00Z',
        },
      },
    });

    await page.goto('/', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
    await expect(page.getByTestId('latest-session-empty')).toBeVisible();
    await expect(page.getByTestId('latest-only-hint')).toHaveCount(0);
    await expect(page.getByTestId('metric-total-sessions-value')).toHaveText('0');
    await expect(page.getByTestId('empty-state')).toBeVisible();
    await expect(page.locator('[data-testid$="-section-header"]')).toHaveCount(0);
  });

  test('shows default latest + today list without manual filter expansion', async ({ page }) => {
    await mockDashboardApis(page, {
      latest: {
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
          route: {
            harness: 'codex',
            id: 'rollout-demo.jsonl',
            href: '/sessions/codex/rollout-demo.jsonl',
          },
        },
        errors: [],
      },
      sessions: {
        total: 2,
        limit: 100,
        offset: 0,
        sessions: [
          {
            session_id: 'second-session',
            agent_type: 'codex',
            agent_name: 'Codex',
            cwd: '/home/pets/zoo/agents_sessions_dashboard',
            timestamp_start: '2026-03-12T08:10:00+00:00',
            status: 'active',
            user_intent: 'подготовить detail page',
            first_user_message: 'подготовить detail page',
            last_user_message: 'сделать ссылку на сессию',
            user_message_count: 4,
            tool_calls: ['exec_command'],
            token_usage: {
              input_tokens: 100,
              output_tokens: 80,
              total_tokens: 180,
            },
            files_modified: [],
            source_file: '/home/pets/.codex/sessions/2026/03/10/rollout-second.jsonl',
            route: {
              harness: 'codex',
              id: 'rollout-second.jsonl',
              href: '/sessions/codex/rollout-second.jsonl',
            },
          },
          {
            session_id: 'third-session',
            agent_type: 'qwen',
            agent_name: 'Qwen',
            cwd: '/home/pets/zoo/agents_sessions_dashboard',
            timestamp_start: '2026-03-12T08:00:00+00:00',
            status: 'completed',
            user_intent: 'закрыть баги published url',
            first_user_message: 'закрыть баги published url',
            last_user_message: 'проверить published smoke',
            user_message_count: 2,
            tool_calls: [],
            token_usage: {
              input_tokens: 50,
              output_tokens: 40,
              total_tokens: 90,
            },
            files_modified: [],
            source_file: '/home/pets/.qwen/projects/demo/chats/third-session.jsonl',
            route: {
              harness: 'qwen',
              id: 'third-session.jsonl',
              href: '/sessions/qwen/third-session.jsonl',
            },
          },
        ],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 2,
          by_agent: { codex: 1, qwen: 1 },
          by_status: { active: 1, completed: 1 },
          total_tokens: 3210,
          last_updated: '2026-03-12T00:00:00Z',
        },
      },
    });

    await page.goto('/', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByText(LOADING_INDICATOR_TEXT)).toHaveCount(0);
    await expect(page.getByTestId('latest-session-card')).toBeVisible();
    await expect(page.getByTestId('metric-total-sessions-value')).toHaveText('2');
    await expect(page.getByTestId('latest-only-hint')).toHaveCount(0);
    await expect(page.getByTestId('session-card')).toHaveCount(2);
    await expect(page.getByTestId('active-section')).toBeVisible();
    await expect(page.getByTestId('completed-section')).toBeVisible();
  });

  test('shows collapsed intent evolution and expands it on demand', async ({ page }) => {
    await mockDashboardApis(page, {
      latest: {
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
          route: {
            harness: 'codex',
            id: 'rollout-demo.jsonl',
            href: '/sessions/codex/rollout-demo.jsonl',
          },
        },
        errors: [],
      },
      sessions: {
        total: 0,
        limit: 100,
        offset: 0,
        sessions: [],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 0,
          by_agent: {},
          by_status: {},
          total_tokens: 0,
          last_updated: '2026-03-12T00:00:00Z',
        },
      },
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

  test('session cards and latest card link to the artifact detail page', async ({ page }) => {
    await mockDashboardApis(page, {
      latest: {
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
          intent_evolution: ['починить фильтр сегодня'],
          route: {
            harness: 'codex',
            id: 'rollout-demo.jsonl',
            href: '/sessions/codex/rollout-demo.jsonl',
          },
        },
        errors: [],
      },
      sessions: {
        total: 1,
        limit: 100,
        offset: 0,
        sessions: [
          {
            session_id: 'second-session',
            agent_type: 'codex',
            agent_name: 'Codex',
            cwd: '/home/pets/zoo/agents_sessions_dashboard',
            timestamp_start: '2026-03-12T08:10:00+00:00',
            status: 'active',
            user_intent: 'открыть detail page',
            first_user_message: 'открыть detail page',
            last_user_message: 'проверить rich card',
            user_message_count: 3,
            tool_calls: ['exec_command'],
            token_usage: {
              input_tokens: 120,
              output_tokens: 90,
              total_tokens: 210,
            },
            files_modified: [],
            source_file: '/home/pets/.codex/sessions/2026/03/10/rollout-second.jsonl',
            route: {
              harness: 'codex',
              id: 'rollout-second.jsonl',
              href: '/sessions/codex/rollout-second.jsonl',
            },
          },
        ],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 1,
          by_agent: { codex: 1 },
          by_status: { active: 1 },
          total_tokens: 300,
          last_updated: '2026-03-12T00:00:00Z',
        },
      },
      detail: {
        meta: {
          timezone: 'Europe/Moscow',
          live_within_minutes: 10,
          active_within_minutes: 60,
        },
        session: {
          provider: 'codex',
          path: '/home/pets/.codex/sessions/2026/03/10/rollout-second.jsonl',
          filename: 'rollout-second.jsonl',
          session_id: 'second-session',
          cwd: '/home/pets/zoo/agents_sessions_dashboard',
          first_user_message: 'первое сообщение',
          last_user_message: 'последнее сообщение',
          started_at: '2026-03-12T08:00:00+00:00',
          started_at_local: '2026-03-12 11:00:00 MSK',
          ended_at: '2026-03-12T08:04:00+00:00',
          ended_at_local: '2026-03-12 11:04:00 MSK',
          duration_seconds: 240,
          duration_human: '4 мин',
          time_window: {
            source: 'session_artifact',
            started_at: '2026-03-12T08:00:00+00:00',
            started_at_local: '2026-03-12 11:00:00 MSK',
            ended_at: '2026-03-12T08:04:00+00:00',
            ended_at_local: '2026-03-12 11:04:00 MSK',
            duration_seconds: 240,
            duration_human: '4 мин',
            scope_summary: 'Commits, files, and timeline evidence are interpreted inside this session window.',
          },
          user_messages: [
            'первое сообщение',
            'собрать контекст',
            'починить detail page',
            'добавить message anchors',
            'проверить timeline',
            'последнее сообщение',
          ],
          message_anchors: {
            first: 'первое сообщение',
            middle: [
              'собрать контекст',
              'починить detail page',
              'добавить message anchors',
              'проверить timeline',
            ],
            last: 'последнее сообщение',
          },
          intent_evolution: ['первый шаг', 'второй шаг'],
          topic_threads: [
            'session detail',
            'message anchors',
            'timeline',
            'git commits',
          ],
          state_model: {
            labels: ['archived'],
            safety_mode: 'read-only',
            summary: 'Сессия доступна как историческое досье. Actions пока остаются безопасными placeholders.',
            rationale: [
              'Ask flow ещё не подключён к backend query layer.',
              'Resume flow не должен обещаться без harness-specific safety checks.',
            ],
            capabilities: {
              can_ask: false,
              can_resume: false,
              can_restore: false,
            },
            ask_session: {
              available: false,
              label: 'Пока не подключено',
              detail: 'Будущий ask-only flow останется недеструктивным.',
            },
            resume_session: {
              available: false,
              label: 'Пока не разрешено',
              detail: 'Resume появится только после явных safety checks.',
            },
          },
          route: {
            harness: 'codex',
            id: 'rollout-second.jsonl',
            href: '/sessions/codex/rollout-second.jsonl',
          },
          tool_calls: ['exec_command'],
          files_modified: [
            'frontend/components/SessionDetailClient.tsx',
            'frontend/components/GitCommitBlock.tsx',
          ],
          git_repository_root: '/home/pets/zoo/agents_sessions_dashboard',
          git_commits: [
            {
              hash: '1234567890abcdef1234567890abcdef12345678',
              short_hash: '1234567',
              title: 'Add session detail route',
              author_name: 'Pets',
              committed_at: '2026-03-12T08:02:00+00:00',
              committed_at_local: '2026-03-12 11:02:00 MSK',
            },
            {
              hash: 'abcdef1234567890abcdef1234567890abcdef12',
              short_hash: 'abcdef1',
              title: 'Add git commit block',
              author_name: 'Pets',
              committed_at: '2026-03-12T08:04:00+00:00',
              committed_at_local: '2026-03-12 11:04:00 MSK',
            },
          ],
          token_usage: {
            total_tokens: 2500,
            input_tokens: 1000,
            output_tokens: 1500,
          },
          timeline: [
            {
              timestamp: '2026-03-12T08:00:00+00:00',
              event_type: 'user_message',
              description: 'первое сообщение',
              icon: '💬',
            },
            {
              timestamp: '2026-03-12T08:01:00+00:00',
              event_type: 'tool_call',
              description: 'rg session detail',
              icon: '🛠',
            },
            {
              timestamp: '2026-03-12T08:02:00+00:00',
              event_type: 'file_edit',
              description: 'frontend/components/SessionDetailClient.tsx',
              icon: '📝',
            },
            {
              timestamp: '2026-03-12T08:03:00+00:00',
              event_type: 'tool_call',
              description: 'pnpm test',
              icon: '🛠',
            },
          ],
        },
      },
    });

    await page.goto('/', {
      waitUntil: 'domcontentloaded',
    });

    const latestLink = page.getByTestId('latest-session-open-link');
    await expect(latestLink).toHaveAttribute('href', '/sessions/codex/rollout-demo.jsonl');

    const firstSessionCard = page.getByTestId('session-card').first();
    await expect(firstSessionCard).toHaveAttribute('href', '/sessions/codex/rollout-second.jsonl');

    await firstSessionCard.click();
    await expect(page).toHaveURL(/\/sessions\/codex\/rollout-second\.jsonl$/);
    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('session-detail-card')).toBeVisible();
    await expect(page.getByTestId('time-window-block')).toBeVisible();
    await expect(page.getByTestId('time-window-start')).toContainText('2026-03-12 11:00:00 MSK');
    await expect(page.getByTestId('time-window-end')).toContainText('2026-03-12 11:04:00 MSK');
    await expect(page.getByTestId('time-window-duration')).toContainText('4 мин');
    await expect(page.getByTestId('evidence-priority')).toBeVisible();
    await expect(page.getByTestId('message-anchors')).toBeVisible();
    await expect(page.getByTestId('message-anchor-first')).toContainText('первое сообщение');
    await expect(page.getByTestId('message-anchor-middle-0')).toContainText('собрать контекст');
    await expect(page.getByTestId('message-anchor-middle-3')).toContainText('проверить timeline');
    await expect(page.getByTestId('message-anchor-middle-4')).toHaveCount(0);
    await expect(page.getByTestId('message-anchor-last')).toContainText('последнее сообщение');
    await expect(page.getByTestId('git-commits-block')).toBeVisible();
    await expect(page.getByTestId('git-commit-item-0')).toContainText('Add session detail route');
    await expect(page.getByTestId('git-commit-item-1')).toContainText('Add git commit block');
    await expect(page.getByTestId('session-timeline')).toBeVisible();
    await expect(page.getByTestId('session-timeline-item-0')).toContainText('первое сообщение');
    await expect(page.getByTestId('session-timeline-item-3')).toContainText('pnpm test');
    await expect(page.getByTestId('topic-threads')).toBeVisible();
    await expect(page.getByTestId('topic-thread-0')).toContainText('session detail');
    await expect(page.getByTestId('future-actions')).toBeVisible();
    await expect(page.getByTestId('evidence-matrix')).toBeVisible();
    await expect(page.getByTestId('matrix-direction-item-0')).toContainText('первый шаг');
    await expect(page.getByTestId('matrix-commit-link-0')).toContainText('Add session detail route');
    await expect(page.getByTestId('matrix-commit-file-0-0')).toContainText('SessionDetailClient.tsx');
    await expect(page.getByTestId('matrix-commit-file-1-0')).toContainText('GitCommitBlock.tsx');
    await expect(page.getByTestId('session-state-model')).toContainText('read-only');
    await expect(page.getByTestId('evidence-sparsity-notice')).toHaveCount(0);
    await expect(page.getByTestId('future-action-ask')).toContainText('Ask This Session');
    await expect(page.getByTestId('future-action-resume')).toContainText('Continue / Resume Session');
  });

  test('detail page runs the ask-only flow and renders evidence-backed answer', async ({ page }) => {
    await mockDashboardApis(page, {
      latest: {
        meta: {
          scanned_providers: 6,
          scanned_files: 1,
        },
        query: {
          timezone: 'Europe/Moscow',
        },
        latest: {
          provider: 'codex',
          path: '/home/pets/.codex/sessions/2026/03/12/rollout-ask.jsonl',
          relative_path: '2026/03/12/rollout-ask.jsonl',
          filename: 'rollout-ask.jsonl',
          session_id: 'session-ask',
          format: 'jsonl',
          modified_at: '2026-03-12T08:05:00+00:00',
          modified_at_local: '2026-03-12 11:05:00 MSK',
          modified_human: 'today at 11:05',
          age_seconds: 30,
          age_human: '30 sec ago',
          activity_state: 'active',
          record_count: 7,
          parse_errors: 0,
          user_message_count: 3,
          first_user_message: 'починить detail page и добавить ask-only flow',
          last_user_message: 'покажи evidence excerpts',
          intent_evolution: ['починить detail page', 'добавить ask-only flow'],
          route: {
            harness: 'codex',
            id: 'rollout-ask.jsonl',
            href: '/sessions/codex/rollout-ask.jsonl',
          },
        },
        errors: [],
      },
      sessions: {
        total: 1,
        limit: 100,
        offset: 0,
        sessions: [
          {
            session_id: 'session-ask',
            agent_type: 'codex',
            status: 'completed',
            source_file: '/home/pets/.codex/sessions/2026/03/12/rollout-ask.jsonl',
            route: {
              harness: 'codex',
              id: 'rollout-ask.jsonl',
              href: '/sessions/codex/rollout-ask.jsonl',
            },
          },
        ],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 1,
          by_agent: { codex: 1 },
          by_status: { completed: 1 },
          total_tokens: 420,
          last_updated: '2026-03-12T08:06:00Z',
        },
      },
      detail: {
        meta: {
          timezone: 'Europe/Moscow',
          live_within_minutes: 10,
          active_within_minutes: 60,
        },
        session: {
          provider: 'codex',
          path: '/home/pets/.codex/sessions/2026/03/12/rollout-ask.jsonl',
          filename: 'rollout-ask.jsonl',
          session_id: 'session-ask',
          cwd: '/home/pets/zoo/agents_sessions_dashboard',
          first_user_message: 'починить detail page и добавить ask-only flow',
          last_user_message: 'покажи evidence excerpts',
          user_messages: [
            'починить detail page и добавить ask-only flow',
            'связать вопрос с локальным query layer',
            'покажи evidence excerpts',
          ],
          started_at: '2026-03-12T08:00:00+00:00',
          started_at_local: '2026-03-12 11:00:00 MSK',
          ended_at: '2026-03-12T08:05:00+00:00',
          ended_at_local: '2026-03-12 11:05:00 MSK',
          duration_seconds: 300,
          duration_human: '5 мин',
          time_window: {
            source: 'session_artifact',
            started_at: '2026-03-12T08:00:00+00:00',
            started_at_local: '2026-03-12 11:00:00 MSK',
            ended_at: '2026-03-12T08:05:00+00:00',
            ended_at_local: '2026-03-12 11:05:00 MSK',
            duration_seconds: 300,
            duration_human: '5 мин',
            scope_summary: 'Коммиты, files modified и timeline ниже читаются только внутри этого окна сессии.',
          },
          message_anchors: {
            first: 'починить detail page и добавить ask-only flow',
            middle: ['связать вопрос с локальным query layer'],
            last: 'покажи evidence excerpts',
          },
          intent_evolution: ['починить detail page', 'добавить ask-only flow'],
          topic_threads: ['detail page', 'ask flow', 'evidence excerpts'],
          state_model: {
            labels: ['archived', 'queryable'],
            safety_mode: 'ask-only',
            summary: 'Сессия доступна как безопасный queryable artifact: ask flow уже работает поверх локального source.',
            rationale: [
              'Source artifact остаётся read-only.',
              'Ask flow использует отдельный local query layer.',
              'Resume остаётся выключенным до harness-specific safety checks.',
            ],
            capabilities: {
              can_ask: true,
              can_resume: false,
              can_restore: false,
            },
            ask_session: {
              available: true,
              label: 'Query layer доступен',
              detail: 'Можно задать вопрос к artifact и получить ответ с evidence excerpts.',
            },
            resume_session: {
              available: false,
              label: 'Пока не разрешено',
              detail: 'Resume остаётся safety-gated до явного harness flow.',
            },
          },
          evidence_sparsity: {
            is_sparse: false,
            summary: 'Есть user messages, timeline и repo signals для безопасного ask-only ответа.',
            present_layers: ['user messages', 'artifact timeline', 'files modified'],
            missing_layers: ['git commits'],
          },
          route: {
            harness: 'codex',
            id: 'rollout-ask.jsonl',
            href: '/sessions/codex/rollout-ask.jsonl',
          },
          tool_calls: ['exec_command'],
          files_modified: ['frontend/components/SessionDetailClient.tsx'],
          git_repository_root: '/home/pets/zoo/agents_sessions_dashboard',
          git_commits: [],
          token_usage: {
            total_tokens: 420,
            input_tokens: 220,
            output_tokens: 200,
          },
          timeline: [
            {
              timestamp: '2026-03-12T08:00:00+00:00',
              event_type: 'user_message',
              description: 'починить detail page и добавить ask-only flow',
              icon: '💬',
            },
            {
              timestamp: '2026-03-12T08:03:00+00:00',
              event_type: 'tool_call',
              description: 'rg session query',
              icon: '🛠',
            },
          ],
        },
      },
      ask: {
        meta: {
          tool: 'nx-session-query',
          tool_version: '1.0.0',
          generated_at: '2026-03-12T08:06:00Z',
          answer_source: 'local_artifact',
          reasoning_mode: 'lexical_evidence_match',
        },
        source: {
          harness_provider: 'codex',
          format: 'jsonl',
          record_count: 7,
          snippet_count: 5,
          user_message_count: 3,
        },
        question: {
          text: 'Какая была главная цель этой сессии?',
        },
        answer: {
          mode: 'ask-only',
          response: 'Главный фокус этой сессии: починить detail page и добавить ask-only flow с evidence excerpts.',
          confidence: 0.94,
          evidence: [
            {
              kind: 'user_message',
              label: 'User message',
              excerpt: 'починить detail page и добавить ask-only flow',
              score: 12,
            },
            {
              kind: 'user_message',
              label: 'User message',
              excerpt: 'покажи evidence excerpts',
              score: 8,
            },
          ],
          limitations: [
            'Ответ собран локально из artifact и lexical overlap, без внешних repo joins.',
          ],
        },
      },
    });

    await page.goto('/sessions/codex/rollout-ask.jsonl', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('future-actions')).toContainText('Ask flow уже работает в безопасном ask-only режиме');
    await expect(page.getByTestId('future-action-ask')).toContainText('ask-only live');
    await expect(page.getByTestId('session-ask-input')).toHaveValue('Какая была главная цель этой сессии?');

    const askRequestPromise = page.waitForRequest((request) => (
      request.method() === 'POST'
      && request.url().includes('/api/session-artifacts/codex/rollout-ask.jsonl/ask')
    ));

    await page.getByTestId('session-ask-submit').click();

    const askRequest = await askRequestPromise;
    expect(askRequest.postDataJSON()).toEqual({
      question: 'Какая была главная цель этой сессии?',
    });

    await expect(page.getByTestId('session-ask-result')).toBeVisible();
    await expect(page.getByTestId('session-ask-response-text')).toContainText('Главный фокус этой сессии');
    await expect(page.getByTestId('session-ask-evidence-0')).toContainText('починить detail page и добавить ask-only flow');
    await expect(page.getByTestId('session-ask-limit-0')).toContainText('lexical overlap');
    await expect(page.getByTestId('future-action-resume')).toContainText('Пока не разрешено');
  });

  test('detail page shows sparse evidence cue and archived state for idle artifacts', async ({ page }) => {
    await mockDashboardApis(page, {
      latest: {
        meta: {
          scanned_providers: 6,
          scanned_files: 1,
        },
        query: {
          timezone: 'Europe/Moscow',
        },
        latest: {
          provider: 'gemini',
          path: '/home/pets/.gemini/tmp/agents-sessions-dashboard/logs.json',
          relative_path: 'agents-sessions-dashboard/logs.json',
          filename: 'logs.json',
          session_id: 'agents-sessions-dashboard',
          format: 'json',
          modified_at: '2026-03-12T06:41:36+00:00',
          modified_at_local: '2026-03-12 09:41:36 MSK',
          modified_human: 'today at 09:41',
          age_seconds: 3600,
          age_human: '1 hour ago',
          activity_state: 'idle',
          record_count: 3,
          parse_errors: 0,
          user_message_count: 3,
          first_user_message: 'start with git status via bash',
          last_user_message: 'run linters',
          intent_evolution: ['start with git status via bash'],
          route: {
            harness: 'gemini',
            id: 'agents-sessions-dashboard',
            href: '/sessions/gemini/agents-sessions-dashboard',
          },
        },
        errors: [],
      },
      sessions: {
        total: 0,
        limit: 100,
        offset: 0,
        sessions: [],
      },
      metrics: {
        success: true,
        data: {
          total_sessions: 1,
          by_agent: { gemini: 1 },
          by_status: { active: 1 },
          total_tokens: 90,
          last_updated: '2026-03-12T00:00:00Z',
        },
      },
      detail: {
        meta: {
          timezone: 'Europe/Moscow',
          live_within_minutes: 10,
          active_within_minutes: 60,
        },
        session: {
          provider: 'gemini',
          path: '/home/pets/.gemini/tmp/agents-sessions-dashboard/logs.json',
          filename: 'logs.json',
          session_id: 'agents-sessions-dashboard',
          cwd: '~/.gemini/tmp/agents-sessions-dashboard',
          first_user_message: 'start with git status via bash',
          last_user_message: 'run linters',
          user_messages: [
            'start with git status via bash',
            'read all changes carefully',
            'run linters',
          ],
          started_at: '2026-03-10T13:48:17+00:00',
          started_at_local: '2026-03-10 16:48:17 MSK',
          ended_at: '2026-03-12T06:41:36+00:00',
          ended_at_local: '2026-03-12 09:41:36 MSK',
          duration_seconds: 147799,
          duration_human: '41 ч 3 мин',
          time_window: {
            source: 'session_artifact',
            started_at: '2026-03-10T13:48:17+00:00',
            started_at_local: '2026-03-10 16:48:17 MSK',
            ended_at: '2026-03-12T06:41:36+00:00',
            ended_at_local: '2026-03-12 09:41:36 MSK',
            duration_seconds: 147799,
            duration_human: '41 ч 3 мин',
            scope_summary: 'Коммиты, files modified и timeline ниже читаются только внутри этого окна сессии.',
          },
          message_anchors: {
            first: 'start with git status via bash',
            middle: ['read all changes carefully'],
            last: 'run linters',
          },
          intent_evolution: ['start with git status via bash'],
          topic_threads: ['git status', 'linters'],
          state_model: {
            labels: ['archived'],
            safety_mode: 'read-only',
            summary: 'Artifact ещё помечен как active, но recent activity уже idle, поэтому detail page честно остаётся read-only до явного restore flow.',
            rationale: [
              'Observed status: active.',
              'Observed activity state: idle.',
              'The source still says active, but the recent activity window is already cold.',
              'Resume stays disabled until a harness-specific restore flow exists.',
              'Ask mode is enabled only when an explicit query layer is wired.',
            ],
            capabilities: {
              can_ask: false,
              can_resume: false,
              can_restore: false,
            },
          },
          evidence_sparsity: {
            is_sparse: true,
            summary: 'Evidence stack пока тонкий: user messages, artifact timeline доступны, но files modified, git commits отсутствуют в этом окне.',
            present_layers: ['user messages', 'artifact timeline'],
            missing_layers: ['files modified', 'git commits'],
          },
          route: {
            harness: 'gemini',
            id: 'agents-sessions-dashboard',
            href: '/sessions/gemini/agents-sessions-dashboard',
          },
          tool_calls: [],
          files_modified: [],
          git_repository_root: null,
          git_commits: [],
          token_usage: {
            total_tokens: 90,
            input_tokens: 50,
            output_tokens: 40,
          },
          timeline: [
            {
              timestamp: '2026-03-10T13:48:17+00:00',
              event_type: 'user_message',
              description: 'start with git status via bash',
              icon: '💬',
            },
          ],
        },
      },
    });

    await page.goto('/sessions/gemini/agents-sessions-dashboard', {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('evidence-sparsity-notice')).toBeVisible();
    await expect(page.getByTestId('evidence-sparsity-notice')).toContainText('Evidence stack пока тонкий');
    await expect(page.getByTestId('evidence-present-layer-0')).toContainText('user messages');
    await expect(page.getByTestId('evidence-missing-layer-1')).toContainText('git commits');
    await expect(page.getByTestId('session-state-model')).toContainText('archived');
    await expect(page.getByTestId('session-state-model')).not.toContainText('live');
  });

  test('real session card click opens the published detail route', async ({ page }) => {
    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);

    const firstSessionCard = page.getByTestId('session-card').first();
    test.skip(await firstSessionCard.count() === 0, 'No visible session cards available for detail-route coverage');

    const href = await firstSessionCard.getAttribute('href');
    expect(href).toBeTruthy();

    await firstSessionCard.click();
    await expect(page).toHaveURL(new RegExp(`${href!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('session-detail-card')).toBeVisible();
    await expect(page.getByTestId('time-window-block')).toBeVisible();
    await expect(page.getByTestId('message-anchors')).toBeVisible();
    await expect(page.getByTestId('git-commits-block')).toBeVisible();
    await expect(page.getByTestId('session-timeline')).toBeVisible();
    await expect(page.getByTestId('future-actions')).toBeVisible();
  });

  test('shows metrics that match the backend payload', async ({ page, request }) => {
    await maybeAuthenticateApiRequest(request);
    const apiMetrics = await getJson<MetricsPayload>(request, METRICS_API_PATH);

    await gotoDashboard(page);
    await maybeAuthenticateThroughUi(page);
    await expectLoadedDashboard(page);

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

  test('session artifact endpoint serves a real session from the published API', async ({ request }) => {
    await maybeAuthenticateApiRequest(request);
    const sessions = await getJson<SessionsPayload>(request, buildSessionsUrl({ limit: 1 }));
    const [firstSession] = sessions.sessions;

    test.skip(!firstSession?.route, 'No sessions with route metadata available for artifact detail coverage');

    const sessionDetail = await getJson<SessionArtifactPayload>(
      request,
      `/api/session-artifacts/${firstSession!.route!.harness}/${encodeURIComponent(firstSession!.route!.id)}`,
    );

    expect(sessionDetail.session.session_id).toBe(firstSession!.session_id);
    expect(sessionDetail.session.provider).toBe(firstSession!.agent_type);
    expect(sessionDetail.session.route.id).toBe(firstSession!.route!.id);
  });
});
