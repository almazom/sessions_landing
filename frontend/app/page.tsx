'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, LatestSessionResponse, Metrics, Session } from '@/lib/api';
import { logClientEvent } from '@/lib/debug';
import { runtimeConfig } from '@/lib/runtime-config';
import { getSessionRouteKey, matchesRoute } from '@/lib/session-route';
import AuthPanel from '@/components/AuthPanel';
import LatestSessionCard from '@/components/LatestSessionCard';
import SessionCard from '@/components/SessionCard';
import MetricsPanel from '@/components/MetricsPanel';

type AuthState = {
  authenticated: boolean;
  password_required: boolean;
  auth_required: boolean;
  password_enabled: boolean;
  telegram_enabled: boolean;
  telegram_configured: boolean;
  telegram_mode?: string | null;
  telegram_client_id?: string | null;
  telegram_bot_username?: string | null;
  telegram_widget_auth_url?: string | null;
  telegram_request_phone?: boolean;
  auth_method: string;
};

type TelegramAuthResult = {
  id_token?: string;
  error?: string;
};

type TelegramLoginApi = {
  auth: (
    options: {
      client_id: number;
      request_access?: Array<'phone' | 'write'>;
    },
    callback: (result: TelegramAuthResult) => void,
  ) => void;
};

declare global {
  interface Window {
    Telegram?: {
      Login?: TelegramLoginApi;
    };
  }
}

function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return [
      error.detail || fallback,
      error.requestId ? `Request ID: ${error.requestId}` : null,
    ].filter(Boolean).join(' ');
  }

  return error instanceof Error ? error.message : fallback;
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [latestSession, setLatestSession] = useState<LatestSessionResponse | null>(null);
  const [latestLoading, setLatestLoading] = useState(true);
  const [latestError, setLatestError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramConfigured, setTelegramConfigured] = useState(false);
  const [telegramMode, setTelegramMode] = useState<string | null>(null);
  const [telegramClientId, setTelegramClientId] = useState<string | null>(null);
  const [telegramBotUsername, setTelegramBotUsername] = useState<string | null>(null);
  const [telegramWidgetAuthUrl, setTelegramWidgetAuthUrl] = useState<string | null>(null);
  const [telegramRequestPhone, setTelegramRequestPhone] = useState(false);
  const [password, setPassword] = useState('');
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authRevision, setAuthRevision] = useState(0);
  const [dateFilter, setDateFilter] = useState<'today' | 'all'>('today');
  const [filter, setFilter] = useState<'all' | 'active' | 'completed' | 'error'>('all');
  const [agentFilter, setAgentFilter] = useState<string>('all');
  const telegramWidgetRef = useRef<HTMLDivElement | null>(null);
  const dashboardLoadRef = useRef(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authErrorParam = params.get('auth_error');
    if (!authErrorParam) {
      return;
    }

    const messageByCode: Record<string, string> = {
      telegram_access_denied: 'Telegram login was cancelled.',
      telegram_login_failed: 'Telegram login failed.',
      telegram_state_mismatch: 'Telegram login expired. Try again.',
    };

    setAuthError(messageByCode[authErrorParam] || 'Telegram login failed.');
    logClientEvent('warn', 'auth.telegram.redirect_error', { authError: authErrorParam });
    window.history.replaceState({}, document.title, window.location.pathname);
  }, []);

  const loadDashboard = useCallback(async () => {
    const loadId = dashboardLoadRef.current + 1;
    dashboardLoadRef.current = loadId;
    setLoadError(null);
    setLatestError(null);
    setLatestLoading(true);

    logClientEvent('info', 'dashboard.load.started', {
      loadId,
      dateFilter,
      statusFilter: filter,
      agentFilter,
    });

    try {
      const authStatus: AuthState = await api.getAuthStatus();
      if (loadId !== dashboardLoadRef.current) {
        return;
      }

      setAuthChecked(true);
      setAuthRequired(authStatus.auth_required);
      setPasswordRequired(authStatus.password_enabled);
      setTelegramEnabled(authStatus.telegram_enabled);
      setTelegramConfigured(authStatus.telegram_configured);
      setTelegramMode(authStatus.telegram_mode ?? null);
      setTelegramClientId(authStatus.telegram_client_id ?? null);
      setTelegramBotUsername(authStatus.telegram_bot_username ?? null);
      setTelegramWidgetAuthUrl(authStatus.telegram_widget_auth_url ?? null);
      setTelegramRequestPhone(Boolean(authStatus.telegram_request_phone));
      setAuthenticated(authStatus.authenticated || !authStatus.auth_required);

      if (authStatus.auth_required && !authStatus.authenticated) {
        setSessions([]);
        setMetrics(null);
        setLatestSession(null);
        setLatestLoading(false);
        logClientEvent('info', 'dashboard.load.auth_required', {
          loadId,
          authMethod: authStatus.auth_method,
        });
        return;
      }

      const [latestRes, sessionsRes, metricsRes] = await Promise.allSettled([
        api.getLatestSession(),
        api.getSessions({
          status: filter === 'all' ? undefined : filter,
          agent: agentFilter === 'all' ? undefined : agentFilter,
          changedDate: dateFilter === 'today' ? getTodayDateString() : undefined,
          limit: runtimeConfig.dashboardSessionsLimit,
        }),
        api.getMetrics(),
      ]);
      if (loadId !== dashboardLoadRef.current) {
        return;
      }

      const unauthorizedError = [latestRes, sessionsRes, metricsRes].find(
        (result) => result.status === 'rejected' && result.reason instanceof ApiError && result.reason.status === 401,
      );
      if (unauthorizedError && unauthorizedError.status === 'rejected') {
        setAuthenticated(false);
        setAuthRequired(true);
        setSessions([]);
        setMetrics(null);
        setLatestSession(null);
        setLatestLoading(false);
        setAuthError('Сессия истекла. Войдите снова.');
        setLoadError(null);
        logClientEvent('warn', 'dashboard.load.unauthorized', {
          loadId,
          requestId: unauthorizedError.reason instanceof ApiError ? unauthorizedError.reason.requestId : null,
          path: unauthorizedError.reason instanceof ApiError ? unauthorizedError.reason.path : null,
        });
        return;
      }

      if (latestRes.status === 'fulfilled') {
        setLatestSession(latestRes.value);
      } else {
        setLatestSession(null);
        setLatestError(getApiErrorMessage(latestRes.reason, 'Не удалось загрузить latest session.'));
        logClientEvent('warn', 'dashboard.latest.failed', {
          loadId,
          error: latestRes.reason instanceof Error ? latestRes.reason.message : String(latestRes.reason),
        });
      }

      if (sessionsRes.status === 'fulfilled') {
        const latestRouteKey = latestRes.status === 'fulfilled'
          ? getSessionRouteKey(latestRes.value.latest)
          : '';
        const nextSessions = latestRouteKey
          ? sessionsRes.value.sessions.filter((session) => !matchesRoute(session, latestRouteKey))
          : sessionsRes.value.sessions;
        setSessions(nextSessions);
      } else {
        setSessions([]);
      }

      if (metricsRes.status === 'fulfilled') {
        setMetrics(metricsRes.value.data);
      } else {
        setMetrics(null);
      }

      const dashboardErrors = [
        sessionsRes.status === 'rejected'
          ? `Сессии: ${getApiErrorMessage(sessionsRes.reason, 'Не удалось загрузить список сессий.')}`
          : null,
        metricsRes.status === 'rejected'
          ? `Метрики: ${getApiErrorMessage(metricsRes.reason, 'Не удалось загрузить метрики.')}`
          : null,
      ].filter(Boolean);

      setLoadError(dashboardErrors.length > 0 ? dashboardErrors.join(' ') : null);
      setLatestLoading(false);
      logClientEvent('info', 'dashboard.load.completed', {
        loadId,
        sessions: sessionsRes.status === 'fulfilled' ? sessionsRes.value.sessions.length : 0,
        totalSessions: sessionsRes.status === 'fulfilled' ? sessionsRes.value.total : 0,
        latestLoaded: latestRes.status === 'fulfilled',
        metricsLoaded: metricsRes.status === 'fulfilled',
      });
    } catch (error) {
      if (loadId !== dashboardLoadRef.current) {
        return;
      }

      if (error instanceof ApiError && error.status === 401) {
        setAuthenticated(false);
        setAuthRequired(true);
        setSessions([]);
        setMetrics(null);
        setLatestSession(null);
        setLatestLoading(false);
        setAuthError('Сессия истекла. Войдите снова.');
        setLoadError(null);
        logClientEvent('warn', 'dashboard.load.unauthorized', {
          loadId,
          requestId: error.requestId,
          path: error.path,
        });
        return;
      }

      setLoadError(getApiErrorMessage(error, 'Не удалось загрузить данные dashboard.'));
      setLatestLoading(false);
      logClientEvent('error', 'dashboard.load.failed', {
        loadId,
        error: error instanceof Error ? error.message : String(error),
        requestId: error instanceof ApiError ? error.requestId : null,
        status: error instanceof ApiError ? error.status : null,
        path: error instanceof ApiError ? error.path : null,
      });
    } finally {
      if (loadId === dashboardLoadRef.current) {
        setLoading(false);
        setLatestLoading(false);
      }
    }
  }, [agentFilter, dateFilter, filter]);

  const completeTelegramLogin = async (idToken: string) => {
    try {
      await api.loginWithTelegram(idToken);
      setPassword('');
      setAuthError(null);
      setAuthRevision((value) => value + 1);
      logClientEvent('info', 'auth.telegram.client_login_succeeded');
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setAuthError('Этот Telegram аккаунт не разрешён.');
      } else {
        setAuthError('Не удалось войти через Telegram.');
      }
      logClientEvent('error', 'auth.telegram.client_login_failed', {
        requestId: error instanceof ApiError ? error.requestId : null,
        status: error instanceof ApiError ? error.status : null,
      });
    } finally {
      setAuthSubmitting(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    void loadDashboard();
  }, [authRevision, loadDashboard]);

  useEffect(() => {
    const container = telegramWidgetRef.current;
    if (!container) {
      return;
    }

    container.innerHTML = '';

    if (!authChecked || authenticated || telegramMode !== 'widget' || !telegramEnabled || !telegramBotUsername || !telegramWidgetAuthUrl) {
      return;
    }

    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', telegramBotUsername);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-radius', '999');
    script.setAttribute('data-userpic', 'false');
    script.setAttribute('data-auth-url', telegramWidgetAuthUrl);
    container.appendChild(script);
    logClientEvent('info', 'auth.telegram.widget_rendered', {
      botUsername: telegramBotUsername,
      authUrl: telegramWidgetAuthUrl,
    });

    return () => {
      container.innerHTML = '';
    };
  }, [authChecked, authenticated, telegramBotUsername, telegramEnabled, telegramMode, telegramWidgetAuthUrl]);

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthSubmitting(true);
    setAuthError(null);
    logClientEvent('info', 'auth.password.login_started');

    try {
      await api.login(password);
      setPassword('');
      setAuthRevision((value) => value + 1);
      logClientEvent('info', 'auth.password.login_succeeded');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setAuthError('Неверный пароль.');
      } else {
        setAuthError('Не удалось войти прямо сейчас.');
      }
      logClientEvent('error', 'auth.password.login_failed', {
        requestId: error instanceof ApiError ? error.requestId : null,
        status: error instanceof ApiError ? error.status : null,
      });
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleTelegramLogin = () => {
    setAuthSubmitting(true);
    setAuthError(null);
    logClientEvent('info', 'auth.telegram.login_started', { telegramEnabled, telegramMode });

    if (!telegramEnabled) {
      setAuthSubmitting(false);
      setAuthError('Telegram login is not configured on the server yet.');
      logClientEvent('warn', 'auth.telegram.login_unavailable');
      return;
    }

    const telegramLogin = window.Telegram?.Login;
    const numericClientId = Number(telegramClientId);

    if (!telegramLogin?.auth || !telegramClientId || Number.isNaN(numericClientId)) {
      logClientEvent('info', 'auth.telegram.login_redirecting_to_server');
      window.location.assign('/api/auth/telegram/start');
      return;
    }

    telegramLogin.auth(
      {
        client_id: numericClientId,
        request_access: telegramRequestPhone ? ['phone'] : [],
      },
      (result) => {
        if (result.error) {
          setAuthSubmitting(false);
          setAuthError(
            result.error === 'access_denied'
              ? 'Telegram login was cancelled.'
              : 'Telegram login failed.',
          );
          logClientEvent('warn', 'auth.telegram.widget_callback_failed', {
            error: result.error,
          });
          return;
        }

        if (!result.id_token) {
          setAuthSubmitting(false);
          setAuthError('Telegram did not return an ID token.');
          logClientEvent('warn', 'auth.telegram.widget_callback_failed', {
            error: 'missing_id_token',
          });
          return;
        }

        void completeTelegramLogin(result.id_token);
      },
    );
  };

  const handleLogout = async () => {
    try {
      await api.logout();
      logClientEvent('info', 'auth.logout.succeeded');
    } catch (error) {
      logClientEvent('error', 'auth.logout.failed', {
        requestId: error instanceof ApiError ? error.requestId : null,
        status: error instanceof ApiError ? error.status : null,
      });
    } finally {
      setAuthenticated(false);
      setSessions([]);
      setMetrics(null);
      setLatestSession(null);
      setLatestError(null);
      setLatestLoading(false);
      setPassword('');
      setAuthError(null);
      setAuthRevision((value) => value + 1);
    }
  };

  // Группировка сессий по статусу
  const activeSessions = sessions.filter(s => s.status === 'active');
  const completedSessions = sessions.filter(s => s.status === 'completed' || s.status === 'paused');
  const errorSessions = sessions.filter(s => s.status === 'error');

  return (
    <main className="min-h-screen p-6">
      {/* Header */}
      <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-nexus-800">
            🤖 Agent Nexus
          </h1>
          <p className="text-nexus-500 mt-1">
            Мониторинг AI агентов в реальном времени
          </p>
        </div>
        {authRequired && authenticated && (
          <button
            data-testid="logout-button"
            onClick={handleLogout}
            className="self-start rounded-lg border border-nexus-200 bg-white px-4 py-2 text-sm text-nexus-700 hover:bg-nexus-50"
          >
            Выйти
          </button>
        )}
      </header>

      {authChecked && !authenticated ? (
        <AuthPanel
          passwordRequired={passwordRequired}
          telegramEnabled={telegramEnabled}
          telegramConfigured={telegramConfigured}
          telegramMode={telegramMode}
          authSubmitting={authSubmitting}
          authError={authError}
          password={password}
          telegramWidgetRef={telegramWidgetRef}
          onPasswordChange={setPassword}
          onPasswordSubmit={handleLogin}
          onTelegramLogin={handleTelegramLogin}
        />
      ) : (
        <>
          <section className="mb-6">
            {latestLoading ? (
              <div
                data-testid="latest-session-loading"
                className="animate-pulse rounded-[28px] border border-nexus-200 bg-white p-6 shadow-sm"
              >
                <div className="h-5 w-40 rounded bg-nexus-200" />
                <div className="mt-3 h-9 w-72 rounded bg-nexus-100" />
                <div className="mt-6 grid gap-3 lg:grid-cols-2">
                  <div className="h-24 rounded-2xl bg-nexus-100" />
                  <div className="h-24 rounded-2xl bg-nexus-100" />
                  <div className="h-24 rounded-2xl bg-nexus-100" />
                  <div className="h-24 rounded-2xl bg-nexus-100" />
                </div>
              </div>
            ) : latestError ? (
              <div
                data-testid="latest-session-error"
                className="rounded-[28px] border border-red-200 bg-red-50 px-6 py-5 text-sm text-red-700"
              >
                ⚠️ Latest session недоступна. {latestError}
              </div>
            ) : latestSession?.latest ? (
              <LatestSessionCard
                session={latestSession.latest}
                scannedProviders={latestSession.meta.scanned_providers}
                scannedFiles={latestSession.meta.scanned_files}
                timezone={latestSession.query.timezone}
                errors={latestSession.errors.map((entry) => entry.detail)}
              />
            ) : (
              <div
                data-testid="latest-session-empty"
                className="rounded-[28px] border border-nexus-200 bg-white px-6 py-5 text-sm text-nexus-500 shadow-sm"
              >
                📭 Latest session не найдена.
              </div>
            )}
          </section>

          {/* Metrics */}
          {metrics && <MetricsPanel metrics={metrics} />}

          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <select
              data-testid="date-filter"
              value={dateFilter}
              onChange={(event) => setDateFilter(event.target.value as 'today' | 'all')}
              className="px-4 py-2 rounded-lg border border-nexus-200 bg-white"
            >
              <option value="today">Сегодня</option>
              <option value="all">Все даты</option>
            </select>

            <select
              data-testid="status-filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value as any)}
              className="px-4 py-2 rounded-lg border border-nexus-200 bg-white"
            >
              <option value="all">Все статусы</option>
              <option value="active">🟢 Активные</option>
              <option value="completed">✅ Завершённые</option>
              <option value="error">❌ Ошибки</option>
            </select>

            <select
              data-testid="agent-filter"
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="px-4 py-2 rounded-lg border border-nexus-200 bg-white"
            >
              <option value="all">Все агенты</option>
              <option value="codex">Codex</option>
              <option value="kimi">Kimi</option>
              <option value="gemini">Gemini</option>
              <option value="qwen">Qwen</option>
              <option value="claude">Claude</option>
              <option value="pi">Pi</option>
            </select>

            <button
              data-testid="refresh-button"
              onClick={() => setAuthRevision((value) => value + 1)}
              className="px-4 py-2 rounded-lg bg-nexus-100 hover:bg-nexus-200"
            >
              🔄 Обновить
            </button>
          </div>

          {/* Sessions Grid */}
          {loadError && (
            <div
              data-testid="dashboard-load-error"
              className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {loadError}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12 text-nexus-400">
              ⏳ Загрузка...
            </div>
          ) : (
            <>
              {/* Active Sessions */}
              {activeSessions.length > 0 && (
                <section data-testid="active-section" className="mb-8">
                  <h2 data-testid="active-section-header" className="text-lg font-semibold text-nexus-700 mb-4">
                    🔴 Активные ({activeSessions.length})
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {activeSessions.map((session) => (
                      <SessionCard key={session.session_id} session={session} />
                    ))}
                  </div>
                </section>
              )}

              {/* Error Sessions */}
              {errorSessions.length > 0 && (
                <section data-testid="error-section" className="mb-8">
                  <h2 data-testid="error-section-header" className="text-lg font-semibold text-red-600 mb-4">
                    ❌ Ошибки ({errorSessions.length})
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {errorSessions.map((session) => (
                      <SessionCard key={session.session_id} session={session} />
                    ))}
                  </div>
                </section>
              )}

              {/* Completed Sessions */}
              {completedSessions.length > 0 && filter !== 'active' && (
                <section data-testid="completed-section">
                  <h2 data-testid="completed-section-header" className="text-lg font-semibold text-nexus-600 mb-4">
                    ✅ Завершённые ({completedSessions.length})
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {completedSessions.slice(0, runtimeConfig.completedSessionsPreviewLimit).map((session) => (
                      <SessionCard key={session.session_id} session={session} />
                    ))}
                  </div>
                </section>
              )}

              {/* Empty State */}
              {sessions.length === 0 && (
                <div data-testid="empty-state" className="text-center py-12 text-nexus-400">
                  📭 Нет сессий
                </div>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
