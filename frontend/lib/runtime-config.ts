function getNumberEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsedValue = Number(rawValue);
  if (Number.isNaN(parsedValue)) {
    return fallback;
  }

  return parsedValue;
}

export const runtimeConfig = {
  apiBase: (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, ''),
  apiRequestTimeoutMs: getNumberEnv('NEXT_PUBLIC_API_TIMEOUT_MS', 15000),
  backendPort: getNumberEnv('NEXT_PUBLIC_BACKEND_PORT', 18890),
  dashboardSessionsLimit: getNumberEnv('NEXT_PUBLIC_DASHBOARD_SESSIONS_LIMIT', 100),
  completedSessionsPreviewLimit: getNumberEnv('NEXT_PUBLIC_COMPLETED_SESSIONS_PREVIEW_LIMIT', 20),
  websocketReconnectMs: getNumberEnv('NEXT_PUBLIC_WS_RECONNECT_MS', 5000),
  websocketPingIntervalMs: getNumberEnv('NEXT_PUBLIC_WS_PING_INTERVAL_MS', 30000),
};
