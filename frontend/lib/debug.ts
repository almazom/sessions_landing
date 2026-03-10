type DebugLevel = 'info' | 'warn' | 'error';

export type DebugEntry = {
  ts: string;
  level: DebugLevel;
  event: string;
  [key: string]: unknown;
};

declare global {
  interface Window {
    __AGENT_NEXUS_DEBUG__?: {
      clear: () => void;
      entries: DebugEntry[];
    };
  }
}

const MAX_ENTRIES = 400;
const debugEntries: DebugEntry[] = [];

function getConsoleMethod(level: DebugLevel): 'log' | 'warn' | 'error' {
  if (level === 'warn') {
    return 'warn';
  }

  if (level === 'error') {
    return 'error';
  }

  return 'log';
}

function syncWindowBuffer() {
  if (typeof window === 'undefined') {
    return;
  }

  window.__AGENT_NEXUS_DEBUG__ = {
    clear: () => {
      debugEntries.splice(0, debugEntries.length);
    },
    entries: debugEntries,
  };
}

export function createRequestId(prefix = 'req'): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function logClientEvent(level: DebugLevel, event: string, fields: Record<string, unknown> = {}) {
  const entry: DebugEntry = {
    ts: new Date().toISOString(),
    level,
    event,
    ...fields,
  };

  debugEntries.push(entry);
  if (debugEntries.length > MAX_ENTRIES) {
    debugEntries.splice(0, debugEntries.length - MAX_ENTRIES);
  }

  syncWindowBuffer();
  console[getConsoleMethod(level)]('[AgentNexus]', entry);
}

export function getDebugEntries(): DebugEntry[] {
  return [...debugEntries];
}
