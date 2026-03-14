import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page } from '@playwright/test';

type AuthStatusPayload = {
  authenticated: boolean;
  auth_required?: boolean;
  password_required?: boolean;
};

type MockInteractivePayload = {
  version: number;
  route: {
    harness: string;
    route_id: string;
    session_href: string;
    interactive_href: string;
  };
  session: {
    session_id: string;
    agent_name: string;
    cwd: string;
    status: string;
    resume_supported: boolean;
  };
  interactive_session: {
    available: boolean;
    label: string;
    detail: string;
    href: string;
    transport: string;
  };
  runtime_identity: {
    thread_id: string;
    session_id: string;
    transport: string;
    source: string;
  } | null;
  artifact: {
    path: string;
    artifact_name: string;
    byte_size: number;
    sha256: string;
  };
  tail: {
    items: Array<Record<string, unknown>>;
    summary_hint: string | null;
    has_more_before: boolean;
  };
  replay: {
    items: Array<Record<string, unknown>>;
    history_complete: boolean;
  };
};

const HARNESS = 'codex';
const FIXTURE_ARTIFACT_ID = 'rollout-interactive-fixture.jsonl';
const DETAIL_ROUTE = `/sessions/${HARNESS}/${FIXTURE_ARTIFACT_ID}`;
const INTERACTIVE_ROUTE = `${DETAIL_ROUTE}/interactive`;
const PARITY_ARTIFACT_ID = process.env.NEXUS_INTERACTIVE_PARITY_ARTIFACT_ID?.trim() || '';
const PARITY_PROMPT = process.env.NEXUS_INTERACTIVE_PARITY_PROMPT?.trim()
  || 'Add 2 to the previous result. Reply with only the final integer.';
const PARITY_EXPECTED_REPLY = process.env.NEXUS_INTERACTIVE_PARITY_EXPECTED_REPLY?.trim() || '5';
const RESUME_ARTIFACT_ID = 'rollout-real-resume.jsonl';
const RESUME_DETAIL_ROUTE = `/sessions/${HARNESS}/${RESUME_ARTIFACT_ID}`;
const RESUME_INTERACTIVE_ROUTE = `${RESUME_DETAIL_ROUTE}/interactive`;
const RESUME_API_BASE_PATH = `/api/session-artifacts/${HARNESS}/${RESUME_ARTIFACT_ID}`;

function buildArtifactRoutes(artifactId: string): { detailRoute: string; interactiveRoute: string; apiBasePath: string } {
  const encodedArtifactId = encodeURIComponent(artifactId);
  return {
    detailRoute: `/sessions/${HARNESS}/${encodedArtifactId}`,
    interactiveRoute: `/sessions/${HARNESS}/${encodedArtifactId}/interactive`,
    apiBasePath: `/api/session-artifacts/${HARNESS}/${encodedArtifactId}`,
  };
}

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

async function maybeAuthenticate(page: Page): Promise<void> {
  const authResponse = await page.context().request.get('/api/auth/status');
  expect(authResponse.ok()).toBeTruthy();
  const authStatus = await authResponse.json() as AuthStatusPayload;

  if (!authStatus.auth_required || authStatus.authenticated) {
    return;
  }

  const password = getLoginPassword();
  if (!password) {
    throw new Error('NEXUS_E2E_PASSWORD or NEXUS_PASSWORD is required when password auth is enabled');
  }

  const loginResponse = await page.context().request.post('/api/auth/login', {
    data: {
      password,
    },
  });
  expect(loginResponse.ok()).toBeTruthy();
}

async function gotoInteractiveRoute(page: Page): Promise<void> {
  await maybeAuthenticate(page);
  const response = await page.goto(INTERACTIVE_ROUTE, {
    waitUntil: 'domcontentloaded',
  });

  expect(response?.ok()).toBeTruthy();
  await expect(page.getByRole('heading', { name: 'Interactive session shell' })).toBeVisible();
}

async function fetchInteractiveBoot(page: Page, artifactId: string): Promise<MockInteractivePayload> {
  await maybeAuthenticate(page);
  const { apiBasePath } = buildArtifactRoutes(artifactId);
  const response = await page.context().request.get(`${apiBasePath}/interactive`);
  expect(response.ok()).toBeTruthy();
  return await response.json() as MockInteractivePayload;
}

function buildResumeDetailPayload(): Record<string, unknown> {
  return {
    meta: {
      timezone: 'Europe/Moscow',
      live_within_minutes: 15,
      active_within_minutes: 180,
    },
    session: {
      provider: HARNESS,
      path: `/tmp/${RESUME_ARTIFACT_ID}`,
      filename: RESUME_ARTIFACT_ID,
      session_id: '019ce72f-7e29-7150-8777-1462772b40fc',
      cwd: '/home/pets/zoo/agents_sessions_dashboard',
      first_user_message: 'Resume this old Codex session from the browser.',
      last_user_message: 'Verify the browser interactive continuation.',
      user_messages: [
        'Resume this old Codex session from the browser.',
        'Verify the browser interactive continuation.',
      ],
      agent_name: 'Codex',
      agent_type: HARNESS,
      status: 'idle',
      modified_at: '2026-03-14T09:00:00+03:00',
      modified_at_local: '2026-03-14 09:00:00 MSK',
      modified_human: 'today at 09:00',
      age_seconds: 120,
      age_human: '2 min ago',
      activity_state: 'idle',
      record_count: 12,
      parse_errors: 0,
      user_message_count: 2,
      format: 'jsonl',
      relative_path: `2026/03/14/${RESUME_ARTIFACT_ID}`,
      source_file: `/tmp/${RESUME_ARTIFACT_ID}`,
      route: {
        harness: HARNESS,
        id: RESUME_ARTIFACT_ID,
        href: RESUME_DETAIL_ROUTE,
      },
      message_anchors: {
        first: 'Resume this old Codex session from the browser.',
        middle: ['Inspect the blocked interactive route.', 'Run explicit resume.'],
        last: 'Verify the browser interactive continuation.',
      },
      intent_evolution: [
        'Open the old session.',
        'Run explicit resume.',
        'Verify the browser continuation.',
      ],
      topic_threads: ['interactive continuation', 'browser resume'],
      tool_calls: ['playwright'],
      files_modified: ['frontend/components/InteractiveSessionShell.tsx'],
      git_commits: [
        {
          hash: '1111111111111111111111111111111111111111',
          short_hash: '1111111',
          title: 'Add interactive route resume CTA',
          author_name: 'Codex',
          committed_at: '2026-03-14T08:59:00+03:00',
          committed_at_local: '2026-03-14 08:59:00 MSK',
        },
      ],
      token_usage: {
        total_tokens: 1200,
        input_tokens: 700,
        output_tokens: 500,
      },
      timeline: [
        {
          timestamp: '2026-03-14T08:55:00+03:00',
          event_type: 'user_message',
          description: 'Resume this old Codex session from the browser.',
        },
        {
          timestamp: '2026-03-14T08:58:00+03:00',
          event_type: 'task_complete',
          description: 'Prepared the browser resume flow.',
        },
      ],
      state_model: {
        labels: ['restorable'],
        safety_mode: 'resume-allowed',
        summary: 'Resume is explicitly allowed for this artifact.',
        rationale: [
          'Resume stays explicit and user-triggered.',
          'Interactive route can inspect the blocked/live state honestly.',
        ],
        capabilities: {
          can_ask: false,
          can_resume: true,
          can_restore: true,
        },
        ask_session: {
          available: false,
          label: 'Ask-only stays disabled',
          detail: 'This mock focuses on resume.',
        },
        resume_session: {
          available: true,
          label: 'Resume supported',
          detail: 'This artifact can explicitly start a resume flow.',
        },
        interactive_session: {
          available: false,
          label: 'Interactive mode blocked',
          detail: 'Open the route or trigger resume to continue.',
          href: RESUME_INTERACTIVE_ROUTE,
          transport: 'codex-app-server',
        },
      },
    },
  };
}

function buildInteractiveBootPayload(available: boolean): MockInteractivePayload {
  return {
    version: 1,
    route: {
      harness: HARNESS,
      route_id: RESUME_ARTIFACT_ID,
      session_href: RESUME_DETAIL_ROUTE,
      interactive_href: RESUME_INTERACTIVE_ROUTE,
    },
    session: {
      session_id: '019ce72f-7e29-7150-8777-1462772b40fc',
      agent_name: 'Codex',
      cwd: '/home/pets/zoo/agents_sessions_dashboard',
      status: available ? 'active' : 'idle',
      resume_supported: true,
    },
    interactive_session: available
      ? {
          available: true,
          label: 'Interactive mode available',
          detail: 'Open the dedicated route to continue this Codex session through the backend interactive flow.',
          href: RESUME_INTERACTIVE_ROUTE,
          transport: 'codex-app-server',
        }
      : {
          available: false,
          label: 'Interactive mode blocked',
          detail: 'Interactive continuation is disabled because no runtime identity mapping was found.',
          href: RESUME_INTERACTIVE_ROUTE,
          transport: 'codex-app-server',
        },
    runtime_identity: available
      ? {
          thread_id: 'thread-resume-001',
          session_id: '019ce72f-7e29-7150-8777-1462772b40fc',
          transport: 'codex-app-server',
          source: 'fixture',
        }
      : null,
    artifact: {
      path: `/tmp/${RESUME_ARTIFACT_ID}`,
      artifact_name: RESUME_ARTIFACT_ID,
      byte_size: 2048,
      sha256: 'a'.repeat(64),
    },
    tail: {
      items: [
        {
          id: 'tail-1',
          summary: 'Old Codex session is ready for explicit resume.',
          detail: 'The browser route should stay honest until the runtime attaches.',
        },
      ],
      summary_hint: 'blocked until resume',
      has_more_before: false,
    },
    replay: {
      items: [
        {
          event_id: 'replay-1',
          event_type: 'history_complete',
          payload: {
            status: 'complete',
          },
        },
      ],
      history_complete: true,
    },
  };
}

async function mockExplicitResumeFlow(page: Page): Promise<void> {
  let resumeStarted = false;

  await page.route('**/api/auth/status', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        auth_required: false,
        password_required: false,
      }),
    });
  });

  await page.route(`**${RESUME_API_BASE_PATH}**`, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;

    if (request.method() === 'POST' && pathname.endsWith('/resume')) {
      resumeStarted = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'started',
          session_id: '019ce72f-7e29-7150-8777-1462772b40fc',
          cwd: '/home/pets/zoo/agents_sessions_dashboard',
          pid: 43210,
          log_path: '/tmp/agent-nexus-resume-rollout-real-resume_jsonl.log',
          interactive_href: RESUME_INTERACTIVE_ROUTE,
          started_at: '2026-03-14T09:01:00+03:00',
        }),
      });
      return;
    }

    if (request.method() === 'GET' && pathname.endsWith('/interactive')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(buildInteractiveBootPayload(resumeStarted)),
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(buildResumeDetailPayload()),
    });
  });
}

test.describe('interactive session browser flow', () => {
  test('tail snapshot shows last messages', async ({ page }) => {
    await gotoInteractiveRoute(page);

    await expect(page).toHaveURL(new RegExp(`${INTERACTIVE_ROUTE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
    await expect(page.getByTestId('interactive-live-attach')).toContainText('Live attach ready');
    await expect(page.getByTestId('interactive-timeline-entry-0')).toContainText(
      'Build deterministic fixture for interactive mode',
    );
    await expect(page.getByText('Replay is complete and the route may attach live')).toBeVisible();
  });

  test('detail CTA opens interactive route', async ({ page }) => {
    await maybeAuthenticate(page);
    const response = await page.goto(DETAIL_ROUTE, {
      waitUntil: 'domcontentloaded',
    });

    expect(response?.ok()).toBeTruthy();
    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('session-detail-interactive-cta')).toBeVisible();

    await page.getByTestId('session-detail-interactive-cta').click();

    await expect(page).toHaveURL(new RegExp(`${INTERACTIVE_ROUTE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
    await expect(page.getByRole('heading', { name: 'Interactive session shell' })).toBeVisible();
  });

  test('interactive prompt roundtrip mutates the real artifact', async ({ page }) => {
    test.skip(!PARITY_ARTIFACT_ID, 'Real interactive parity artifact is required for this test');

    const parityRoutes = buildArtifactRoutes(PARITY_ARTIFACT_ID);
    const beforeBoot = await fetchInteractiveBoot(page, PARITY_ARTIFACT_ID);
    const response = await page.goto(parityRoutes.interactiveRoute, {
      waitUntil: 'domcontentloaded',
    });

    expect(response?.ok()).toBeTruthy();
    await expect(page.getByRole('heading', { name: 'Interactive session shell' })).toBeVisible();
    await expect(page.getByTestId('interactive-composer-input')).toBeEnabled();
    await expect(page.getByTestId('interactive-stream-status')).toContainText('Stream connected');

    const submitResponsePromise = page.waitForResponse((routeResponse) => (
      routeResponse.request().method() === 'POST'
      && routeResponse.url().includes(`${parityRoutes.apiBasePath}/interactive/prompt`)
    ));
    const turnStartedEntry = page.locator('[data-testid^="interactive-timeline-entry-"]').filter({
      hasText: 'Turn started',
    }).first();
    await page.getByTestId('interactive-composer-input').fill(PARITY_PROMPT);
    await page.getByTestId('interactive-composer-submit').click();

    await expect(turnStartedEntry).toBeVisible();

    const submitResponse = await submitResponsePromise;
    expect(submitResponse.ok()).toBeTruthy();
    const submitPayload = await submitResponse.json() as {
      artifact_updated: boolean;
      assistant_message: string;
      artifact_after: MockInteractivePayload['artifact'];
      boot_payload: MockInteractivePayload;
    };

    expect(submitPayload.artifact_updated).toBeTruthy();
    expect(submitPayload.artifact_after.sha256).not.toBe(beforeBoot.artifact.sha256);
    expect(submitPayload.artifact_after.byte_size).toBeGreaterThan(beforeBoot.artifact.byte_size);
    expect(submitPayload.assistant_message).toContain(PARITY_EXPECTED_REPLY);
    await expect(page.getByTestId('interactive-submit-feedback')).toContainText(PARITY_EXPECTED_REPLY);
    await expect(page.getByText('Browser continuation acknowledged the prompt')).toHaveCount(0);

    const promptTimelineEntry = page.locator('[data-testid^="interactive-timeline-entry-"]').filter({
      hasText: PARITY_PROMPT,
    }).first();
    await expect(promptTimelineEntry).toBeVisible();

    await page.reload({
      waitUntil: 'domcontentloaded',
    });

    await expect(page.getByRole('heading', { name: 'Interactive session shell' })).toBeVisible();
    await expect(promptTimelineEntry).toBeVisible();
    const afterBoot = await fetchInteractiveBoot(page, PARITY_ARTIFACT_ID);
    expect(afterBoot.artifact.sha256).not.toBe(beforeBoot.artifact.sha256);
  });

  test('detail page can explicitly resume a blocked interactive session', async ({ page }) => {
    await mockExplicitResumeFlow(page);

    const resumeRequestPromise = page.waitForRequest((request) => (
      request.method() === 'POST'
      && request.url().includes(`${RESUME_API_BASE_PATH}/resume`)
    ));

    const response = await page.goto(RESUME_DETAIL_ROUTE, {
      waitUntil: 'domcontentloaded',
    });

    expect(response?.ok()).toBeTruthy();
    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('session-detail-resume-cta')).toBeVisible();
    await expect(page.getByTestId('future-action-resume')).toContainText('Resume supported');

    await page.getByTestId('session-detail-resume-cta').click();

    await resumeRequestPromise;
    await expect(page).toHaveURL(new RegExp(`${RESUME_INTERACTIVE_ROUTE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
    await expect(page.getByTestId('interactive-route-status')).toContainText('Interactive mode available');
    await expect(page.getByTestId('interactive-live-attach')).toContainText('Live attach ready');
    await expect(page.getByTestId('interactive-composer-input')).toBeEnabled();
  });

  test('blocked interactive route keeps the composer available for backend continuation', async ({ page }) => {
    await mockExplicitResumeFlow(page);

    const response = await page.goto(RESUME_INTERACTIVE_ROUTE, {
      waitUntil: 'domcontentloaded',
    });

    expect(response?.ok()).toBeTruthy();
    await expect(page.getByRole('heading', { name: 'Interactive session shell' })).toBeVisible();
    await expect(page.getByTestId('interactive-route-status')).toContainText('Interactive mode blocked');
    await expect(page.getByTestId('interactive-composer-input')).toBeEnabled();
    await expect(page.getByTestId('interactive-resume-cta')).toHaveCount(0);
  });
});
