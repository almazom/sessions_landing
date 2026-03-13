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
  const summary =
    typeof item.summary === 'string'
      ? item.summary
      : typeof item.title === 'string'
        ? item.title
        : typeof item.text === 'string'
          ? item.text
          : 'Interactive event';
  const detail =
    typeof item.detail === 'string'
      ? item.detail
      : typeof item.description === 'string'
        ? item.description
        : 'No extra detail was captured for this event yet.';

  return {
    id: typeof item.id === 'string' ? item.id : fallbackId,
    summary,
    detail,
  };
}

function buildTimelineEntries(payload: InteractiveBootPayload): InteractiveTimelineEntry[] {
  const timelineSource = [...payload.tail.items, ...payload.replay.items];
  const mappedEntries = timelineSource.map((item, index) =>
    summarizeEntry(item, `interactive-entry-${index + 1}`),
  );

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
  const isReconnect = payload.runtime_identity.source === 'recovered' || sessionStatus === 'reconnect';
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

export function buildInteractiveRouteState(payload: InteractiveBootPayload): InteractiveRouteState {
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
      timelineEntries: buildTimelineEntries(payload),
      composer: {
        enabled: false,
        placeholder: 'Interactive continuation is blocked for this session.',
        helperText: payload.interactive_session.detail,
        submitLabel: 'Continue session',
      },
      alerts: [],
    };
  }

  if (reconnectAlert) {
    return {
      phase,
      health: 'reconnect',
      statusLabel: reconnectAlert.title,
      timelineEntries: buildTimelineEntries(payload),
      composer: {
        enabled: false,
        placeholder: 'Waiting for the live thread to reconnect before sending input.',
        helperText: reconnectAlert.detail,
        submitLabel: 'Queue prompt',
      },
      alerts,
    };
  }

  if (busyAlert) {
    return {
      phase,
      health: degradedAlert ? 'degraded' : 'busy',
      statusLabel: busyAlert.title,
      timelineEntries: buildTimelineEntries(payload),
      composer: {
        enabled: false,
        placeholder: 'The session is still busy finishing replay or live work.',
        helperText: busyAlert.detail,
        submitLabel: 'Queue prompt',
      },
      alerts,
    };
  }

  if (degradedAlert) {
    return {
      phase,
      health: 'degraded',
      statusLabel: degradedAlert.title,
      timelineEntries: buildTimelineEntries(payload),
      composer: {
        enabled: true,
        placeholder: 'Send the next prompt while the route stays honest about partial evidence.',
        helperText: degradedAlert.detail,
        submitLabel: 'Queue prompt',
      },
      alerts,
    };
  }

  return {
    phase,
    health: 'healthy',
    statusLabel: 'Live timeline ready',
    timelineEntries: buildTimelineEntries(payload),
    composer: {
      enabled: true,
      placeholder: 'Send the next prompt to continue this session.',
      helperText: 'Composer state is ready. Prompt submit wiring lands in the next transport/integration cards.',
      submitLabel: 'Queue prompt',
    },
    alerts,
  };
}
