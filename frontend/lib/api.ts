/** API client for Agent Nexus backend */

import { createRequestId, logClientEvent } from '@/lib/debug';
import { runtimeConfig } from '@/lib/runtime-config';

const API_BASE = runtimeConfig.apiBase;

export class ApiError extends Error {
  status: number;

  detail: string | null;

  requestId: string | null;

  path: string;

  constructor(status: number, detail: string | null = null, requestId: string | null = null, path = '') {
    super(detail ? `API Error ${status}: ${detail}` : `API Error: ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
    this.path = path;
  }
}

export interface Session {
  session_id: string;
  agent_type: string;
  agent_name: string;
  cwd: string;
  timestamp_start: string;
  timestamp_end?: string;
  status: 'active' | 'completed' | 'error' | 'paused' | 'unknown';
  user_intent: string;
  first_user_message?: string;
  last_user_message?: string;
  user_message_count?: number;
  tool_calls: string[];
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  files_modified: string[];
  source_file: string;
  error_message?: string;
  route?: SessionRoute;
}

export interface SessionRoute {
  harness: string;
  id: string;
  href: string;
}

export interface LatestSessionSummary {
  provider: string;
  path: string;
  relative_path: string;
  filename: string;
  session_id: string;
  format: 'json' | 'jsonl';
  project_hint?: string;
  modified_at: string;
  modified_at_local: string;
  modified_human: string;
  age_seconds: number;
  age_human: string;
  activity_state: 'live' | 'active' | 'idle';
  record_count: number;
  parse_errors: number;
  user_message_count: number;
  started_at?: string;
  started_at_local?: string;
  duration_seconds?: number;
  duration_human?: string;
  first_user_message: string;
  last_user_message: string;
  intent_evolution: string[];
  intent_summary_source?: 'ai' | 'local_fallback';
  intent_summary_provider?: string;
  route?: SessionRoute;
}

export interface LatestSessionResponse {
  meta: {
    tool: string;
    tool_version: string;
    generated_at: string;
    timezone: string;
    scanned_providers: number;
    scanned_files: number;
  };
  query: {
    mode: 'latest';
    providers: string[];
    timezone: string;
    live_within_minutes: number;
    active_within_minutes: number;
    cognize_prompt_id?: string;
    cognize_provider_chain?: string;
    providers_config_path: string;
  };
  latest: LatestSessionSummary | null;
  errors: Array<{
    provider: string;
    stage: string;
    detail: string;
  }>;
}

export interface Metrics {
  total_sessions: number;
  by_agent: Record<string, number>;
  by_status: Record<string, number>;
  total_tokens: number;
  last_updated: string;
}

export interface SessionsResponse {
  total: number;
  limit: number;
  offset: number;
  sessions: Session[];
}

export interface SessionTimelineEvent {
  timestamp: string;
  event_type: string;
  description: string;
  icon?: string;
  details?: string | null;
}

export interface SessionPlanStep {
  step: string;
  status: string;
}

export interface SessionMessageAnchors {
  first: string;
  middle: string[];
  last: string;
}

export interface SessionGitCommit {
  hash: string;
  short_hash: string;
  title: string;
  author_name: string;
  committed_at: string;
  committed_at_local?: string;
}

export type SessionStateLabel = 'archived' | 'restorable' | 'live' | 'queryable';
export type SessionSafetyMode = 'read-only' | 'ask-only' | 'resume-allowed';

export interface SessionStateCapability {
  available: boolean;
  label: string;
  detail: string;
}

export interface SessionStateCapabilities {
  can_ask: boolean;
  can_resume: boolean;
  can_restore: boolean;
}

export interface SessionStateModel {
  labels: SessionStateLabel[];
  safety_mode: SessionSafetyMode;
  summary: string;
  rationale: string[];
  capabilities?: SessionStateCapabilities;
  ask_session?: SessionStateCapability;
  resume_session?: SessionStateCapability;
}

export interface SessionEvidenceSparsity {
  is_sparse: boolean;
  summary: string;
  present_layers: string[];
  missing_layers: string[];
}

export interface SessionTimeWindow {
  source: string;
  started_at?: string | null;
  started_at_local?: string | null;
  ended_at?: string | null;
  ended_at_local?: string | null;
  duration_seconds?: number | null;
  duration_human?: string | null;
  scope_summary: string;
}

export interface SessionArtifactSummary extends LatestSessionSummary {
  agent_name?: string;
  cwd: string;
  status?: string;
  user_intent?: string;
  user_messages: string[];
  message_anchors: SessionMessageAnchors;
  tool_calls: string[];
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  files_modified: string[];
  ended_at?: string | null;
  ended_at_local?: string | null;
  time_window?: SessionTimeWindow;
  git_branch?: string | null;
  git_repository_root?: string | null;
  git_commits: SessionGitCommit[];
  topic_threads?: string[];
  state_model?: SessionStateModel;
  evidence_sparsity?: SessionEvidenceSparsity;
  plan_steps: SessionPlanStep[];
  timeline: SessionTimelineEvent[];
  error_message?: string | null;
}

export interface SessionArtifactResponse {
  meta: {
    timezone: string;
    live_within_minutes: number;
    active_within_minutes: number;
  };
  session: SessionArtifactSummary;
}

export interface SessionAskEvidenceItem {
  kind: 'user_message' | 'assistant_message' | 'timeline' | 'artifact_field';
  label: string;
  excerpt: string;
  score: number;
}

export interface SessionAskResponse {
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
    evidence: SessionAskEvidenceItem[];
    limitations: string[];
  };
}

export interface AuthStatus {
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
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private buildUrl(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const method = options?.method || 'GET';
    const requestId = createRequestId('http');
    const controller = new AbortController();
    const startedAt = Date.now();
    let didTimeout = false;
    const timeout = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, runtimeConfig.apiRequestTimeoutMs);
    const headers = new Headers(options?.headers);
    headers.set('X-Request-ID', requestId);

    logClientEvent('info', 'http.request.started', {
      requestId,
      method,
      path,
      url: this.buildUrl(path),
    });

    let res: Response;

    try {
      res = await fetch(this.buildUrl(path), {
        ...options,
        headers,
        credentials: 'include',
        signal: controller.signal,
      });
    } catch (error) {
      clearTimeout(timeout);
      const durationMs = Date.now() - startedAt;
      const detail = didTimeout
        ? `Request timed out after ${runtimeConfig.apiRequestTimeoutMs}ms`
        : error instanceof Error
          ? error.message
          : 'Network request failed';

      logClientEvent('error', 'http.request.failed', {
        requestId,
        method,
        path,
        detail,
        durationMs,
      });

      throw new ApiError(0, detail, requestId, path);
    }

    clearTimeout(timeout);
    const responseRequestId = res.headers.get('X-Request-ID') || requestId;
    const durationMs = Date.now() - startedAt;

    if (!res.ok) {
      let detail: string | null = null;

      try {
        const payload = await res.json();
        if (typeof payload?.detail === 'string') {
          detail = payload.detail;
        }
      } catch {
        detail = await res.text().catch(() => null);
      }

      logClientEvent('warn', 'http.request.completed', {
        requestId: responseRequestId,
        method,
        path,
        status: res.status,
        ok: false,
        detail,
        durationMs,
      });

      throw new ApiError(res.status, detail, responseRequestId, path);
    }

    logClientEvent('info', 'http.request.completed', {
      requestId: responseRequestId,
      method,
      path,
      status: res.status,
      ok: true,
      durationMs,
    });

    return res.json();
  }

  // Sessions
  async getSessions(params?: {
    status?: string;
    agent?: string;
    changedDate?: string;
    limit?: number;
    offset?: number;
  }): Promise<SessionsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.agent) searchParams.set('agent', params.agent);
    if (params?.changedDate) searchParams.set('changed_date', params.changedDate);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));

    const query = searchParams.toString();
    return this.fetch<SessionsResponse>(`/api/sessions${query ? `?${query}` : ''}`);
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.fetch<Session>(`/api/sessions/${sessionId}`);
  }

  async getLatestSession(): Promise<LatestSessionResponse> {
    return this.fetch<LatestSessionResponse>('/api/latest-session');
  }

  async getSessionArtifact(harness: string, artifactId: string): Promise<SessionArtifactResponse> {
    return this.fetch<SessionArtifactResponse>(
      `/api/session-artifacts/${encodeURIComponent(harness)}/${encodeURIComponent(artifactId)}`,
    );
  }

  async askSessionArtifact(harness: string, artifactId: string, question: string): Promise<SessionAskResponse> {
    return this.fetch<SessionAskResponse>(
      `/api/session-artifacts/${encodeURIComponent(harness)}/${encodeURIComponent(artifactId)}/ask`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      },
    );
  }

  async getMetrics(): Promise<{ success: boolean; data: Metrics }> {
    return this.fetch(`/api/metrics`);
  }

  async rescanSessions(): Promise<{ success: boolean; sessions_found: number }> {
    return this.fetch('/api/sessions/scan', { method: 'POST' });
  }

  // Auth
  async login(password: string): Promise<{ success: boolean; message: string }> {
    return this.fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
  }

  async logout(): Promise<{ success: boolean }> {
    return this.fetch('/api/auth/logout', { method: 'POST' });
  }

  async loginWithTelegram(idToken: string): Promise<{ success: boolean; message: string }> {
    return this.fetch('/api/auth/telegram/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: idToken }),
    });
  }

  async getAuthStatus(): Promise<AuthStatus> {
    return this.fetch('/api/auth/status');
  }

  // WebSocket
  getWebSocketUrl(): string {
    if (this.baseUrl) {
      const url = new URL(this.baseUrl);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.pathname = `${url.pathname.replace(/\/$/, '')}/ws`;
      url.search = '';
      url.hash = '';
      return url.toString();
    }

    if (typeof window !== 'undefined') {
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProtocol}//${window.location.host}/ws`;
    }

    return `ws://127.0.0.1:${runtimeConfig.backendPort}/ws`;
  }
}

export const api = new ApiClient(API_BASE);
