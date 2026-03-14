import type { InteractiveBootPayload } from '@/lib/api';

export type InteractiveRoutePhase = 'ready' | 'blocked';
export type InteractiveRouteHealth = 'healthy' | 'reconnect' | 'busy' | 'degraded' | 'blocked';

export interface InteractiveRouteAlert {
  key: string;
  title: string;
  detail: string;
  tone: 'sky' | 'amber' | 'rose';
}

export interface InteractiveTimelineEntry {
  id: string;
  summary: string;
  detail: string;
}

export interface InteractiveComposerState {
  enabled: boolean;
  placeholder: string;
  helperText: string;
  submitLabel: string;
}

export interface InteractiveRouteState {
  phase: InteractiveRoutePhase;
  health: InteractiveRouteHealth;
  statusLabel: string;
  timelineEntries: InteractiveTimelineEntry[];
  composer: InteractiveComposerState;
  alerts: InteractiveRouteAlert[];
}

// Keep interactive route behavior derived from the boot payload until live transport lands.
function summarizeEntry(item: Record<string, unknown>, fallbackId: string): InteractiveTimelineEntry {
  let summary = 'Interactive event';
  if (typeof item.summary === 'string') {
    summary = item.summary;
  } else if (typeof item.title === 'string') {
    summary = item.title;
  } else if (typeof item.text === 'string') {
    summary = item.text;
  }

  let detail = 'No extra detail was captured for this event yet.';
  if (typeof item.detail === 'string') {
    detail = item.detail;
  } else if (typeof item.description === 'string') {
    detail = item.description;
  }

  return {
    id: typeof item.id === 'string' ? item.id : fallbackId,
    summary,
    detail,
  };
}

function summarizeReplayItem(item: Record<string, unknown>, fallbackId: string): InteractiveTimelineEntry {
  const eventType = typeof item.event_type === 'string' ? item.event_type : 'interactive_event';
  const payload = typeof item.payload === 'object' && item.payload !== null
    ? item.payload as Record<string, unknown>
    : {};
  const summaryByType: Record<string, string> = {
    user_message: 'Replay captured the previous user prompt',
    tool_call: 'Replay captured a tool call',
    task_complete: 'Replay reached the task completion boundary',
    history_complete: 'Replay is complete and the route may attach live',
  };

  let detail = 'Replay evidence is available for this session event.';
  if (typeof payload.text === 'string') {
    detail = payload.text;
  } else if (typeof payload.tool_name === 'string') {
    detail = `Tool call: ${payload.tool_name}`;
  } else if (typeof payload.status === 'string') {
    detail = `Status: ${payload.status}`;
  }

  return {
    id: typeof item.event_id === 'string' ? item.event_id : fallbackId,
    summary: summaryByType[eventType] || `Replay event: ${eventType}`,
    detail,
  };
}

function buildBlockedComposerState(payload: InteractiveBootPayload): InteractiveComposerState {
  if (!payload.session.resume_supported) {
    return {
      enabled: false,
      placeholder: 'Interactive continuation is blocked for this session.',
      helperText: payload.interactive_session.detail,
      submitLabel: 'Continue session',
    };
  }

  return {
    enabled: true,
    placeholder: 'Send the next prompt. The browser will resume this session and update the shared artifact.',
    helperText: `${payload.interactive_session.detail} Browser submit now runs a real continuation through the recorded Codex session.`,
    submitLabel: 'Resume and send prompt',
  };
}

function buildTimelineEntries(
  payload: InteractiveBootPayload,
  liveEntries: InteractiveTimelineEntry[] = [],
): InteractiveTimelineEntry[] {
  const tailEntries = payload.tail.items.map((item, index) =>
    summarizeEntry(item, `interactive-tail-${index + 1}`),
  );
  const replayEntries = payload.replay.items.map((item, index) =>
    summarizeReplayItem(item, `interactive-replay-${index + 1}`),
  );
  const mappedEntries = [...tailEntries, ...replayEntries, ...liveEntries];

  if (mappedEntries.length > 0) {
    return mappedEntries;
  }

  return [
    {
      id: 'interactive-entry-placeholder',
      summary: 'Waiting for replay and live timeline data',
      detail: 'This route now has a frontend state model, but the replay/live transport cards have not been delivered yet.',
    },
  ];
}

function buildRouteAlerts(payload: InteractiveBootPayload): InteractiveRouteAlert[] {
  const sessionStatus = payload.session.status.trim().toLowerCase();
  const isReconnect = payload.runtime_identity?.source === 'recovered' || sessionStatus === 'reconnect';
  const isBusy =
    !isReconnect &&
    ['active', 'running', 'waiting'].includes(sessionStatus) &&
    !payload.replay.history_complete;
  const isDegraded = payload.tail.items.length === 0 || !payload.replay.history_complete;
  const alerts: InteractiveRouteAlert[] = [];

  if (isReconnect) {
    alerts.push({
      key: 'reconnect',
      title: 'Reconnecting to runtime',
      detail: 'The route is preserving history while the browser transport restores the live thread.',
      tone: 'sky',
    });
  }

  if (isBusy) {
    alerts.push({
      key: 'busy',
      title: 'Session is busy',
      detail: 'Interactive input stays paused until replay handoff is complete and the runtime stops streaming.',
      tone: 'amber',
    });
  }

  if (isDegraded) {
    alerts.push({
      key: 'degraded',
      title: 'Degraded snapshot',
      detail: 'This screen is intentionally honest about missing replay or tail data instead of pretending the route is fully attached.',
      tone: 'rose',
    });
  }

  return alerts;
}

export function buildInteractiveRouteState(
  payload: InteractiveBootPayload,
  liveEntries: InteractiveTimelineEntry[] = [],
): InteractiveRouteState {
  const phase: InteractiveRoutePhase = payload.interactive_session.available ? 'ready' : 'blocked';
  const alerts = buildRouteAlerts(payload);
  const reconnectAlert = alerts.find((alert) => alert.key === 'reconnect');
  const busyAlert = alerts.find((alert) => alert.key === 'busy');
  const degradedAlert = alerts.find((alert) => alert.key === 'degraded');

  if (phase === 'blocked') {
    return {
      phase,
      health: 'blocked',
      statusLabel: payload.interactive_session.label,
      timelineEntries: buildTimelineEntries(payload, liveEntries),
      composer: buildBlockedComposerState(payload),
      alerts: [],
    };
  }

  if (reconnectAlert) {
    return {
      phase,
      health: 'reconnect',
      statusLabel: reconnectAlert.title,
      timelineEntries: buildTimelineEntries(payload, liveEntries),
      composer: {
        enabled: false,
        placeholder: 'Waiting for the live thread to reconnect before sending input.',
        helperText: reconnectAlert.detail,
        submitLabel: 'Send prompt',
      },
      alerts,
    };
  }

  if (busyAlert) {
    return {
      phase,
      health: degradedAlert ? 'degraded' : 'busy',
      statusLabel: busyAlert.title,
      timelineEntries: buildTimelineEntries(payload, liveEntries),
      composer: {
        enabled: false,
        placeholder: 'The session is still busy finishing replay or live work.',
        helperText: busyAlert.detail,
        submitLabel: 'Send prompt',
      },
      alerts,
    };
  }

  if (degradedAlert) {
    return {
      phase,
      health: 'degraded',
      statusLabel: degradedAlert.title,
      timelineEntries: buildTimelineEntries(payload, liveEntries),
      composer: {
        enabled: true,
        placeholder: 'Send the next prompt while the route stays honest about partial evidence.',
        helperText: degradedAlert.detail,
        submitLabel: 'Send prompt',
      },
      alerts,
    };
  }

  return {
    phase,
    health: 'healthy',
    statusLabel: 'Live timeline ready',
    timelineEntries: buildTimelineEntries(payload, liveEntries),
    composer: {
      enabled: true,
      placeholder: 'Send the next prompt to continue this session.',
      helperText: 'Prompt submit writes into the same Codex session artifact through the backend continuation flow.',
      submitLabel: 'Send prompt',
    },
    alerts,
  };
}
