import { useEffect, useRef, useState, useCallback } from 'react';
import { CONFIG } from './config';
import type { DigitalTwinState } from './types';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export function useDigitalTwinWebSocket(onStateReceived?: (state: DigitalTwinState) => void) {
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [latestState, setLatestState] = useState<DigitalTwinState | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isUnmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (isUnmountedRef.current) return;

    setStatus('connecting');
    setErrorMsg(null);

    try {
      const ws = new WebSocket(CONFIG.WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isUnmountedRef.current) return;
        setStatus('connected');
        setErrorMsg(null);
      };

      ws.onmessage = (event) => {
        if (isUnmountedRef.current) return;
        try {
          const state: DigitalTwinState = JSON.parse(event.data);
          setLatestState(state);
          if (onStateReceived) {
            onStateReceived(state);
          }
        } catch (err: any) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = () => {
        if (isUnmountedRef.current) return;
        setStatus('error');
        setErrorMsg('WebSocket connection encountered an error');
      };

      ws.onclose = () => {
        if (isUnmountedRef.current) return;
        setStatus('disconnected');
        // Auto-reconnect after 2 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 2000);
      };
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(err?.message || 'WebSocket connection failed');
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    }
  }, [onStateReceived]);

  useEffect(() => {
    isUnmountedRef.current = false;
    connect();

    return () => {
      isUnmountedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { status, latestState, errorMsg, reconnect: connect };
}
