'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';

import { useWebSocket } from '@/hooks/useWebSocket';
import { ApiError, api, type InteractiveBootPayload } from '@/lib/api';
import { buildInteractiveRouteState, type InteractiveTimelineEntry } from '@/lib/interactive-state';

interface Props {
  harness: string;
  artifactId: string;
}

type ConnectionPhase = 'attaching' | 'attached' | 'reconnecting';
const RESUME_BOOT_POLL_ATTEMPTS = 4;
const RESUME_BOOT_POLL_DELAY_MS = 800;

type InteractiveStreamEvent = {
  event_id?: string;
  kind?: string;
  status?: string;
  summary?: string;
  payload?: Record<string, unknown>;
};

type InteractiveSocketMessage = {
  type: string;
  data?: {
    harness?: string;
    route_id?: string;
    event?: InteractiveStreamEvent;
  };
};

type TurnUsagePayload = {
  output_tokens?: number;
};

function renderErrorDetail(error: unknown): string {
  if (error instanceof ApiError && error.detail) {
    return error.detail;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return 'Interactive route could not load its initial boot payload.';
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function alertToneClasses(tone: 'sky' | 'amber' | 'rose'): string {
  if (tone === 'sky') {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-100';
  }
  if (tone === 'amber') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
  }
  return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
}

function buildAttachStatusLabel(
  payload: InteractiveBootPayload,
  connectionPhase: ConnectionPhase,
): string {
  if (!payload.interactive_session.available) {
    return 'Continuation blocked';
  }
  if (connectionPhase === 'reconnecting') {
    return 'Reconnecting to runtime';
  }
  if (connectionPhase === 'attaching') {
    return 'Attaching live runtime';
  }
  return 'Live attach ready';
}

function buildAttachStatusDetail(
  payload: InteractiveBootPayload,
  routeComposerEnabled: boolean,
  connectionPhase: ConnectionPhase,
): string {
  if (!payload.interactive_session.available) {
    if (routeComposerEnabled) {
      return 'Live runtime is not attached, but browser submit can resume this session through the backend and refresh the shared artifact.';
    }
    return payload.interactive_session.detail;
  }
  if (connectionPhase === 'reconnecting') {
    return 'The browser is restoring the route state from the previous prompt roundtrip.';
  }
  if (connectionPhase === 'attaching') {
    return 'Replay is complete and the browser is preparing the live continuation boundary.';
  }
  return `Connected to ${payload.runtime_identity?.thread_id || payload.route.route_id} and ready for the next prompt.`;
}

function buildLiveTimelineEntry(event: InteractiveStreamEvent): InteractiveTimelineEntry | null {
  const kind = typeof event.kind === 'string' ? event.kind : '';
  const status = typeof event.status === 'string' ? event.status : '';
  const summary = typeof event.summary === 'string' ? event.summary : 'Interactive event';
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  const eventId = typeof event.event_id === 'string' && event.event_id ? event.event_id : '';

  if (!kind) {
    return null;
  }

  if (kind === 'user_prompt') {
    return {
      id: eventId || `user-prompt-${Date.now()}`,
      summary,
      detail: typeof payload.text === 'string' ? payload.text : 'Browser submitted a new prompt.',
    };
  }

  if (kind === 'thread') {
    return {
      id: eventId || 'thread-started',
      summary,
      detail: typeof payload.thread_id === 'string'
        ? `Thread ${payload.thread_id} accepted the continuation.`
        : 'The interactive runtime accepted the continuation request.',
    };
  }

  if (kind === 'turn') {
    if (status === 'started') {
      return {
        id: eventId || `turn-started-${Date.now()}`,
        summary,
        detail: 'Codex started working on the next turn.',
      };
    }
    const usage = payload.usage && typeof payload.usage === 'object'
      ? payload.usage as TurnUsagePayload
      : null;
    const usageDetail = usage && typeof usage.output_tokens === 'number'
      ? `Turn completed. Output tokens: ${usage.output_tokens}.`
      : 'Codex finished the current turn.';
    return {
      id: eventId || `turn-completed-${Date.now()}`,
      summary,
      detail: usageDetail,
    };
  }

  if (kind === 'agent_message') {
    return {
      id: eventId || `agent-message-${Date.now()}`,
      summary: 'Assistant message',
      detail: typeof payload.text === 'string' && payload.text ? payload.text : summary,
    };
  }

  if (kind === 'command') {
    const commandText = typeof payload.command === 'string' ? payload.command : summary;
    const outputText = typeof payload.aggregated_output === 'string' ? payload.aggregated_output : '';
    return {
      id: eventId || `command-${Date.now()}`,
      summary: status === 'started' ? 'Command started' : 'Command update',
      detail: outputText ? `${commandText}\n${outputText}` : commandText,
    };
  }

  if (kind === 'tool_call') {
    const toolName = typeof payload.tool === 'string' ? payload.tool : summary;
    return {
      id: eventId || `tool-${Date.now()}`,
      summary: `Tool call: ${toolName}`,
      detail: typeof payload.server === 'string' && payload.server
        ? `Server: ${payload.server}`
        : 'Tool call is running in the interactive continuation.',
    };
  }

  if (kind === 'todo_list') {
    return {
      id: eventId || `todo-${Date.now()}`,
      summary: 'Todo list updated',
      detail: typeof payload.total_count === 'number' && typeof payload.completed_count === 'number'
        ? `${payload.completed_count}/${payload.total_count} tasks completed.`
        : 'Todo list changed during the interactive continuation.',
    };
  }

  if (kind === 'error') {
    return {
      id: eventId || `error-${Date.now()}`,
      summary,
      detail: typeof payload.message === 'string' ? payload.message : 'Interactive continuation reported an error.',
    };
  }

  return {
    id: eventId || `${kind}-${Date.now()}`,
    summary,
    detail: `Interactive event kind: ${kind}.`,
  };
}

export default function InteractiveSessionShell({ harness, artifactId }: Props) {
  const [payload, setPayload] = useState<InteractiveBootPayload | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [composerValue, setComposerValue] = useState('');
  const [connectionPhase, setConnectionPhase] = useState<ConnectionPhase>('attaching');
  const [resumeSubmitting, setResumeSubmitting] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [resumeFeedback, setResumeFeedback] = useState<string | null>(null);
  const [promptSubmitting, setPromptSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitFeedback, setSubmitFeedback] = useState<string | null>(null);
  const [liveTimelineEntries, setLiveTimelineEntries] = useState<InteractiveTimelineEntry[]>([]);
  const timelineViewportRef = useRef<HTMLDivElement | null>(null);
  const fetchBootPayload = useCallback(async () => {
    return api.getSessionArtifactInteractiveBoot(harness, artifactId);
  }, [artifactId, harness]);
  const handleSocketMessage = useCallback((message: InteractiveSocketMessage) => {
    if (message.type !== 'interactive_event' || !payload) {
      return;
    }

    const data = message.data;
    if (!data || data.harness !== payload.route.harness || data.route_id !== payload.route.route_id) {
      return;
    }

    const nextEntry = buildLiveTimelineEntry(data.event || {});
    if (!nextEntry) {
      return;
    }

    setLiveTimelineEntries((currentEntries) => {
      if (currentEntries.some((entry) => entry.id === nextEntry.id)) {
        return currentEntries;
      }
      return [...currentEntries, nextEntry];
    });

    if (data.event?.kind === 'turn' && data.event.status === 'started') {
      setConnectionPhase('attaching');
    } else if (data.event?.kind === 'turn' && data.event.status === 'completed') {
      setConnectionPhase('attached');
    }
  }, [payload]);
  const { connected: websocketConnected, send: sendWebSocketMessage } = useWebSocket(handleSocketMessage);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const nextPayload = await fetchBootPayload();
        if (!cancelled) {
          setPayload(nextPayload);
          setErrorDetail(null);
        }
      } catch (error) {
        if (!cancelled) {
          setPayload(null);
          setErrorDetail(renderErrorDetail(error));
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [fetchBootPayload]);

  useEffect(() => {
    if (!payload) {
      return undefined;
    }

    setConnectionPhase('attaching');
    const timer = window.setTimeout(() => {
      setConnectionPhase('attached');
    }, 300);

    return () => {
      window.clearTimeout(timer);
    };
  }, [payload]);

  useEffect(() => {
    setLiveTimelineEntries([]);
  }, [artifactId, harness]);

  useEffect(() => {
    const viewport = timelineViewportRef.current;
    if (!viewport || liveTimelineEntries.length === 0) {
      return;
    }

    viewport.scrollTop = viewport.scrollHeight;
  }, [liveTimelineEntries]);

  useEffect(() => {
    if (!payload || !websocketConnected) {
      return;
    }

    sendWebSocketMessage({
      type: 'subscribe_interactive',
      data: {
        harness: payload.route.harness,
        route_id: payload.route.route_id,
      },
    });
  }, [payload, sendWebSocketMessage, websocketConnected]);

  const handlePromptSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!payload || promptSubmitting) {
      return;
    }

    const normalizedPrompt = composerValue.trim();
    if (!normalizedPrompt) {
      return;
    }

    setPromptSubmitting(true);
    setSubmitError(null);
    setSubmitFeedback(null);
    setConnectionPhase('attaching');

    try {
      const result = await api.submitSessionArtifactInteractivePrompt(harness, artifactId, normalizedPrompt);
      setComposerValue('');
      setPayload(result.boot_payload);
      setErrorDetail(null);
      setSubmitFeedback(
        result.assistant_message
          ? `Prompt completed. Latest assistant reply: ${result.assistant_message}`
          : 'Prompt completed and the shared session artifact changed.',
      );
    } catch (submitActionError) {
      setSubmitError(renderErrorDetail(submitActionError));
      setConnectionPhase('attached');
    } finally {
      setPromptSubmitting(false);
    }
  };

  const handleResumeSession = async () => {
    if (!payload?.session.resume_supported || resumeSubmitting) {
      return;
    }

    setResumeSubmitting(true);
    setResumeError(null);
    setResumeFeedback(null);

    try {
      const result = await api.resumeSessionArtifact(harness, artifactId);
      let latestPayload: InteractiveBootPayload | null = null;

      for (let attempt = 0; attempt < RESUME_BOOT_POLL_ATTEMPTS; attempt += 1) {
        latestPayload = await fetchBootPayload();
        setPayload(latestPayload);
        setErrorDetail(null);
        if (latestPayload.interactive_session.available) {
          break;
        }
        if (attempt < RESUME_BOOT_POLL_ATTEMPTS - 1) {
          await delay(RESUME_BOOT_POLL_DELAY_MS);
        }
      }

      if (latestPayload?.interactive_session.available) {
        setResumeFeedback('Resume started and the interactive route attached to the live runtime.');
      } else {
        const logSuffix = result.log_path ? ` Check ${result.log_path} for the backend resume log.` : '';
        setResumeFeedback(`Resume started, but the route is still waiting for runtime identity mapping.${logSuffix}`);
      }
    } catch (resumeActionError) {
      setResumeError(renderErrorDetail(resumeActionError));
    } finally {
      setResumeSubmitting(false);
    }
  };

  if (errorDetail) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.1),_transparent_32%),linear-gradient(180deg,_#020617_0%,_#0f172a_100%)] px-4 py-4 text-slate-100 sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-6xl flex-col rounded-[28px] border border-slate-800 bg-slate-950/92 shadow-2xl shadow-slate-950/60">
          <header className="flex items-center justify-between gap-4 border-b border-slate-800 px-4 py-4 sm:px-6">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.28em] text-rose-300">Interactive Route</p>
              <h1 className="mt-2 text-xl font-semibold text-white sm:text-2xl">Interactive session shell</h1>
            </div>
            <Link
              href={`/sessions/${encodeURIComponent(harness)}/${encodeURIComponent(artifactId)}`}
              className="inline-flex shrink-0 rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:text-white"
            >
              Back to session dossier
            </Link>
          </header>

          <section className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
              <div className="mx-auto max-w-4xl space-y-4">
                <div className="rounded-3xl border border-rose-500/30 bg-rose-500/10 p-5">
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-rose-200">Initialization failed</p>
                  <p className="mt-3 text-sm leading-7 text-slate-200">
                    Interactive bootstrap could not start for this session, so the route is staying explicit about the
                    failure instead of showing a fake live shell.
                  </p>
                  <p className="mt-4 text-sm leading-7 text-slate-300">{errorDetail}</p>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.1),_transparent_32%),linear-gradient(180deg,_#020617_0%,_#0f172a_100%)] px-4 py-4 text-slate-100 sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-6xl flex-col rounded-[28px] border border-slate-800 bg-slate-950/92 shadow-2xl shadow-slate-950/60">
          <header className="border-b border-slate-800 px-4 py-4 sm:px-6">
            <p className="text-[11px] uppercase tracking-[0.28em] text-sky-300">Interactive Route</p>
            <h1 className="mt-2 text-xl font-semibold text-white sm:text-2xl">Interactive session shell</h1>
          </header>
          <section className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
              <div className="mx-auto max-w-4xl rounded-3xl border border-slate-800 bg-slate-900/70 p-5 sm:p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-sky-300">Preparing interactive session</p>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  Loading the backend boot payload, route identity, and the first honest interactive state for this
                  session.
                </p>
              </div>
            </div>
          </section>
        </div>
      </main>
    );
  }

  const routeState = buildInteractiveRouteState(payload, liveTimelineEntries);
  const boundaryEventCandidate = payload.replay.items[payload.replay.items.length - 1];
  const boundaryEventId = (
    boundaryEventCandidate
    && typeof boundaryEventCandidate.event_id === 'string'
    && boundaryEventCandidate.event_id
  )
    ? boundaryEventCandidate.event_id
    : 'unavailable';
  const backHref = payload.route.session_href;
  const runtimeIdentity = payload.runtime_identity;
  const attachStatusLabel = buildAttachStatusLabel(payload, connectionPhase);
  const attachStatusDetail = buildAttachStatusDetail(payload, routeState.composer.enabled, connectionPhase);
  const transportLabel = runtimeIdentity?.transport || payload.interactive_session.transport || 'Unavailable';
  const transportDetail = runtimeIdentity?.thread_id || 'No live runtime mapping is attached to this route yet.';
  const streamStatusLabel = websocketConnected ? 'Stream connected' : 'Stream connecting';

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.12),_transparent_38%),linear-gradient(180deg,_#020617_0%,_#0f172a_100%)] px-4 py-4 text-slate-100 sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-6xl flex-col overflow-hidden rounded-[28px] border border-slate-800 bg-slate-950/92 shadow-2xl shadow-slate-950/60">
        <header className="border-b border-slate-800 px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.28em] text-sky-300">Interactive Route</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold text-white sm:text-2xl">Interactive session shell</h1>
                <span
                  data-testid="interactive-route-status"
                  className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-100"
                >
                  {payload.interactive_session.label}
                </span>
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{payload.interactive_session.detail}</p>
            </div>
            <Link
              href={backHref}
              className="inline-flex shrink-0 rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:text-white"
            >
              Back to session dossier
            </Link>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1">
              Session {payload.session.session_id}
            </span>
            <span className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1">
              {transportLabel}
            </span>
            <span className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1">
              {attachStatusLabel}
            </span>
            <span
              data-testid="interactive-stream-status"
              className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1"
            >
              {streamStatusLabel}
            </span>
          </div>

          {routeState.alerts.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {routeState.alerts.map((alert) => (
                <div
                  key={alert.key}
                  className={`rounded-full border px-3 py-1.5 text-xs ${alertToneClasses(alert.tone)}`}
                >
                  <span className="font-medium">{alert.title}</span>
                </div>
              ))}
            </div>
          ) : null}
        </header>

        <section className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
            <div className="mx-auto flex min-h-full max-w-4xl flex-col">
              <div
                data-testid="interactive-live-attach"
                className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.24em] text-sky-300">{attachStatusLabel}</div>
                    <div className="mt-1 leading-6 text-slate-300">{attachStatusDetail}</div>
                  </div>
                  <div className="text-xs text-slate-500">Boundary: {boundaryEventId}</div>
                </div>
              </div>

              <details className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/40" data-testid="interactive-route-details">
                <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">
                  Route details
                </summary>
                <div className="grid gap-3 border-t border-slate-800 px-4 py-4 text-sm text-slate-300 sm:grid-cols-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Transport</div>
                    <div className="mt-2 text-slate-100">{transportLabel}</div>
                    <div className="mt-1 leading-6 text-slate-400">{transportDetail}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Session</div>
                    <div className="mt-2 text-slate-100">{payload.session.session_id}</div>
                    <div className="mt-1 leading-6 text-slate-400">{payload.session.cwd || 'No cwd recorded'}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Replay</div>
                    <div className="mt-2 text-slate-100">{payload.replay.history_complete ? 'History complete' : 'Replay in progress'}</div>
                    <div className="mt-1 leading-6 text-slate-400">This route is driven by the shared session artifact and current runtime mapping when available.</div>
                  </div>
                </div>
              </details>

              <div className="mt-4 flex-1 rounded-[26px] border border-slate-800 bg-slate-900/70 shadow-xl shadow-slate-950/30">
                <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-4 sm:px-5">
                  <div>
                    <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-sky-300">Live timeline</h2>
                    <p className="mt-1 text-sm text-slate-400">Terminal-style session movement stays as the main surface.</p>
                  </div>
                  <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">
                    {routeState.statusLabel}
                  </span>
                </div>

                <div
                  ref={timelineViewportRef}
                  className="max-h-[calc(100vh-27rem)] min-h-[20rem] overflow-y-auto px-4 py-4 sm:max-h-[calc(100vh-25rem)] sm:px-5"
                >
                  {payload.tail.items.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 p-5 text-sm text-slate-400">
                      No tail snapshot yet. Replay handoff will fill this area in the next card.
                    </div>
                  ) : null}
                  <ol className="space-y-3">
                    {routeState.timelineEntries.map((entry, index) => (
                      <li
                        key={entry.id}
                        data-testid={`interactive-timeline-entry-${index}`}
                        className="rounded-2xl border border-slate-800 bg-slate-950/65 p-4"
                      >
                        <p className="text-sm font-medium text-white">{entry.summary}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-400">{entry.detail}</p>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-slate-800 bg-slate-950/95 px-4 py-4 backdrop-blur sm:px-6">
            <div className="mx-auto max-w-4xl">
              {payload.session.resume_supported && !payload.interactive_session.available && !routeState.composer.enabled ? (
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <div className="max-w-2xl">
                    <div className="text-sm font-medium text-white">Resume this session</div>
                    <p className="mt-1 text-sm leading-6 text-slate-400">
                      Resume stays explicit. The browser refreshes the boot payload and only switches to live-ready if
                      the backend exposes a real runtime mapping.
                    </p>
                  </div>
                  <button
                    data-testid="interactive-resume-cta"
                    type="button"
                    onClick={handleResumeSession}
                    disabled={resumeSubmitting}
                    className="inline-flex shrink-0 rounded-full bg-sky-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-sky-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                  >
                  {resumeSubmitting ? 'Starting resume…' : 'Resume this session'}
                  </button>
                </div>
              ) : null}

              {submitFeedback ? (
                <div
                  data-testid="interactive-submit-feedback"
                  className="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm leading-6 text-emerald-100"
                >
                  {submitFeedback}
                </div>
              ) : null}
              {submitError ? (
                <div
                  data-testid="interactive-submit-error"
                  className="mb-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm leading-6 text-rose-100"
                >
                  {submitError}
                </div>
              ) : null}
              {resumeFeedback ? (
                <div
                  data-testid="interactive-resume-feedback"
                  className="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm leading-6 text-emerald-100"
                >
                  {resumeFeedback}
                </div>
              ) : null}
              {resumeError ? (
                <div
                  data-testid="interactive-resume-error"
                  className="mb-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm leading-6 text-rose-100"
                >
                  {resumeError}
                </div>
              ) : null}

              <div className="rounded-[26px] border border-slate-800 bg-slate-900/80 p-4 sm:p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-sky-300">Continue session</h2>
                    <p className="mt-1 text-sm text-slate-400">{routeState.composer.helperText}</p>
                  </div>
                  <div className="text-xs text-slate-500">Reload after a prompt to verify reconnect state restoration.</div>
                </div>

                <form
                  data-testid="interactive-composer-form"
                  className="space-y-4"
                  onSubmit={handlePromptSubmit}
                >
                  <textarea
                    data-testid="interactive-composer-input"
                    value={composerValue}
                    onChange={(event) => setComposerValue(event.target.value)}
                    placeholder={routeState.composer.placeholder}
                    disabled={!routeState.composer.enabled || promptSubmitting}
                    className="min-h-24 w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-400 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-500 sm:min-h-28"
                  />
                  <div className="flex items-center justify-end gap-4">
                    <button
                      data-testid="interactive-composer-submit"
                      type="submit"
                      disabled={!routeState.composer.enabled || promptSubmitting || composerValue.trim().length === 0}
                      className="inline-flex rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-sky-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                    >
                      {promptSubmitting ? 'Sending…' : routeState.composer.submitLabel}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
