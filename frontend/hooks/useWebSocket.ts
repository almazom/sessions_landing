'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { createRequestId, logClientEvent } from '@/lib/debug';
import { runtimeConfig } from '@/lib/runtime-config';

interface WSMessage {
  type: string;
  data?: any;
  timestamp: string;
}

export function useWebSocket(onMessage?: (msg: WSMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connectionIdRef = useRef(createRequestId('ws'));

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = api.getWebSocketUrl();
    const connectionId = connectionIdRef.current;
    logClientEvent('info', 'ws.connecting', { connectionId, wsUrl });
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      logClientEvent('info', 'ws.connected', { connectionId, wsUrl });
      setConnected(true);
      setError(null);
    };

    ws.onclose = () => {
      logClientEvent('warn', 'ws.disconnected', { connectionId, wsUrl });
      setConnected(false);
      
      setTimeout(connect, runtimeConfig.websocketReconnectMs);
    };

    ws.onerror = (err) => {
      logClientEvent('error', 'ws.error', {
        connectionId,
        wsUrl,
        error: err instanceof Event ? 'websocket_error' : String(err),
      });
      setError('Ошибка подключения');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        logClientEvent('info', 'ws.message.received', {
          connectionId,
          type: msg?.type ?? 'unknown',
        });
        onMessage?.(msg);
      } catch (e) {
        logClientEvent('error', 'ws.message.parse_failed', {
          connectionId,
          error: e instanceof Error ? e.message : String(e),
        });
      }
    };

    wsRef.current = ws;
  }, [onMessage]);

  const send = useCallback((msg: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logClientEvent('info', 'ws.message.sent', {
        connectionId: connectionIdRef.current,
        type: msg?.type ?? 'unknown',
      });
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const ping = useCallback(() => {
    send({ type: 'ping' });
  }, [send]);

  useEffect(() => {
    connect();
    
    const interval = setInterval(ping, runtimeConfig.websocketPingIntervalMs);
    
    return () => {
      clearInterval(interval);
      wsRef.current?.close();
    };
  }, [connect, ping]);

  return { connected, error, send };
}
